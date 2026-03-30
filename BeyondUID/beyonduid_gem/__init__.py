from dataclasses import dataclass, field
from itertools import combinations

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.sv import SV

from ..beyonduid_gamedata import TableCfg, WeaponGemInfoTable
from ..beyonduid_gamedata.i18n_text import get_i18n_text
from ..beyonduid_gamedata.weapon_gem_info import WeaponGemEnergyPointData, WeaponGemRecommendationData
from ..utils.error_reply import prefix as P
from .draw_img import draw_gem_recommend_img

sv_weapon_gem = SV("byd武器基质")


@dataclass
class _MultiPointPlan:
    point: WeaponGemEnergyPointData
    locked_primary_ids: list[str] = field(default_factory=list)
    locked_lock_term_id: str | None = None
    covered_weapon_names: list[str] = field(default_factory=list)
    lock_covered_weapon_names: list[str] = field(default_factory=list)
    rank_positions: list[int] = field(default_factory=list)
    extra_weapon_names: list[str] = field(default_factory=list)
    remaining_term_hit_weapon_names: list[str] = field(default_factory=list)
    remaining_term_hit_count: int = 0


def _get_term_name(term_id: str) -> str:
    gem_data = TableCfg.GemTable().get(term_id, {})
    return get_i18n_text(gem_data.get("tagName")) or term_id


def _format_point_name(point: WeaponGemEnergyPointData) -> str:
    return f"{point.domain_name}·{point.point_name.removeprefix('重度能量淤积点·')}"


def _desired_lock_term_ids(
    data: WeaponGemRecommendationData,
    point: WeaponGemEnergyPointData,
) -> list[str]:
    result: list[str] = []
    for term_id in data.recommended_secondary_term_ids:
        if term_id in point.guaranteed_secondary_term_ids:
            result.append(term_id)
    for term_id in data.recommended_skill_term_ids:
        if term_id in point.guaranteed_skill_term_ids:
            result.append(term_id)
    return result


def _pick_locked_primary_ids(
    data_list: list[WeaponGemRecommendationData],
    point: WeaponGemEnergyPointData,
) -> list[str]:
    point_primary_set = set(point.primary_term_ids)
    desired_count: dict[str, int] = {}
    for data in data_list:
        for term_id in set(data.recommended_primary_term_ids):
            if term_id in point_primary_set:
                desired_count[term_id] = desired_count.get(term_id, 0) + 1

    selected = sorted(
        desired_count,
        key=lambda term_id: (
            desired_count[term_id],
            1 if term_id == "gat_passive_attr_main" else 0,
            term_id,
        ),
        reverse=True,
    )[:3]

    filler_candidates = [
        "gat_passive_attr_main",
        *[term_id for term_id in point.primary_term_ids if term_id != "gat_passive_attr_main"],
    ]
    for term_id in filler_candidates:
        if len(selected) >= 3:
            break
        if term_id in point_primary_set and term_id not in selected:
            selected.append(term_id)
    return selected[:3]


def _pick_locked_lock_term_id(
    data_list: list[WeaponGemRecommendationData],
    point: WeaponGemEnergyPointData,
) -> str | None:
    desired_count: dict[str, int] = {}
    for data in data_list:
        for term_id in set(_desired_lock_term_ids(data, point)):
            desired_count[term_id] = desired_count.get(term_id, 0) + 1

    if not desired_count:
        return None

    return max(
        desired_count,
        key=lambda term_id: (
            desired_count[term_id],
            1 if term_id.startswith("gat_") else 0,
            term_id,
        ),
    )


def _is_weapon_covered_by_plan(data: WeaponGemRecommendationData, plan: _MultiPointPlan) -> bool:
    has_primary = bool(set(plan.locked_primary_ids).intersection(data.recommended_primary_term_ids))
    if not has_primary:
        return False
    if plan.locked_lock_term_id is None:
        return True
    return plan.locked_lock_term_id in _desired_lock_term_ids(data, plan.point)


def _has_remaining_desired_terms_in_point(
    data: WeaponGemRecommendationData,
    plan: _MultiPointPlan,
) -> bool:
    desired_term_ids = set(data.recommended_secondary_term_ids + data.recommended_skill_term_ids)
    if plan.locked_lock_term_id:
        desired_term_ids.discard(plan.locked_lock_term_id)
    point_term_ids = set(plan.point.guaranteed_secondary_term_ids + plan.point.guaranteed_skill_term_ids)
    return bool(desired_term_ids.intersection(point_term_ids))


def _build_multi_point_plan(
    point: WeaponGemEnergyPointData,
    lock_data_list: list[WeaponGemRecommendationData],
    all_data_list: list[WeaponGemRecommendationData],
    rank_positions: list[int],
) -> _MultiPointPlan:
    locked_primary_ids = _pick_locked_primary_ids(lock_data_list, point)
    locked_lock_term_id = _pick_locked_lock_term_id(lock_data_list, point)

    plan = _MultiPointPlan(
        point=point,
        locked_primary_ids=locked_primary_ids,
        locked_lock_term_id=locked_lock_term_id,
        rank_positions=rank_positions,
    )
    for data in all_data_list:
        if bool(set(plan.locked_primary_ids).intersection(data.recommended_primary_term_ids)):
            plan.covered_weapon_names.append(data.weapon.name)
        if _is_weapon_covered_by_plan(data, plan):
            plan.lock_covered_weapon_names.append(data.weapon.name)
            if _has_remaining_desired_terms_in_point(data, plan):
                plan.remaining_term_hit_weapon_names.append(data.weapon.name)
                plan.remaining_term_hit_count += 1

    return plan


def _select_multi_point_plans(data_list: list[WeaponGemRecommendationData]) -> list[_MultiPointPlan]:
    if not data_list:
        return []

    point_map: dict[str, WeaponGemEnergyPointData] = {}
    point_ranks: dict[str, list[int]] = {}
    for data_index, data in enumerate(data_list):
        seen_keys: set[str] = set()
        rank = 0
        for point in data.recommended_energy_points:
            point_key = _format_point_name(point)
            if point_key in seen_keys:
                continue
            seen_keys.add(point_key)
            rank += 1

            current = point_map.get(point_key)
            if current is None or (point.world_level, point.recommend_lv) > (current.world_level, current.recommend_lv):
                point_map[point_key] = point

            point_ranks.setdefault(point_key, [999] * len(data_list))
            point_ranks[point_key][data_index] = rank

    plans: list[_MultiPointPlan] = []
    for point_key, point in point_map.items():
        for subset_size in range(len(data_list), 0, -1):
            for subset in combinations(data_list, subset_size):
                plan = _build_multi_point_plan(point, list(subset), data_list, point_ranks[point_key])
                if not plan.lock_covered_weapon_names:
                    continue
                plans.append(plan)

    plans.sort(
        key=lambda plan: (
            1 if plan.locked_lock_term_id is not None else 0,
            len(plan.lock_covered_weapon_names),
            plan.remaining_term_hit_count,
            len(plan.covered_weapon_names),
            -plan.rank_positions[0],
            -sum(plan.rank_positions),
            plan.point.world_level,
            plan.point.recommend_lv,
        ),
        reverse=True,
    )

    filtered_plans: list[_MultiPointPlan] = []
    seen_plan_keys: set[tuple[str, tuple[str, ...], tuple[str, ...], str | None]] = set()
    for plan in plans:
        plan_key = (
            plan.point.point_id,
            tuple(sorted(plan.lock_covered_weapon_names)),
            tuple(sorted(plan.locked_primary_ids)),
            plan.locked_lock_term_id,
        )
        if plan_key in seen_plan_keys:
            continue
        seen_plan_keys.add(plan_key)
        filtered_plans.append(plan)
    return filtered_plans


def _list_extra_weapon_names(
    plan: _MultiPointPlan,
    data_list: list[WeaponGemRecommendationData],
) -> list[str]:
    current_names = {data.weapon.name for data in data_list}
    extra_names: list[str] = []
    for weapon_id in TableCfg.WeaponBasicTable():
        data = WeaponGemInfoTable.get_by_weapon_id(weapon_id)
        if data is None or data.weapon.name in current_names:
            continue
        if _is_weapon_covered_by_plan(data, plan):
            extra_names.append(data.weapon.name)
    return sorted(set(extra_names))


def _format_lock_terms(
    locked_primary_ids: list[str],
    locked_lock_term_id: str | None,
) -> list[str]:
    primary_names = [_get_term_name(term_id) for term_id in locked_primary_ids]
    lines = [f"锁基础：{' / '.join(primary_names) or '无'}"]
    if locked_lock_term_id:
        lines.append(f"锁附加/技能：{_get_term_name(locked_lock_term_id)}")
    else:
        lines.append("锁附加/技能：无公共可锁词条")
    return lines


def _format_single_gem_reply(data: WeaponGemRecommendationData) -> str:
    best = data.best_energy_point
    if best is None:
        return f"{data.weapon.name}：未找到推荐副本"

    locked_primary_ids = _pick_locked_primary_ids([data], best)
    locked_lock_term_id = _pick_locked_lock_term_id([data], best)
    lines = [f"{data.weapon.name}：{_format_point_name(best)}"]
    lines.extend(_format_lock_terms(locked_primary_ids, locked_lock_term_id))
    return "\n".join(lines)


def _format_multi_gem_reply(data_list: list[WeaponGemRecommendationData]) -> str:
    plans = _select_multi_point_plans(data_list)
    weapon_names = [data.weapon.name for data in data_list]
    lines = [f"武器：{' / '.join(weapon_names)}"]

    if not plans:
        lines.append("未找到可一起刷的推荐副本")
    else:
        for index, plan in enumerate(plans[:3], start=1):
            if plan.locked_lock_term_id is not None:
                covered_names = plan.lock_covered_weapon_names
                plan_type = "完整共锁方案"
            else:
                covered_names = plan.covered_weapon_names
                plan_type = "仅公共三基础方案"

            remaining_names = [name for name in weapon_names if name not in covered_names]
            plan.extra_weapon_names = _list_extra_weapon_names(plan, data_list)

            lines.append(f"方案{index}：{_format_point_name(plan.point)}")
            lines.append(f"方案类型：{plan_type}")
            if covered_names:
                lines.append(f"当前输入里可一起刷：{' / '.join(covered_names)}")
            else:
                lines.append("当前输入里可一起刷：无")
            if plan.locked_lock_term_id is None:
                lines.append("说明：这个方案只有三条基础属性能公共锁定，第四条附加/技能词条不共通。")
            if plan.extra_weapon_names:
                lines.append(f"当前选项下还能刷的其他武器：{' / '.join(plan.extra_weapon_names[:8])}")
            else:
                lines.append("当前选项下还能刷的其他武器：无")
            lines.extend(_format_lock_terms(plan.locked_primary_ids, plan.locked_lock_term_id))
            if remaining_names:
                lines.append(f"仍需单独处理：{' / '.join(remaining_names)}")

    lines.append("各武器最佳：")
    for data in data_list:
        best = data.best_energy_point
        if best is None:
            lines.append(f"{data.weapon.name}：未找到推荐副本")
            continue
        lines.append(f"{data.weapon.name}：{_format_point_name(best)}")
    return "\n".join(lines)


def _split_weapon_names(text: str) -> list[str]:
    normalized = text.strip()
    for sep in ("，", ",", "、", "\n", "\t", "；", ";", "|", "/"):
        normalized = normalized.replace(sep, " ")
    return [item.strip() for item in normalized.split() if item.strip()]


@sv_weapon_gem.on_command(("武器基质", "武器刷什么基质", "武器基质副本"))
async def query_weapon_gem(bot: Bot, ev: Event):
    weapon_names = _split_weapon_names(ev.text)
    if not weapon_names:
        return await bot.send(f"请在命令后输入武器名称，例如：{P}武器基质 落草 不知归")

    data_list: list[WeaponGemRecommendationData] = []
    not_found: list[str] = []
    for weapon_name in weapon_names:
        data = WeaponGemInfoTable.get_by_weapon_name(weapon_name)
        if data is None:
            not_found.append(weapon_name)
            continue
        data_list.append(data)

    if not data_list:
        return await bot.send("\n".join(f"{name}：未找到推荐副本" for name in not_found))

    img = await draw_gem_recommend_img(data_list, not_found)
    await bot.send(img)

import json
import math
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.utils.image.convert import convert_img
from gsuid_core.utils.image.image_tools import core_font, crop_center_img
from PIL import Image, ImageDraw
from pydantic import BaseModel

from BeyondUID.utils.resource.RESOURCE_PATH import (
    PLAYER_PATH,
    charicon_path,
    charremoteicon700_path,
    itemiconbig_path,
)

from ..utils.image import get_footer

CARD_W = 175
BAR_H = 26
CARD_H = 260
GAP = 5
ROW_GAP = 10

TEXT_PATH = Path(__file__).parent / "texture2d"

# 各池 UP：pool_id -> charId 或 weaponId（限定池为角色，武器池为武器）
UP_ITEMS = {
    "special_1_0_1": "chr_0016_laevat",
    "weponbox_1_0_1": "wpn_sword_0006",
}


class BaseGachaRecordItem(BaseModel):
    """Base gacha record item model."""

    poolId: str
    poolName: str
    rarity: int
    gachaTs: str
    seqId: str


class CharRecordItem(BaseGachaRecordItem):
    """Single gacha record item model."""

    charId: str
    charName: str
    isFree: bool
    isNew: bool


class WeaponRecordItem(BaseGachaRecordItem):
    """Single gacha record item model."""

    weaponId: str
    weaponName: str
    weaponType: str
    isNew: bool


class PoolExportInfo(BaseModel):
    uid: str
    lang: str
    timezone: int
    exportTimestamp: int
    version: str


class GachaPoolExport(BaseModel):
    info: PoolExportInfo
    charList: list[CharRecordItem]
    weaponList: list[WeaponRecordItem]


def get_pity_per_pool(
    items: list[CharRecordItem] | list[WeaponRecordItem],
) -> dict[str, int]:
    """按 poolId 分组，计算每个池子当前多少抽没出6星（从最近一次抽卡往前数，不含免费抽）。
    角色池排除 isFree，武器池无 isFree 时全部计抽。"""
    by_pool: dict[str, list] = defaultdict(list)
    for item in items:
        by_pool[item.poolId].append(item)

    result = {}
    for pool_id, pool_items in by_pool.items():
        # 按 gachaTs 降序，同 gachaTs 时按 seqId 降序，确保同一批十连内顺序正确
        sorted_items = sorted(
            pool_items, key=lambda x: (int(x.gachaTs), int(x.seqId)), reverse=True
        )
        pity = 0
        for item in sorted_items:
            if item.rarity == 6:
                break
            if not getattr(item, "isFree", False):
                pity += 1
        result[pool_id] = pity
    return result


def get_pull_number_in_pool(
    items: list[CharRecordItem] | list[WeaponRecordItem],
    item: CharRecordItem | WeaponRecordItem,
) -> int:
    """池内按 gachaTs 正序排序后，该条目的 1-based 抽数（不含免费抽）。"""
    pool_items = [i for i in items if i.poolId == item.poolId]
    non_free_items = [i for i in pool_items if not getattr(i, "isFree", False)]
    pool_sorted = sorted(non_free_items, key=lambda x: (int(x.gachaTs), int(x.seqId)))
    for idx, i in enumerate(pool_sorted):
        if i.seqId == item.seqId and i.gachaTs == item.gachaTs:
            return idx + 1
    return 1


def _pool_stats_char(
    char_list: list[CharRecordItem], predicate: Callable[[CharRecordItem], bool]
) -> dict[str, int]:
    """按谓词过滤角色池，返回 total, free_count, six_count, non_free_count。"""
    items = [c for c in char_list if predicate(c)]
    non_free = [c for c in items if not c.isFree]
    six = [c for c in items if c.rarity == 6]
    return {
        "total": len(items),
        "free_count": len(items) - len(non_free),
        "six_count": len(six),
        "non_free_count": len(non_free),
    }


def _pool_stats_weapon(weapon_list: list[WeaponRecordItem]) -> dict[str, int]:
    """武器池统计：total, six_count。"""
    six = [w for w in weapon_list if w.rarity == 6]
    return {"total": len(weapon_list), "six_count": len(six)}


async def _draw_card(
    img: Image.Image,
    xy_point: tuple[int, int],
    gacha_num: int,
    *,
    char_id: str | None = None,
    weapon_id: str | None = None,
    is_up: bool = False,
    is_free: bool = False,
) -> None:
    """在画布 img 的 xy_point 处绘制一张六星卡（角色或武器）。
    层序：sg_bg → 头像 → 可选 UP 标 → sg6_fg → 「N抽」或「欧皇」文字。
    调用时须且仅须指定 char_id 或 weapon_id 之一。"""
    if (char_id is None) == (weapon_id is None):
        raise ValueError("须指定 char_id 或 weapon_id 其一")

    x0, y0 = xy_point

    # 加载头像：角色用 charicon/charremoteicon700，武器用 weapon_icon 或占位
    if char_id is not None:
        icon_path = charicon_path / f"icon_{char_id}.png"
        if not icon_path.exists():
            icon_path = charicon_path / "icon_chr_unknown_man.png"

        avatar = Image.open(icon_path).convert("RGBA")

        sg_bg_img = Image.open(TEXT_PATH / "sg_bg.png").convert("RGBA")
        sg_bg_img.paste(avatar, (14, 9), avatar)
    else:
        icon_path = itemiconbig_path / f"{weapon_id}.png"
        if not icon_path.exists():
            icon_path = charicon_path / "icon_chr_unknown_man.png"

        avatar = Image.open(icon_path).convert("RGBA")
        avatar = crop_center_img(avatar, CARD_W - 21, CARD_H - 60)

        sg_bg_img = Image.open(TEXT_PATH / "sg_bg.png").convert("RGBA")
        sg_bg_img.paste(avatar, (13, 30), avatar)

    # UP 标（角色卡或武器卡）
    if is_up:
        up_tag = Image.open(TEXT_PATH / "up_tag.png")
        tag_size = 80
        up_tag = up_tag.resize((tag_size, tag_size))
        sg_bg_img.paste(up_tag, (CARD_W - tag_size + 5, 4), up_tag)

    # sg6_fg → 「N抽」或「欧皇」文字
    fg_img = Image.open(TEXT_PATH / "sg6_fg.png")
    sg_bg_img.paste(fg_img, (0, 0), fg_img)
    # 免费抽出的6星显示「欧皇」
    text_str = "欧皇" if is_free else f"{gacha_num}抽"
    font = core_font(30)
    text_draw = ImageDraw.Draw(sg_bg_img)
    text_draw.text((90, 235), text_str, font=font, fill="white", anchor="mm")

    img.paste(sg_bg_img, (x0, y0), sg_bg_img)


def _build_pool_header_layer(
    *,
    pity_display: int,
    pool_type: str | None = None,
    pool_char_list: list[CharRecordItem] | None = None,
    char_stats: dict[str, int] | None = None,
    gacha_export: GachaPoolExport | None = None,
    weapon_list: list[WeaponRecordItem] | None = None,
) -> tuple[Image.Image, int]:
    """生成单池 header 层（角色池/武器池通用）：card_bg + 代表图 + 统计文字。
    返回 (layer, banner_height)。须传入角色池参数或武器池参数其一。"""
    is_char = pool_char_list is not None
    if is_char and (char_stats is None or gacha_export is None or pool_type is None):
        raise ValueError("角色池须提供 pool_type, char_stats, gacha_export")
    if not is_char and weapon_list is None:
        raise ValueError("须提供 pool_char_list 或 weapon_list")

    card_bg_img = Image.open(TEXT_PATH / "card_bg.png").convert("RGBA")
    cw, ch = card_bg_img.size
    rep_offset_x, rep_offset_y = 750, 50  # 代表图左上角

    # 代表图：角色池 = UP 或最近 6 星角色；武器池 = UP 或最近 6 星武器
    rep_img: Image.Image
    if is_char:
        rep_char_id: str | None = None
        if pool_type == "limited" and pool_char_list:
            pool_id = pool_char_list[0].poolId if pool_char_list else ""
            rep_char_id = UP_ITEMS.get(pool_id)
        if not rep_char_id and pool_char_list:
            six_star = sorted(
                [c for c in pool_char_list if c.rarity == 6],
                key=lambda x: int(x.gachaTs),
                reverse=True,
            )
            if six_star:
                rep_char_id = six_star[0].charId
        if not rep_char_id:
            rep_char_id = "chr_default"
        icon_path = charremoteicon700_path / f"icon_{rep_char_id}.png"
        if not icon_path.exists():
            icon_path = charicon_path / "icon_chr_default.png"
        rep_img = Image.open(icon_path).convert("RGBA").resize((400, 400))
    else:
        rep_weapon_id: str | None = None
        if weapon_list:
            pool_id = weapon_list[0].poolId if weapon_list else ""
            rep_weapon_id = UP_ITEMS.get(pool_id)
        if not rep_weapon_id and weapon_list:
            six_star = sorted(
                [w for w in weapon_list if w.rarity == 6],
                key=lambda x: int(x.gachaTs),
                reverse=True,
            )
            if six_star:
                rep_weapon_id = six_star[0].weaponId
        icon_path = itemiconbig_path / f"{rep_weapon_id}.png"
        if not icon_path.exists():
            logger.warning(f"Weapon icon not found for {rep_weapon_id}, using default char icon")
            icon_path = charicon_path / "icon_chr_default.png"
        rep_img = Image.open(icon_path).convert("RGBA").resize((400, 400))

    rep_img = rep_img.crop((0, 100, 400, 300))
    rep_w, rep_h = rep_img.size
    layer_w = max(cw, rep_offset_x + rep_w)
    layer_h = max(ch, rep_offset_y + rep_h)
    header_layer = Image.new("RGBA", (layer_w, layer_h), (0, 0, 0, 0))
    header_layer.paste(rep_img, (rep_offset_x, rep_offset_y), mask=rep_img)
    header_layer.paste(card_bg_img, (0, 0), mask=card_bg_img)

    # 池标题图（如 A.png）
    title_icon = TEXT_PATH / "A.png"
    title_img = Image.open(title_icon).convert("RGBA")
    title_draw = ImageDraw.Draw(title_img)
    title_draw.text(
        (100, 32), "已         抽没出6星", font=core_font(size=20), fill="black", anchor="lm"
    )
    title_draw.text(
        (145, 27), f"{pity_display}", font=core_font(size=36), fill="red", anchor="mm"
    )
    # 当前UP角色ICON
    up_icon = (
        Image.open(charremoteicon700_path / "icon_chr_0022_bounda.png")
        .convert("RGBA")
        .resize((104, 97))
    )
    title_img.paste(up_icon, (-10, -6), mask=up_icon)
    header_layer.paste(title_img, (107, 72), mask=title_img)

    layer_draw = ImageDraw.Draw(header_layer)

    # 计算池子时间范围
    pool_items_for_time: list = pool_char_list if is_char else (weapon_list or [])
    if pool_items_for_time:
        timestamps = [int(item.gachaTs) for item in pool_items_for_time]
        min_ts, max_ts = min(timestamps), max(timestamps)
        start_date = datetime.fromtimestamp(min_ts / 1000).strftime("%Y.%m.%d")
        end_date = datetime.fromtimestamp(max_ts / 1000).strftime("%Y.%m.%d")
        pool_time = f"{start_date} ~ {end_date}"
    else:
        pool_time = "-"
    layer_draw.text((1110, 226), pool_time, font=core_font(size=25), fill="black", anchor="rm")

    match pool_type:
        case "limited":
            pool_name = "限定寻访"
        case "standard":
            pool_name = "常驻寻访"
        case "beginner":
            pool_name = "新手寻访"
        case _:
            pool_name = "武器寻访"
    layer_draw.text((82, 46), pool_name, font=core_font(size=34), fill=(68, 68, 68), anchor="lm")

    text_start_xy = (200, 223)
    value_start_xy = (200, 190)
    offset = 134

    if is_char and char_stats and gacha_export:
        total_n = char_stats["total"]
        free_n = char_stats["free_count"]
        six_n = char_stats["six_count"]
        non_free_n = char_stats["non_free_count"]

        layer_draw.text(
            (value_start_xy[0] + offset * 2, value_start_xy[1]),
            f"{total_n}",
            font=core_font(size=35),
            fill="black",
            anchor="mm",
        )
        layer_draw.text(
            (text_start_xy[0] + offset * 2, text_start_xy[1]),
            "抽卡数",
            font=core_font(size=20),
            fill="black",
            anchor="mm",
        )

        layer_draw.text(
            (value_start_xy[0] + offset, value_start_xy[1]),
            f"{free_n}",
            font=core_font(size=35),
            fill="black",
            anchor="mm",
        )
        layer_draw.text(
            (text_start_xy[0] + offset, text_start_xy[1]),
            "免费次数",
            font=core_font(size=20),
            fill="black",
            anchor="mm",
        )
        if six_n > 0 and non_free_n > 0:
            avg_pity = non_free_n / six_n
            layer_draw.text(
                value_start_xy,
                f"{avg_pity:.1f}",
                font=core_font(size=35),
                fill="black",
                anchor="mm",
            )
        else:
            layer_draw.text(
                value_start_xy, "-", font=core_font(size=35), fill="black", anchor="mm"
            )
        layer_draw.text(
            text_start_xy, "平均出率", font=core_font(size=20), fill="black", anchor="mm"
        )

        if pool_type == "limited":
            up_six_count = sum(
                1
                for item in gacha_export.charList
                if item.poolId.startswith("special_")
                and item.rarity == 6
                and UP_ITEMS.get(item.poolId) == item.charId
            )
            if up_six_count > 0 and non_free_n > 0:
                avg_up = non_free_n / up_six_count
                layer_draw.text(
                    (value_start_xy[0] + offset * 3, value_start_xy[1]),
                    f"{avg_up:.0f}",
                    font=core_font(size=35),
                    fill="black",
                    anchor="mm",
                )
            else:
                layer_draw.text(
                    (value_start_xy[0] + offset * 3, value_start_xy[1]),
                    "-",
                    font=core_font(size=35),
                    fill="black",
                    anchor="mm",
                )
            layer_draw.text(
                (text_start_xy[0] + offset * 3, text_start_xy[1]),
                "平均UP",
                font=core_font(size=20),
                fill="black",
                anchor="mm",
            )
    else:
        stats = _pool_stats_weapon(weapon_list or [])
        total_n = stats["total"]
        six_n = stats["six_count"]
        layer_draw.text(
            (value_start_xy[0] + offset * 1, value_start_xy[1]),
            f"{total_n}",
            font=core_font(size=35),
            fill="black",
            anchor="mm",
        )
        layer_draw.text(
            (text_start_xy[0] + offset * 1, text_start_xy[1]),
            "抽卡数",
            font=core_font(size=20),
            fill="black",
            anchor="mm",
        )
        if six_n > 0 and total_n > 0:
            avg_pity = total_n / six_n
            layer_draw.text(
                (value_start_xy[0] + offset * 0, value_start_xy[1]),
                f"{avg_pity:.1f}",
                font=core_font(size=35),
                fill="black",
                anchor="mm",
            )
        else:
            layer_draw.text(
                (value_start_xy[0] + offset * 0, value_start_xy[1]),
                "-",
                font=core_font(size=35),
                fill="black",
                anchor="mm",
            )
        layer_draw.text(
            (text_start_xy[0] + offset * 0, text_start_xy[1]),
            "平均出率",
            font=core_font(size=20),
            fill="black",
            anchor="mm",
        )

    return header_layer, ch


async def draw_gachalogs_img(uid: str, bot: Bot, ev: Event):
    path = PLAYER_PATH / uid
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)

    gachalogs_path = path / "gacha_logs.json"

    if not gachalogs_path.exists():
        return await bot.send("未找到抽卡记录文件，请先刷新抽卡记录。")

    with gachalogs_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    gacha_export = GachaPoolExport.model_validate(data)

    if gacha_export.info.uid != uid:
        return await bot.send(
            f"抽卡记录 UID 与请求 UID 不符。\n"
            f"绑定的 UID 为 {uid}，抽卡记录 UID 为 {gacha_export.info.uid}。"
        )

    char_list = gacha_export.charList
    weapon_list = gacha_export.weaponList
    total_gacha_num = len(char_list) + len(weapon_list)

    pity_by_pool = get_pity_per_pool(char_list)
    pity_weapon = get_pity_per_pool(weapon_list)
    limited_items = [c for c in char_list if c.poolId.startswith("special_")]
    # 按 gachaTs 降序，同 gachaTs 时按 seqId 降序，确保同一批十连内顺序正确
    limited_sorted = sorted(
        limited_items, key=lambda x: (int(x.gachaTs), int(x.seqId)), reverse=True
    )
    pity_limited = 0
    for item in limited_sorted:
        if item.rarity == 6:
            break
        if not item.isFree:
            pity_limited += 1

    def _limited_pred(c: CharRecordItem) -> bool:
        return c.poolId.startswith("special_")

    limited_stats = _pool_stats_char(char_list, _limited_pred)
    standard_list = [c for c in char_list if c.poolId == "standard"]
    standard_stats = _pool_stats_char(char_list, lambda c: c.poolId == "standard")
    beginner_list = [c for c in char_list if c.poolId == "beginner"]
    beginner_stats = _pool_stats_char(char_list, lambda c: c.poolId == "beginner")

    pity_weapon_display = max(pity_weapon.values(), default=0) if pity_weapon else 0

    header_limited, lim_banner_h = _build_pool_header_layer(
        pity_display=pity_limited,
        pool_type="limited",
        pool_char_list=limited_items,
        char_stats=limited_stats,
        gacha_export=gacha_export,
    )
    header_weapon, wep_banner_h = _build_pool_header_layer(
        pity_display=pity_weapon_display,
        weapon_list=weapon_list,
    )
    header_standard, std_banner_h = _build_pool_header_layer(
        pity_display=pity_by_pool.get("standard", 0),
        pool_type="standard",
        pool_char_list=standard_list,
        char_stats=standard_stats,
        gacha_export=gacha_export,
    )
    header_beginner, beg_banner_h = _build_pool_header_layer(
        pity_display=pity_by_pool.get("beginner", 0),
        pool_type="beginner",
        pool_char_list=beginner_list,
        char_stats=beginner_stats,
        gacha_export=gacha_export,
    )

    six_limited = [c for c in limited_items if c.rarity == 6]
    six_weapon = [w for w in weapon_list if w.rarity == 6]
    six_standard = [c for c in standard_list if c.rarity == 6]
    six_beginner = [c for c in beginner_list if c.rarity == 6]

    def block_height(banner_h: int, six_count: int) -> int:
        rows = math.ceil(six_count / 6) if six_count else 0
        return banner_h + ROW_GAP + rows * (CARD_H + ROW_GAP)

    def _sort_ts(x):
        return int(x.gachaTs)

    h_lim = block_height(lim_banner_h, len(six_limited))
    h_wep = block_height(wep_banner_h, len(six_weapon))
    h_std = block_height(std_banner_h, len(six_standard))
    h_beg = block_height(beg_banner_h, len(six_beginner))

    title_img = Image.open(TEXT_PATH / "title.png")

    total_h = 700 + ROW_GAP + h_lim + ROW_GAP + h_wep + ROW_GAP + h_std + ROW_GAP + h_beg

    bg4 = Image.open(TEXT_PATH / "bg" / "bg4.jpg")
    img = crop_center_img(bg4, 1200, total_h)

    # 唯一 title_img
    icon_chr_0030_zhuangfy_img = Image.open(
        charremoteicon700_path / "icon_chr_0030_zhuangfy.png"
    ).resize((137, 137))
    title_img.paste(icon_chr_0030_zhuangfy_img, (55, 413), mask=icon_chr_0030_zhuangfy_img)
    frame_fg_img = Image.open(TEXT_PATH / "frame_fg.png")
    title_img.paste(frame_fg_img, (52, 413), mask=frame_fg_img)
    title_img_draw = ImageDraw.Draw(title_img)
    title_img_draw.text((327, 507), f"UID: {uid}", font=core_font(20), fill="black", anchor="mm")
    role_name = ev.sender["nickname"]
    title_img_draw.text((222, 458), role_name, font=core_font(36), fill="white", anchor="lm")

    title_img_draw.text(
        (906, 480), f"{total_gacha_num}", font=core_font(40), fill="white", anchor="mm"
    )
    title_img_draw.text(
        (906, 514), "总抽卡数", font=core_font(size=20), fill="yellow", anchor="mm"
    )

    title_img_draw.text(
        (1070, 480), f"{total_gacha_num}", font=core_font(40), fill="white", anchor="mm"
    )
    title_img_draw.text(
        (1070, 514), "不歪率", font=core_font(size=20), fill="yellow", anchor="mm"
    )

    img.paste(title_img, (0, -87), mask=title_img)

    _data = {
        "总抽卡": total_gacha_num,
        "不歪率": f"{total_gacha_num - pity_limited - pity_weapon_display}",
    }
    for indexn, nk in enumerate(_data):
        nv = _data[nk]
        yellow_card = Image.open(TEXT_PATH / "yellow_card.png")
        yellow_card_draw = ImageDraw.Draw(yellow_card)
        yellow_card_draw.text(
            (265, 94), str(nk), font=core_font(30), fill=(68, 68, 68), anchor="rm"
        )
        yellow_card_draw.text(
            (276, 87), str(nv), font=core_font(46), fill=(68, 68, 68), anchor="lm"
        )
        img.paste(yellow_card, (38 + indexn * 544, 485), mask=yellow_card)

    current_y = 663 + ROW_GAP

    # 四类池：header, banner_h, h, six_sorted, pull_list, 是否角色池, 是否画 UP 标
    pools = [
        (
            header_limited,
            lim_banner_h,
            h_lim,
            sorted(six_limited, key=_sort_ts, reverse=True),
            char_list,
            True,
            True,
        ),
        (
            header_weapon,
            wep_banner_h,
            h_wep,
            sorted(six_weapon, key=_sort_ts, reverse=True),
            weapon_list,
            False,
            True,
        ),
        (
            header_standard,
            std_banner_h,
            h_std,
            sorted(six_standard, key=_sort_ts, reverse=True),
            char_list,
            True,
            False,
        ),
        (
            header_beginner,
            beg_banner_h,
            h_beg,
            sorted(six_beginner, key=_sort_ts, reverse=True),
            char_list,
            True,
            False,
        ),
    ]
    for header, banner_h, h, six_sorted, pull_list, is_char_pool, use_is_up in pools:
        img.paste(header, (0, current_y), mask=header)
        grid_y = current_y + banner_h + ROW_GAP - 30
        for index, item in enumerate(six_sorted):
            col, row = index % 6, index // 6
            xy = (60 + col * (CARD_W + GAP), grid_y + row * (CARD_H + ROW_GAP))
            gacha_num = get_pull_number_in_pool(pull_list, item)
            is_free = getattr(item, "isFree", False)
            if is_char_pool:
                item_id = item.charId
                is_up = (UP_ITEMS.get(item.poolId) == item_id) if use_is_up else False
                await _draw_card(
                    img, xy, gacha_num, char_id=item_id, is_up=is_up, is_free=is_free
                )
            else:
                item_id = item.weaponId
                is_up = (UP_ITEMS.get(item.poolId) == item_id) if use_is_up else False
                await _draw_card(
                    img, xy, gacha_num, weapon_id=item_id, is_up=is_up, is_free=is_free
                )
        current_y += h + ROW_GAP

    footer_img = get_footer()
    img.paste(footer_img, (100, current_y - ROW_GAP - 10), mask=footer_img)

    await bot.send(await convert_img(img))
    return None

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.subscribe import Subscribe, gs_subscribe
from gsuid_core.sv import SV

from ..utils.database.models import BeyondBind
from ..utils.error_reply import UID_HINT
from ..utils.error_reply import prefix as P

sv_self_config = SV("byd配置")

PRIV_MAP = {
    "推送": "push",
    "自动签到": None,
}


# 开启 自动签到 功能
@sv_self_config.on_prefix(("开启", "关闭"))
async def open_switch_func(bot: Bot, ev: Event):
    user_id = ev.user_id
    config_name = ev.text

    if config_name not in PRIV_MAP:
        return await bot.send(f"[beyond]\n❌ 请输入正确的功能名称...\n🚩 例如: {P}开启自动签到")

    logger.info(f"[beyond] [{user_id}]尝试[{ev.command[:2]}]了[{ev.text}]功能")

    platform_roleid = await BeyondBind.get_uid_by_game(ev.user_id, ev.bot_id)
    if platform_roleid is None:
        return await bot.send(UID_HINT)
    logger.info(f"[beyond] [{user_id}] 角色ID为[{platform_roleid}]")

    c_name = f"[Beyond] {config_name}"

    if "开启" in ev.command:
        im = f"[beyond]已为[PlatformRoleID{platform_roleid}]开启{config_name}功能。"

        if PRIV_MAP[config_name] is None and await gs_subscribe.get_subscribe(c_name, uid=platform_roleid):
            await Subscribe.update_data_by_data(
                {
                    "task_name": c_name,
                    "uid": platform_roleid,
                },
                {
                    "user_id": ev.user_id,
                    "bot_id": ev.bot_id,
                    "group_id": ev.group_id,
                    "bot_self_id": ev.bot_self_id,
                    "user_type": ev.user_type,
                    "WS_BOT_ID": ev.WS_BOT_ID,
                },
            )
        else:
            await gs_subscribe.add_subscribe(
                "single",
                c_name,
                ev,
                extra_message=PRIV_MAP[config_name],
                uid=platform_roleid,
            )
    else:
        data = await gs_subscribe.get_subscribe(
            c_name,
            ev.user_id,
            ev.bot_id,
            ev.user_type,
        )
        if data:
            await gs_subscribe.delete_subscribe(
                "single",
                c_name,
                ev,
                uid=platform_roleid,
            )
            im = f"[beyond]已为[PlatformRoleID{platform_roleid}]关闭{config_name}功能。"
        else:
            im = (
                f"[beyond]\n"
                f"未找到[PlatformRoleID{platform_roleid}]的{config_name}功能配置, "
                f"该功能可能未开启。"
            )

    await bot.send(im)

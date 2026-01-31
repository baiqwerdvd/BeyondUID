from gsuid_core.sv import SV, get_plugin_available_prefix
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.utils.error_reply import UID_HINT

from .set_config import set_config_func
from ..utils.database.models import BeyondBind

sv_self_config = SV("byd配置")

ZMD_PREFIX = get_plugin_available_prefix("BeyondUID")

# 开启 自动签到 功能
@sv_self_config.on_prefix(("byd开启", "byd关闭"))
async def open_switch_func(bot: Bot, ev: Event):
    user_id = ev.user_id
    config_name = ev.text

    logger.info(f"[{user_id}]尝试[{ev.command[2:]}]了[{ev.text}]功能")

    if ev.command == "byd开启":
        query = True
        gid = ev.group_id if ev.group_id else "on"
    else:
        query = False
        gid = "off"

    is_admin = ev.user_pm <= 2
    if ev.at and is_admin:
        user_id = ev.at
    elif ev.at:
        return await bot.send("你没有权限...")

    uid = await BeyondBind.get_uid_by_game(ev.user_id, bot.bot_id)
    if uid is None:
        return await bot.send(UID_HINT)

    im = await set_config_func(
        ev.bot_id,
        config_name=config_name,
        uid=uid,
        user_id=user_id,
        option=gid,
        query=query,
        is_admin=is_admin,
    )
    await bot.send(im)

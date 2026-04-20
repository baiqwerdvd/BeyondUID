from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.sv import SV

from ..utils.database.models import BeyondBind
from ..utils.error_reply import UID_HINT
from .note import get_daily_info

sv_get_note = SV("终末地每日信息")


@sv_get_note.on_fullmatch(
    (
        "每日",
        "mr",
        "便笺",
        "便签",
        "实时便笺",
        "当前状态",
    )
)
async def send_daily_info(bot: Bot, ev: Event):
    logger.info("开始执行[byd每日信息]")
    user_id = ev.at if ev.at else ev.user_id
    logger.info(f"[byd每日信息]UserID: {user_id}")

    uid = await BeyondBind.get_uid_by_game(user_id, ev.bot_id)
    if uid is None:
        return await bot.send(UID_HINT)
    logger.info(f"[byd每日信息]UID: {uid}")

    im = await get_daily_info(str(uid))
    await bot.send(im)

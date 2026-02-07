from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.sv import SV

from ..utils.database.models import BeyondBind, BeyondUser

from .draw_img import draw_gachalogs_img
from .get_gachalogs import fetch_full_record

sv_gacha_log = SV("byd抽卡记录")


@sv_gacha_log.on_fullmatch(("抽卡记录", "抽卡纪录"))
async def send_gacha_log_card_info(bot: Bot, ev: Event):
    logger.info("开始执行[byd抽卡记录]")
    uid = await BeyondBind.get_uid_by_game(ev.user_id, ev.bot_id)
    if uid is None:
        return await bot.send("请先绑定终末地账号，使用指令：byd扫码登录 进行绑定")
    await draw_gachalogs_img(uid, bot, ev)


@sv_gacha_log.on_command(("刷新抽卡记录", "更新抽卡记录"))
async def sync_gachalog(bot: Bot, ev: Event):
    logger.info("开始执行[byd刷新抽卡记录]")
    uid_and_platform_roleid = await BeyondUser.get_uid_and_platform_roleid_by_game(
        user_id=ev.user_id,
        bot_id=ev.bot_id,
    )
    if uid_and_platform_roleid is None:
        return await bot.send("请先绑定终末地账号，使用指令：byd扫码登录 进行绑定")
    uid, platform_roleid = uid_and_platform_roleid

    if uid is None or platform_roleid is None:
        return await bot.send("请先绑定终末地账号，使用指令：byd扫码登录 进行绑定")

    await bot.send(f"UID{uid}开始执行[刷新抽卡记录],需要一定时间...请勿重复触发！")
    await fetch_full_record(uid, platform_roleid, bot, ev)

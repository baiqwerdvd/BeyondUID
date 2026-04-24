from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment
from gsuid_core.sv import SV
from gsuid_core.utils.image.convert import convert_img

from .get_data import get_calendar_image

sv_calendar = SV("终末地活动日历")


@sv_calendar.on_fullmatch(("活动日历", "版本日历"))
async def send_calendar(bot: Bot, ev: Event):
    logger.info("开始执行[byd活动日历]")

    try:
        result = await get_calendar_image()
    except Exception as e:
        logger.exception("[byd活动日历] 获取失败")
        return await bot.send(f"活动日历获取失败: {e!s}")

    if isinstance(result, str):
        return await bot.send(result)

    msg = [
        MessageSegment.text("[终末地] 活动日历\n"),
        MessageSegment.image(await convert_img(result)),
    ]
    await bot.send(msg)

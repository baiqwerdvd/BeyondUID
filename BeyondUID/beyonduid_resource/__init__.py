from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.sv import SV

from ..utils.resource.download_all_resource import download_all_resource, is_downloading

sv_download_config = SV("byd资源下载", pm=1)


@sv_download_config.on_fullmatch(("下载全部资源", "资源更新"))
async def send_download_resource_msg(bot: Bot, ev: Event):
    if is_downloading():
        return await bot.send("[beyond] 正在下载中，请勿重复触发")
    await bot.send("[beyond] 正在开始下载~可能需要较久的时间！")
    await bot.send(f"[beyond] {await download_all_resource()}")


async def startup():
    logger.info("[beyond资源文件下载] 正在检查与下载缺失的资源文件,可能需要较长时间,请稍等")
    logger.info(f"[beyond资源文件下载] {await download_all_resource()}")

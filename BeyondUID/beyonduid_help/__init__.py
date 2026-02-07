from gsuid_core.bot import Bot
from gsuid_core.help.utils import register_help
from gsuid_core.models import Event
from gsuid_core.sv import SV
from PIL import Image

from ..utils.error_reply import prefix as P
from .get_help import ICON, get_help

sv_dna_help = SV("byd帮助")


@sv_dna_help.on_fullmatch("帮助")
async def send_help_img(bot: Bot, ev: Event):
    await bot.send_option(await get_help(ev.user_pm))


register_help("BeyondUID", f"{P}帮助", Image.open(ICON))

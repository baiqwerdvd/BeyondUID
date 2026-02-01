from gsuid_core.bot import Bot
from gsuid_core.help.utils import register_help
from gsuid_core.models import Event
from gsuid_core.sv import SV, get_plugin_available_prefix
from PIL import Image

from .get_help import ICON, get_help

sv_dna_help = SV("byd帮助")


@sv_dna_help.on_fullmatch("帮助")
async def send_help_img(bot: Bot, ev: Event):
    await bot.send_option(await get_help(ev.user_pm))


register_help("BeyondUID", f"{get_plugin_available_prefix('BeyondUID')}帮助", Image.open(ICON))

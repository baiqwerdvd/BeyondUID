import json
from pathlib import Path

from gsuid_core.help.draw_new_plugin_help import get_new_help
from gsuid_core.help.model import PluginHelp
from PIL import Image

from ..utils.error_reply import prefix as P
from ..utils.image import get_footer
from ..version import BeyondUID_version

ICON = Path(__file__).parent.parent.parent / "ICON.png"
HELP_DATA = Path(__file__).parent / "help.json"
ICON_PATH = Path(__file__).parent / "icon_path"
TEXT_PATH = Path(__file__).parent / "texture2d"


def get_help_data() -> dict[str, PluginHelp]:
    with open(HELP_DATA, encoding="utf-8") as file:
        return json.load(file)


plugin_help = get_help_data()


async def get_help(pm: int):
    return await get_new_help(
        plugin_name="BeyondUID",
        plugin_info={f"v{BeyondUID_version}": ""},
        plugin_icon=Image.open(ICON),
        plugin_help=plugin_help,
        plugin_prefix=P,
        help_mode="dark",
        banner_bg=Image.open(TEXT_PATH / "banner_bg.png"),
        banner_sub_text="完成这份合约，前往潜力无限的新热土，离开我们熟悉的家园——开拓未知的新世界。",
        help_bg=Image.open(TEXT_PATH / "bg.jpg"),
        cag_bg=Image.open(TEXT_PATH / "cag_bg.png"),
        item_bg=Image.open(TEXT_PATH / "item.png"),
        icon_path=ICON_PATH,
        footer=get_footer(),
        enable_cache=False,
        column=3,
        pm=pm,
    )

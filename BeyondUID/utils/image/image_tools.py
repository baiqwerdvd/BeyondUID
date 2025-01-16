from pathlib import Path

from gsuid_core.utils.image.image_tools import CustomizeImage
from PIL import Image

BG_PATH = Path(__file__).parent / "bg"
NM_BG_PATH = BG_PATH / "nm_bg"
SP_BG_PATH = BG_PATH / "sp_bg"


async def get_simple_bg(
    based_w: int, based_h: int, image: str | None | Image.Image = None
) -> Image.Image:
    CIL = CustomizeImage(NM_BG_PATH)
    return CIL.get_image(image, based_w, based_h)

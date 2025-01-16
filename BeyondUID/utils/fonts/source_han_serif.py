from pathlib import Path

from PIL import ImageFont

FONT_ORIGIN_PATH = Path(__file__).parent / "SourceHanSerifCN-Medium.ttf"


def source_han_serif_origin(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_ORIGIN_PATH), size=size)


sans_font_12 = source_han_serif_origin(12)
sans_font_28 = source_han_serif_origin(28)
sans_font_120 = source_han_serif_origin(34)

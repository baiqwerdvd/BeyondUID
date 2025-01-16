from pathlib import Path

from PIL import ImageFont

FONT_ORIGIN_PATH = Path(__file__).parent / "SourceHanSansCN-Medium.ttf"


def source_han_sans_cn_origin(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_ORIGIN_PATH), size=size)


sans_font_12 = source_han_sans_cn_origin(12)
sans_font_18 = source_han_sans_cn_origin(18)
sans_font_20 = source_han_sans_cn_origin(20)
sans_font_22 = source_han_sans_cn_origin(22)
sans_font_24 = source_han_sans_cn_origin(24)
sans_font_26 = source_han_sans_cn_origin(26)
sans_font_36 = source_han_sans_cn_origin(36)
sans_font_34 = source_han_sans_cn_origin(34)
sans_font_38 = source_han_sans_cn_origin(38)
sans_font_28 = source_han_sans_cn_origin(28)
sans_font_50 = source_han_sans_cn_origin(50)
sans_font_120 = source_han_sans_cn_origin(120)

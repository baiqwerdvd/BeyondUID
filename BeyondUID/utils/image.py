from typing import Tuple, Union, Optional
from pathlib import Path

from PIL import Image, ImageOps, ImageDraw

TEXT_PATH = Path(__file__).parent / "texture2d"
ICON = Path(__file__).parent.parent.parent / "ICON.png"

# Gold & Earth Tones
COLOR_LIGHT_GOLDENROD = (250, 250, 210)  # 浅金黄色
COLOR_PALE_GOLDENROD = (238, 232, 170)  # 淡金黄色的
COLOR_KHAKI = (240, 230, 140)  # 黄褐色
COLOR_GOLDENROD = (218, 165, 32)  # 金毛
COLOR_GOLD = (255, 215, 0)  # 金
COLOR_ORANGE = (255, 165, 0)  # 橙子
COLOR_DARK_ORANGE = (255, 140, 0)  # 深橙色
COLOR_PERU = (205, 133, 63)  # 秘鲁
COLOR_CHOCOLATE = (210, 105, 30)  # 巧克力
COLOR_SADDLE_BROWN = (139, 69, 19)  # 马鞍棕色
COLOR_SIENNA = (160, 82, 45)  # 赭色

# Red & Pink Tones
COLOR_LIGHT_SALMON = (255, 160, 122)  # 浅鲑红 / Lightsalmon #FFA07A
COLOR_SALMON = (250, 128, 114)  # 三文鱼 / Salmon #FA8072
COLOR_DARK_SALMON = (233, 150, 122)  # 黑鲑 / Dark Salmon #E9967A
COLOR_LIGHT_CORAL = (240, 128, 128)  # 轻珊瑚 / Light Coral #F08080
COLOR_INDIAN_RED = (205, 92, 92)  # 印度红 / Indian Red #CD5C5C
COLOR_CRIMSON = (220, 20, 60)  # 赤红 / Crimson #DC143C
COLOR_FIRE_BRICK = (178, 34, 34)  # 耐火砖 / Fire Brick #B22222
COLOR_RED = (255, 0, 0)  # 红色 / Red #FF0000
COLOR_DARK_RED = (139, 0, 0)  # 深红 / Dark Red #8B0000
COLOR_MAROON = (128, 0, 0)  # 栗色 / Maroon #800000
COLOR_TOMATO = (255, 99, 71)  # 番茄 / Tomato #FF6347
COLOR_ORANGE_RED = (255, 69, 0)  # 橙红 / Orange Red #FF4500
COLOR_PALE_VIOLET_RED = (219, 112, 147)  # 泛紫红 / Pale Violet Red #DB7093

# Basic Colors
COLOR_BLACK = (0, 0, 0)
COLOR_WHITE = (255, 255, 255)
COLOR_GRAY = (128, 128, 128)
COLOR_LIGHT_GRAY = (230, 230, 230)
COLOR_RED = (255, 0, 0)
COLOR_GREEN = (76, 175, 80)
COLOR_BLUE = (30, 40, 60)
COLOR_PURPLE = (138, 43, 226)

Color = Union[str, Tuple[int, int, int], Tuple[int, int, int, int]]


def get_footer():
    return Image.open(TEXT_PATH / "footer.png")

def add_footer(
    img: Image.Image,
    w: int = 0,
    offset_y: int = 0,
    is_invert: bool = False,
):
    footer = Image.open(TEXT_PATH / "footer.png")
    if is_invert:
        r, g, b, a = footer.split()
        rgb_image = Image.merge("RGB", (r, g, b))
        rgb_image = ImageOps.invert(rgb_image.convert("RGB"))
        r2, g2, b2 = rgb_image.split()
        footer = Image.merge("RGBA", (r2, g2, b2, a))

    if w != 0:
        footer = footer.resize(
            (w, int(footer.size[1] * w / footer.size[0])),
        )

    x, y = (
        int((img.size[0] - footer.size[0]) / 2),
        img.size[1] - footer.size[1] - 20 + offset_y,
    )

    img.paste(footer, (x, y), footer)
    return img


def get_ICON():
    return Image.open(ICON).convert("RGBA")



class SmoothDrawer:
    """通用抗锯齿绘制工具"""

    def __init__(self, scale: int = 4):
        self.scale = scale

    def rounded_rectangle(
        self,
        xy: Union[Tuple[int, int, int, int], Tuple[int, int]],
        radius: int,
        fill: Optional[Color] = None,
        outline: Optional[Color] = None,
        width: int = 0,
        target: Optional[Image.Image] = None,
    ):
        if len(xy) == 4:
            # 边界框坐标 (x0, y0, x1, y1)
            x0, y0, x1, y1 = xy
            w = abs(x1 - x0)
            h = abs(y1 - y0)
            # 如果提供了目标图片，使用边界框的实际坐标
            paste_x, paste_y = min(x0, x1), min(y0, y1)
        elif len(xy) == 2:
            # 尺寸 (width, height) - 向后兼容
            w, h = xy
            paste_x, paste_y = 0, 0
        else:
            raise ValueError(f"xy 参数必须是 2 或 4 个元素的元组，当前为 {len(xy)} 个元素")

        if h <= 0 or w <= 0:
            return

        large = Image.new("RGBA", (w * self.scale, h * self.scale), (0, 0, 0, 0))
        draw = ImageDraw.Draw(large)

        # 绘制
        draw.rounded_rectangle(
            (0, 0, w * self.scale, h * self.scale),
            radius=radius * self.scale,
            fill=fill,
            outline=outline,
            width=width * self.scale,
        )

        result = large.resize((w, h))

        if target is not None:
            target.alpha_composite(result, (paste_x, paste_y))
            return

        return

import textwrap
from typing import Any

from bs4 import BeautifulSoup, element
from PIL import Image, ImageDraw

from gsuid_core.logger import logger
from gsuid_core.utils.fonts.fonts import core_font as cf
from gsuid_core.utils.image.convert import convert_img
from gsuid_core.utils.image.image_tools import get_div
from gsuid_core.utils.image.utils import download_pic_to_image

from .model import BulletinData


async def get_ann_img(data: BulletinData) -> str | bytes:
    match data.displayType:
        case "rich_text":
            soup = BeautifulSoup(data.data.html, "lxml")
            img = await soup_to_img(data.header, soup, "")
            return img
        case _:
            img = await download_pic_to_image("")
            return await convert_img(img)
        # case _:
        #     return "暂不支持的公告类型"


async def process_tag(
    elements: list[dict[str, Any]],
    point: int,
    init_point: int,
    tag: element.Tag,
):
    space = 10
    _type = _data = None

    logger.debug(f"[GsCore] 正在处理TAG: {tag.name}")

    if tag.name == "img":
        img_url = tag.get("src")
        if isinstance(img_url, str):
            if img_url.startswith("https://web.hycdn.cn/"):
                img = await download_pic_to_image(img_url)
                new_h = int((930 / img.size[0]) * img.size[1])
                img = img.resize((930, new_h))
                point += new_h
                _type = "image"
                _data = img
    elif tag.name and tag.name.startswith("h") and tag.name != "html":
        text = tag.get_text(strip=True)
        line = len(textwrap.wrap(text, width=14))
        point += 70 * line if line >= 1 else 70
        _type = "title"
        _data = text
    elif tag.name == "div" and tag.has_attr("class"):
        if "media-wrap image-wrap" in tag["class"]:
            tag_img = tag.find("img")
            if isinstance(tag_img, element.Tag):
                img_url = tag_img.get("src")
                if img_url:
                    point += 60
                    _type = "div"
                    _data = "div"
    elif tag.name == "p":
        text = tag.get_text(strip=True)
        if text:
            if tag.get("style") == "text-align:right;":
                line = len(textwrap.wrap(text, width=57))
                point += 30 * line if line >= 1 else 30
                _type = "right_text"
                _data = text
            else:
                line = len(textwrap.wrap(text, width=57))
                point += 30 * line if line >= 1 else 30
                _type = "text"
                _data = text
        else:
            point += 10

    if _data is not None and _type is not None:
        if elements:
            pre_pos = elements[-1]["next_pos"]
        else:
            pre_pos = init_point
        elements.append(
            {
                "type": _type,
                "data": _data,
                "pos": pre_pos,
                "next_pos": point,
            }
        )
        point += space

    return point, elements


async def soup_to_img(
    header: str, soup: BeautifulSoup, bannerImageUrl: str
) -> str | bytes:
    banner_img = None
    banner_img_new_h = 0
    header_img = None
    header_img_new_h = 0

    if bannerImageUrl != "":
        banner_img = await download_pic_to_image(bannerImageUrl)
        banner_img_new_h = int((930 / banner_img.size[0]) * banner_img.size[1])
        banner_img = banner_img.resize((930, banner_img_new_h))

    if header != "":
        header_img = (
            "https://ak.hycdn.cn/announce/assets/images/announcement/header.jpg"
        )
        header_img = await download_pic_to_image(header_img)
        header_img_new_h = int((930 / header_img.size[0]) * header_img.size[1])
        header_img = header_img.resize((930, header_img_new_h))

    elements = []
    if banner_img:
        point = 105 + banner_img_new_h + 15
        init_point = 105 + banner_img_new_h + 15
    else:
        point = 105
        init_point = 105
    div = get_div()

    logger.info("[GsCore] 开始解析帖子内容...")
    for tag in soup.descendants:
        point, elements = await process_tag(
            elements,
            point,
            init_point,
            tag,  # type: ignore
        )
    logger.info("[GsCore] 帖子解析完成!进入图片处理流程...")

    img = Image.new("RGB", (1000, point), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    if banner_img:
        img.paste(banner_img, (35, 35))

    if header_img:
        pad = 50 + banner_img_new_h if banner_img else 35

        img.paste(header_img, (35, pad))
        draw.text(
            (45, 7 + pad),
            header,
            font=cf(30),
            fill=(255, 255, 255),
        )

    for i in elements:
        if i["type"] == "image":
            img.paste(i["data"], (35, i["pos"]))
        elif i["type"] == "title":
            draw.text(
                (35, i["pos"]),
                i["data"],
                font=cf(30),
                fill=(0, 0, 0),
            )
        elif i["type"] == "strong_text":
            wrapped_text = textwrap.wrap(i["data"], width=57)
            for index, line in enumerate(wrapped_text):
                # 加粗
                draw.text(
                    (35, i["pos"] + index * 30),
                    line,
                    font=cf(16),
                    fill=(0, 0, 0),
                )
        elif i["type"] == "text":
            wrapped_text = textwrap.wrap(i["data"], width=57)
            for index, line in enumerate(wrapped_text):
                draw.text(
                    (35, i["pos"] + index * 30),
                    line,
                    font=cf(16),
                    fill=(0, 0, 0),
                )
        elif i["type"] == "right_text":
            wrapped_text = textwrap.wrap(i["data"], width=57)
            for index, line in enumerate(wrapped_text):
                draw.text(
                    (965, i["pos"] + index * 30),
                    line,
                    anchor="rm",
                    font=cf(16),
                    fill=(0, 0, 0),
                )
        elif i["type"] == "div":
            img.paste(div, (0, i["pos"]), div)

    logger.info("[GsCore] 图片处理完成!")

    return await convert_img(img)

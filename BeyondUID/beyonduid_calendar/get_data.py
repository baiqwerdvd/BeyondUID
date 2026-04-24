"""从游戏公告中拉取官方版本日历图片，并做本地缓存。

缓存策略：
- 缓存文件保存在 data/BeyondUID/calendar/ 目录下
- 缓存元数据 (calendar_cache.json) 记录了当前缓存的 CID、version、图片URL
- 当公告 version 发生变化时，重新下载图片
- 缓存的图片以 calendar_{cid}.png 命名
"""

import json
import re
from io import BytesIO
from pathlib import Path

import aiohttp
from gsuid_core.data_store import get_res_path
from gsuid_core.logger import logger
from PIL import Image

from ..beyonduid_ann.get_data import BASE_URL, GAME_CODE, LANGUAGE

CALENDAR_CACHE_DIR = get_res_path(["BeyondUID", "calendar"])
CACHE_META_FILE = CALENDAR_CACHE_DIR / "calendar_cache.json"

# 确保缓存目录存在
CALENDAR_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _load_cache_meta() -> dict:
    """加载缓存元数据"""
    if CACHE_META_FILE.exists():
        try:
            with CACHE_META_FILE.open("r", encoding="UTF-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"[活动日历] 加载缓存元数据失败: {e}")
    return {}


def _save_cache_meta(meta: dict) -> None:
    """保存缓存元数据"""
    try:
        with CACHE_META_FILE.open("w", encoding="UTF-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    except OSError as e:
        logger.error(f"[活动日历] 保存缓存元数据失败: {e}")


def _get_cached_image(cid: str) -> Path:
    """获取缓存图片路径"""
    return CALENDAR_CACHE_DIR / f"calendar_{cid}.png"


async def _find_calendar_cid(session: aiohttp.ClientSession) -> tuple[str, int] | None:
    """从公告列表中查找版本日历公告的 CID 和 version。

    Returns:
        (cid, version) 元组，未找到时返回 None
    """
    url = (
        f"{BASE_URL}/bulletin/v2/aggregate"
        f"?lang={LANGUAGE}&channel=1&subChannel=1&platform=Windows"
        f"&type=0&code={GAME_CODE}&hideDetail=1&server=1"
    )

    async with session.get(url) as response:
        response.raise_for_status()
        data = await response.json()

    if data.get("code") != 0:
        logger.warning(f"[活动日历] API 返回错误: {data.get('code')}")
        return None

    aggregate = data["data"]

    # 从 list 中找 tab=events 且标题包含"版本日历"的公告
    for item in aggregate.get("list", []):
        if item.get("tab") == "events":
            title = item.get("title", "").replace("\\n", "")
            if "版本日历" in title:
                cid = item["cid"]
                # 从 onlineList 中找到对应的 version
                version = 0
                for online in aggregate.get("onlineList", []):
                    if online["cid"] == cid:
                        version = online["version"]
                        break
                return (cid, version)

    return None


def _extract_image_url_from_html(html: str) -> str | None:
    """从公告 HTML 中提取图片 URL"""
    # 匹配 <img src="..."> 中的 URL
    match = re.search(r'<img\s+[^>]*src="([^"]+)"', html)
    if match:
        return match.group(1)
    return None


async def _fetch_calendar_detail(
    session: aiohttp.ClientSession, cid: str
) -> tuple[str | None, str | None]:
    """获取版本日历公告详情，返回 (image_url, title)"""
    url = f"{BASE_URL}/bulletin/detail/{cid}?lang={LANGUAGE}&code={GAME_CODE}"

    async with session.get(url) as response:
        response.raise_for_status()
        data = await response.json()

    if data.get("code") != 0:
        logger.warning(f"[活动日历] 获取公告详情失败: {data.get('code')}")
        return None, None

    detail = data["data"]
    title = detail.get("title", "").replace("\\n", "")

    # 优先从 data.url 获取 (picture 类型的公告)
    data_block = detail.get("data", {})
    img_url = data_block.get("url")

    # 如果没有 data.url，尝试从 HTML 中提取
    if not img_url and data_block.get("html"):
        img_url = _extract_image_url_from_html(data_block["html"])

    return img_url, title


async def _download_image(session: aiohttp.ClientSession, url: str) -> Image.Image:
    """下载图片并返回 PIL Image"""
    async with session.get(url) as response:
        response.raise_for_status()
        content = await response.read()
        return Image.open(BytesIO(content))


async def get_calendar_image() -> Image.Image | str:
    """获取活动日历图片。

    优先使用缓存，当公告版本更新时自动刷新缓存。

    Returns:
        PIL Image 对象（成功）或 错误消息字符串（失败）
    """
    cache_meta = _load_cache_meta()

    async with aiohttp.ClientSession() as session:
        # 1. 查找版本日历公告
        result = await _find_calendar_cid(session)
        if result is None:
            return "未找到版本日历公告，可能当前版本暂未发布日历"

        cid, version = result

        # 2. 检查缓存是否有效
        cached_cid = cache_meta.get("cid")
        cached_version = cache_meta.get("version")
        cached_image_path = _get_cached_image(cid)

        if (
            cached_cid == cid
            and cached_version == version
            and cached_image_path.exists()
        ):
            logger.info(f"[活动日历] 使用缓存: CID={cid}, version={version}")
            return Image.open(cached_image_path)

        # 3. 缓存失效，重新获取
        logger.info(f"[活动日历] 缓存失效，重新获取: CID={cid}, version={version}")

        img_url, title = await _fetch_calendar_detail(session, cid)
        if not img_url:
            return "版本日历公告中未找到图片"

        logger.info(f"[活动日历] 下载日历图片: {img_url}")
        img = await _download_image(session, img_url)

        # 4. 保存缓存
        # 清理旧的缓存图片
        if cached_cid and cached_cid != cid:
            old_path = _get_cached_image(cached_cid)
            if old_path.exists():
                old_path.unlink()
                logger.debug(f"[活动日历] 清理旧缓存: {old_path}")

        img.save(str(cached_image_path), "PNG")
        _save_cache_meta(
            {
                "cid": cid,
                "version": version,
                "image_url": img_url,
                "title": title,
            }
        )
        logger.info(f"[活动日历] 缓存已更新: CID={cid}, version={version}")

        return img

import asyncio

from gsuid_core.utils.download_resource.download_core import check_speed

from ...beyonduid_gamedata import TableCfg
from .download_from_cos import download_all_file_from_cos
from .RESOURCE_PATH import TABLE_CFG_PATH

_download_lock = asyncio.Lock()


def is_downloading() -> bool:
    return _download_lock.locked()


def _table_mtimes() -> dict[str, float]:
    return {str(f): f.stat().st_mtime for f in TABLE_CFG_PATH.rglob("*") if f.is_file()}


async def download_all_resource() -> str:
    if _download_lock.locked():
        return "正在下载中，请勿重复触发"

    async with _download_lock:
        # 测速结果有缓存，download_all_file 里再调一次不会重新测
        _, base_url = await check_speed()
        if not base_url:
            return "没有可用的资源节点，下载失败"

        before = _table_mtimes()
        await download_all_file_from_cos()
        if _table_mtimes() == before:
            return "资源下载完成，数据表无变化"
        TableCfg.reload()
        return "资源下载完成，数据表已重新加载"

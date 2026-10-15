import httpx
from gsuid_core.logger import logger
from gsuid_core.utils.download_resource.download_core import download_all_file
from gsuid_core.utils.download_resource.download_file import download

from ...beyonduid_gamedata import TABLE_FILES
from .RESOURCE_PATH import (
    TABLE_CFG_PATH,
    charicon_path,
    charremoteicon700_path,
    itemiconbig_path,
)


async def download_all_file_from_cos():
    await download_all_file(
        "BeyondUID",
        {
            "resource/charremoteicon700": charremoteicon700_path,
            "resource/itemiconbig": itemiconbig_path,
            "resource/charicon": charicon_path,
        },
    )


async def _remote_size(client: httpx.AsyncClient, url: str) -> int | None:
    # 关掉压缩，否则 nginx 走分块传输，响应里没有 Content-Length
    resp = await client.head(url, headers={"Accept-Encoding": "identity"})
    if resp.status_code != 200 or "content-length" not in resp.headers:
        return None
    return int(resp.headers["content-length"])


async def download_tables_from_cos(tag: str, base_url: str) -> tuple[list[str], list[str]]:
    """只拉 TABLE_FILES 里的表，镜像上整个 TableCfg 有两百多 MB。返回 (已更新, 失败)。"""
    updated: list[str] = []
    failed: list[str] = []
    async with httpx.AsyncClient(timeout=httpx.Timeout(200.0)) as client:
        # 逐个下载：镜像并发一高就会断开连接
        for name in TABLE_FILES:
            url = f"{base_url}/BeyondUID/TableCfg/{name}"
            local = TABLE_CFG_PATH / name
            try:
                size = await _remote_size(client, url)
            except httpx.HTTPError as e:
                logger.warning(f"[beyond资源文件下载] 获取 {name} 大小失败: {e!r}")
                size = None
            if size is None:
                failed.append(name)
                continue
            if local.exists() and local.stat().st_size == size:
                continue
            if await download(url, TABLE_CFG_PATH, name, client, tag) == 200:
                updated.append(name)
            else:
                failed.append(name)
    return updated, failed

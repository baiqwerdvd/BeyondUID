from pathlib import Path

import aiofiles
from aiohttp.client import ClientSession
from aiohttp.client_exceptions import ClientConnectorError
from gsuid_core.logger import logger


async def download_file(
    url: str,
    path: Path,
    name: str,
):
    sess = ClientSession()
    try:
        async with sess.get(url) as res:
            content = await res.read()
    except ClientConnectorError:
        logger.warning(f"[BeyondUID]{name}下载失败")
        return url, path, name
    async with aiofiles.open(path / name, "wb") as f:
        await f.write(content)

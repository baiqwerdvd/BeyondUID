import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any

import aiohttp
from gsuid_core.data_store import get_res_path
from gsuid_core.logger import aiofiles, logger
from msgspec import convert

from .config import REMOTE_CONFIG_URLS, ConfigType
from .model import (
    ConfigUpdate,
    LauncherVersion,
    NetworkConfig,
    Platform,
    ResVersion,
    ServerConfig,
    UpdateCheckResult,
)

REQUEST_TIMEOUT = 30


class UpdateChecker:
    def __init__(self):
        self.session: aiohttp.ClientSession | None = None

    @asynccontextmanager
    async def get_session(self):
        if self.session is None:
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            self.session = aiohttp.ClientSession(timeout=timeout)
        try:
            yield self.session
        except Exception as e:
            logger.error(f"HTTP请求异常: {e}")
            raise

    async def fetch_config(
        self, config_type: ConfigType, platform: Platform
    ) -> dict[str, Any] | None:
        url = REMOTE_CONFIG_URLS[config_type].format(device=platform)

        try:
            async with self.get_session() as session:
                async with session.get(url) as response:
                    if response.status == 404:
                        logger.debug(f"配置未找到 {config_type} ({platform})")
                        return None

                    if response.status != 200:
                        logger.warning(
                            f"获取配置失败 {config_type} ({platform}): HTTP {response.status}"
                        )
                        return None

                    text = await response.text()
                    return json.loads(text)
        except asyncio.TimeoutError:
            logger.error(f"获取配置超时 {config_type} ({platform})")
            return None
        except Exception as e:
            logger.error(f"获取配置异常 {config_type} ({platform}): {e}")
            return None

    async def load_cached_config(
        self, config_type: ConfigType, platform: Platform
    ) -> dict[str, Any] | None:
        path = get_res_path("BeyondUID") / f"{config_type}_{platform}.json"

        if not path.exists():
            return None

        try:
            async with aiofiles.open(path, encoding="utf-8") as f:
                content = await f.read()
                return json.loads(content)
        except Exception as e:
            logger.error(f"读取缓存配置失败 {config_type} ({platform}): {e}")
            return None

    async def save_config(
        self, config_type: ConfigType, platform: Platform, data: dict[str, Any]
    ) -> bool:
        path = get_res_path("BeyondUID") / f"{config_type}_{platform}.json"

        try:
            path.parent.mkdir(parents=True, exist_ok=True)

            async with aiofiles.open(path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(data, indent=2, ensure_ascii=False))

            return True
        except Exception as e:
            logger.error(f"保存配置失败 {config_type} ({platform}): {e}")
            return False

    def parse_config_data(self, config_type: ConfigType, data: dict[str, Any]) -> Any:
        try:
            match config_type:
                case ConfigType.RES_VERSION:
                    return convert(data, ResVersion)
                case ConfigType.SERVER_CONFIG:
                    if data.get("code") == 404:
                        return ServerConfig(addr="", port=0)
                    return convert(data, ServerConfig)
                case ConfigType.LAUNCHER_VERSION:
                    return convert(data, LauncherVersion)
                case ConfigType.NETWORK_CONFIG:
                    if data.get("code") == 404:
                        return NetworkConfig(
                            asset="",
                            hgage="",
                            sdkenv="",
                            u8root="",
                            appcode=0,
                            channel="",
                            netlogid="",
                            gameclose=False,
                            netlogurl="",
                            accounturl="",
                            launcherurl="",
                        )
                    return convert(data, NetworkConfig)
                case _:
                    return convert(data, dict[str, Any])
        except Exception as e:
            logger.warning(f"解析配置数据失败 {config_type}: {e}, {data}")
            match config_type:
                case ConfigType.SERVER_CONFIG:
                    return ServerConfig(addr="", port=0)
                case _:
                    return data

    async def check_single_config(
        self, config_type: ConfigType, platform: Platform
    ) -> ConfigUpdate:
        new_data = await self.fetch_config(config_type, platform)
        if new_data is None:
            cached_data = await self.load_cached_config(config_type, platform)
            if cached_data is None:
                logger.error(f"无法获取配置 {config_type} ({platform})")
                return ConfigUpdate(old={}, new={}, updated=False)
            new_data = cached_data

        old_data = await self.load_cached_config(config_type, platform)
        if old_data is None:
            old_data = {}

        if config_type == ConfigType.NETWORK_CONFIG:
            if new_data.get("code") == 404 and old_data.get("code") == 404:
                return ConfigUpdate(old={}, new={}, updated=False)
            elif new_data.get("code") == 404:
                new_data = old_data

        parsed_old = self.parse_config_data(config_type, old_data)
        parsed_new = self.parse_config_data(config_type, new_data)

        await self.save_config(config_type, platform, new_data)

        updated = parsed_old != parsed_new

        return ConfigUpdate(old=parsed_old, new=parsed_new, updated=updated)

    async def check_platform_updates(self, platform: Platform) -> UpdateCheckResult:
        logger.debug(f"检查 {platform} 平台更新")

        tasks = [self.check_single_config(config_type, platform) for config_type in ConfigType]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        config_updates = {}
        for _, (config_type, result) in enumerate(zip(ConfigType, results)):
            if isinstance(result, Exception):
                logger.error(f"检查配置更新失败 {config_type} ({platform}): {result}")
                config_updates[config_type.value] = ConfigUpdate(old={}, new={}, updated=False)
            else:
                config_updates[config_type.value] = result

        return UpdateCheckResult(
            network_config=config_updates[ConfigType.NETWORK_CONFIG],
            game_config=config_updates[ConfigType.GAME_CONFIG],
            res_version=config_updates[ConfigType.RES_VERSION],
            server_config=config_updates[ConfigType.SERVER_CONFIG],
            launcher_version=config_updates[ConfigType.LAUNCHER_VERSION],
            platform=platform,
        )

update_checker = UpdateChecker()

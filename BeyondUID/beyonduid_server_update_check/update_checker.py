import json
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, get_args
from uuid import UUID, uuid4

import aiohttp
from gsuid_core.data_store import get_res_path
from gsuid_core.logger import aiofiles, logger
from pydantic import BaseModel, ValidationError

from .config import REMOTE_CONFIG_URLS, ConfigType
from .model import (
    ConfigUpdate,
    GameConfigWithError,
    LauncherVersion,
    LauncherVersionWithError,
    NetworkConfig,
    NetworkConfigWithError,
    Platform,
    PlatformLocalConfig,
    RemoteConfigDataWithUUID,
    RemoteConfigError,
    RemoteConfigLocalStorage,
    RemoteConfigRemoteData,
    RemoteDataItem,
    ResVersion,
    ResVersionWithError,
    ServerConfig,
    ServerConfigWithError,
    UpdateCheckResult,
)

REQUEST_TIMEOUT = 30


class UpdateChecker:
    def __init__(self):
        self.session: aiohttp.ClientSession | None = None
        self.config_file_path = get_res_path("BeyondUID") / "remote_config_storage.json"

    @asynccontextmanager
    async def get_session(self):
        if self.session is None:
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            self.session = aiohttp.ClientSession(timeout=timeout)

        yield self.session

    @staticmethod
    def _convert_to_model[T: BaseModel](
        data: dict[str, Any],
        model: type[T],
    ) -> T | RemoteConfigError:
        try:
            return RemoteConfigError.model_validate(data)
        except ValidationError:
            try:
                return model.model_validate(data)
            except ValidationError as e:
                logger.error(f"Failed to validate data with model {model.__name__}: {e}")
                return RemoteConfigError(
                    code=500,
                    reason="Validation Error",
                    message=f"Data validation failed for {model.__name__}",
                    metadata=data,
                )

    async def _fetch_single_config(
        self, url: str, config_type: ConfigType
    ) -> RemoteDataItem | None:
        try:
            async with self.get_session() as session:
                async with session.get(url) as response:
                    text = await response.text()
            data = json.loads(text)

            if config_type == ConfigType.GAME_CONFIG:
                if isinstance(data, dict) and "code" in data and "msg" in data:
                    return RemoteConfigError.model_validate(data)
                return data
            else:
                model_map = {
                    ConfigType.NETWORK_CONFIG: NetworkConfig,
                    ConfigType.RES_VERSION: ResVersion,
                    ConfigType.SERVER_CONFIG: ServerConfig,
                    ConfigType.LAUNCHER_VERSION: LauncherVersion,
                }
                model = model_map.get(config_type)
                if model:
                    return self._convert_to_model(data, model)
                else:
                    logger.error(f"Unknown config type: {config_type}")
                    return None

        except aiohttp.ClientError as e:
            logger.error(f"网络请求失败或响应错误 {config_type.value}: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败 {config_type.value}: {e}")
            return None
        except Exception as e:
            logger.error(f"获取 {config_type.value} 时发生意外错误: {e}")
            return None

    async def fetch_config(self, platform: Platform) -> RemoteConfigRemoteData | None:
        results = {}
        for config_type, url_template in REMOTE_CONFIG_URLS.items():
            url = url_template.format(device=platform.value)
            config_data = await self._fetch_single_config(url, config_type)
            if config_data is None:
                logger.error(
                    f"Failed to fetch {config_type.value} for {platform.value}. "
                    "Aborting full fetch."
                )
                return None
            results[config_type.name.lower()] = config_data

        return RemoteConfigRemoteData(
            network_config=results.get("network_config", NetworkConfig()),
            res_version=results.get("res_version", ResVersion()),
            server_config=results.get("server_config", ServerConfig()),
            launcher_version=results.get("launcher_version", LauncherVersion()),
            game_config=results.get("game_config", {}),
        )

    async def load_cached_config(self) -> RemoteConfigLocalStorage:
        if not self.config_file_path.exists():
            logger.info("缓存配置文件不存在，将创建新的空配置。")
            return RemoteConfigLocalStorage(version="1.0", platforms={})

        try:
            async with aiofiles.open(self.config_file_path, "r", encoding="utf-8") as f:
                content = await f.read()
                return RemoteConfigLocalStorage.model_validate_json(content)
        except Exception as e:
            logger.error(f"加载缓存配置失败或配置损坏: {e}.")
            return RemoteConfigLocalStorage(version="1.0", platforms={})

    async def save_config(
        self, new_remote_data: RemoteConfigRemoteData, platform: Platform
    ) -> bool:
        storage = await self.load_cached_config()
        current_time = datetime.now().isoformat()

        if platform not in storage.platforms:
            storage.platforms[platform] = PlatformLocalConfig(
                network_config=RemoteConfigDataWithUUID[NetworkConfigWithError](
                    data={}, last_updated="", last_uuid=UUID(int=0)
                ),
                res_version=RemoteConfigDataWithUUID[ResVersionWithError](
                    data={}, last_updated="", last_uuid=UUID(int=0)
                ),
                server_config=RemoteConfigDataWithUUID[ServerConfigWithError](
                    data={}, last_updated="", last_uuid=UUID(int=0)
                ),
                game_config=RemoteConfigDataWithUUID[GameConfigWithError](
                    data={}, last_updated="", last_uuid=UUID(int=0)
                ),
                launcher_version=RemoteConfigDataWithUUID[LauncherVersionWithError](
                    data={}, last_updated="", last_uuid=UUID(int=0)
                ),
            )

        def _update_config_type_storage(
            storage_data_with_uuid: RemoteConfigDataWithUUID,
            remote_data_item: RemoteDataItem,
            config_name: str,
        ) -> RemoteConfigDataWithUUID:
            last_saved_data = None
            if (
                storage_data_with_uuid.last_uuid
                and storage_data_with_uuid.last_uuid in storage_data_with_uuid.data
            ):
                last_saved_item = storage_data_with_uuid.data[storage_data_with_uuid.last_uuid]
                if isinstance(last_saved_item.data, BaseModel):
                    last_saved_data = last_saved_item.data.model_dump(mode="json")
                else:
                    last_saved_data = last_saved_item.data

            current_data_to_compare = remote_data_item
            if isinstance(current_data_to_compare, BaseModel):
                current_data_to_compare = current_data_to_compare.model_dump(mode="json")

            if last_saved_data == current_data_to_compare:
                storage_data_with_uuid.last_updated = current_time
                logger.debug(f"配置 for {platform.value} - {config_name} 未改变。")
            else:
                current_uuid = uuid4()
                storage_type = type(storage_data_with_uuid)
                model_fields = storage_type.model_fields["data"]
                value_type = get_args(model_fields.annotation)[1]
                storage_data_with_uuid = storage_type(
                    data={
                        current_uuid: value_type(data=remote_data_item, fetch_time=current_time)
                    },
                    last_updated=current_time,
                    last_uuid=current_uuid,
                )
                logger.debug(f"配置 for {platform.value} - {config_name} 已更新。")

            return storage_data_with_uuid

        storage.platforms[platform].network_config = _update_config_type_storage(
            storage.platforms[platform].network_config,
            new_remote_data.network_config,
            "network_config",
        )
        storage.platforms[platform].res_version = _update_config_type_storage(
            storage.platforms[platform].res_version,
            new_remote_data.res_version,
            "res_version",
        )
        storage.platforms[platform].server_config = _update_config_type_storage(
            storage.platforms[platform].server_config,
            new_remote_data.server_config,
            "server_config",
        )
        storage.platforms[platform].launcher_version = _update_config_type_storage(
            storage.platforms[platform].launcher_version,
            new_remote_data.launcher_version,
            "launcher_version",
        )
        storage.platforms[platform].game_config = _update_config_type_storage(
            storage.platforms[platform].game_config,
            new_remote_data.game_config,
            "game_config",
        )

        # Ensure the parent directory exists
        self.config_file_path.parent.mkdir(parents=True, exist_ok=True)
        # Dump the entire storage to JSON
        storage_json = storage.model_dump_json(indent=4)
        async with aiofiles.open(self.config_file_path, "w", encoding="utf-8") as f:
            await f.write(storage_json)

        return True

    def _get_latest_data_from_storage(
        self, storage_item: RemoteConfigDataWithUUID
    ) -> dict[str, Any]:
        if storage_item and storage_item.data and storage_item.last_uuid in storage_item.data:
            stored_config_data = storage_item.data[storage_item.last_uuid].data
            if isinstance(stored_config_data, BaseModel):
                return stored_config_data.model_dump(mode="json")
            return stored_config_data
        return {}

    def parse_config_data(
        self, data: RemoteConfigRemoteData | PlatformLocalConfig
    ) -> dict[str, Any]:
        if isinstance(data, RemoteConfigRemoteData):
            return {
                "network_config": data.network_config.model_dump(mode="json"),
                "res_version": data.res_version.model_dump(mode="json"),
                "server_config": data.server_config.model_dump(mode="json"),
                "launcher_version": data.launcher_version.model_dump(mode="json"),
                "game_config": data.game_config
                if isinstance(data.game_config, dict)
                else data.game_config.model_dump(mode="json"),
            }
        elif isinstance(data, PlatformLocalConfig):
            result = {}
            for config_type_str in [
                "network_config",
                "res_version",
                "server_config",
                "launcher_version",
                "game_config",
            ]:
                config_storage: RemoteConfigDataWithUUID = getattr(data, config_type_str)
                result[config_type_str] = self._get_latest_data_from_storage(config_storage)
            return result

    async def check_single_config(self, platform: Platform) -> ConfigUpdate:
        new_remote_data = await self.fetch_config(platform)
        if new_remote_data is None:
            logger.error(f"无法获取配置 {platform.value}")
            return ConfigUpdate(old={}, new={}, updated=False)

        old_storage = await self.load_cached_config()
        old_platform_data = old_storage.platforms.get(platform, None)
        if old_platform_data is None:
            logger.info(f"没有找到 {platform.value} 的旧配置，使用默认值。")
            old_platform_data = PlatformLocalConfig(
                network_config=RemoteConfigDataWithUUID[NetworkConfigWithError](
                    data={}, last_updated="", last_uuid=UUID(int=0)
                ),
                res_version=RemoteConfigDataWithUUID[ResVersionWithError](
                    data={}, last_updated="", last_uuid=UUID(int=0)
                ),
                server_config=RemoteConfigDataWithUUID[ServerConfigWithError](
                    data={}, last_updated="", last_uuid=UUID(int=0)
                ),
                game_config=RemoteConfigDataWithUUID[GameConfigWithError](
                    data={}, last_updated="", last_uuid=UUID(int=0)
                ),
                launcher_version=RemoteConfigDataWithUUID[LauncherVersionWithError](
                    data={}, last_updated="", last_uuid=UUID(int=0)
                ),
            )
        old_platform_data = self.parse_config_data(old_platform_data)

        parsed_new = self.parse_config_data(new_remote_data)
        new_platform_data = {
            "network_config": parsed_new["network_config"],
            "res_version": parsed_new["res_version"],
            "server_config": parsed_new["server_config"],
            "launcher_version": parsed_new["launcher_version"],
            "game_config": parsed_new["game_config"],
        }

        updated = old_platform_data != new_platform_data

        await self.save_config(new_remote_data, platform)

        return ConfigUpdate(old=old_platform_data, new=new_platform_data, updated=updated)

    async def check_platform_updates(self, platform: Platform) -> UpdateCheckResult:
        logger.debug(f"检查 {platform.value} 平台更新")

        result = await self.check_single_config(platform)

        network_config_update = ConfigUpdate(
            old=result.old.get("network_config", {}),
            new=result.new.get("network_config", {}),
            updated=result.old.get("network_config", {}) != result.new.get("network_config", {}),
        )

        game_config_update = ConfigUpdate(
            old=result.old.get("game_config", {}),
            new=result.new.get("game_config", {}),
            updated=result.old.get("game_config", {}) != result.new.get("game_config", {}),
        )

        res_version_update = ConfigUpdate(
            old=result.old.get("res_version", {}),
            new=result.new.get("res_version", {}),
            updated=result.old.get("res_version", {}) != result.new.get("res_version", {}),
        )

        server_config_update = ConfigUpdate(
            old=result.old.get("server_config", {}),
            new=result.new.get("server_config", {}),
            updated=result.old.get("server_config", {}) != result.new.get("server_config", {}),
        )

        launcher_version_update = ConfigUpdate(
            old=result.old.get("launcher_version", {}),
            new=result.new.get("launcher_version", {}),
            updated=result.old.get("launcher_version", {})
            != result.new.get("launcher_version", {}),
        )

        return UpdateCheckResult(
            network_config=network_config_update,
            game_config=game_config_update,
            res_version=res_version_update,
            server_config=server_config_update,
            launcher_version=launcher_version_update,
            platform=platform,
        )


update_checker = UpdateChecker()

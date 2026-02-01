import json
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, TypeVar, get_args
from uuid import UUID, uuid4

import aiohttp
from gsuid_core.data_store import get_res_path
from gsuid_core.logger import aiofiles, logger
from pydantic import BaseModel, ValidationError

from .config import (
    ENCRYPTED_CONFIG_TYPES,
    REMOTE_CONFIG_URLS,
    ConfigType,
)
from .model import (
    ConfigUpdate,
    EngineConfig,
    FetchParams,
    LauncherVersion,
    NetworkConfig,
    Platform,
    PlatformLocalConfig,
    RemoteConfigDataWithUUID,
    RemoteConfigLocalStorage,
    RemoteConfigRemoteData,
    ResVersion,
    U8Config,
    UpdateCheckResult,
)
from .utils import RemoteConfigUtils, U8ConfigUtils, normalize_data_for_comparison

REQUEST_TIMEOUT = 30
T = TypeVar("T", bound=BaseModel)


class UpdateChecker:
    def __init__(self):
        self.session: aiohttp.ClientSession | None = None
        self.config_file_path = get_res_path("BeyondUID") / "remote_config_storage_v2.json"
        self._shared_rand_str: str | None = None  # 从 Windows 平台获取，共享给所有平台

    @asynccontextmanager
    async def get_session(self):
        if self.session is None:
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            self.session = aiohttp.ClientSession(timeout=timeout)

        yield self.session

    @staticmethod
    def _convert_to_model(data: dict[str, Any], model: type[T]) -> T | None:
        try:
            return model.model_validate(data)
        except ValidationError as e:
            logger.error(f"Failed to validate data with model {model.__name__}: {e}")
            return None

    @staticmethod
    def _build_url(
        url_template: str,
        platform: Platform,
        fetch_params: FetchParams | None = None,
    ) -> str:
        if fetch_params:
            return url_template.format(
                device=platform.value,
                version=fetch_params.version,
                rand_str=fetch_params.rand_str,
            )
        return url_template.format(device=platform.value)

    async def _fetch_and_decrypt_u8_config(self, file_path_url: str) -> U8Config | None:
        try:
            target_url = file_path_url + "/U8Data/config/u8ExtraConfig.bin"
            async with self.get_session() as session:
                async with session.get(target_url) as response:
                    if response.status != 200:
                        logger.warning(
                            f"Failed to fetch U8 config from {target_url}: status {response.status}"
                        )
                        return None
                    encrypted_bytes = await response.read()

            decrypted_bytes = U8ConfigUtils.decrypt_bin(encrypted_bytes)

            decrypted_text = decrypted_bytes.decode("utf-8")
            data = json.loads(decrypted_text)
            return self._convert_to_model(data, U8Config)

        except aiohttp.ClientError as e:
            logger.warning(f"Network error fetching U8 config: {e}")
            return None
        except Exception as e:
            logger.warning(f"Failed to decrypt U8 config: {e}")
            return None

    async def _ensure_shared_rand_str(self) -> str | None:
        if self._shared_rand_str:
            return self._shared_rand_str

        win_url = self._build_url(REMOTE_CONFIG_URLS[ConfigType.LAUNCHER_VERSION], Platform.WINDOWS)
        win_launcher = await self._fetch_single_config(win_url, ConfigType.LAUNCHER_VERSION)

        if isinstance(win_launcher, LauncherVersion):
            if win_launcher.pkg and win_launcher.pkg.file_path:
                u8_config = await self._fetch_and_decrypt_u8_config(win_launcher.pkg.file_path)
                if u8_config and u8_config.randStr:
                    self._shared_rand_str = u8_config.randStr
                    rand_preview = self._shared_rand_str[:8]
                    logger.trace(f"Cached shared randStr from Windows: {rand_preview}")
                    return self._shared_rand_str

        logger.warning("Failed to get shared randStr from Windows platform")
        return None

    async def _extract_fetch_params(
        self, launcher_version: LauncherVersion, platform: Platform
    ) -> FetchParams | None:
        version = launcher_version.version
        rand_str = ""

        if platform == Platform.WINDOWS:
            if launcher_version.pkg and launcher_version.pkg.file_path:
                file_path = launcher_version.pkg.file_path
                u8_config = await self._fetch_and_decrypt_u8_config(file_path)
                if u8_config and u8_config.randStr:
                    rand_str = u8_config.randStr
                    self._shared_rand_str = rand_str  # 同时缓存为共享值
                    logger.trace(f"Extracted randStr from U8 config: {rand_str[:8]}...")
        else:
            shared = await self._ensure_shared_rand_str()
            if shared:
                rand_str = shared
                logger.trace(f"Using shared randStr for {platform.value}: {rand_str[:8]}...")

        if version and rand_str:
            return FetchParams(version=version, rand_str=rand_str)

        # default 平台不支持 version 获取，使用 debug 级别日志
        if platform == Platform.DEFAULT:
            logger.trace(f"Platform {platform.value} does not support version fetch")
        else:
            rand_str_preview = rand_str[:8] if rand_str else ""
            logger.warning(
                f"Failed to extract FetchParams for {platform.value}: "
                f"version={version}, rand_str={rand_str_preview}"
            )
        return None

    async def _fetch_single_config(self, url: str, config_type: ConfigType) -> Any | None:
        try:
            async with self.get_session() as session:
                async with session.get(url) as response:
                    text = await response.text()

            if config_type in ENCRYPTED_CONFIG_TYPES:
                try:
                    data = json.loads(text)
                    logger.trace(f"{config_type.value} is plain JSON, skipping decryption")
                except json.JSONDecodeError:
                    try:
                        decrypted_text = RemoteConfigUtils.get_text(text)
                        data = json.loads(decrypted_text)
                    except Exception as e:
                        logger.warning(f"Failed to decrypt {config_type.value}: {e}")
                        logger.debug(f"Response content (first 100 chars): {text[:100]}")
                        return None
            else:
                data = json.loads(text)

            model_map = {
                ConfigType.NETWORK_CONFIG: NetworkConfig,
                ConfigType.ENGINE_CONFIG: EngineConfig,
                ConfigType.RES_VERSION: ResVersion,
                ConfigType.LAUNCHER_VERSION: LauncherVersion,
            }

            model = model_map.get(config_type)
            if model:
                result = self._convert_to_model(data, model)
                if result is None:
                    logger.warning(f"Model validation failed for {config_type.value}, using raw data")
                    return data
                return result
            elif config_type == ConfigType.GAME_CONFIG:
                return data
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

    async def fetch_all_configs(self, platform: Platform) -> RemoteConfigRemoteData | None:
        results: dict[str, Any] = {}

        launcher_url = self._build_url(REMOTE_CONFIG_URLS[ConfigType.LAUNCHER_VERSION], platform)
        launcher_data = await self._fetch_single_config(launcher_url, ConfigType.LAUNCHER_VERSION)
        if launcher_data is None:
            logger.error(f"Failed to fetch LAUNCHER_VERSION for {platform.value}. Aborting full fetch.")
            return None
        results["launcher_version"] = launcher_data

        fetch_params: FetchParams | None = None
        if isinstance(launcher_data, LauncherVersion):
            fetch_params = await self._extract_fetch_params(launcher_data, platform)
            if fetch_params:
                logger.trace(
                    f"Extracted FetchParams for {platform.value}: "
                    f"version={fetch_params.version}, rand_str={fetch_params.rand_str[:8]}..."
                )

        independent_configs = [
            ConfigType.ENGINE_CONFIG,
            ConfigType.NETWORK_CONFIG,
            ConfigType.GAME_CONFIG,
        ]
        for config_type in independent_configs:
            url = self._build_url(REMOTE_CONFIG_URLS[config_type], platform)
            config_data = await self._fetch_single_config(url, config_type)
            if config_data is None:
                logger.error(
                    f"Failed to fetch {config_type.value} for {platform.value}. Aborting full fetch."
                )
                return None
            results[config_type.name.lower()] = config_data

        if fetch_params:
            res_version_url = self._build_url(
                REMOTE_CONFIG_URLS[ConfigType.RES_VERSION], platform, fetch_params
            )
            res_version_data = await self._fetch_single_config(res_version_url, ConfigType.RES_VERSION)
            if res_version_data is None:
                logger.error(f"Failed to fetch RES_VERSION for {platform.value}. Aborting full fetch.")
                return None
            results["res_version"] = res_version_data
        else:
            if platform == Platform.DEFAULT:
                logger.trace(f"Platform {platform.value} uses default RES_VERSION")
            else:
                logger.warning(
                    f"No FetchParams available for {platform.value}, "
                    "RES_VERSION will use default empty value."
                )
            results["res_version"] = ResVersion()

        return RemoteConfigRemoteData(
            network_config=results.get("network_config", NetworkConfig()),
            res_version=results.get("res_version", ResVersion()),
            engine_config=results.get("engine_config", EngineConfig()),
            launcher_version=results.get("launcher_version", LauncherVersion()),
            game_config=results.get("game_config", {}),
        )

    async def load_cached_config(self) -> RemoteConfigLocalStorage:
        if not self.config_file_path.exists():
            logger.info("缓存配置文件不存在，将创建新的空配置。")
            return RemoteConfigLocalStorage(version="2.0", platforms={})

        try:
            async with aiofiles.open(self.config_file_path, "r", encoding="utf-8") as f:
                content = await f.read()
                return RemoteConfigLocalStorage.model_validate_json(content)
        except Exception as e:
            logger.error(f"加载缓存配置失败或配置损坏: {e}.")
            return RemoteConfigLocalStorage(version="2.0", platforms={})

    def _create_empty_platform_config(self) -> PlatformLocalConfig:
        return PlatformLocalConfig(
            network_config=RemoteConfigDataWithUUID[NetworkConfig](
                data={}, last_updated="", last_uuid=UUID(int=0)
            ),
            res_version=RemoteConfigDataWithUUID[ResVersion](
                data={}, last_updated="", last_uuid=UUID(int=0)
            ),
            engine_config=RemoteConfigDataWithUUID[EngineConfig](
                data={}, last_updated="", last_uuid=UUID(int=0)
            ),
            game_config=RemoteConfigDataWithUUID[dict[str, Any]](
                data={}, last_updated="", last_uuid=UUID(int=0)
            ),
            launcher_version=RemoteConfigDataWithUUID[LauncherVersion](
                data={}, last_updated="", last_uuid=UUID(int=0)
            ),
        )

    async def save_config(self, new_remote_data: RemoteConfigRemoteData, platform: Platform) -> bool:
        storage = await self.load_cached_config()
        current_time = datetime.now().isoformat()

        if platform not in storage.platforms:
            storage.platforms[platform] = self._create_empty_platform_config()

        def _update_config_type_storage(
            storage_data_with_uuid: RemoteConfigDataWithUUID,
            remote_data_item: Any,
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

            if normalize_data_for_comparison(last_saved_data) == normalize_data_for_comparison(
                current_data_to_compare
            ):
                storage_data_with_uuid.last_updated = current_time
                logger.trace(f"配置 for {platform.value} - {config_name} 未改变。")
            else:
                current_uuid = uuid4()
                storage_type = type(storage_data_with_uuid)
                model_fields = storage_type.model_fields["data"]
                value_type = get_args(model_fields.annotation)[1]

                new_data = dict(storage_data_with_uuid.data)
                new_data[current_uuid] = value_type(data=remote_data_item, fetch_time=current_time)

                storage_data_with_uuid = storage_type(
                    data=new_data,
                    last_updated=current_time,
                    last_uuid=current_uuid,
                )
                logger.trace(f"配置 for {platform.value} - {config_name} 已更新。")

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
        storage.platforms[platform].engine_config = _update_config_type_storage(
            storage.platforms[platform].engine_config,
            new_remote_data.engine_config,
            "engine_config",
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

        self.config_file_path.parent.mkdir(parents=True, exist_ok=True)
        storage_json = storage.model_dump_json(indent=4)
        async with aiofiles.open(self.config_file_path, "w", encoding="utf-8") as f:
            await f.write(storage_json)

        return True

    def _get_latest_data_from_storage(self, storage_item: RemoteConfigDataWithUUID) -> dict[str, Any]:
        if storage_item and storage_item.data and storage_item.last_uuid in storage_item.data:
            stored_config_data = storage_item.data[storage_item.last_uuid].data
            if isinstance(stored_config_data, BaseModel):
                return stored_config_data.model_dump(mode="json")
            return stored_config_data
        return {}

    def parse_config_data(self, data: RemoteConfigRemoteData | PlatformLocalConfig) -> dict[str, Any]:
        if isinstance(data, RemoteConfigRemoteData):
            return {
                "network_config": data.network_config.model_dump(mode="json"),
                "res_version": data.res_version.model_dump(mode="json"),
                "engine_config": data.engine_config.model_dump(mode="json"),
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
                "engine_config",
                "launcher_version",
                "game_config",
            ]:
                config_storage: RemoteConfigDataWithUUID = getattr(data, config_type_str)
                result[config_type_str] = self._get_latest_data_from_storage(config_storage)
            return result

    async def check_single_config(self, platform: Platform) -> tuple[ConfigUpdate, bool]:
        new_remote_data = await self.fetch_all_configs(platform)
        if new_remote_data is None:
            logger.error(f"无法获取配置 {platform.value}")
            return ConfigUpdate(old={}, new={}, updated=False), False

        old_storage = await self.load_cached_config()
        old_platform_data = old_storage.platforms.get(platform, None)
        is_first_init = old_platform_data is None  # 记录是否为首次初始化

        if old_platform_data is None:
            logger.info(f"没有找到 {platform.value} 的旧配置，这是首次初始化。")
            old_platform_data = self._create_empty_platform_config()
        old_platform_data = self.parse_config_data(old_platform_data)

        parsed_new = self.parse_config_data(new_remote_data)
        new_platform_data = {
            "network_config": parsed_new["network_config"],
            "res_version": parsed_new["res_version"],
            "engine_config": parsed_new["engine_config"],
            "launcher_version": parsed_new["launcher_version"],
            "game_config": parsed_new["game_config"],
        }

        updated = normalize_data_for_comparison(old_platform_data) != normalize_data_for_comparison(
            new_platform_data
        )

        await self.save_config(new_remote_data, platform)

        return (
            ConfigUpdate(old=old_platform_data, new=new_platform_data, updated=updated),
            is_first_init,
        )

    @staticmethod
    def _create_config_update(
        result: ConfigUpdate,
        config_key: str,
    ) -> ConfigUpdate:
        old_data = result.old.get(config_key, {})
        new_data = result.new.get(config_key, {})
        return ConfigUpdate(
            old=old_data,
            new=new_data,
            updated=normalize_data_for_comparison(old_data) != normalize_data_for_comparison(new_data),
        )

    async def check_platform_updates(self, platform: Platform) -> UpdateCheckResult:
        logger.trace(f"检查 {platform.value} 平台更新")

        result, is_first_init = await self.check_single_config(platform)

        config_keys = [
            "network_config",
            "game_config",
            "res_version",
            "engine_config",
            "launcher_version",
        ]
        config_updates = {key: self._create_config_update(result, key) for key in config_keys}

        return UpdateCheckResult(
            network_config=config_updates["network_config"],
            game_config=config_updates["game_config"],
            res_version=config_updates["res_version"],
            engine_config=config_updates["engine_config"],
            launcher_version=config_updates["launcher_version"],
            platform=platform,
            is_first_init=is_first_init,
        )


update_checker = UpdateChecker()

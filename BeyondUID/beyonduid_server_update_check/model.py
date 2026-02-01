from enum import Enum
from typing import Any, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field

T = TypeVar("T")


class Platform(Enum):
    DEFAULT = "default"
    WINDOWS = "Windows"
    ANDROID = "Android"
    IOS = "iOS"
    PLAYSTATION = "PlayStation"


class FetchParams(BaseModel):
    version: str
    rand_str: str


class U8Config(BaseModel):
    envName: str
    launcherUrl: str
    appCode: str
    appType: str
    appId: str
    u8Root: str
    ageTips: str
    randStr: str


class EngineConfigParam(BaseModel):
    Platform: str
    Processor: str | None
    DeviceModel: str | None
    SOCModel: str | None
    OSVersionMin: int | None
    OSVersionMax: int | None
    Params: dict[str, str]


class EngineConfig(BaseModel):
    CL: int = 0
    Configs: str = ""  # JSON string containing config details
    Version: int = 0

    def get_parsed_configs(self) -> dict[str, EngineConfigParam]:
        import json

        try:
            configs_dict = json.loads(self.Configs)
            return {key: EngineConfigParam.model_validate(value) for key, value in configs_dict.items()}
        except (json.JSONDecodeError, ValueError):
            return {}


class NetworkConfig(BaseModel):
    hgage: str = ""
    hggov: str = ""
    u8root: str = ""
    gameclose: bool = False
    netlogurl: str = ""
    launcherurl: str = ""


class ResVersionItem(BaseModel):
    url: str
    md5: str
    package_size: str


class ResourcePkg(BaseModel):
    packs: list[ResVersionItem]
    total_size: str
    file_path: str
    url: str
    md5: str
    package_size: str
    file_id: str
    sub_channel: str
    game_files_md5: str


class ResourceItem(BaseModel):
    name: str  # "main" or "initial"
    version: str  # e.g., "5310633-12"
    path: str  # resource download path


class ResVersionConfigs(BaseModel):
    kick_flag: bool = False


class ResVersion(BaseModel):
    resources: list[ResourceItem] = Field(default_factory=list)
    configs: str = ""  # JSON string containing kick_flag
    res_version: str = ""  # e.g., "initial_5310633-12_main_5310633-12"
    patch_index_path: str = ""
    domain: str = ""

    def get_parsed_configs(self) -> ResVersionConfigs:
        """Parse the configs JSON string into structured data"""
        import json

        try:
            data = json.loads(self.configs)
            return ResVersionConfigs.model_validate(data)
        except (json.JSONDecodeError, ValueError):
            return ResVersionConfigs()


class LauncherVersion(BaseModel):
    action: int = 0
    version: str = ""
    request_version: str = ""
    pkg: ResourcePkg | None = None
    patch: dict[str, Any] | None = None
    state: int = 0
    launcher_action: int = 0


class ConfigUpdate(BaseModel):
    old: dict[str, Any]
    new: dict[str, Any]
    updated: bool = False


class UpdateCheckResult(BaseModel):
    network_config: ConfigUpdate
    game_config: ConfigUpdate
    res_version: ConfigUpdate
    engine_config: ConfigUpdate
    launcher_version: ConfigUpdate
    platform: Platform
    is_first_init: bool = False  # 标识是否为首次初始化


class RemoteConfigError(BaseModel):
    code: int = 0
    reason: str = ""
    message: str = ""


class RemoteConfigData(BaseModel, Generic[T]):
    data: T
    fetch_time: str


class RemoteConfigDataWithUUID(BaseModel, Generic[T]):
    data: dict[UUID, RemoteConfigData[T]] = Field(default_factory=dict)
    last_updated: str
    last_uuid: UUID


class PlatformLocalConfig(BaseModel):
    network_config: RemoteConfigDataWithUUID[NetworkConfig]
    res_version: RemoteConfigDataWithUUID[ResVersion]
    engine_config: RemoteConfigDataWithUUID[EngineConfig]
    game_config: RemoteConfigDataWithUUID[dict[str, Any]]
    launcher_version: RemoteConfigDataWithUUID[LauncherVersion]


class RemoteConfigLocalStorage(BaseModel):
    version: str

    platforms: dict[Platform, PlatformLocalConfig]


class RemoteConfigRemoteData(BaseModel):
    network_config: NetworkConfig
    res_version: ResVersion
    engine_config: EngineConfig
    game_config: dict[str, Any]
    launcher_version: LauncherVersion

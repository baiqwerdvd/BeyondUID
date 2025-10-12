from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class Platform(StrEnum):
    DEFAULT = "default"
    WINDOWS = "Windows"
    ANDROID = "Android"
    PLAYSTATION = "PlayStation"


class NetworkConfig(BaseModel):
    asset: str = ""
    hgage: str = ""
    sdkenv: str = ""
    u8root: str = ""
    appcode: int = 0
    channel: str = ""
    netlogid: str = ""
    gameclose: bool = False
    netlogurl: str = ""
    accounturl: str = ""
    launcherurl: str = ""


class ResVersion(BaseModel):
    version: str = ""
    kickFlag: bool = False


class ServerConfig(BaseModel):
    addr: str = ""
    port: int = 0


class LauncherVersion(BaseModel):
    action: int = 0
    version: str = ""
    request_version: str = ""
    pkg: dict[str, Any] | None = None
    patch: dict[str, Any] | None = None


class ConfigUpdate(BaseModel):
    old: dict[str, Any]
    new: dict[str, Any]
    updated: bool = False


class UpdateCheckResult(BaseModel):
    network_config: ConfigUpdate
    game_config: ConfigUpdate
    res_version: ConfigUpdate
    server_config: ConfigUpdate
    launcher_version: ConfigUpdate
    platform: Platform


class RemoteConfigError(BaseModel):
    code: int
    reason: str
    message: str
    metadata: dict[str, Any]


type RemoteDataItem = BaseModel | RemoteConfigError | dict[str, Any]
type NetworkConfigWithError = NetworkConfig | RemoteConfigError
type ResVersionWithError = ResVersion | RemoteConfigError
type ServerConfigWithError = ServerConfig | RemoteConfigError
type GameConfigWithError = dict[str, Any] | RemoteConfigError
type LauncherVersionWithError = LauncherVersion | RemoteConfigError


class RemoteConfigData[T](BaseModel):
    data: T
    fetch_time: str


class RemoteConfigDataWithUUID[T](BaseModel):
    data: dict[UUID, RemoteConfigData[T]] = Field(default_factory=dict)
    last_updated: str
    last_uuid: UUID


class PlatformLocalConfig(BaseModel):
    network_config: RemoteConfigDataWithUUID[NetworkConfig | RemoteConfigError]
    res_version: RemoteConfigDataWithUUID[ResVersion | RemoteConfigError]
    server_config: RemoteConfigDataWithUUID[ServerConfig | RemoteConfigError]
    game_config: RemoteConfigDataWithUUID[dict[str, Any] | RemoteConfigError]
    launcher_version: RemoteConfigDataWithUUID[LauncherVersion | RemoteConfigError]


class RemoteConfigLocalStorage(BaseModel):
    version: str

    platforms: dict[Platform, PlatformLocalConfig]


class RemoteConfigRemoteData(BaseModel):
    network_config: NetworkConfig | RemoteConfigError
    res_version: ResVersion | RemoteConfigError
    server_config: ServerConfig | RemoteConfigError
    game_config: dict[str, Any] | RemoteConfigError
    launcher_version: LauncherVersion | RemoteConfigError

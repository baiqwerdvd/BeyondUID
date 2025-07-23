from enum import StrEnum
from typing import Any

from msgspec import Struct


class Platform(StrEnum):
    DEFAULT = "default"
    ANDROID = "android"


class NetworkConfig(Struct):
    asset: str
    hgage: str
    sdkenv: str
    u8root: str
    appcode: int
    channel: str
    netlogid: str
    gameclose: bool
    netlogurl: str
    accounturl: str
    launcherurl: str


class ResVersion(Struct):
    version: str
    kickFlag: bool


class ServerConfig(Struct):
    addr: str
    port: int


class LauncherVersion(Struct):
    action: int
    version: str
    request_version: str
    pkg: dict[str, Any] | None = None
    patch: dict[str, Any] | None = None


class ConfigUpdate(Struct):
    old: Any
    new: Any
    updated: bool = False


class UpdateCheckResult(Struct):
    network_config: ConfigUpdate
    game_config: ConfigUpdate
    res_version: ConfigUpdate
    server_config: ConfigUpdate
    launcher_version: ConfigUpdate
    platform: Platform

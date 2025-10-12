from enum import StrEnum
from typing import ClassVar


class UpdatePriority(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class UpdateConfig:
    PRIORITY_MAP: ClassVar[dict[str, UpdatePriority]] = {
        "launcher_version": UpdatePriority.LOW,
        "res_version": UpdatePriority.CRITICAL,
        "server_config": UpdatePriority.MEDIUM,
        "game_config": UpdatePriority.MEDIUM,
        "network_config": UpdatePriority.HIGH,
    }

    PRIORITY_ICONS: ClassVar[dict[UpdatePriority, str]] = {
        UpdatePriority.CRITICAL: "🚨",
        UpdatePriority.HIGH: "⚡",
        UpdatePriority.MEDIUM: "📢",
        UpdatePriority.LOW: "ℹ️",
    }

    priority_order: ClassVar[list[UpdatePriority]] = [
        UpdatePriority.CRITICAL,
        UpdatePriority.HIGH,
        UpdatePriority.MEDIUM,
        UpdatePriority.LOW,
    ]

    @classmethod
    def get_priority(cls, update_type: str) -> UpdatePriority:
        return cls.PRIORITY_MAP.get(update_type, UpdatePriority.LOW)

    @classmethod
    def get_icon(cls, priority: UpdatePriority) -> str:
        return cls.PRIORITY_ICONS.get(priority, "📝")


class ConfigType(StrEnum):
    NETWORK_CONFIG = "network_config"
    GAME_CONFIG = "game_config"
    RES_VERSION = "res_version"
    SERVER_CONFIG = "server_config"
    LAUNCHER_VERSION = "launcher_version"


REMOTE_CONFIG_URLS = {
    ConfigType.NETWORK_CONFIG: "https://game-config.hypergryph.com/api/remote_config/get_remote_config/3/prod-cbt3/default/{device}/network_config",
    ConfigType.GAME_CONFIG: "https://game-config.hypergryph.com/api/remote_config/get_remote_config/3/prod-cbt3/default/{device}/game_config",
    ConfigType.RES_VERSION: "https://game-config.hypergryph.com/api/remote_config/get_remote_config/3/prod-cbt3/default/{device}/res_version",
    ConfigType.SERVER_CONFIG: "https://game-config.hypergryph.com/api/remote_config/get_remote_config/3/prod-cbt3/default/{device}/server_config_China",
    ConfigType.LAUNCHER_VERSION: "https://launcher.hypergryph.com/api/game/get_latest?appcode=CAdYGoQmEUZnxXGf&channel=1",
}

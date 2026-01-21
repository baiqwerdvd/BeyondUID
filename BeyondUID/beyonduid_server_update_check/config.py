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
        "engine_config": UpdatePriority.LOW,
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
    ENGINE_CONFIG = "engine_config"
    LAUNCHER_VERSION = "launcher_version"


REMOTE_CONFIG_URLS = {
    ConfigType.ENGINE_CONFIG: "https://game-config.hypergryph.com/api/remote_config/3/prod-engine/default/{device}/engine_config",
    ConfigType.NETWORK_CONFIG: "https://game-config.hypergryph.com/api/remote_config/v2/3/prod-obt/default/{device}/network_config",
    ConfigType.GAME_CONFIG: "https://game-config.hypergryph.com/api/remote_config/v2/3/prod-obt/default/{device}/game_config",
    ConfigType.LAUNCHER_VERSION: "https://launcher.hypergryph.com/api/game/get_latest?appcode=6LL0KJuqHBVz33WK&channel=1&platform={device}&sub_channel=1&source=game",
    ConfigType.RES_VERSION: "https://launcher.hypergryph.com/api/game/get_latest_resources?appcode=6LL0KJuqHBVz33WK&platform={device}&game_version=1.0&version={version}&rand_str={rand_str}",
}

ENCRYPTED_CONFIG_TYPES = {ConfigType.NETWORK_CONFIG, ConfigType.GAME_CONFIG}

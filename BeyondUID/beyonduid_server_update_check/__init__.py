import asyncio
import json
import random
from contextlib import asynccontextmanager
from enum import StrEnum
from typing import Any, ClassVar, cast

import aiofiles
import aiohttp
from gsuid_core.aps import scheduler
from gsuid_core.bot import Bot
from gsuid_core.data_store import get_res_path
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.subscribe import gs_subscribe
from gsuid_core.sv import SV
from msgspec import Struct, convert

from ..beyonduid_config import PREFIX

sv_server_check = SV("终末地版本更新")
sv_server_check_sub = SV("订阅终末地版本更新", pm=3)

TASK_NAME_SERVER_CHECK = "订阅终末地版本更新"
CHECK_INTERVAL_SECONDS = 10
REQUEST_TIMEOUT = 30


class UpdatePriority(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Platform(StrEnum):
    DEFAULT = "default"
    ANDROID = "Android"


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

    @classmethod
    def get_priority(cls, update_type: str) -> UpdatePriority:
        return cls.PRIORITY_MAP.get(update_type, UpdatePriority.LOW)

    @classmethod
    def get_icon(cls, priority: UpdatePriority) -> str:
        return cls.PRIORITY_ICONS.get(priority, "📝")

    DEFAULT = "default"
    ANDROID = "Android"
    WINDOWS = "Windows"


class ConfigType(StrEnum):
    NETWORK_CONFIG = "network_config"
    GAME_CONFIG = "game_config"
    RES_VERSION = "res_version"
    SERVER_CONFIG = "server_config"
    LAUNCHER_VERSION = "launcher_version"


REMOTE_CONFIG_URLS = {
    ConfigType.NETWORK_CONFIG: "https://game-config.hypergryph.com/api/remote_config/get_remote_config/3/prod-cbt/default/{device}/network_config",
    ConfigType.GAME_CONFIG: "https://game-config.hypergryph.com/api/remote_config/get_remote_config/3/prod-cbt/default/{device}/game_config",
    ConfigType.RES_VERSION: "https://game-config.hypergryph.com/api/remote_config/get_remote_config/3/prod-cbt/default/{device}/res_version",
    ConfigType.SERVER_CONFIG: "https://game-config.hypergryph.com/api/remote_config/get_remote_config/3/prod-cbt/default/{device}/server_config_China",
    ConfigType.LAUNCHER_VERSION: "https://launcher.hypergryph.com/api/game/get_latest?appcode=CAdYGoQmEUZnxXGf&channel=1",
}


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
    platform: str


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

    async def close(self):
        if self.session:
            await self.session.close()
            self.session = None

    async def fetch_config(self, config_type: ConfigType, platform: str) -> dict[str, Any] | None:
        url = REMOTE_CONFIG_URLS[config_type].format(device=platform)

        try:
            async with self.get_session() as session:
                async with session.get(url) as response:
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
        self, config_type: ConfigType, platform: str
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
        self, config_type: ConfigType, platform: str, data: dict[str, Any]
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

    async def check_single_config(self, config_type: ConfigType, platform: str) -> ConfigUpdate:
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

    async def check_platform_updates(self, platform: str) -> UpdateCheckResult:
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


class NotificationManager:
    @staticmethod
    def has_any_update(result: UpdateCheckResult) -> bool:
        return any(
            [
                result.network_config.updated,
                result.game_config.updated,
                result.res_version.updated,
                result.server_config.updated,
                result.launcher_version.updated,
            ]
        )

    @staticmethod
    def format_dict_changes(old_dict: dict[str, Any], new_dict: dict[str, Any]) -> str:
        update_keys = set()
        delete_keys = set()
        new_keys = set()

        for key, value in new_dict.items():
            if key not in old_dict:
                new_keys.add(key)
            elif value != old_dict[key]:
                update_keys.add(key)

        for key in old_dict:
            if key not in new_dict:
                delete_keys.add(key)

        messages = []

        if update_keys:
            updates = [
                f"{key}: {old_dict.get(key)} -> {new_dict.get(key)}" for key in update_keys
            ]
            messages.append("Updated:\n" + "\n".join(updates))

        if new_keys:
            new_items = [f"{key}: {new_dict.get(key)}" for key in new_keys]
            messages.append("New:\n" + "\n".join(new_items))

        if delete_keys:
            deleted_items = [f"{key}: {old_dict.get(key)}" for key in delete_keys]
            messages.append("Deleted:\n" + "\n".join(deleted_items))

        return "\n\n".join(messages) if messages else "配置已更新"

    @staticmethod
    def build_update_message(result: UpdateCheckResult) -> str:
        platform_name = "Windows端" if result.platform == "default" else f"{result.platform}端"

        updates = []

        if result.launcher_version.updated:
            updates.append(
                {
                    "type": "launcher_version",
                    "priority": UpdateConfig.get_priority("launcher_version"),
                    "title": "客户端版本更新",
                    "content": f"版本: {result.launcher_version.old.version} → {result.launcher_version.new.version}",
                }
            )

        if result.res_version.updated:
            content = f"版本: {result.res_version.old.version} → {result.res_version.new.version}"
            if result.res_version.new.kickFlag != result.res_version.old.kickFlag:
                content += f"\nkickFlag: {result.res_version.old.kickFlag} → {result.res_version.new.kickFlag}"

            updates.append(
                {
                    "type": "res_version",
                    "priority": UpdateConfig.get_priority("res_version"),
                    "title": "资源版本更新",
                    "content": content,
                }
            )

        if result.server_config.updated:
            updates.append(
                {
                    "type": "server_config",
                    "priority": UpdateConfig.get_priority("server_config"),
                    "title": "服务器配置更新",
                    "content": f"地址: {result.server_config.old.addr} → {result.server_config.new.addr}\n端口: {result.server_config.old.port} → {result.server_config.new.port}",
                }
            )

        if result.game_config.updated:
            changes = NotificationManager.format_dict_changes(
                result.game_config.old, result.game_config.new
            )
            updates.append(
                {
                    "type": "game_config",
                    "priority": UpdateConfig.get_priority("game_config"),
                    "title": "游戏配置更新",
                    "content": changes,
                }
            )

        if result.network_config.updated:
            changes = NotificationManager.format_dict_changes(
                result.network_config.old, result.network_config.new
            )
            updates.append(
                {
                    "type": "network_config",
                    "priority": UpdateConfig.get_priority("network_config"),
                    "title": "网络配置更新",
                    "content": changes,
                }
            )

        if not updates:
            return ""

        priority_order = [
            UpdatePriority.CRITICAL,
            UpdatePriority.HIGH,
            UpdatePriority.MEDIUM,
            UpdatePriority.LOW,
        ]
        updates.sort(key=lambda x: priority_order.index(x["priority"]))

        messages = []
        for update in updates:
            icon = UpdateConfig.get_icon(update["priority"])
            messages.append(f"{icon} {update['title']}\n{update['content']}")

        highest_priority = updates[0]["priority"]
        header_icon = UpdateConfig.get_icon(highest_priority)

        header = f"{header_icon} 检测到{platform_name}终末地更新"
        content = "\n\n".join(messages)
        full_message = f"{header}\n\n{content}"

        return full_message

    @staticmethod
    async def send_update_notifications(result: UpdateCheckResult):
        datas = await gs_subscribe.get_subscribe(TASK_NAME_SERVER_CHECK)
        if not datas:
            logger.info("[终末地版本更新] 暂无群订阅")
            return

        message = NotificationManager.build_update_message(result)
        if not message:
            return

        update_types = []
        if result.launcher_version.updated:
            update_types.append("客户端版本")
        if result.res_version.updated:
            update_types.append("资源版本")
        if result.server_config.updated:
            update_types.append("服务器配置")
        if result.game_config.updated:
            update_types.append("游戏配置")
        if result.network_config.updated:
            update_types.append("网络配置")

        logger.warning(f"检测到终末地更新: {', '.join(update_types)}")

        failed_count = 0
        success_count = 0

        for subscribe in datas:
            try:
                await subscribe.send(message)
                success_count += 1
                await asyncio.sleep(random.uniform(0.5, 1.5))

            except Exception as e:
                failed_count += 1
                logger.error(f"发送通知失败 (群{subscribe.group_id}): {e}")

        logger.info(f"更新通知发送完成: 成功{success_count}个群，失败{failed_count}个群")


update_checker = UpdateChecker()


@sv_server_check.on_command("取Android端终末地最新版本")
async def get_latest_version_android(bot: Bot, ev: Event):
    try:
        result = await update_checker.check_platform_updates(Platform.ANDROID)
        await bot.send(
            f"clientVersion: {result.launcher_version.new.version}\n"
            f"resVersion: {result.res_version.new.version}\n"
            f"kickFlag: {result.res_version.new.kickFlag}"
        )
    except Exception as e:
        logger.error(f"获取Android端版本失败: {e}")
        await bot.send("获取版本信息失败，请稍后重试")


@sv_server_check.on_command("取终末地最新版本")
async def get_latest_version_windows(bot: Bot, ev: Event):
    try:
        result = await update_checker.check_platform_updates(Platform.DEFAULT)
        await bot.send(
            f"clientVersion: {result.launcher_version.new.version}\n"
            f"resVersion: {result.res_version.new.version}\n"
            f"kickFlag: {result.res_version.new.kickFlag}"
        )
    except Exception as e:
        logger.error(f"获取Windows端版本失败: {e}")
        await bot.send("获取版本信息失败，请稍后重试")


@sv_server_check.on_fullmatch(("取终末地网络配置", "取终末地network_config"))
async def get_network_config(bot: Bot, ev: Event):
    try:
        result = await update_checker.check_single_config(
            ConfigType.NETWORK_CONFIG, Platform.DEFAULT
        )

        data = cast(NetworkConfig, result.new)

        content = "\n".join(
            f"{key}: {value}" for key, value in data.__dict__.items() if value is not None
        )
        await bot.send(f"终末地网络配置:\n{content}")

    except Exception as e:
        logger.error(f"获取终末地网络配置失败: {e}")
        await bot.send("获取网络配置失败，请稍后重试")


@sv_server_check_sub.on_fullmatch(f"{PREFIX}取消订阅版本更新")
async def unsubscribe_version_updates(bot: Bot, ev: Event):
    if ev.group_id is None:
        return await bot.send("请在群聊中使用此命令")

    try:
        data = await gs_subscribe.get_subscribe(TASK_NAME_SERVER_CHECK)
        if not data:
            return await bot.send("当前没有任何群订阅版本更新")

        target_subscribe = None
        for subscribe in data:
            if subscribe.group_id == ev.group_id:
                target_subscribe = subscribe
                break

        if not target_subscribe:
            return await bot.send("当前群未订阅版本更新")

        await gs_subscribe.delete_subscribe("session", TASK_NAME_SERVER_CHECK, ev)

        logger.info(f"群 {ev.group_id} 取消订阅终末地版本更新")
        await bot.send("已取消订阅终末地版本更新")

    except Exception as e:
        logger.error(f"取消订阅失败: {e}")
        await bot.send("取消订阅失败，请稍后重试")


@sv_server_check_sub.on_fullmatch(f"{PREFIX}查看订阅状态")
async def check_subscription_status(bot: Bot, ev: Event):
    """查看订阅状态"""
    try:
        data = await gs_subscribe.get_subscribe(TASK_NAME_SERVER_CHECK)

        if not data:
            return await bot.send("当前没有任何群订阅版本更新")

        total_groups = len(data)
        current_group_subscribed = any(sub.group_id == ev.group_id for sub in data)

        status_msg = "📊 终末地版本更新订阅状态\n\n"
        status_msg += f"总订阅群数: {total_groups}\n"
        status_msg += f"当前群状态: {'已订阅 ✅' if current_group_subscribed else '未订阅 ❌'}\n"
        status_msg += f"检查间隔: {CHECK_INTERVAL_SECONDS}秒"

        await bot.send(status_msg)

    except Exception as e:
        logger.error(f"查看订阅状态失败: {e}")
        await bot.send("查看订阅状态失败，请稍后重试")


@sv_server_check_sub.on_command(f"{PREFIX}订阅列表")
async def list_all_subscriptions(bot: Bot, ev: Event):
    try:
        data = await gs_subscribe.get_subscribe(TASK_NAME_SERVER_CHECK)

        if not data:
            return await bot.send("当前没有任何群订阅版本更新")

        subscription_list = ["📋 终末地版本更新订阅列表\n"]

        for i, subscribe in enumerate(data, 1):
            subscription_list.append(
                f"{i}. 群号: {subscribe.group_id} "
                f"(订阅时间: {getattr(subscribe, 'created_at', '未知')})"
            )

        message = "\n".join(subscription_list)
        await bot.send(message)

    except Exception as e:
        logger.error(f"查看订阅列表失败: {e}")
        await bot.send("查看订阅列表失败，请稍后重试")


@sv_server_check_sub.on_fullmatch(f"{PREFIX}订阅版本更新")
async def subscribe_version_updates(bot: Bot, ev: Event):
    if ev.group_id is None:
        return await bot.send("请在群聊中订阅")

    try:
        data = await gs_subscribe.get_subscribe(TASK_NAME_SERVER_CHECK)
        if data:
            for subscribe in data:
                if subscribe.group_id == ev.group_id:
                    return await bot.send("已经订阅了终末地版本更新！")

        await gs_subscribe.add_subscribe(
            "session",
            task_name=TASK_NAME_SERVER_CHECK,
            event=ev,
            extra_message="",
        )

        logger.info(f"群 {ev.group_id} 成功订阅终末地版本更新")
        await bot.send("成功订阅终末地版本更新!")

    except Exception as e:
        logger.error(f"订阅失败: {e}")
        await bot.send("订阅失败，请稍后重试")


@scheduler.scheduled_job(
    "interval", seconds=CHECK_INTERVAL_SECONDS, id="byd_check_windows_update"
)
async def check_windows_updates():
    try:
        result = await update_checker.check_platform_updates(Platform.DEFAULT)

        if not NotificationManager.has_any_update(result):
            logger.debug("Windows端无更新")
            return

        await NotificationManager.send_update_notifications(result)

    except Exception as e:
        logger.error(f"检查Windows端更新失败: {e}")


@scheduler.scheduled_job(
    "interval", seconds=CHECK_INTERVAL_SECONDS, id="byd_check_android_update"
)
async def check_android_updates():
    try:
        result = await update_checker.check_platform_updates(Platform.ANDROID)

        if not NotificationManager.has_any_update(result):
            logger.debug("Android端无更新")
            return

        await NotificationManager.send_update_notifications(result)

    except Exception as e:
        logger.error(f"检查Android端更新失败: {e}")

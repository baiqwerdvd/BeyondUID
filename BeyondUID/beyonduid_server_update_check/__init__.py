import asyncio
import random
from typing import Any, cast

from gsuid_core.aps import scheduler
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.subscribe import gs_subscribe
from gsuid_core.sv import SV
from msgspec import Struct
from msgspec.structs import asdict

from .config import ConfigType, UpdateConfig, UpdatePriority
from .model import (
    LauncherVersion,
    NetworkConfig,
    Platform,
    ResVersion,
    ServerConfig,
    UpdateCheckResult,
)
from .update_checker import update_checker

sv_server_check = SV("终末地版本更新")
sv_server_check_sub = SV("订阅终末地版本更新", pm=3)

TASK_NAME_SERVER_CHECK = "订阅终末地版本更新"
CHECK_INTERVAL_SECONDS = 10


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
    def format_dict_changes(
        old_dict: dict[str, Any] | Struct, new_dict: dict[str, Any] | Struct
    ) -> str:
        if isinstance(old_dict, Struct):
            old_dict = asdict(old_dict)
        if isinstance(new_dict, Struct):
            new_dict = asdict(new_dict)

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
        platform_name = (
            "Windows端" if result.platform == Platform.DEFAULT else f"{result.platform}端"
        )

        updates = []

        if result.launcher_version.updated:
            data_new = cast(LauncherVersion, result.launcher_version.new)
            data_old = cast(LauncherVersion, result.launcher_version.old)

            updates.append(
                {
                    "type": "launcher_version",
                    "priority": UpdateConfig.get_priority("launcher_version"),
                    "title": "客户端版本更新",
                    "content": f"版本: {data_old.version} → {data_new.version}",
                }
            )

        if result.res_version.updated:
            data_new = cast(ResVersion, result.res_version.new)
            data_old = cast(ResVersion, result.res_version.old)

            content = f"版本: {data_old.version} → {data_new.version}"
            if data_new.kickFlag != data_old.kickFlag:
                content += f"\nkickFlag: {data_old.kickFlag} → {data_new.kickFlag}"

            updates.append(
                {
                    "type": "res_version",
                    "priority": UpdateConfig.get_priority("res_version"),
                    "title": "资源版本更新",
                    "content": content,
                }
            )

        if result.server_config.updated:
            data_new = cast(ServerConfig, result.server_config.new)
            data_old = cast(ServerConfig, result.server_config.old)

            message = (
                f"地址: {data_old.addr} → {data_new.addr}\n"
                f"端口: {data_old.port} → {data_new.port}"
            )
            updates.append(
                {
                    "type": "server_config",
                    "priority": UpdateConfig.get_priority("server_config"),
                    "title": "服务器配置更新",
                    "content": message,
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
            data_new = cast(NetworkConfig, result.network_config.new)
            data_old = cast(NetworkConfig, result.network_config.old)

            changes = NotificationManager.format_dict_changes(data_old, data_new)

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


@sv_server_check.on_command("取Android端最新版本")
async def get_latest_version_android(bot: Bot, ev: Event):
    try:
        result = await update_checker.check_platform_updates(Platform.ANDROID)

        launcher_data = cast(LauncherVersion, result.launcher_version.new)
        res_version_data = cast(ResVersion, result.res_version.new)

        await bot.send(
            "终末地版本信息(Android):\n"
            f"clientVersion: {launcher_data.version}\n"
            f"resVersion: {res_version_data.version}\n"
            f"kickFlag: {res_version_data.kickFlag}"
        )
    except Exception as e:
        logger.error(f"获取Android端版本失败: {e}")
        await bot.send("获取版本信息失败，请稍后重试")


@sv_server_check.on_command("取最新版本")
async def get_latest_version_windows(bot: Bot, ev: Event):
    try:
        result = await update_checker.check_platform_updates(Platform.DEFAULT)

        launcher_data = cast(LauncherVersion, result.launcher_version.new)
        res_version_data = cast(ResVersion, result.res_version.new)

        await bot.send(
            "终末地版本信息(default):\n"
            f"clientVersion: {launcher_data.version}\n"
            f"resVersion: {res_version_data.version}\n"
            f"kickFlag: {res_version_data.kickFlag}"
        )
    except Exception as e:
        logger.error(f"获取Windows端版本失败: {e}")
        await bot.send("获取版本信息失败，请稍后重试")


@sv_server_check.on_fullmatch(("取网络配置", "取network_config"))
async def get_network_config(bot: Bot, ev: Event):
    try:
        result = await update_checker.check_single_config(
            ConfigType.NETWORK_CONFIG, Platform.DEFAULT
        )

        data = cast(NetworkConfig, result.new)

        content = "\n".join(
            f"{key}: {value}" for key, value in asdict(data).items() if value is not None
        )
        await bot.send(f"终末地网络配置:\n{content}")

    except Exception as e:
        logger.error(f"获取终末地网络配置失败: {e}")
        await bot.send("获取网络配置失败，请稍后重试")


@sv_server_check_sub.on_fullmatch("取消订阅版本更新")
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


@sv_server_check_sub.on_fullmatch("查看订阅状态")
async def check_subscription_status(bot: Bot, ev: Event):
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


@sv_server_check_sub.on_command("订阅列表")
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


@sv_server_check_sub.on_fullmatch("订阅版本更新")
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

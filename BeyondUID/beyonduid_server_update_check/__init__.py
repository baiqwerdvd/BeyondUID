import asyncio
import json
import random
from typing import Any

from gsuid_core.aps import scheduler
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.subscribe import gs_subscribe
from gsuid_core.sv import SV
from pydantic import BaseModel

from .config import UpdateConfig
from .model import (
    ConfigUpdate,
    LauncherVersion,
    NetworkConfig,
    Platform,
    RemoteConfigError,
    ResVersion,
    ServerConfig,
    UpdateCheckResult,
)
from .update_checker import UpdateChecker, update_checker

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
        old_dict: dict[str, Any] | BaseModel, new_dict: dict[str, Any] | BaseModel
    ) -> str:
        if isinstance(old_dict, BaseModel):
            old_dict = old_dict.model_dump(mode="json")
        if isinstance(new_dict, BaseModel):
            new_dict = new_dict.model_dump(mode="json")

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
                f"  - {key}: {old_dict.get(key)} → {new_dict.get(key)}"
                for key in sorted(update_keys)
            ]
            messages.append("Update:\n" + "\n".join(updates))

        if new_keys:
            new_items = [f"  - {key}: {new_dict.get(key)}" for key in sorted(new_keys)]
            messages.append("New:\n" + "\n".join(new_items))

        if delete_keys:
            deleted_items = [f"  - {key}: {old_dict.get(key)}" for key in sorted(delete_keys)]
            messages.append("Delete:\n" + "\n".join(deleted_items))

        return "\n\n".join(messages) if messages else "No changes detected"

    @staticmethod
    def _build_error_message(error_obj: RemoteConfigError | dict[str, Any]) -> str:
        if isinstance(error_obj, dict):
            error_obj = RemoteConfigError.model_validate(error_obj)
        return f"{error_obj.code} - {error_obj.reason} - {error_obj.message}"

    @staticmethod
    def _get_data_representation(data: Any) -> str:
        if NotificationManager.is_error(data):
            return NotificationManager._build_error_message(data)

        if data is None:
            return "No data available"

        if isinstance(data, BaseModel):
            return data.model_dump_json(indent=2)
        elif isinstance(data, dict):
            return json.dumps(data, indent=2, ensure_ascii=False)
        return str(data)

    @staticmethod
    def is_error(obj: dict[str, Any]) -> bool:
        try:
            RemoteConfigError.model_validate(obj)
            return True
        except Exception:
            return False

    @staticmethod
    def safe_convert_to_model[T: BaseModel](data: dict[str, Any], model: type[T]) -> T:
        try:
            return model.model_validate(data)
        except Exception as _:
            return model()

    @staticmethod
    def _build_single_update_content(result: UpdateCheckResult) -> list[dict[str, Any]]:
        updates = []

        update_types_info = [
            ("launcher_version", "客户端版本更新"),
            ("res_version", "资源版本更新"),
            ("server_config", "服务器配置更新"),
            ("game_config", "游戏配置更新"),
            ("network_config", "网络配置更新"),
        ]

        for attr_name, title_prefix in update_types_info:
            update_item: ConfigUpdate = getattr(result, attr_name)

            if update_item.updated:
                old_data = update_item.old
                new_data = update_item.new

                is_old_error = NotificationManager.is_error(old_data)
                is_new_error = NotificationManager.is_error(new_data)

                if not is_old_error and is_new_error:
                    content_old = NotificationManager._get_data_representation(old_data)
                    content_new = NotificationManager._get_data_representation(new_data)
                    updates.append(
                        {
                            "type": "error_detected",
                            "priority": UpdateConfig.get_priority("error_detected"),
                            "title": f"{title_prefix}：检测到配置错误",
                            "content": f"原配置:\n{content_old}\n\n新状态: 错误\n{content_new}",
                        }
                    )
                elif is_old_error and not is_new_error:
                    content_old = NotificationManager._get_data_representation(old_data)
                    content_new = NotificationManager._get_data_representation(new_data)
                    updates.append(
                        {
                            "type": "error_resolved",
                            "priority": UpdateConfig.get_priority("error_resolved"),
                            "title": f"{title_prefix}：配置错误已解决",
                            "content": f"原状态: 错误\n{content_old}\n\n新配置:\n{content_new}",
                        }
                    )
                elif is_old_error and is_new_error:
                    if old_data != new_data:
                        content_new = NotificationManager._get_data_representation(new_data)
                        content_old = NotificationManager._get_data_representation(old_data)
                        updates.append(
                            {
                                "type": "error_detected",
                                "priority": UpdateConfig.get_priority("error_detected"),
                                "title": f"{title_prefix}：配置错误详情更新",
                                "content": f"原错误:\n{content_old}\n\n新错误:\n{content_new}",
                            }
                        )
                elif not is_old_error and not is_new_error:
                    content = ""
                    if attr_name == "launcher_version":
                        old_data = NotificationManager.safe_convert_to_model(
                            old_data, LauncherVersion
                        )
                        new_data = NotificationManager.safe_convert_to_model(
                            new_data, LauncherVersion
                        )
                        content = f"version: {old_data.version} → {new_data.version}"
                    elif attr_name == "res_version":
                        old_data = NotificationManager.safe_convert_to_model(old_data, ResVersion)
                        new_data = NotificationManager.safe_convert_to_model(new_data, ResVersion)
                        content = f"version: {old_data.version} → {new_data.version}"
                        if new_data.kickFlag != old_data.kickFlag:
                            content += f"\nkickFlag: {old_data.kickFlag} → {new_data.kickFlag}"
                    elif attr_name == "server_config":
                        old_data = NotificationManager.safe_convert_to_model(
                            old_data, ServerConfig
                        )
                        new_data = NotificationManager.safe_convert_to_model(
                            new_data, ServerConfig
                        )
                        content = (
                            f"addr: {old_data.addr} → {new_data.addr}\n"
                            f"port: {old_data.port} → {new_data.port}"
                        )
                    elif attr_name in ["game_config", "network_config"]:
                        content = NotificationManager.format_dict_changes(old_data, new_data)

                    if content:
                        updates.append(
                            {
                                "type": attr_name,
                                "priority": UpdateConfig.get_priority(attr_name),
                                "title": title_prefix,
                                "content": content,
                            }
                        )

        return updates

    @staticmethod
    def build_update_message(platform_name: str, updates_list: list[dict[str, Any]]) -> str:
        if not updates_list:
            return ""

        updates_list.sort(key=lambda x: UpdateConfig.priority_order.index(x["priority"]))

        messages = []
        for update in updates_list:
            icon = UpdateConfig.get_icon(update["priority"])
            messages.append(f"{icon} {update['title']}\n{update['content']}")

        highest_priority = updates_list[0]["priority"]
        header_icon = UpdateConfig.get_icon(highest_priority)

        header = f"{header_icon} 检测到{platform_name}终末地更新"
        content = "\n\n".join(messages)
        full_message = f"{header}\n\n{content}"

        return full_message

    @staticmethod
    async def send_update_notifications(results: dict[Platform, UpdateCheckResult]):
        datas = await gs_subscribe.get_subscribe(TASK_NAME_SERVER_CHECK)
        if not datas:
            logger.info("[终末地版本更新] 暂无群订阅")
            return

        grouped_messages: dict[str, list[Platform]] = {}
        full_update_details: dict[str, str] = {}

        for platform, result in results.items():
            if not NotificationManager.has_any_update(result):
                continue

            platform_name = (
                "Windows端" if result.platform == Platform.DEFAULT else f"{result.platform}端"
            )

            platform_updates = NotificationManager._build_single_update_content(result)

            update_content_str = "\n".join(
                sorted([f"{u['type']}:{u['content']}" for u in platform_updates])
            )

            if update_content_str not in grouped_messages:
                grouped_messages[update_content_str] = []
                full_update_details[update_content_str] = (
                    NotificationManager.build_update_message(platform_name, platform_updates)
                )

            grouped_messages[update_content_str].append(platform)

        if not grouped_messages:
            logger.debug("未检测到任何终末地更新")
            return

        messages_to_send: list[str] = []
        for update_content_str, platforms_with_same_update in grouped_messages.items():
            if len(platforms_with_same_update) > 1:
                platform_names = [
                    "Windows端" if p == Platform.DEFAULT else f"{p.value}端"
                    for p in platforms_with_same_update
                ]

                first_platform = platforms_with_same_update[0]
                first_platform_updates = NotificationManager._build_single_update_content(
                    results[first_platform]
                )

                highest_priority = max(
                    first_platform_updates,
                    key=lambda x: UpdateConfig.priority_order.index(x["priority"]),
                )["priority"]
                header_icon = UpdateConfig.get_icon(highest_priority)

                consolidated_header = f"{header_icon} 检测到{'、'.join(platform_names)}终末地更新"

                original_full_message = full_update_details[update_content_str]
                content_part = "\n\n".join(original_full_message.split("\n\n")[1:])

                messages_to_send.append(f"{consolidated_header}\n\n{content_part}")

                logger.warning(f"检测到{'、'.join(platform_names)}终末地更新 (内容一致)")
            else:
                platform = platforms_with_same_update[0]
                platform_name = (
                    "Windows端" if platform == Platform.DEFAULT else f"{platform.value}端"
                )

                messages_to_send.append(full_update_details[update_content_str])

                single_platform_result = results[platform]
                update_types = []
                if single_platform_result.launcher_version.updated:
                    update_types.append("客户端版本")
                if single_platform_result.res_version.updated:
                    update_types.append("资源版本")
                if single_platform_result.server_config.updated:
                    update_types.append("服务器配置")
                if single_platform_result.game_config.updated:
                    update_types.append("游戏配置")
                if single_platform_result.network_config.updated:
                    update_types.append("网络配置")
                logger.warning(f"检测到{platform_name}终末地更新: {', '.join(update_types)}")

        failed_count = 0
        success_count = 0

        for message in messages_to_send:
            if not message:
                continue
            for subscribe in datas:
                try:
                    await subscribe.send(message)
                    success_count += 1
                    await asyncio.sleep(random.uniform(0.5, 1.5))
                except Exception as e:
                    failed_count += 1
                    logger.error(f"发送通知失败 (群{subscribe.group_id}): {e}")

        logger.info(f"更新通知发送完成: 成功{success_count}次，失败{failed_count}次")


@sv_server_check.on_command("取Android端最新版本")
async def get_latest_version_android(bot: Bot, ev: Event):
    try:
        result = await update_checker.check_platform_updates(Platform.ANDROID)

        launcher_data = UpdateChecker._convert_to_model(
            result.launcher_version.new,
            LauncherVersion,
        )
        res_version_data = UpdateChecker._convert_to_model(
            result.res_version.new,
            ResVersion,
        )

        clientVersion = (
            f"clientVersion: {launcher_data.version}"
            if isinstance(launcher_data, LauncherVersion)
            else f"clientVersion: {launcher_data.reason} - {launcher_data.message}"
        )
        resVersion = (
            f"resVersion: {res_version_data.version}"
            if isinstance(res_version_data, ResVersion)
            else f"resVersion: {res_version_data.reason} - {res_version_data.message}"
        )
        kickFlag = (
            res_version_data.kickFlag
            if isinstance(res_version_data, ResVersion)
            else f"kickFlag: {res_version_data.reason} - {res_version_data.message}"
        )

        await bot.send(f"终末地版本信息(Android):\n{clientVersion}\n{resVersion}\n{kickFlag}")
    except Exception as e:
        logger.error(f"获取Android端版本失败: {e}")
        await bot.send("获取版本信息失败，请稍后重试")


@sv_server_check.on_command("取最新版本")
async def get_latest_version_windows(bot: Bot, ev: Event):
    try:
        result = await update_checker.check_platform_updates(Platform.DEFAULT)

        launcher_data = UpdateChecker._convert_to_model(
            result.launcher_version.new,
            LauncherVersion,
        )
        res_version_data = UpdateChecker._convert_to_model(
            result.res_version.new,
            ResVersion,
        )

        clientVersion = (
            f"clientVersion: {launcher_data.version}"
            if isinstance(launcher_data, LauncherVersion)
            else f"clientVersion: {launcher_data.reason} - {launcher_data.message}"
        )
        resVersion = (
            f"resVersion: {res_version_data.version}"
            if isinstance(res_version_data, ResVersion)
            else f"resVersion: {res_version_data.reason} - {res_version_data.message}"
        )
        kickFlag = (
            res_version_data.kickFlag
            if isinstance(res_version_data, ResVersion)
            else f"kickFlag: {res_version_data.reason} - {res_version_data.message}"
        )

        await bot.send(f"终末地版本信息(default):\n{clientVersion}\n{resVersion}\n{kickFlag}")
    except Exception as e:
        logger.error(f"获取Windows端版本失败: {e}")
        await bot.send("获取版本信息失败，请稍后重试")


@sv_server_check.on_fullmatch(("取网络配置", "取network_config"))
async def get_network_config(bot: Bot, ev: Event):
    try:
        result = await update_checker.check_platform_updates(Platform.DEFAULT)

        data = UpdateChecker._convert_to_model(
            result.network_config.new,
            NetworkConfig,
        )

        content = "\n".join(
            f"{key}: {value}" for key, value in data.model_dump().items() if value is not None
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
    "interval", seconds=CHECK_INTERVAL_SECONDS, id="byd_check_remote_config_update"
)
async def check_remote_config_updates():
    results = {}
    for platform in Platform:
        result = await update_checker.check_platform_updates(platform)

        if not NotificationManager.has_any_update(result):
            logger.debug(f"{platform.value}端无更新")
            continue

        results[platform] = result

    await NotificationManager.send_update_notifications(results)

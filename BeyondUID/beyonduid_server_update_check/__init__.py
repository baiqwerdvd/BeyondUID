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
    EngineConfig,
    LauncherVersion,
    NetworkConfig,
    Platform,
    RemoteConfigError,
    ResVersion,
    UpdateCheckResult,
)
from .update_checker import UpdateChecker, update_checker

sv_server_check = SV("终末地版本更新")
sv_server_check_sub = SV("订阅终末地版本更新", pm=3)

TASK_NAME_SERVER_CHECK = "订阅终末地版本更新"
CHECK_INTERVAL_SECONDS = 10

SEPARATOR = "━" * 24
THIN_SEPARATOR = "─" * 24


class OutputFormatter:
    @staticmethod
    def format_header(title: str) -> str:
        return f"{title}\n{SEPARATOR}"

    @staticmethod
    def format_section(title: str, content: str) -> str:
        return f"[{title}]\n{content}"

    @staticmethod
    def format_change(label: str, old_value: Any, new_value: Any, indent: int = 2) -> str:
        prefix = " " * indent
        return f"{prefix}{label}: {old_value} → {new_value}"

    @staticmethod
    def format_new_item(label: str, value: Any, indent: int = 2) -> str:
        prefix = " " * indent
        return f"{prefix}+ {label}: {value}"

    @staticmethod
    def format_deleted_item(label: str, value: Any, indent: int = 2) -> str:
        prefix = " " * indent
        return f"{prefix}- {label}: {value}"

    @staticmethod
    def format_key_value(label: str, value: Any, width: int = 10) -> str:
        return f"{label.ljust(width)}: {value}"

    @staticmethod
    def format_bool(value: bool) -> str:
        return "是" if value else "否"


class NotificationManager:
    @staticmethod
    def has_any_update(result: UpdateCheckResult) -> bool:
        return any(
            [
                result.network_config.updated,
                result.game_config.updated,
                result.res_version.updated,
                result.engine_config.updated,
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
                OutputFormatter.format_change(key, old_dict.get(key), new_dict.get(key))
                for key in sorted(update_keys)
            ]
            messages.extend(updates)

        if new_keys:
            new_items = [
                OutputFormatter.format_new_item(key, new_dict.get(key))
                for key in sorted(new_keys)
            ]
            messages.extend(new_items)

        if delete_keys:
            deleted_items = [
                OutputFormatter.format_deleted_item(key, old_dict.get(key))
                for key in sorted(delete_keys)
            ]
            messages.extend(deleted_items)

        return "\n".join(messages) if messages else "  无变化"

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
            return "无数据"

        if isinstance(data, BaseModel):
            return data.model_dump_json(indent=2)
        elif isinstance(data, dict):
            return json.dumps(data, indent=2, ensure_ascii=False)
        return str(data)

    @staticmethod
    def is_error(obj: dict[str, Any]) -> bool:
        if not all(key in obj for key in ("code", "reason", "message")):
            return False
        if obj.get("code") == 0:
            return False
        return True

    @staticmethod
    def safe_convert_to_model[T: BaseModel](data: dict[str, Any], model: type[T]) -> T:
        try:
            return model.model_validate(data)
        except Exception:
            return model()

    @staticmethod
    def _format_engine_config_changes(old_data: dict, new_data: dict) -> str:
        """Format engine config changes with parsed Configs"""
        old_configs_str = old_data.get("Configs", "{}")
        new_configs_str = new_data.get("Configs", "{}")

        try:
            old_configs = json.loads(old_configs_str) if old_configs_str else {}
            new_configs = json.loads(new_configs_str) if new_configs_str else {}
        except json.JSONDecodeError:
            old_configs = {}
            new_configs = {}

        messages = []

        # Check for version changes
        old_version = old_data.get("Version", 0)
        new_version = new_data.get("Version", 0)
        if old_version != new_version:
            messages.append(OutputFormatter.format_change("Version", old_version, new_version))

        # Check for config entry changes
        old_keys = set(old_configs.keys())
        new_keys = set(new_configs.keys())

        added_keys = new_keys - old_keys
        removed_keys = old_keys - new_keys
        common_keys = old_keys & new_keys

        for key in sorted(added_keys):
            messages.append(OutputFormatter.format_new_item(key, "新增配置项"))

        for key in sorted(removed_keys):
            messages.append(OutputFormatter.format_deleted_item(key, "已移除"))

        for key in sorted(common_keys):
            if old_configs[key] != new_configs[key]:
                messages.append(OutputFormatter.format_change(key, "已修改", "详见配置"))

        return "\n".join(messages) if messages else "  无变化"

    @staticmethod
    def _build_single_update_content(result: UpdateCheckResult) -> list[dict[str, Any]]:
        updates = []

        update_types_info = [
            ("launcher_version", "客户端版本更新"),
            ("res_version", "资源版本更新"),
            ("engine_config", "引擎配置更新"),
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
                    content_new = NotificationManager._get_data_representation(new_data)
                    updates.append(
                        {
                            "type": "error_detected",
                            "priority": UpdateConfig.get_priority("error_detected"),
                            "title": f"{title_prefix} - 检测到错误",
                            "content": f"  原配置正常\n  新状态: 错误\n  {content_new}",
                        }
                    )
                elif is_old_error and not is_new_error:
                    updates.append(
                        {
                            "type": "error_resolved",
                            "priority": UpdateConfig.get_priority("error_resolved"),
                            "title": f"{title_prefix} - 错误已解决",
                            "content": "  配置已恢复正常",
                        }
                    )
                elif is_old_error and is_new_error:
                    if old_data != new_data:
                        content_new = NotificationManager._get_data_representation(new_data)
                        updates.append(
                            {
                                "type": "error_detected",
                                "priority": UpdateConfig.get_priority("error_detected"),
                                "title": f"{title_prefix} - 错误详情更新",
                                "content": f"  {content_new}",
                            }
                        )
                elif not is_old_error and not is_new_error:
                    content = ""
                    if attr_name == "launcher_version":
                        old_model = NotificationManager.safe_convert_to_model(
                            old_data, LauncherVersion
                        )
                        new_model = NotificationManager.safe_convert_to_model(
                            new_data, LauncherVersion
                        )
                        content = OutputFormatter.format_change(
                            "版本", old_model.version, new_model.version
                        )
                    elif attr_name == "res_version":
                        old_model = NotificationManager.safe_convert_to_model(
                            old_data, ResVersion
                        )
                        new_model = NotificationManager.safe_convert_to_model(
                            new_data, ResVersion
                        )
                        changes = []

                        # Check res_version string changes
                        if new_model.res_version != old_model.res_version:
                            changes.append(
                                OutputFormatter.format_change(
                                    "资源版本",
                                    old_model.res_version or "无",
                                    new_model.res_version or "无",
                                )
                            )

                        # Check kick_flag changes
                        old_kick = old_model.get_parsed_configs().kick_flag
                        new_kick = new_model.get_parsed_configs().kick_flag
                        if old_kick != new_kick:
                            changes.append(
                                OutputFormatter.format_change(
                                    "踢出标记",
                                    OutputFormatter.format_bool(old_kick),
                                    OutputFormatter.format_bool(new_kick),
                                )
                            )

                        # Check resource changes
                        old_resources = {r.name: r.version for r in old_model.resources}
                        new_resources = {r.name: r.version for r in new_model.resources}
                        for name, version in new_resources.items():
                            old_ver = old_resources.get(name)
                            if old_ver != version:
                                changes.append(
                                    OutputFormatter.format_change(
                                        f"资源[{name}]", old_ver or "无", version
                                    )
                                )

                        content = "\n".join(changes) if changes else ""
                    elif attr_name == "engine_config":
                        content = NotificationManager._format_engine_config_changes(
                            old_data, new_data
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

        header = f"{header_icon} 检测到 {platform_name} 终末地更新"
        content = "\n\n".join(messages)
        full_message = f"{header}\n{SEPARATOR}\n{content}\n{SEPARATOR}"

        return full_message

    @staticmethod
    async def send_update_notifications(results: dict[Platform, UpdateCheckResult]):
        datas = await gs_subscribe.get_subscribe(TASK_NAME_SERVER_CHECK)
        if not datas:
            logger.debug("[终末地版本更新] 暂无群订阅")
            return

        grouped_messages: dict[str, list[Platform]] = {}
        full_update_details: dict[str, str] = {}

        for platform, result in results.items():
            if not NotificationManager.has_any_update(result):
                continue

            platform_name = (
                "Windows 端" if result.platform == Platform.DEFAULT else f"{result.platform} 端"
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
                    "Windows 端" if p == Platform.DEFAULT else f"{p.value} 端"
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

                consolidated_header = (
                    f"{header_icon} 检测到 {'、'.join(platform_names)} 终末地更新"
                )

                original_full_message = full_update_details[update_content_str]
                parts = original_full_message.split(SEPARATOR)
                content_part = SEPARATOR.join(parts[1:]) if len(parts) > 1 else ""

                messages_to_send.append(f"{consolidated_header}\n{SEPARATOR}{content_part}")

                logger.warning(f"检测到 {'、'.join(platform_names)} 终末地更新 (内容一致)")
            else:
                platform = platforms_with_same_update[0]
                platform_name = (
                    "Windows 端" if platform == Platform.DEFAULT else f"{platform.value} 端"
                )

                messages_to_send.append(full_update_details[update_content_str])

                single_platform_result = results[platform]
                update_types = []
                if single_platform_result.launcher_version.updated:
                    update_types.append("客户端版本")
                if single_platform_result.res_version.updated:
                    update_types.append("资源版本")
                if single_platform_result.engine_config.updated:
                    update_types.append("引擎配置")
                if single_platform_result.game_config.updated:
                    update_types.append("游戏配置")
                if single_platform_result.network_config.updated:
                    update_types.append("网络配置")
                logger.warning(f"检测到 {platform_name} 终末地更新: {', '.join(update_types)}")

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

        logger.info(f"更新通知发送完成: 成功 {success_count} 次，失败 {failed_count} 次")


def _format_version_info(
    platform_name: str,
    launcher_data: LauncherVersion | RemoteConfigError,
    res_data: ResVersion | RemoteConfigError,
) -> str:
    lines = [f"📦 终末地版本信息 ({platform_name})", ""]

    # Client version
    if isinstance(launcher_data, LauncherVersion):
        lines.append(f"▸ 客户端版本: {launcher_data.version}")
    else:
        lines.append(f"▸ 客户端版本: 错误 - {launcher_data.reason}")

    # Kick flag
    if isinstance(res_data, ResVersion):
        kick_flag_str = OutputFormatter.format_bool(res_data.get_parsed_configs().kick_flag)
        lines.append(f"▸ 踢出标记: {kick_flag_str}")

    lines.append("")  # Empty line for spacing

    # Resource version
    if isinstance(res_data, ResVersion):
        lines.append("▸ 资源版本")
        lines.append(f"  {res_data.res_version or '未知'}")
        for resource in res_data.resources:
            lines.append(f"  · {resource.name}: {resource.version}")
    else:
        lines.append(f"▸ 资源版本: 错误 - {res_data.reason}")

    return "\n".join(lines)


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

        if launcher_data is None:
            launcher_data = RemoteConfigError(
                code=-1, reason="解析失败", message="无法解析客户端版本"
            )
        if res_version_data is None:
            res_version_data = RemoteConfigError(
                code=-1, reason="解析失败", message="无法解析资源版本"
            )

        message = _format_version_info("Android", launcher_data, res_version_data)
        await bot.send(message)
    except Exception as e:
        logger.error(f"获取 Android 端版本失败: {e}")
        await bot.send("获取版本信息失败，请稍后重试")


@sv_server_check.on_command(("取最新版本", "取Windows端最新版本", "取PC端最新版本"))
async def get_latest_version_windows(bot: Bot, ev: Event):
    try:
        result = await update_checker.check_platform_updates(Platform.WINDOWS)

        launcher_data = UpdateChecker._convert_to_model(
            result.launcher_version.new,
            LauncherVersion,
        )
        res_version_data = UpdateChecker._convert_to_model(
            result.res_version.new,
            ResVersion,
        )

        if launcher_data is None:
            launcher_data = RemoteConfigError(
                code=-1, reason="解析失败", message="无法解析客户端版本"
            )
        if res_version_data is None:
            res_version_data = RemoteConfigError(
                code=-1, reason="解析失败", message="无法解析资源版本"
            )

        message = _format_version_info("Windows", launcher_data, res_version_data)
        await bot.send(message)
    except Exception as e:
        logger.error(f"获取 Windows 端版本失败: {e}")
        await bot.send("获取版本信息失败，请稍后重试")


@sv_server_check.on_fullmatch(("取网络配置", "取network_config"))
async def get_network_config(bot: Bot, ev: Event):
    try:
        result = await update_checker.check_platform_updates(Platform.DEFAULT)

        data = UpdateChecker._convert_to_model(
            result.network_config.new,
            NetworkConfig,
        )

        if data is None:
            await bot.send("获取网络配置失败，无法解析数据")
            return

        lines = [
            "终末地网络配置",
            SEPARATOR,
        ]
        for key, value in data.model_dump().items():
            lines.append(OutputFormatter.format_key_value(key, value, width=12))
        lines.append(SEPARATOR)

        await bot.send("\n".join(lines))

    except Exception as e:
        logger.error(f"获取终末地网络配置失败: {e}")
        await bot.send("获取网络配置失败，请稍后重试")


@sv_server_check.on_fullmatch(("取引擎配置", "取engine_config"))
async def get_engine_config(bot: Bot, ev: Event):
    try:
        result = await update_checker.check_platform_updates(Platform.DEFAULT)

        data = UpdateChecker._convert_to_model(
            result.engine_config.new,
            EngineConfig,
        )

        if data is None:
            await bot.send("获取引擎配置失败，无法解析数据")
            return

        lines = [
            "终末地引擎配置",
            SEPARATOR,
            OutputFormatter.format_key_value("Version", data.Version),
            OutputFormatter.format_key_value("CL", data.CL),
            THIN_SEPARATOR,
        ]

        # Parse and display config entries
        parsed_configs = data.get_parsed_configs()
        for config_name, config_data in parsed_configs.items():
            lines.append(f"  {config_name}")
            lines.append(f"    平台: {config_data.Platform}")
            if config_data.Processor:
                lines.append(f"    处理器: {config_data.Processor[:30]}...")
            if config_data.DeviceModel:
                lines.append(f"    设备: {config_data.DeviceModel}")
            if config_data.SOCModel:
                lines.append(f"    SOC: {config_data.SOCModel}")

        lines.append(SEPARATOR)
        await bot.send("\n".join(lines))

    except Exception as e:
        logger.error(f"获取终末地引擎配置失败: {e}")
        await bot.send("获取引擎配置失败，请稍后重试")


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

        status_text = "已订阅" if current_group_subscribed else "未订阅"
        interval_text = f"{CHECK_INTERVAL_SECONDS} 秒"
        lines = [
            "终末地版本更新订阅状态",
            SEPARATOR,
            OutputFormatter.format_key_value("总订阅群数", total_groups, width=12),
            OutputFormatter.format_key_value("当前群状态", status_text, width=12),
            OutputFormatter.format_key_value("检查间隔", interval_text, width=12),
            SEPARATOR,
        ]

        await bot.send("\n".join(lines))

    except Exception as e:
        logger.error(f"查看订阅状态失败: {e}")
        await bot.send("查看订阅状态失败，请稍后重试")


@sv_server_check_sub.on_command("订阅列表")
async def list_all_subscriptions(bot: Bot, ev: Event):
    try:
        data = await gs_subscribe.get_subscribe(TASK_NAME_SERVER_CHECK)

        if not data:
            return await bot.send("当前没有任何群订阅版本更新")

        lines = [
            "终末地版本更新订阅列表",
            SEPARATOR,
        ]

        for i, subscribe in enumerate(data, 1):
            created_at = getattr(subscribe, "created_at", "未知")
            lines.append(f"  {i}. 群号: {subscribe.group_id}")
            lines.append(f"     订阅时间: {created_at}")

        lines.append(SEPARATOR)
        lines.append(f"共 {len(data)} 个群订阅")

        message = "\n".join(lines)
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

        # 跳过首次初始化的平台，不发送更新通知
        if result.is_first_init:
            logger.info(f"{platform.value} 端首次初始化，跳过更新通知")
            continue

        if not NotificationManager.has_any_update(result):
            logger.debug(f"{platform.value} 端无更新")
            continue

        results[platform] = result

    await NotificationManager.send_update_notifications(results)

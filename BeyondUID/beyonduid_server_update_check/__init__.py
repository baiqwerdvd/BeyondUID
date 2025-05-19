import asyncio
import json
import random
from enum import StrEnum
from typing import Any, Literal

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

task_name_server_check = "订阅终末地版本更新"


class Device(StrEnum):
    Default = "Default"
    Android = "Android"
    Windows = "Windows"

    def iter(self):
        return self.__class__.__dict__.items()


remote_cofig = {
    "network_config": "https://game-config.hypergryph.com/api/remote_config/get_remote_config/3/prod-cbt/default/{device}/network_config",
    "game_config": "https://game-config.hypergryph.com/api/remote_config/get_remote_config/3/prod-cbt/default/{device}/game_config",
    "res_version": "https://game-config.hypergryph.com/api/remote_config/get_remote_config/3/prod-cbt/default/{device}/res_version",
    "server_config": "https://game-config.hypergryph.com/api/remote_config/get_remote_config/3/prod-cbt/default/{device}/server_config_China",
    "launcher_version": "https://launcher.hypergryph.com/api/game/get_latest?appcode=CAdYGoQmEUZnxXGf&channel=1",
}


class VersionModel(Struct):
    clientVersion: str
    resVersion: str


class NetworkConfigUpdate(Struct):
    old: dict[str, Any]
    new: dict[str, Any]


class GameConfigUpdate(Struct):
    old: dict[str, Any]
    new: dict[str, Any]


class ResVersion(Struct):
    version: str
    kickFlag: bool


class ResVersionUpdate(Struct):
    old: ResVersion
    new: ResVersion


class ServerConfig(Struct):
    addr: str
    port: int


class ServerConfigUpdate(Struct):
    old: ServerConfig
    new: ServerConfig


class LauncherVersion(Struct):
    action: int
    version: str
    request_version: str
    pkg: dict[str, Any] | None = None
    patch: dict[str, Any] | None = None


class LauncherVersionUpdate(Struct):
    old: LauncherVersion
    new: LauncherVersion


class UpdateCheckResult(Struct):
    network_config: NetworkConfigUpdate
    game_config: GameConfigUpdate
    res_version: ResVersionUpdate
    server_config: ServerConfigUpdate
    launcher_version: LauncherVersionUpdate

    network_config_updated: bool = False
    game_config_updated: bool = False
    res_updated: bool = False
    server_config_updated: bool = False
    client_updated: bool = False


async def check_update(target_platform: Literal["Android", "Windows"]) -> UpdateCheckResult:
    """
    check if there is an update

    Returns:
        tuple[VersionModel, bool, bool]:
            VersionModel: the current version
            bool: if the client version is updated
            bool: if the resource version is updated
    """
    network_config_update = None
    game_config_update = None
    res_version_update = None
    server_config_update = None
    launcher_version_update = None

    for key, url in remote_cofig.items():
        url = url.format(device=target_platform)
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = json.loads(await response.text())

        path = get_res_path("ArknightsUID") / f"{key}_{target_platform}.json"
        if not path.exists():
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

        with open(path, encoding="utf-8") as f:
            base_data = json.load(f)

        match key:
            case "network_config":
                network_config = convert(data, dict[str, Any])
                base_network_config = convert(base_data, dict[str, Any])
                network_config_update = NetworkConfigUpdate(
                    old=base_network_config, new=network_config
                )
            case "game_config":
                game_config = convert(data, dict[str, Any])
                base_game_config = convert(base_data, dict[str, Any])
                game_config_update = GameConfigUpdate(old=base_game_config, new=game_config)
            case "res_version":
                res_version = convert(data, ResVersion)
                base_res_version = convert(base_data, ResVersion)
                res_version_update = ResVersionUpdate(old=base_res_version, new=res_version)
            case "server_config":
                server_config = convert(data, ServerConfig)
                base_server_config = convert(base_data, ServerConfig)
                server_config_update = ServerConfigUpdate(
                    old=base_server_config, new=server_config
                )
            case "launcher_version":
                launcher_version = convert(data, LauncherVersion)
                base_launcher_version = convert(base_data, LauncherVersion)
                launcher_version_update = LauncherVersionUpdate(
                    old=base_launcher_version, new=launcher_version
                )

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    assert network_config_update
    assert game_config_update
    assert res_version_update
    assert server_config_update
    assert launcher_version_update

    return UpdateCheckResult(
        network_config=network_config_update,
        game_config=game_config_update,
        res_version=res_version_update,
        server_config=server_config_update,
        launcher_version=launcher_version_update,
        network_config_updated=network_config_update.old != network_config_update.new,
        game_config_updated=game_config_update.old != game_config_update.new,
        res_updated=res_version_update.old != res_version_update.new,
        server_config_updated=server_config_update.old != server_config_update.new,
        client_updated=launcher_version_update.old != launcher_version_update.new,
    )


@sv_server_check.on_command("取终末地最新版本 Android")
async def get_latest_version(bot: Bot, ev: Event):
    result = await check_update("Android")
    await bot.send(
        f"clientVersion: {result.launcher_version.new.version}\nresVersion: {result.res_version.new.version}"
    )


@sv_server_check.on_command("取终末地最新版本 Windows")
async def get_latest_version_win(bot: Bot, ev: Event):
    result = await check_update("Windows")
    await bot.send(
        f"clientVersion: {result.launcher_version.new.version}\nresVersion: {result.res_version.new.version}"
    )


@sv_server_check_sub.on_fullmatch(f"{PREFIX}订阅版本更新")
async def sub_ann_(bot: Bot, ev: Event):
    if ev.group_id is None:
        return await bot.send("请在群聊中订阅")
    data = await gs_subscribe.get_subscribe(task_name_server_check)
    if data:
        for subscribe in data:
            if subscribe.group_id == ev.group_id:
                return await bot.send("已经订阅了终末地版本更新！")

    await gs_subscribe.add_subscribe(
        "session",
        task_name=task_name_server_check,
        event=ev,
        extra_message="",
    )

    logger.info(data)
    await bot.send("成功订阅终末地版本更新!")


@scheduler.scheduled_job("interval", seconds=2, id="byd check update")
async def byd_client_update_checker():
    logger.info("Checking for Beyond client update")

    for target_platform in ["Android", "Windows"]:
        result = await check_update(target_platform)
        if (
            not result.res_updated
            and not result.client_updated
            and not result.server_config_updated
            and not result.game_config_updated
            and not result.network_config_updated
        ):
            logger.info("No update found")
            return

        datas = await gs_subscribe.get_subscribe(task_name_server_check)
        if not datas:
            logger.info("[终末地版本更新] 暂无群订阅")
            return

        for subscribe in datas:
            if result.client_updated:
                logger.warning("检测到终末地客户端版本更新")
                match target_platform:
                    case "Android":
                        await subscribe.send(
                            f"检测到Android平台终末地客户端版本更新\nclientVersion: {result.launcher_version.old.version} -> {result.launcher_version.new.version}\nresVersion: {result.res_version.new.version}",
                        )
                        await asyncio.sleep(random.uniform(1, 3))
                    case "Windows":
                        await subscribe.send(
                            f"检测到Windows平台终末地客户端版本更新\nclientVersion: {result.launcher_version.old.version} -> {result.launcher_version.new.version}\nresVersion: {result.res_version.new.version}",
                        )
                        await asyncio.sleep(random.uniform(1, 3))
            elif result.res_updated:
                logger.warning("检测到终末地资源版本更新")
                match target_platform:
                    case "Android":
                        await subscribe.send(
                            f"检测到Android平台终末地资源版本更新\nresVersion: {result.res_version.old.version} -> {result.res_version.new.version}",
                        )
                        await asyncio.sleep(random.uniform(1, 3))
                    case "Windows":
                        await subscribe.send(
                            f"检测到Windows平台终末地资源版本更新\nresVersion: {result.res_version.old.version} -> {result.res_version.new.version}",
                        )
                        await asyncio.sleep(random.uniform(1, 3))
            elif result.server_config_updated:
                logger.warning("检测到终末地服务器配置更新")
                match target_platform:
                    case "Android":
                        await subscribe.send(
                            f"检测到Android平台终末地服务器配置更新\naddr: {result.server_config.old.addr} -> {result.server_config.new.addr}\nport: {result.server_config.old.port} -> {result.server_config.new.port}",
                        )
                        await asyncio.sleep(random.uniform(1, 3))
                    case "Windows":
                        await subscribe.send(
                            f"检测到Windows平台终末地服务器配置更新\naddr: {result.server_config.old.addr} -> {result.server_config.new.addr}\nport: {result.server_config.old.port} -> {result.server_config.new.port}",
                        )
                        await asyncio.sleep(random.uniform(1, 3))
            elif result.game_config_updated:
                logger.warning("检测到终末地游戏配置更新")
                update_keys = set()
                for key, value in result.game_config.new.items():
                    if key not in result.game_config.old:
                        update_keys.add(key)
                        continue
                    if value != result.game_config.old[key]:
                        update_keys.add(key)
                msg = "\n".join(
                    [
                        f"{key}: {result.game_config.old.get(key)} -> {result.game_config.new.get(key)}"
                        for key in update_keys
                    ]
                )
                match target_platform:
                    case "Android":
                        await subscribe.send(
                            f"检测到Android平台终末地游戏配置更新\n{msg}",
                        )
                        await asyncio.sleep(random.uniform(1, 3))
                    case "Windows":
                        await subscribe.send(
                            f"检测到Windows平台终末地游戏配置更新\n{msg}",
                        )
                        await asyncio.sleep(random.uniform(1, 3))
            elif result.network_config_updated:
                logger.warning("检测到终末地网络配置更新")
                update_keys = set()
                for key, value in result.network_config.new.items():
                    if key not in result.network_config.old:
                        update_keys.add(key)
                        continue
                    if value != result.network_config.old[key]:
                        update_keys.add(key)
                msg = "\n".join(
                    [
                        f"{key}: {result.network_config.old.get(key)} -> {result.network_config.new.get(key)}"
                        for key in update_keys
                    ]
                )
                match target_platform:
                    case "Android":
                        await subscribe.send(
                            f"检测到Android平台终末地网络配置更新\n{msg}",
                        )
                        await asyncio.sleep(random.uniform(1, 3))
                    case "Windows":
                        await subscribe.send(
                            f"检测到Windows平台终末地网络配置更新\n{msg}",
                        )
                        await asyncio.sleep(random.uniform(1, 3))
        logger.info("Update check finished")

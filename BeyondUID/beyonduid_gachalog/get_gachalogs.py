import asyncio
import json
import time
from pathlib import Path
from typing import TypeVar

import httpx
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from sklandcore.byd_client import BeyondClient
from sklandcore.constants import OAuth2AppCode
from sklandcore.models.auth import GrantCodeDataType1BindingAPI
from sklandcore.platform import HypergryphDeviceWindows

from ..beyonduid_gachalog.model import (
    BaseGachaRecordItem,
    CharacterGachaPoolType,
    CharRecordItem,
    EFResponse,
    GachaPoolExport,
    GachaRecordList,
    PoolExportInfo,
    WeaponRecordItem,
)
from ..utils.database.models import BeyondUser
from ..utils.resource.RESOURCE_PATH import PLAYER_PATH

T = TypeVar("T", bound=BaseGachaRecordItem)


async def get_u8_token(
    client: BeyondClient,
    uid: str,
    hg_token: str,
    device_token: str,
) -> str:
    binding_grant_data = await client._hypergryph_auth.get_grant_code(
        app_code=OAuth2AppCode.BINDING_API,
        token=hg_token,
        device_token=device_token,
        type=1,
    )
    assert isinstance(binding_grant_data, GrantCodeDataType1BindingAPI)

    binding_data = await client._hypergryph_auth.get_u8_token_by_uid(
        uid=uid,
        token=binding_grant_data.token,
    )
    return binding_data.token


def load_existing_gacha_data(export_file: Path) -> GachaPoolExport | None:
    if not export_file.exists():
        return None
    try:
        with export_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return GachaPoolExport.model_validate(data)
    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"Failed to load existing gacha data: {e}, will fetch all records")
        return None


def get_max_seq_id(records: list[T]) -> int:
    if not records:
        return 0
    return max(int(record.seqId) for record in records)


def merge_records(
    existing: list[T],
    new_records: list[T],
) -> tuple[list[T], int]:
    """
    合并现有记录和新记录，按 seqId 去重
    返回: (合并后的记录列表, 新增记录数)
    """
    existing_seq_ids = {record.seqId for record in existing}
    new_count = 0
    merged = list(existing)

    for record in new_records:
        if record.seqId not in existing_seq_ids:
            merged.append(record)
            existing_seq_ids.add(record.seqId)
            new_count += 1

    merged.sort(key=lambda x: int(x.seqId), reverse=True)
    return merged, new_count


async def fetch_record(
    url: str,
    http_client: httpx.AsyncClient,
    u8_token: str,
    item_type: type[T],
    extra_params: dict[str, str] = {},
    existing_max_seq_id: int = 0,
) -> list[T]:
    """
    拉取抽卡记录，支持增量拉取
    Args:
        existing_max_seq_id: 现有记录中最大的 seqId，遇到小于等于此值的记录时提前终止
    """
    has_more = True
    seq_id = 0
    records: list[T] = []

    while has_more:
        params = {
            "lang": "zh-cn",
            "token": u8_token,
            "server_id": "1",
        }
        params.update(extra_params)
        if seq_id > 0:
            params["seq_id"] = str(seq_id)

        response = await http_client.get(
            url,
            params=params,
        )
        response.raise_for_status()

        gacha_record_list = EFResponse[GachaRecordList[item_type]].model_validate(response.json()).data

        # 检查是否遇到已存在的记录，如果是则提前终止
        should_stop = False
        for record in gacha_record_list.list:
            if int(record.seqId) <= existing_max_seq_id:
                should_stop = True
                break
            records.append(record)

        if should_stop:
            logger.debug(f"Reached existing record at seqId {existing_max_seq_id}, stopping fetch")
            break

        has_more = gacha_record_list.hasMore
        if gacha_record_list.list:
            seq_id = int(gacha_record_list.list[-1].seqId)
        else:
            break
        await asyncio.sleep(0.1)

    return records


async def fetch_full_record(uid: str, platform_roleid: str, bot: Bot, ev: Event):
    user = await BeyondUser.get_user_by_roleid(
        platform_roleid=platform_roleid,
        user_id=ev.user_id,
        bot_id=bot.bot_id,
    )
    if user is None:
        return await bot.send("未找到用户设备信息，请重新绑定账号。")
    device_token, device, hg_token = (
        user.device_token,
        HypergryphDeviceWindows.model_validate_json(user.device_json),
        user.hgtoken,
    )

    beyond_client = BeyondClient(device)
    await beyond_client.initialize()

    u8_token = await get_u8_token(
        client=beyond_client,
        uid=uid,
        hg_token=hg_token,
        device_token=device_token,
    )

    # 加载现有数据
    path = PLAYER_PATH / platform_roleid
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)
    export_file = path / "gacha_logs.json"

    existing_data = load_existing_gacha_data(export_file)
    existing_char_list: list[CharRecordItem] = []
    existing_weapon_list: list[WeaponRecordItem] = []
    if existing_data:
        existing_char_list = existing_data.charList
        existing_weapon_list = existing_data.weaponList
        logger.debug(
            f"Loaded existing data: {len(existing_char_list)} char records, "
            f"{len(existing_weapon_list)} weapon records"
        )

    # 获取现有记录中最大的 seqId
    char_max_seq_id = get_max_seq_id(existing_char_list)
    weapon_max_seq_id = get_max_seq_id(existing_weapon_list)
    logger.debug(f"Existing max seqId - char: {char_max_seq_id}, weapon: {weapon_max_seq_id}")

    http_client = httpx.AsyncClient()

    # 增量拉取角色记录
    fetch_record_char: list[CharRecordItem] = []
    for pool_type in CharacterGachaPoolType:
        list_records = await fetch_record(
            "https://ef-webview.hypergryph.com/api/record/char",
            http_client,
            u8_token,
            CharRecordItem,
            {"pool_type": pool_type.value},
            existing_max_seq_id=char_max_seq_id,
        )
        fetch_record_char.extend(list_records)
        logger.debug(f"New char records fetched for pool {pool_type.value}: {len(list_records)}")

    # 增量拉取武器记录
    fetch_record_weapon = await fetch_record(
        "https://ef-webview.hypergryph.com/api/record/weapon",
        http_client,
        u8_token,
        WeaponRecordItem,
        existing_max_seq_id=weapon_max_seq_id,
    )
    logger.debug(f"New weapon records fetched: {len(fetch_record_weapon)}")

    await http_client.aclose()

    # 合并记录
    merged_char_list, new_char_count = merge_records(existing_char_list, fetch_record_char)
    merged_weapon_list, new_weapon_count = merge_records(existing_weapon_list, fetch_record_weapon)

    gacha_export = GachaPoolExport(
        info=PoolExportInfo(
            uid=platform_roleid,
            lang="zh-cn",
            timezone=8,
            exportTimestamp=int(time.time()),
            version="v1.0",
        ),
        charList=merged_char_list,
        weaponList=merged_weapon_list,
    )

    with export_file.open("w", encoding="utf-8") as f:
        json.dump(
            gacha_export.model_dump(),
            f,
            ensure_ascii=False,
            indent=2,
        )

    logger.info(
        f"Gacha records updated - "
        f"Total: {len(merged_char_list)} char, {len(merged_weapon_list)} weapon | "
        f"New: {new_char_count} char, {new_weapon_count} weapon"
    )

    await bot.send(
        f"UID {platform_roleid}抽卡记录已更新！\n"
        f"新增角色记录：{new_char_count} 条\n"
        f"新增武器记录：{new_weapon_count} 条"
    )

import json
from pathlib import Path

import aiohttp
import msgspec
from gsuid_core.data_store import get_res_path
from gsuid_core.logger import logger
from msgspec import convert
from msgspec import json as msgjson

from .model import (
    BulletinAggregate,
    BulletinData,
    BulletinTargetData,
    BulletinTargetDataItem,
)


async def get_announcement(cid: str) -> BulletinData:
    url = f"https://game-hub.hypergryph.com/bulletin/detail/{cid}?lang=zh-cn&code=endfield_cbt2"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            data = await response.json()
    data = convert(data.get("data", {}), BulletinData)
    return data


async def check_bulletin_update() -> dict[str, BulletinData]:
    bulletin_path = get_res_path(["BeyondUID", "announce"]) / "bulletin.aggregate.json"
    logger.debug("Checking for game bulletin...")

    is_first = False if bulletin_path.exists() else True

    if is_first:
        bulletin_aggregate = BulletinAggregate()
    else:
        try:
            with Path.open(bulletin_path, encoding="UTF-8") as file:
                data = json.load(file)
            bulletin_aggregate = convert(data, BulletinAggregate)
        except json.JSONDecodeError as _:
            bulletin_aggregate = BulletinAggregate()
        except msgspec.DecodeError as _:
            bulletin_aggregate = BulletinAggregate()

    windows_data = None
    android_data = None

    async with aiohttp.ClientSession() as session:
        for platform in ["Windows", "Android"]:
            async with session.get(
                f"https://game-hub.hypergryph.com/bulletin/aggregate?lang=zh-cn&platform={platform}&server=China&type=1&code=endfield_cbt2&hideDetail=1"
            ) as response:
                cur_meta = await response.json()
                if cur_meta.get("code") == 0:
                    match platform:
                        case "Windows":
                            windows_data = convert(cur_meta.get("data", {}), BulletinTargetData)
                            bulletin_aggregate.target.Windows = windows_data
                        case "Android":
                            android_data = convert(cur_meta.get("data", {}), BulletinTargetData)
                            bulletin_aggregate.target.Android = android_data

    update_list = []
    if windows_data is not None:
        update_list.extend(windows_data.list_)
    if android_data is not None:
        update_list.extend(android_data.list_)

    if not update_list:
        logger.debug("No new bulletin found.")
        return {}

    update_set: set[int] = set()
    update_list: list[BulletinTargetDataItem] = [
        x for x in update_list if x.startAt not in update_set and not update_set.add(x.startAt)
    ]
    update_list.sort(key=lambda x: x.startAt, reverse=True)

    new_ann: dict[str, BulletinData] = {}

    for item in update_list:
        for key, value in bulletin_aggregate.update.items():
            if value.cid == item.cid and value.startAt == item.startAt:
                break
            elif value.cid == item.cid and value.startAt != item.startAt:
                bulletin_aggregate.update.pop(key)
                if "_" in key:
                    new_key = f"{item.cid}_{int(key.split('_')[1]) + 1}"
                else:
                    new_key = f"{item.cid}_1"
                ann = await get_announcement(item.cid)
                bulletin_aggregate.update[new_key] = ann
                new_ann[item.cid] = ann
                logger.info(f"Bumped bulletin found: {item.cid}:{item.title}")
                break
            elif value.cid != item.cid:
                continue

        if item.cid not in bulletin_aggregate.data:
            ann = await get_announcement(item.cid)
            bulletin_aggregate.data[item.cid] = ann
            new_ann[item.cid] = ann
            logger.info(f"New bulletin found: {item.cid}:{item.title}")

    bulletin_aggregate.data = dict(
        sorted(bulletin_aggregate.data.items(), key=lambda x: int(x[0]))
    )
    bulletin_aggregate.update = dict(
        sorted(bulletin_aggregate.update.items(), key=lambda x: x[1].cid, reverse=False)
    )

    data = msgjson.decode(msgjson.encode(bulletin_aggregate))
    with Path.open(bulletin_path, mode="w", encoding="UTF-8") as file:
        json.dump(data, file, sort_keys=False, indent=4, ensure_ascii=False)
    logger.debug("The file 'bulletin.aggregate.json' has been successfully updated.")

    if is_first:
        logger.info("Initial success, will be updated in the next polling.")
        return {}
    else:
        return new_ann

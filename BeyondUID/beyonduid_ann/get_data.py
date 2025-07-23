import json
from enum import StrEnum
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

BASE_URL = "https://game-hub.hypergryph.com"
GAME_CODE = "endfield_cbt2"
LANGUAGE = "zh-cn"
BULLETIN_FILE = "bulletin.aggregate.json"


class Platform(StrEnum):
    WINDOWS = "Windows"
    ANDROID = "Android"


async def get_announcement(cid: str) -> BulletinData:
    url = f"{BASE_URL}/bulletin/detail/{cid}?lang={LANGUAGE}&code={GAME_CODE}"

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as response:
                response.raise_for_status()
                data = await response.json()
                return convert(data.get("data", {}), BulletinData)
        except (aiohttp.ClientError, json.JSONDecodeError, msgspec.DecodeError) as e:
            logger.error(f"Failed to get announcement {cid}: {e}")
            raise


def load_bulletin_aggregate(bulletin_path: Path) -> BulletinAggregate:
    if not bulletin_path.exists():
        return BulletinAggregate()

    try:
        with bulletin_path.open(encoding="UTF-8") as file:
            data = json.load(file)
        return convert(data, BulletinAggregate)
    except (json.JSONDecodeError, msgspec.DecodeError) as e:
        logger.warning(f"Failed to load bulletin aggregate, creating new one: {e}")
        return BulletinAggregate()


async def fetch_platform_data(
    session: aiohttp.ClientSession, platform: Platform
) -> BulletinTargetData | None:
    url = (
        f"{BASE_URL}/bulletin/aggregate"
        f"?lang={LANGUAGE}&platform={platform}&server=China"
        f"&type=1&code={GAME_CODE}&hideDetail=1"
    )

    try:
        async with session.get(url) as response:
            response.raise_for_status()
            data = await response.json()

            if data.get("code") == 0:
                return convert(data.get("data", {}), BulletinTargetData)
            else:
                logger.warning(
                    f"API returned error code for {platform}: {data.get('code')}, {url}"
                )
                return None
    except (aiohttp.ClientError, json.JSONDecodeError, msgspec.DecodeError) as e:
        logger.error(f"Failed to fetch {platform} data: {e}")
        return None


def deduplicate_updates(
    update_list: list[BulletinTargetDataItem],
) -> list[BulletinTargetDataItem]:
    seen_start_times = set()
    deduplicated = []

    for item in update_list:
        if item.startAt not in seen_start_times:
            seen_start_times.add(item.startAt)
            deduplicated.append(item)

    return sorted(deduplicated, key=lambda x: x.startAt, reverse=True)


def generate_update_key(cid: str, existing_key: str | None = None) -> str:
    if existing_key and "_" in existing_key:
        version = int(existing_key.split("_")[1]) + 1
        return f"{cid}_{version}"
    return f"{cid}_1"


async def process_bulletin_updates(
    update_list: list[BulletinTargetDataItem], bulletin_aggregate: BulletinAggregate
) -> dict[str, BulletinData]:
    new_announcements = {}

    for item in update_list:
        existing_key = None
        for key, value in list(bulletin_aggregate.update.items()):
            if value.cid == item.cid:
                if value.startAt == item.startAt:
                    break
                else:
                    bulletin_aggregate.update.pop(key)
                    existing_key = key
                    break
        else:
            if item.cid not in bulletin_aggregate.data:
                try:
                    ann = await get_announcement(item.cid)
                    bulletin_aggregate.data[item.cid] = ann
                    new_announcements[item.cid] = ann
                    logger.info(f"New bulletin found: {item.cid}:{item.title}")
                except Exception as e:
                    logger.error(f"Failed to get new announcement {item.cid}: {e}")
                continue

        if existing_key:
            try:
                new_key = generate_update_key(item.cid, existing_key)
                ann = await get_announcement(item.cid)
                bulletin_aggregate.update[new_key] = ann
                new_announcements[item.cid] = ann
                logger.info(f"Updated bulletin found: {item.cid}:{item.title}")
            except Exception as e:
                logger.error(f"Failed to get updated announcement {item.cid}: {e}")

    return new_announcements


def save_bulletin_aggregate(bulletin_aggregate: BulletinAggregate, bulletin_path: Path) -> None:
    bulletin_aggregate.data = dict(
        sorted(bulletin_aggregate.data.items(), key=lambda x: int(x[0]))
    )
    bulletin_aggregate.update = dict(
        sorted(bulletin_aggregate.update.items(), key=lambda x: x[1].cid)
    )

    try:
        data = msgjson.decode(msgjson.encode(bulletin_aggregate))
        with bulletin_path.open(mode="w", encoding="UTF-8") as file:
            json.dump(data, file, sort_keys=False, indent=4, ensure_ascii=False)
        logger.debug(f"Successfully updated {BULLETIN_FILE}")
    except Exception as e:
        logger.error(f"Failed to save bulletin aggregate: {e}")
        raise


async def check_bulletin_update() -> dict[str, BulletinData]:
    bulletin_path = get_res_path(["BeyondUID", "announce"]) / BULLETIN_FILE
    logger.debug("Checking for game bulletin...")

    is_first_run = not bulletin_path.exists()
    bulletin_aggregate = load_bulletin_aggregate(bulletin_path)

    platform_data_map = {}
    async with aiohttp.ClientSession() as session:
        for platform in Platform:
            platform_data = await fetch_platform_data(session, platform)
            if platform_data:
                platform_data_map[platform] = platform_data
                setattr(bulletin_aggregate.target, platform, platform_data)

    all_updates = []
    for platform_data in platform_data_map.values():
        all_updates.extend(platform_data.list_)

    if not all_updates:
        logger.debug("No bulletin updates found.")
        return {}

    update_list = deduplicate_updates(all_updates)

    new_announcements = await process_bulletin_updates(update_list, bulletin_aggregate)

    save_bulletin_aggregate(bulletin_aggregate, bulletin_path)

    if is_first_run:
        logger.info("Initial run completed, updates will be detected in next polling.")
        return {}

    return new_announcements

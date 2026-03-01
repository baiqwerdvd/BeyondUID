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
    Platform,
)

BASE_URL = "https://game-hub.hypergryph.com"
GAME_CODE = "endfield_5SD9TN"
LANGUAGE = "zh-cn"
BULLETIN_FILE = "bulletin.aggregate.release.json"


async def get_announcement(cid: str) -> BulletinData | None:
    url = f"{BASE_URL}/bulletin/detail/{cid}?lang={LANGUAGE}&code={GAME_CODE}"

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as response:
                response.raise_for_status()
                data = await response.json()

                # {"code":1500,"msg":"Bulletin not found","data":{}}
                if data.get("code") == 1500:
                    logger.warning(f"Bulletin not found for CID: {cid}")
                    return None

                return convert(data["data"], BulletinData)
        except (aiohttp.ClientError, json.JSONDecodeError, msgspec.DecodeError) as e:
            logger.error(f"Failed to get announcement {cid}: {e}")
            raise


def load_bulletin_aggregate(bulletin_path: Path) -> BulletinAggregate:
    if not bulletin_path.exists():
        return BulletinAggregate.default()

    try:
        with bulletin_path.open(encoding="UTF-8") as file:
            data = json.load(file)
        return convert(data, BulletinAggregate)
    except (json.JSONDecodeError, msgspec.DecodeError) as e:
        logger.warning(f"Failed to load bulletin aggregate, creating new one: {e}")
        return BulletinAggregate.default()


async def fetch_aggregate_data(
    session: aiohttp.ClientSession, platform: Platform
) -> BulletinTargetData | None:
    url = (
        f"{BASE_URL}/bulletin/v2/aggregate"
        f"?lang={LANGUAGE}&channel=1&subChannel=1&platform={platform.value}"
        f"&type=0&code={GAME_CODE}&hideDetail=1&server=1"
    )

    try:
        async with session.get(url) as response:
            response.raise_for_status()
            data = await response.json()

        if data.get("code") == 0:
            aggregate_data = data["data"]

            return convert(aggregate_data, BulletinTargetData)
        else:
            logger.warning(f"API returned error code for {platform.value}: {data.get('code')}, {url}")
            return None
    except (aiohttp.ClientError, json.JSONDecodeError, msgspec.DecodeError) as e:
        logger.error(f"Failed to fetch aggregate data for {platform.value}: {e}")
        return None


def deduplicate_updates(
    update_list: list[BulletinTargetDataItem],
) -> list[BulletinTargetDataItem]:
    seen_cids = set()
    deduplicated = []

    for item in update_list:
        if item.cid not in seen_cids:
            seen_cids.add(item.cid)
            deduplicated.append(item)

    return sorted(deduplicated, key=lambda x: x.startAt, reverse=True)


def generate_update_key(cid: str, existing_key: str | None = None) -> str:
    if existing_key and "_" in existing_key:
        version = int(existing_key.split("_")[1]) + 1
        return f"{cid}_{version}"
    return f"{cid}_1"


async def process_bulletin_updates(
    update_list: list[BulletinTargetDataItem],
    bulletin_aggregate: BulletinAggregate,
) -> dict[str, BulletinData]:
    new_announcements = {}

    for item in update_list:
        existing_key: str | None = None
        existing_entry: BulletinData | None = None

        # check for an existing entry in the "update" dictionary first
        for key, value in list(bulletin_aggregate.update.items()):
            if value.cid == item.cid:
                existing_key = key
                existing_entry = value
                break

        # if there was no match in updates, look in the main data cache
        if existing_entry is None:
            existing_entry = bulletin_aggregate.data.get(item.cid)

        # if we have seen this CID before, we may need to refresh it
        if existing_entry:
            try:
                ann = await get_announcement(item.cid)
                if not ann:
                    logger.warning(f"Announcement not found for CID: {item.cid}")
                    continue
            except Exception as e:
                logger.error(f"Failed to fetch announcement for version check {item.cid}: {e}")
                continue

            # if both timestamp and version are unchanged, nothing to do
            if ann.startAt == existing_entry.startAt and ann.version == existing_entry.version:
                continue

            # otherwise treat it as an updated bulletin
            if existing_key:
                # remove the old update entry before creating a new one
                bulletin_aggregate.update.pop(existing_key, None)
                new_key = generate_update_key(item.cid, existing_key)
            else:
                new_key = generate_update_key(item.cid)

            bulletin_aggregate.update[new_key] = ann
            new_announcements[item.cid] = ann
            logger.info(f"Updated bulletin found: {item.cid}:{item.title}")
            continue

        # not seen before at all – this is a brand‑new announcement
        try:
            ann = await get_announcement(item.cid)
            if not ann:
                logger.warning(f"Announcement not found for CID: {item.cid}")
                continue
            bulletin_aggregate.data[item.cid] = ann
            new_announcements[item.cid] = ann
            logger.info(f"New bulletin found: {item.cid}:{item.title}")
        except Exception as e:
            logger.error(f"Failed to get new announcement {item.cid}: {e}")

    return new_announcements


def save_bulletin_aggregate(bulletin_aggregate: BulletinAggregate, bulletin_path: Path) -> None:
    bulletin_aggregate.data = dict(sorted(bulletin_aggregate.data.items(), key=lambda x: int(x[0])))
    bulletin_aggregate.update = dict(sorted(bulletin_aggregate.update.items(), key=lambda x: x[1].cid))

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

    platform_data_map: dict[Platform, BulletinTargetData] = {}

    async with aiohttp.ClientSession() as session:
        for platform in Platform:
            result = await fetch_aggregate_data(session, platform)
            if result:
                platform_data_map[platform] = result

    for platform, platform_data in platform_data_map.items():
        setattr(bulletin_aggregate.target, platform.value, platform_data)

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

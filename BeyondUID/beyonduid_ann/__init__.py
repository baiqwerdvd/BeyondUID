import asyncio
import json
import random

import aiohttp
from gsuid_core.aps import scheduler
from gsuid_core.bot import Bot
from gsuid_core.data_store import get_res_path
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment
from gsuid_core.subscribe import gs_subscribe
from gsuid_core.sv import SV
from msgspec import convert

from ..beyonduid_config.beyond_config import BeyondConfig
from .draw_img import get_ann_img
from .get_data import (
    BASE_URL,
    BULLETIN_FILE,
    GAME_CODE,
    LANGUAGE,
    check_bulletin_update,
    get_announcement,
)
from .model import BulletinAggregate, BulletinTargetData

sv_ann = SV("终末地公告")
sv_ann_sub = SV("订阅终末地公告", pm=3)

task_name_ann = "订阅终末地公告"
ann_minute_check: int = BeyondConfig.get_config("AnnMinuteCheck").data


@sv_ann.on_command("公告")
async def ann_(bot: Bot, ev: Event):
    cid = ev.text.strip()
    if not cid.isdigit():
        return await bot.send("公告ID不正确")

    data = await get_announcement(cid)
    if not data:
        bulletin_path = get_res_path(["BeyondUID", "announce"]) / BULLETIN_FILE
        try:
            with bulletin_path.open("r", encoding="UTF-8") as file:
                bulletin_data = convert(json.load(file), BulletinAggregate)
            data = bulletin_data.data.get(cid)
        except Exception as e:
            logger.exception(e)
            return await bot.send("读取本地公告缓存失败！")

        if not data:
            return await bot.send("未找到该公告或CID无效！")

    try:
        img = await get_ann_img(data)
        title = data.title.replace("\\n", "")
        msg = [
            MessageSegment.text(f"[终末地公告] {title}\n"),
            MessageSegment.image(img),
        ]
        await bot.send(msg)
    except Exception as e:
        logger.exception(e)
        await bot.send("公告图片生成失败！")


@sv_ann.on_command("强制刷新全部公告")
async def force_ann_(bot: Bot, ev: Event):
    data = await check_bulletin_update()
    await bot.send(f"成功刷新{len(data)}条公告!")


@sv_ann.on_command("获取当前Windows公告列表")
async def get_ann_list_(bot: Bot, ev: Event):
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{BASE_URL}/bulletin/v2/aggregate?lang={LANGUAGE}&channel=1&subChannel=1&platform=Windows&type=1&code={GAME_CODE}&hideDetail=1"
        ) as response:
            data = await response.json()

    data = convert(data["data"], BulletinTargetData)
    msg = ""
    for i in data.list_:
        title = i.title.replace("\\n", "")
        msg += f"CID: {i.cid} - {title}\n"

    await bot.send(msg)


@sv_ann.on_command("获取当前Android公告列表")
async def get_ann_list_and(bot: Bot, ev: Event):
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{BASE_URL}/bulletin/v2/aggregate?lang={LANGUAGE}&channel=1&subChannel=1&platform=Android&type=1&code={GAME_CODE}&hideDetail=1"
        ) as response:
            data = await response.json()

    data = convert(data["data"], BulletinTargetData)
    msg = ""
    for i in data.list_:
        title = i.title.replace("\\n", "")
        msg += f"CID: {i.cid} - {title}\n"

    await bot.send(msg)


@sv_ann_sub.on_fullmatch("订阅公告")
async def sub_ann_(bot: Bot, ev: Event):
    if ev.group_id is None:
        return await bot.send("请在群聊中订阅")
    data = await gs_subscribe.get_subscribe(task_name_ann)
    if data:
        for subscribe in data:
            if subscribe.group_id == ev.group_id:
                return await bot.send("已经订阅了终末地公告！")

    await gs_subscribe.add_subscribe(
        "session",
        task_name=task_name_ann,
        event=ev,
        extra_message="",
    )

    logger.info(data)
    await bot.send("成功订阅终末地公告!")


@sv_ann_sub.on_fullmatch(("取消订阅公告", "取消公告", "退订公告"))
async def unsub_ann_(bot: Bot, ev: Event):
    if ev.group_id is None:
        return await bot.send("请在群聊中取消订阅")

    data = await gs_subscribe.get_subscribe(task_name_ann)
    if data:
        for subscribe in data:
            if subscribe.group_id == ev.group_id:
                await gs_subscribe.delete_subscribe("session", task_name_ann, ev)
                return await bot.send("成功取消订阅终末地公告!")

    return await bot.send("未曾订阅终末地公告！")


@scheduler.scheduled_job("interval", minutes=ann_minute_check, id="byd check ann")
async def check_byd_ann():
    logger.debug("[终末地公告] 定时任务: 终末地公告查询..")

    updates = await check_bulletin_update()

    datas = await gs_subscribe.get_subscribe(task_name_ann)
    if not datas:
        logger.debug("[终末地公告] 暂无群订阅")
        return

    if len(updates) == 0:
        logger.debug("[终末地公告] 没有最新公告")
        return

    logger.info(f"[终末地公告] 共查询到{len(updates)}条最新公告")
    for data in updates.values():
        try:
            img = await get_ann_img(data)
            title = data.title.replace("\\n", "")
            msg = [
                MessageSegment.text(f"[终末地公告更新] {title}\n"),
                MessageSegment.image(img),
            ]

            if isinstance(img, str):
                continue
            for subscribe in datas:
                await subscribe.send(msg)
                await asyncio.sleep(random.uniform(1, 3))
        except Exception as e:
            logger.exception(e)

    logger.info("[终末地公告] 推送完毕")

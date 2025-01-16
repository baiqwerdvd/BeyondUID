import asyncio
import random

import aiohttp
from msgspec import convert

from gsuid_core.aps import scheduler
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment
from gsuid_core.subscribe import gs_subscribe
from gsuid_core.sv import SV

from ..beyonduid_config import PREFIX, BydConfig
from .draw_img import get_ann_img
from .get_data import check_bulletin_update, get_announcement
from .model import BulletinTargetData

sv_ann = SV("终末地公告")
sv_ann_sub = SV("订阅终末地公告", pm=3)

task_name_ann = "订阅终末地公告"
ann_minute_check: int = BydConfig.get_config("AnnMinuteCheck").data


@sv_ann.on_command(f"{PREFIX}公告")
async def ann_(bot: Bot, ev: Event):
    cid = ev.text

    if not cid.isdigit():
        raise Exception("公告ID不正确")

    data = await get_announcement(cid)
    img = await get_ann_img(data)
    title = data.title.replace("\\n", "")
    msg = [
        MessageSegment.text(f"[终末地公告] {title}\n"),
        MessageSegment.image(img),
    ]
    await bot.send(msg)


@sv_ann.on_command(f"{PREFIX}强制刷新全部公告")
async def force_ann_(bot: Bot, ev: Event):
    data = await check_bulletin_update()
    await bot.send(f"成功刷新{len(data)}条公告!")


@sv_ann.on_command(f"{PREFIX}获取当前Windows公告列表")
async def get_ann_list_(bot: Bot, ev: Event):
    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://game-hub.hypergryph.com/bulletin/aggregate?lang=zh-cn&platform=Windows&server=China&type=1&code=endfield_cbt2&hideDetail=1"
        ) as response:
            data = await response.json()

    data = convert(data.get("data", {}), BulletinTargetData)
    msg = ""
    for i in data.list_:
        title = i.title.replace("\\n", "")
        msg += f"CID: {i.cid} - {title}\n"

    await bot.send(msg)


@sv_ann_sub.on_fullmatch(f"{PREFIX}订阅公告")
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


@sv_ann_sub.on_fullmatch(
    (f"{PREFIX}取消订阅公告", f"{PREFIX}取消公告", f"{PREFIX}退订公告")
)
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


@scheduler.scheduled_job("interval", minutes=ann_minute_check)
async def check_ark_ann():
    logger.info("[终末地公告] 定时任务: 终末地公告查询..")

    updates = await check_bulletin_update()

    datas = await gs_subscribe.get_subscribe(task_name_ann)
    if not datas:
        logger.info("[终末地公告] 暂无群订阅")
        return

    if len(updates) == 0:
        logger.info("[终末地公告] 没有最新公告")
        return

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

import asyncio
import io
import sys
import uuid

import qrcode
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment
from gsuid_core.sv import SV
from gsuid_core.utils.image.convert import convert_img
from sklandcore.byd_client import BeyondClient
from sklandcore.constants import OAuth2AppCode
from sklandcore.models.auth import (
    BindingListData,
    CheckScanLoginStatusSuccessData,
    GrantCodeDataType1BindingAPI,
)
from sklandcore.platform import HypergryphDeviceWindows, PlatformEnum

from BeyondUID.utils.database.models import BeyondBind, BeyondUser

if sys.version_info >= (3, 11):
    from asyncio import timeout
else:
    from async_timeout import timeout

beyond_scan_login = SV("扫码登录")


@beyond_scan_login.on_command(("扫码登录", "扫码登陆"))
async def on_beyond_scan_login(bot: Bot, ev: Event):
    device_uuid = str(uuid.uuid4()).replace("-", "")
    device = HypergryphDeviceWindows(
        type="windows",
        device_id=device_uuid,
        device_id2=device_uuid,
        device_model=f"LAPTOP-{device_uuid[:8]}",
        device_type=PlatformEnum.WINDOWS,
    )

    client = BeyondClient(device)
    await client.initialize()

    scan_login_data = await client.generate_scan_login()

    qr = qrcode.QRCode()
    qr.add_data(scan_login_data.scanUrl)
    data = io.BytesIO()
    qr.make_image().save(data)

    app_names = [app.name for app in scan_login_data.enableScanAppList]

    await bot.send(
        [
            MessageSegment.at(ev.user_id),
            MessageSegment.text("\n"),
            MessageSegment.text("请使用以下应用扫码登录：\n" + " ".join(app_names)),
            MessageSegment.image(await convert_img(data.getvalue())),
        ],
    )

    scanCode = None

    try:
        async with timeout(60):
            while True:
                status = await client.check_scan_login_status(scan_login_data.scanId)
                logger.debug(f"Scan status: {status}")
                if isinstance(status, CheckScanLoginStatusSuccessData):
                    logger.info("Scan confirmed!")
                    scanCode = status.scanCode
                    break
                elif status in ["未扫码", "已扫码待确认"]:
                    logger.debug("Waiting for user to scan and confirm...")
                else:
                    logger.info("Scan login failed or expired.")
                    return
                await asyncio.sleep(3)
    except asyncio.TimeoutError:
        await bot.send("扫码登录超时，请重新发送指令获取二维码。")
        return

    # Step 1: Get account token and deviceToken via scan login
    account_token_data = await client._hypergryph_auth.token_by_scan_code(
        appCode=OAuth2AppCode.ENDFIELD,
        from_=0,
        scan_code=scanCode,
    )

    # Step 2: Get grant code via OAuth2 grant API
    binding_grant_data = await client._hypergryph_auth.get_grant_code(
        app_code=OAuth2AppCode.BINDING_API,
        token=account_token_data.token,
        device_token=account_token_data.deviceToken,
        type=1,
    )
    assert isinstance(binding_grant_data, GrantCodeDataType1BindingAPI)

    # Step 3: Get binding list via Binding API to get Endfield UID
    binding_list_data: BindingListData = await client._hypergryph_auth.get_binding_list(
        token=binding_grant_data.token,
        app_code=OAuth2AppCode.BINDING_LIST_ENDFIELD,
    )

    if len(binding_list_data.list) == 0 or len(binding_list_data.list[0].bindingList) == 0:
        await bot.send("扫码登录成功，但该Hypergryph账号下没有绑定任何Endfield账号。")
        return
    if len(binding_list_data.list[0].bindingList[0].roles) > 1:
        await bot.send(
            "扫码登录成功，但检测到该Endfield账号UID下有多个游戏角色，请指定uid\n"
            + ", ".join(role.roleId for role in binding_list_data.list[0].bindingList[0].roles),
        )
        try:
            async with timeout(60):
                while True:
                    resp = await bot.receive_mutiply_resp()
                    if resp is not None:
                        text = resp.text
                        if text in [role.roleId for role in binding_list_data.list[0].bindingList[0].roles]:
                            uid = text
                            break
                        else:
                            await bot.send("您输入的UID不在可选列表中，请重新输入。")
        except asyncio.TimeoutError:
            await bot.send("指定UID超时，登录流程终止。")
            return
    uid: str = binding_list_data.list[0].bindingList[0].uid
    roles = binding_list_data.list[0].bindingList[0].roles
    if len(roles) == 1:
        platform_roleid = roles[0].roleId
    elif len(roles) == 0:
        await bot.send("扫码登录成功，但该Endfield账号UID下没有任何游戏角色。")
        return
    else:
        logger.error(binding_list_data)
        await bot.send("发生未知错误，请重试。")
        return

    # 二次确认绑定
    msgs = [
        MessageSegment.at(ev.user_id),
        MessageSegment.text("\n"),
        MessageSegment.text("请确认绑定信息：\n"),
        MessageSegment.text(f"Endfield账号UID：{uid}\n"),
        MessageSegment.text(f"角色ID：{platform_roleid}\n"),
        MessageSegment.text("回复“确认”以绑定，或回复“取消”以终止登录流程。"),
    ]
    await bot.send(msgs)
    try:
        async with timeout(60):
            while True:
                resp = await bot.receive_mutiply_resp()
                if resp is not None:
                    text = resp.text
                    if text == "确认":
                        break
                    elif text == "取消":
                        await bot.send("绑定已取消。")
                        return
    except asyncio.TimeoutError:
        await bot.send("确认绑定超时，登录流程终止。")
        return

    await BeyondBind.insert_uid(
        bot_id=bot.bot_id,
        user_id=ev.user_id,
        uid=platform_roleid,
    )
    await BeyondUser.insert_or_update_user(
        bot_id=bot.bot_id,
        user_id=ev.user_id,
        uid=uid,
        platform_roleid=platform_roleid,
        hgtoken=account_token_data.token,
        device_token=account_token_data.deviceToken,
        device_json=device.model_dump_json(),
        platform="Windows",
    )

    await bot.send(f"扫码登录成功，Endfield账号UID：{uid}")

import asyncio
import sys
from typing import Literal

if sys.version_info >= (3, 11):
    from asyncio import timeout
else:
    from async_timeout import timeout

import httpx
from pydantic import BaseModel
from sklandcore.auth.hypergryph import HypergryphAuth
from sklandcore.auth.skland import SklandAuth
from sklandcore.constants import SKLAND_HEADERS, SKLAND_WEB_HEADERS, OAuth2AppCode
from sklandcore.did import getDid
from sklandcore.models.auth import HypergryphTokenData
from sklandcore.signature import get_web_signed_headers
from sklandcore.skd_client import SklandClient

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.sv import SV

from ..beyonduid_gamedata import TableCfg
from ..beyonduid_gamedata.i18n_text import get_i18n_text
from ..utils.database.models import BeyondBind, BeyondUser
from ..utils.error_reply import UID_HINT

ENDFIELD_POSITION_URL = "https://zonai.skland.com/web/v1/game/endfield/map/me/position"
ENDFIELD_POSITION_AGREE_POLICY_URL = "https://zonai.skland.com/web/v1/game/endfield/map/agree-policy"
POSITION_POLICY_RETRY_MESSAGE = "请同意获取角色位置的相关政策后重试"

sv_position = SV("终末地位置")


class EndfieldPosition(BaseModel):
    x: float
    y: float
    z: float


class EndfieldPositionData(BaseModel):
    pos: EndfieldPosition
    levelId: str
    isOnline: bool
    mapId: str


class EndfieldPositionResponse(BaseModel):
    code: int
    message: str
    timestamp: str
    data: EndfieldPositionData | None = None


class EndfieldCommonResponse(BaseModel):
    code: int
    message: str
    timestamp: str


def _resolve_table_name(table_row: dict[str, object] | None) -> str:
    if not table_row:
        return ""
    show_name = table_row.get("showName")
    return get_i18n_text(show_name)


def get_map_name(map_id: str) -> str:
    return _resolve_table_name(TableCfg.MapIdTable().get(map_id))


def get_level_name(level_id: str) -> str:
    return _resolve_table_name(TableCfg.LevelDescTable().get(level_id))


async def initialize(client: SklandClient, user: BeyondUser) -> None:
    if client._initialized:
        return
    client._initialized = True

    if user.device_id:
        client._device_id = user.device_id
    else:
        client._device_id = await getDid()
        user.device_id = client._device_id
        await BeyondUser.update_data(
            bot_id=user.bot_id,
            user_id=user.user_id,
            uid=user.uid,
            device_id=client._device_id,
        )

    client._http = httpx.AsyncClient(timeout=30.0)
    client._hypergryph_auth = HypergryphAuth(
        http_client=client._http,
        headers=SKLAND_HEADERS,
    )
    client._skland_auth = SklandAuth(
        http_client=client._http,
        device_id=client._device_id,
    )
    client._game_api = None


def _get_web_headers(
    url: str,
    method: Literal["GET", "POST"],
    body: dict | None,
    sign_token: str,
    cred: str,
    device_id: str,
) -> dict[str, str]:
    return get_web_signed_headers(
        url=url,
        method=method,
        body=body,
        base_headers=SKLAND_WEB_HEADERS,
        old_token=sign_token,
        cred=cred,
        device_id=device_id,
    )


def need_agree_position_policy(position_resp: EndfieldPositionResponse) -> bool:
    return position_resp.code != 0 and POSITION_POLICY_RETRY_MESSAGE in position_resp.message


async def get_position_info(
    client: SklandClient,
    role_id: str,
    server_id: str = "1",
) -> EndfieldPositionResponse:
    query = f"roleId={role_id}&serverId={server_id}"
    url = f"{ENDFIELD_POSITION_URL}?{query}"
    headers = _get_web_headers(
        url=url,
        method="GET",
        body=None,
        sign_token=client._token,
        cred=client._cred,
        device_id=client._device_id,
    )

    response = await client._http.get(url, headers=headers)
    response.raise_for_status()
    logger.debug(response.content)
    return EndfieldPositionResponse.model_validate_json(response.content)


async def agree_position_policy(
    client: SklandClient,
    role_id: str,
    server_id: str = "1",
) -> EndfieldCommonResponse:
    payload = {
        "roleId": role_id,
        "serverId": server_id,
    }
    headers = _get_web_headers(
        url=ENDFIELD_POSITION_AGREE_POLICY_URL,
        method="POST",
        body=payload,
        sign_token=client._token,
        cred=client._cred,
        device_id=client._device_id,
    )

    response = await client._http.post(
        ENDFIELD_POSITION_AGREE_POLICY_URL,
        headers=headers,
        json=payload,
    )
    response.raise_for_status()
    return EndfieldCommonResponse.model_validate_json(response.content)


async def _confirm_agree_position_policy(bot: Bot) -> bool | None:
    await bot.send("检测到需要同意获取角色位置的相关政策。\n" "回复“确认”以同意并继续查询，回复“取消”以终止。")
    try:
        async with timeout(60):
            while True:
                resp = await bot.receive_mutiply_resp()
                if resp is None:
                    continue
                text = resp.text.strip()
                if text == "确认":
                    return True
                if text == "取消":
                    return False
    except asyncio.TimeoutError:
        return None


def format_position_message(position_resp: EndfieldPositionResponse) -> str:
    position_title = "[endfield] [位置]"

    if position_resp.code != 0:
        return f"{position_title} 获取位置失败: {position_resp.message}"

    if not position_resp.data:
        return f"{position_title} 接口未返回位置数据"

    data = position_resp.data
    online_text = "在线" if data.isOnline else "离线"
    map_name = get_map_name(data.mapId)
    level_name = get_level_name(data.levelId)
    map_text = f"{map_name} ({data.mapId})" if map_name else data.mapId
    level_text = f"{level_name} ({data.levelId})" if level_name else data.levelId
    return (
        f"{position_title}\n"
        f"在线状态: {online_text}\n"
        f"地图: {map_text}\n"
        f"区域: {level_text}\n"
        f"坐标: x={data.pos.x:.3f}, y={data.pos.y:.3f}, z={data.pos.z:.3f}"
    )


async def get_endfield_position(
    platform_roleid: str,
    server_id: str = "1",
    bot: Bot | None = None,
) -> str:
    position_title = "[endfield] [位置]"
    logger.info(f"{position_title} {platform_roleid} 开始获取位置")

    user = await BeyondUser.get_user_only_by_roleid(platform_roleid=platform_roleid)
    if not user:
        return UID_HINT

    try:
        client = SklandClient("")
        await initialize(client, user)
        await client.login_by_token(
            app_code=OAuth2AppCode.SKLAND,
            account_token=HypergryphTokenData(
                token=user.hgtoken,
                hgId="",
                deviceToken=user.device_token,
            ),
        )

        position_resp = await get_position_info(
            client=client,
            role_id=platform_roleid,
            server_id=server_id,
        )
        if need_agree_position_policy(position_resp):
            if bot is None:
                return f"{position_title} {position_resp.message}"

            confirm_result = await _confirm_agree_position_policy(bot)
            if confirm_result is None:
                return f"{position_title} 确认超时，已取消位置查询。"
            if not confirm_result:
                return f"{position_title} 已取消位置查询。"

            agree_resp = await agree_position_policy(
                client=client,
                role_id=platform_roleid,
                server_id=server_id,
            )
            if agree_resp.code != 0:
                return f"{position_title} 同意政策失败: {agree_resp.message}"

            position_resp = await get_position_info(
                client=client,
                role_id=platform_roleid,
                server_id=server_id,
            )

        return format_position_message(position_resp)
    except httpx.HTTPStatusError as e:
        logger.error(f"{position_title} HTTP错误: {e}")
        return f"{position_title} 网络请求失败: {e.response.status_code}"
    except Exception as e:
        logger.exception(f"{position_title} 获取位置异常")
        return f"{position_title} 获取位置出错: {e!s}"


@sv_position.on_fullmatch("位置")
async def get_position_func(bot: Bot, ev: Event):
    logger.info(f"[Beyond] [位置] 用户: {ev.user_id}")
    uid = await BeyondBind.get_uid_by_game(ev.user_id, ev.bot_id)
    if uid is None:
        return await bot.send(UID_HINT)

    logger.info(f"[Beyond] [位置] UID: {uid}")
    result = await get_endfield_position(str(uid), bot=bot)
    await bot.send(result)
    return None

from enum import Enum
from typing import Literal

import httpx
from gsuid_core.logger import logger
from sklandcore.auth.hypergryph import HypergryphAuth
from sklandcore.auth.skland import SklandAuth
from sklandcore.constants import SKLAND_HEADERS, SKLAND_WEB_HEADERS, OAuth2AppCode
from sklandcore.did import getDid
from sklandcore.models.auth import HypergryphTokenData
from sklandcore.signature import get_web_signed_headers
from sklandcore.skd_client import SklandClient

from ..utils.database.models import BeyondUser
from ..utils.error_reply import UID_HINT

from .model import (
    EndfieldAttendanceInfoResponse,
    EndfieldAttendanceRecordResponse,
    EndfieldSignResultResponse,
)


class AlreadySignedError(Exception):
    """重复签到异常"""

    pass


class SklandGameName(Enum):
    Arknights = "arknights"
    Endfield = "endfield"


ENDFIELD_ATTENDANCE_URL = "https://zonai.skland.com/web/v1/game/endfield/attendance"
ENDFIELD_ATTENDANCE_RECORD_URL = "https://zonai.skland.com/web/v1/game/endfield/attendance/record"


def _handle_403_response(response: httpx.Response) -> None:
    if response.status_code != 403:
        return

    logger.warning(response.text)
    try:
        error_data = response.json()
        if error_data.get("code") == 10001 and "重复签到" in error_data.get("message", ""):
            raise AlreadySignedError("今日已签到")
    except (ValueError, KeyError, AlreadySignedError):
        raise
    except Exception:
        pass


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
    client._hypergryph_auth = HypergryphAuth(http_client=client._http, headers=SKLAND_HEADERS)
    client._skland_auth = SklandAuth(http_client=client._http, device_id=client._device_id)
    client._game_api = None


def _get_web_headers(
    url: str,
    method: Literal["GET", "POST"],
    body: dict | None,
    sign_token: str,
    cred: str,
    device_id: str,
) -> dict[str, str]:
    """获取Web API签名请求头"""
    return get_web_signed_headers(
        url=url,
        method=method,
        body=body,
        base_headers=SKLAND_WEB_HEADERS,
        old_token=sign_token,
        cred=cred,
        device_id=device_id,
    )


async def get_attendance_info(client: SklandClient) -> EndfieldAttendanceInfoResponse:
    """获取签到日历信息"""
    headers = _get_web_headers(
        url=ENDFIELD_ATTENDANCE_URL,
        method="GET",
        body=None,
        sign_token=client._token,
        cred=client._cred,
        device_id=client._device_id,
    )

    response = await client._http.get(
        ENDFIELD_ATTENDANCE_URL,
        headers=headers,
    )
    _handle_403_response(response)
    response.raise_for_status()

    return EndfieldAttendanceInfoResponse.model_validate_json(response.content)


async def get_attendance_record(client: SklandClient) -> EndfieldAttendanceRecordResponse:
    """获取签到记录"""
    headers = _get_web_headers(
        url=ENDFIELD_ATTENDANCE_RECORD_URL,
        method="GET",
        body=None,
        sign_token=client._token,
        cred=client._cred,
        device_id=client._device_id,
    )

    response = await client._http.get(
        ENDFIELD_ATTENDANCE_RECORD_URL,
        headers=headers,
    )
    _handle_403_response(response)
    response.raise_for_status()

    return EndfieldAttendanceRecordResponse.model_validate_json(response.content)


async def do_attendance(client: SklandClient, uid: str) -> EndfieldSignResultResponse:
    """执行签到"""
    headers = _get_web_headers(
        url=ENDFIELD_ATTENDANCE_URL,
        method="POST",
        body=None,
        sign_token=client._token,
        cred=client._cred,
        device_id=client._device_id,
    )
    # sk-game-role: f"{platform}_{uid}_1"
    sk_game_role = f"{headers['platform']}_{uid}_1"
    headers["sk-game-role"] = sk_game_role

    logger.debug(f"签到请求头: {headers}")

    response = await client._http.post(
        ENDFIELD_ATTENDANCE_URL,
        headers=headers,
    )
    logger.debug(f"签到返回内容: {response.text}")
    _handle_403_response(response)
    response.raise_for_status()

    return EndfieldSignResultResponse.model_validate_json(response.content)


async def sign_in(
    platform_roleid: str,
    game_name: SklandGameName = SklandGameName.Endfield,
) -> str:
    sign_title = f"[{game_name.value}] [签到]"
    logger.info(f"{sign_title} {platform_roleid} 开始执行签到")

    user = await BeyondUser.get_user_only_by_roleid(
        platform_roleid=platform_roleid,
    )
    if not user:
        return UID_HINT

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

    # 先检查今日是否已签到
    try:
        attendance_info = await get_attendance_info(client)
        if attendance_info.code != 0:
            return f"{sign_title} 获取签到信息失败: {attendance_info.message}"

        if attendance_info.data and attendance_info.data.hasToday:
            # 已经签到过，获取签到记录
            try:
                record_resp = await get_attendance_record(client)
            except AlreadySignedError:
                return f"{sign_title} 今日已签到！"
            except Exception as e:
                logger.error(f"{sign_title} 获取签到记录失败: {e}")
                return f"{sign_title} 获取签到记录失败: {e!s}"
            if record_resp.code == 0 and record_resp.data:
                records = record_resp.data.records
                resource_map = record_resp.data.resourceInfoMap
                if records:
                    award_names = []
                    for record in records:
                        if record.awardId in resource_map:
                            info = resource_map[record.awardId]
                            award_names.append(f"{info.name}×{info.count}")
                    return f"{sign_title} 今日已签到！\n获得: {', '.join(award_names)}"
            return f"{sign_title} 今日已签到！"

        # 执行签到
        sign_result = await do_attendance(client, platform_roleid)
        if sign_result.code != 0:
            return f"{sign_title} 签到失败: {sign_result.message}"

        if sign_result.data:
            award_ids = sign_result.data.awardIds
            resource_map = sign_result.data.resourceInfoMap
            award_names = []
            for award in award_ids:
                if award.id in resource_map:
                    info = resource_map[award.id]
                    award_names.append(f"{info.name}×{info.count}")

            tomorrow_awards = sign_result.data.tomorrowAwardIds
            tomorrow_names = []
            for award in tomorrow_awards:
                if award.id in resource_map:
                    info = resource_map[award.id]
                    tomorrow_names.append(f"{info.name}×{info.count}")

            result_msg = f"{sign_title} 签到成功！\n"
            result_msg += f"✨ 今日获得: {', '.join(award_names)}\n"
            if tomorrow_names:
                result_msg += f"📅 明日奖励: {', '.join(tomorrow_names)}"
            return result_msg.strip()

        return f"{sign_title} 签到成功！"

    except AlreadySignedError:
        return f"{sign_title} 今日已签到！"
    except httpx.HTTPStatusError as e:
        logger.error(f"{sign_title} HTTP错误: {e}")
        return f"{sign_title} 网络请求失败: {e.response.status_code}"
    except Exception as e:
        logger.exception(f"{sign_title} 签到异常")
        return f"{sign_title} 签到出错: {e!s}"

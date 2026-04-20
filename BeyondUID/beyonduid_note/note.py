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
from .model import EndfieldStatisticResponse

ENDFIELD_STATISTIC_URL = "https://zonai.skland.com/api/v1/game/endfield/statistic"


async def _initialize(client: SklandClient, user: BeyondUser) -> None:
    """初始化 SklandClient（复用签到模块的初始化逻辑）"""
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
    method: str,
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


async def get_statistic_data(client: SklandClient) -> EndfieldStatisticResponse:
    """获取每日统计数据"""
    headers = _get_web_headers(
        url=ENDFIELD_STATISTIC_URL,
        method="GET",
        body=None,
        sign_token=client._token,
        cred=client._cred,
        device_id=client._device_id,
    )

    response = await client._http.get(
        ENDFIELD_STATISTIC_URL,
        headers=headers,
    )
    response.raise_for_status()

    return EndfieldStatisticResponse.model_validate_json(response.content)


async def get_daily_info(platform_roleid: str) -> str:
    """获取每日信息文字版"""
    sign_title = "[终末地] [每日信息]"
    logger.info(f"{sign_title} {platform_roleid} 开始查询")

    user = await BeyondUser.get_user_only_by_roleid(
        platform_roleid=platform_roleid,
    )
    if not user:
        return UID_HINT

    try:
        client = SklandClient("")
        await _initialize(client, user)
        await client.login_by_token(
            app_code=OAuth2AppCode.SKLAND,
            account_token=HypergryphTokenData(
                token=user.hgtoken,
                hgId="",
                deviceToken=user.device_token,
            ),
        )

        resp = await get_statistic_data(client)
        if resp.code != 0:
            return f"{sign_title} 查询失败: {resp.message}"

        if not resp.data:
            return f"{sign_title} 查询失败: 返回数据为空"

        stat = resp.data.data

        # 构造文字信息
        lines = [
            f"{'=' * 20}",
            f"📊 终末地每日信息",
            f"{'=' * 20}",
            f"",
            f"🎖️ 战令等级: {stat.bp.current}/{stat.bp.total}",
            f"📋 每日活跃: {stat.dailyMission.current}/{stat.dailyMission.total}",
            f"📅 周常任务: {stat.weeklyMission.current}/{stat.weeklyMission.total}",
            f"⚔️ 副本挑战: {stat.dungeon.current}次 (累计{stat.dungeon.total}次)",
            f"✅ 今日签到: {'已签到' if stat.signIn else '未签到'}",
        ]

        return "\n".join(lines)

    except httpx.HTTPStatusError as e:
        logger.error(f"{sign_title} HTTP错误: {e}")
        return f"{sign_title} 网络请求失败: {e.response.status_code}"
    except Exception as e:
        logger.exception(f"{sign_title} 查询异常")
        return f"{sign_title} 查询出错: {e!s}"

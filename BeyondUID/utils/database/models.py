from typing import Any, ClassVar, TypeVar

from gsuid_core.utils.database.base_models import (
    Bind,
    Push,
    T_BaseIDModel,
    with_session,
)
from gsuid_core.utils.database.models import User
from gsuid_core.webconsole.mount_app import GsAdminModel, PageSchema, site
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlmodel import Field

T_BeyondUser = TypeVar("T_BeyondUser", bound="BeyondUser")


class BeyondBind(Bind, table=True):
    __table_args__: ClassVar[dict[str, Any]] = {"extend_existing": True}

    uid: str | None = Field(default=None, title="当前角色ID，需要注意，这里的UID是终末地的角色ID")


class BeyondUser(User, table=True):
    __table_args__: ClassVar[dict[str, Any]] = {"extend_existing": True}

    uid: str = Field(default=None, title="游戏UID")
    platform_roleid: str = Field(default=None, title="当前角色ID")
    hgtoken: str = Field(default="", title="hgtoken")
    device_id: str = Field(default="", title="设备ID")
    device_token: str = Field(default="", title="设备Token")
    device_json: str = Field(default="", title="设备信息JSON")
    platform: str = Field(default="Windows", title="平台")
    bbs_sign_switch: str = Field(default="off", title="自动社区签到")
    created_time: int | None = Field(default=None, title="创建时间")
    last_used_time: int | None = Field(default=None, title="最后使用时间")

    @classmethod
    @with_session
    async def get_uid_and_platform_roleid_by_game(
        cls: type[T_BeyondUser],
        session: AsyncSession,
        user_id: str,
        bot_id: str,
    ) -> tuple[str | None, str | None] | None:
        obj = await cls.base_select_data(
            bot_id=bot_id,
            user_id=user_id,
        )
        if obj:
            return obj.uid, obj.platform_roleid
        return None

    @classmethod
    @with_session
    async def get_user_by_roleid(
        cls: type[T_BeyondUser],
        session: AsyncSession,
        bot_id: str,
        user_id: str,
        platform_roleid: str,
    ) -> T_BeyondUser | None:
        obj = await cls.base_select_data(
            bot_id=bot_id,
            user_id=user_id,
            platform_roleid=platform_roleid,
        )
        return obj

    @classmethod
    @with_session
    async def get_user_only_by_roleid(
        cls: type[T_BeyondUser],
        session: AsyncSession,
        platform_roleid: str,
    ) -> T_BeyondUser | None:
        obj = await cls.base_select_data(
            platform_roleid=platform_roleid,
        )
        return obj

    @classmethod
    @with_session
    async def insert_or_update_user(
        cls: type[T_BeyondUser],
        session: AsyncSession,
        bot_id: str,
        user_id: str,
        uid: str,
        platform_roleid: str,
        hgtoken: str,
        device_id: str = "",
        device_token: str = "",
        device_json: str = "",
        platform: str = "Windows",
    ) -> T_BeyondUser:
        obj = await cls.base_select_data(
            bot_id=bot_id,
            user_id=user_id,
            uid=uid,
        )
        if obj:
            obj.hgtoken = hgtoken
            obj.device_id = device_id
            obj.device_token = device_token
            obj.device_json = device_json
            obj.platform = platform
            session.add(obj)
            await session.commit()
            await session.refresh(obj)
            return obj
        obj = cls(
            bot_id=bot_id,
            user_id=user_id,
            cookie="",
            uid=uid,
            platform_roleid=platform_roleid,
            hgtoken=hgtoken,
            device_id=device_id,
            device_token=device_token,
            device_json=device_json,
            platform=platform,
        )
        session.add(obj)
        await session.commit()
        await session.refresh(obj)
        return obj

    @classmethod
    @with_session
    async def get_all_beyond_users(
        cls: type[T_BeyondUser],
        session: AsyncSession,
    ) -> list[T_BeyondUser]:
        """获取所有已绑定的用户"""
        stmt = select(cls).where(cls.hgtoken != "").where(cls.hgtoken.isnot(None))  # type: ignore
        result = await session.execute(stmt)
        return list(result.scalars().all())


class BeyondPush(Push, table=True):
    __table_args__: ClassVar[dict[str, Any]] = {"extend_existing": True}

    uid: str | None = Field(default=None, title="终末地UID")
    version_push: bool | None = Field(default=False, title="版本更新推送")
    version_is_push: bool | None = Field(default=False, title="版本更新是否已经推送")

    @classmethod
    async def insert_push_data(cls, bot_id: str, uid: str, skd_uid: str):
        await cls.full_insert_data(
            bot_id=bot_id,
            uid=uid,
            version_push=False,
            version_is_push=False,
        )

    @classmethod
    @with_session
    async def base_select_data(  # pyright: ignore[reportIncompatibleMethodOverride]
        cls: type[T_BaseIDModel], session: AsyncSession, **data
    ) -> T_BaseIDModel | None:
        stmt = select(cls)
        for k, v in data.items():
            stmt = stmt.where(getattr(cls, k) == v)
        result = await session.execute(stmt)
        data = result.scalars().all()
        return data[0] if data else None

    @classmethod
    async def update_push_data(cls, uid: str, data: dict) -> bool:
        retcode = -1
        if await cls.data_exist(uid=uid):
            retcode = await cls.update_data_by_uid(
                uid,
                cls.bot_id,
                None,
                **data,
            )
        return not bool(retcode)

    @classmethod
    async def select_push_data(cls: type[T_BaseIDModel], uid: str) -> T_BaseIDModel | None:
        return await cls.base_select_data(uid=uid)

    @classmethod
    async def push_exists(cls, uid: str) -> bool:
        return await cls.data_exist(uid=uid)


@site.register_admin
class BeyondBindadmin(GsAdminModel):
    pk_name = "id"
    page_schema = PageSchema(label="终末地绑定管理", icon="fa fa-users")  # type: ignore

    # 配置管理模型
    model = BeyondBind


@site.register_admin
class BeyondPushadmin(GsAdminModel):
    pk_name = "id"
    page_schema = PageSchema(label="终末地推送管理", icon="fa fa-database")  # type: ignore

    # 配置管理模型
    model = BeyondPush

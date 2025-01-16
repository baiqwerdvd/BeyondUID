from typing import Type

from gsuid_core.utils.database.base_models import (
    BaseModel,
    Bind,
    Push,
    T_BaseIDModel,
    User,
    with_session,
)
from gsuid_core.webconsole.mount_app import GsAdminModel, PageSchema, site
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlmodel import Field


class BeyondBind(Bind, table=True):
    uid: str | None = Field(default=None, title="终末地UID")


class BeyondPush(Push, table=True):
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
    async def base_select_data(
        cls: Type[T_BaseIDModel], session: AsyncSession, **data
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
    async def select_push_data(cls: Type[T_BaseIDModel], uid: str) -> T_BaseIDModel | None:
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

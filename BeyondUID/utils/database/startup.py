from gsuid_core.server import on_core_start
from gsuid_core.utils.database.base_models import async_maker
from sqlalchemy.sql import text

exec_list = []


@on_core_start
async def ark_adapter():
    async with async_maker() as session:
        for _t in exec_list:
            try:
                await session.execute(text(_t))
                await session.commit()
            except:  # noqa: E722
                pass

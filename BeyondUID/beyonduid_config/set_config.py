# from gsuid_core.bot import Bot
# from gsuid_core.logger import logger
# from gsuid_core.models import Event
# from gsuid_core.subscribe import Subscribe, gs_subscribe
# from gsuid_core.sv import SV

# from ..utils.database.models import BeyondPush, BeyondUser
# from ..utils.error_reply import UID_HINT
# from ..utils.error_reply import prefix as P

# from .beyond_config import BeyondConfig
# from .config_default import CONIFG_DEFAULT

PUSH_MAP = {
    "版本更新": "version",
}


# async def set_config_func(
#     bot_id: str,
#     config_name: str = "",
#     uid: str = "0",
#     user_id: str = "",
#     option: str = "0",
#     query: bool | None = None,
#     is_admin: bool = False,
# ):
#     for _name in CONIFG_DEFAULT:
#         config = CONIFG_DEFAULT[_name]
#         if config.title == config_name and isinstance(config.data, bool):
#             name = _name
#             break
#     else:
#         logger.info(
#             f"uid: {uid}, option: {option}, config_name: {config_name}",
#         )
#         if config_name in PRIV_MAP:
#             # 执行设置
#             # await BeyondUser.update_user_data(
#             #     uid,
#             #     {
#             #         f"{PRIV_MAP[config_name]}_switch": option,
#             #     },
#             # )
#             pass
#         elif config_name.replace("推送", "") in PUSH_MAP:
#             await BeyondPush.update_push_data(
#                 uid,
#                 {
#                     f"{PUSH_MAP[config_name.replace('推送', '')]}_push": option,
#                 },
#             )
#         else:
#             return "该配置项不存在!"

#         if option == "on":
#             succeed_msg = "开启至私聊消息!"
#         elif option == "off":
#             succeed_msg = "关闭!"
#         else:
#             succeed_msg = f"开启至群{option}"
#         return f"{config_name}已{succeed_msg}"

#     if is_admin:
#         logger.info(f"config_name:{config_name},query:{query}")
#         # 执行设置
#         if query is not None:
#             BeyondConfig.set_config(name, query)
#             im = "成功设置{}为{}。".format(config_name, "开" if query else "关")
#         else:
#             im = "未传入参数query!"
#     else:
#         im = "只有管理员才能设置群服务。"
#     return im

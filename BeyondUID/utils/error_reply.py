from copy import deepcopy

from gsuid_core.sv import get_plugin_available_prefix
from gsuid_core.utils.error_reply import ERROR_CODE

prefix = get_plugin_available_prefix("BeyondUID")

UID_HINT = f"你还没有绑定过哦！\n请使用[{prefix}扫码登录]命令绑定!"


BEYOND_ERROR_CODE = deepcopy(ERROR_CODE)


def get_error(retcode: int) -> str:
    msg_list = [f"❌错误代码为: {retcode}"]
    if retcode in BEYOND_ERROR_CODE:
        msg_list.append(f"📝错误信息: {BEYOND_ERROR_CODE[retcode]}")
    return "\n".join(msg_list)

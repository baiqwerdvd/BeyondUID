from gsuid_core.utils.plugins_config.models import (
    GSC,
    GsIntConfig,
)

CONIFG_DEFAULT: dict[str, GSC] = {
    "AnnMinuteCheck": GsIntConfig(
        "公告推送时间检测（单位min）", "公告推送时间检测（单位min）", 1, 60
    ),
}

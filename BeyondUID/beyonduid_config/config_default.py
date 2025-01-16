from gsuid_core.utils.plugins_config.models import (
    GSC,
    GsIntConfig,
    GsStrConfig,
)

CONIFG_DEFAULT: dict[str, GSC] = {
    "BydPrefix": GsStrConfig(
        "插件命令前缀（确认无冲突再修改）",
        "用于设置BeyondUID前缀的配置",
        "byd",
    ),
    "AnnMinuteCheck": GsIntConfig(
        "公告推送时间检测（单位min）", "公告推送时间检测（单位min）", 1, 60
    ),
}

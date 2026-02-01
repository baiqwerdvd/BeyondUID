from gsuid_core.utils.plugins_config.models import (
    GSC,
    GsBoolConfig,
    GsIntConfig,
    GsListStrConfig,
)

CONIFG_DEFAULT: dict[str, GSC] = {
    "SignTime": GsListStrConfig("每晚签到时间设置", "每晚Skland签到时间设置(时,分)", ["0", "38"]),
    "PrivateSignReport": GsBoolConfig(
        "签到私聊报告",
        "关闭后将不再给任何人推送当天签到任务完成情况",
        False,
    ),
    "SchedSignin": GsBoolConfig(
        "定时签到",
        "开启后每晚00:30将开始自动签到任务",
        True,
    ),
    "AnnMinuteCheck": GsIntConfig(
        "公告推送时间检测（单位min）", "公告推送时间检测（单位min）", 1, 60
    ),
}

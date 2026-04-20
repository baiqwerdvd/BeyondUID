from pydantic import BaseModel


class BPInfo(BaseModel):
    """战令信息"""

    current: int
    total: int


class DailyMissionInfo(BaseModel):
    """每日任务信息"""

    current: int
    total: int


class DungeonInfo(BaseModel):
    """副本信息"""

    current: int
    total: int
    maxTs: str = "0"


class WeeklyMissionInfo(BaseModel):
    """周常任务信息"""

    current: int
    total: int


class EndfieldStatisticData(BaseModel):
    """Endfield统计数据内层"""

    bp: BPInfo
    dailyMission: DailyMissionInfo
    dungeon: DungeonInfo
    pic: str = ""
    signIn: bool
    weeklyMission: WeeklyMissionInfo


class EndfieldStatisticOuterData(BaseModel):
    """Endfield统计数据外层"""

    data: EndfieldStatisticData
    signUrl: str = ""
    bindUrl: str = ""
    openUrl: str = ""
    detailUrl: str = ""
    jumpUrl: str = ""
    currentTs: str = ""
    gameLogo: str = ""


class EndfieldStatisticResponse(BaseModel):
    """GET /api/v1/game/endfield/statistic 完整响应"""

    code: int
    message: str
    timestamp: str
    data: EndfieldStatisticOuterData | None = None

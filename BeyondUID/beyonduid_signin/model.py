from pydantic import BaseModel

# ============ Endfield Attendance Models ============


class EndfieldResourceInfo(BaseModel):
    """Endfield签到资源信息"""

    id: str
    count: int
    name: str
    icon: str


class EndfieldCalendarItem(BaseModel):
    """Endfield签到日历项"""

    awardId: str
    available: bool
    done: bool


class EndfieldAttendanceInfo(BaseModel):
    """GET /attendance 响应数据"""

    currentTs: str
    calendar: list[EndfieldCalendarItem]
    first: list[EndfieldCalendarItem]
    resourceInfoMap: dict[str, EndfieldResourceInfo]
    hasToday: bool


class EndfieldAttendanceRecord(BaseModel):
    """签到记录项"""

    ts: str
    awardId: str


class EndfieldAttendanceRecordData(BaseModel):
    """GET /attendance/record 响应数据"""

    records: list[EndfieldAttendanceRecord]
    resourceInfoMap: dict[str, EndfieldResourceInfo]


class EndfieldAwardId(BaseModel):
    """签到奖励ID"""

    id: str
    type: int  # 1: first奖励, 2: 日常奖励


class EndfieldSignResult(BaseModel):
    """POST /attendance 签到结果"""

    ts: str
    awardIds: list[EndfieldAwardId]
    resourceInfoMap: dict[str, EndfieldResourceInfo]
    tomorrowAwardIds: list[EndfieldAwardId]


class EndfieldBaseResponse(BaseModel):
    """Endfield API基础响应"""

    code: int
    message: str
    timestamp: str


class EndfieldAttendanceInfoResponse(EndfieldBaseResponse):
    """GET /attendance 完整响应"""

    data: EndfieldAttendanceInfo | None = None


class EndfieldAttendanceRecordResponse(EndfieldBaseResponse):
    """GET /attendance/record 完整响应"""

    data: EndfieldAttendanceRecordData | None = None


class EndfieldSignResultResponse(EndfieldBaseResponse):
    """POST /attendance 完整响应"""

    data: EndfieldSignResult | None = None

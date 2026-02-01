from enum import Enum

from msgspec import Struct, field


class Platform(Enum):
    WINDOWS = "Windows"
    ANDROID = "Android"
    IOS = "iOS"
    PLAYSTATION = "PlayStation"


class DisplayType(Enum):
    PICTURE = "picture"
    RICH_TEXT = "rich_text"


class BulletinTargetDataItem(Struct):
    cid: str
    type: int
    tab: str
    orderType: int
    orderWeight: int
    displayType: DisplayType
    startAt: int
    focus: int
    title: str


class BulletinOnlineListItem(Struct):
    cid: str
    version: int
    needRedDot: bool
    needPopup: bool


class BulletinTargetData(Struct):
    topicCid: str = ""
    type: int = 1
    platform: str = "Windows"
    server: str = "#DEFAULT"
    channel: str = "1"
    subChannel: str = "#DEFAULT"
    lang: str = "zh-cn"
    key: str = "1:Windows:#DEFAULT:1:#DEFAULT:zh-cn"
    version: str = "fb3c9f2e794067115b9037624ff8940c"
    onlineList: list[BulletinOnlineListItem] = field(name="onlineList", default_factory=list)
    popupVersion: int = 0
    updatedAt: int = 0
    list_: list[BulletinTargetDataItem] = field(name="list", default_factory=list)


class BulletinTarget(Struct):
    Windows: BulletinTargetData
    Android: BulletinTargetData
    iOS: BulletinTargetData
    PlayStation: BulletinTargetData


class BulletinDataData(Struct):
    linkType: int
    url: str | None = None
    link: str | None = None
    html: str | None = None


class BulletinData(Struct):
    cid: str
    type: int
    tab: str
    orderType: int
    orderWeight: int
    displayType: DisplayType
    focus: int
    startAt: int
    title: str
    header: str
    jumpButton: str | None
    data: BulletinDataData
    needRedDot: bool
    needPopup: bool
    version: int


class BulletinAggregate(Struct):
    data: dict[str, BulletinData]
    update: dict[str, BulletinData]
    target: BulletinTarget

    @staticmethod
    def default() -> "BulletinAggregate":
        return BulletinAggregate(
            data={},
            update={},
            target=BulletinTarget(
                Windows=BulletinTargetData(),
                Android=BulletinTargetData(),
                iOS=BulletinTargetData(),
                PlayStation=BulletinTargetData(),
            ),
        )

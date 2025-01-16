from typing import Any

from msgspec import Struct, field


class BulletinTargetDataItem(Struct):
    cid: str
    type: int
    tab: str
    orderType: int
    orderWeight: int
    displayType: str
    startAt: int
    focus: int
    title: str


class BulletinTargetDataPopup(Struct):
    popupList: list[Any]
    defaultPopup: str


# {
#     "topicCid": "2113",
#     "type": 1,
#     "platform": "Windows",
#     "server": "#DEFAULT",
#     "channel": "#DEFAULT",
#     "lang": "zh-cn",
#     "key": "1:Windows:#DEFAULT:#DEFAULT:zh-cn",
#     "version": "49b6d014b5ceccebda48f108b9597fa3",
#     "onlineList": ["9821"],
#     "popupList": [],
#     "popupVersion": 0,
#     "updatedAt": 1736983800,
#     "list": [
#         {
#             "cid": "9821",
#             "type": 1,
#             "tab": "news",
#             "orderType": 1,
#             "orderWeight": 1,
#             "displayType": "rich_text",
#             "startAt": 1736983800,
#             "focus": 0,
#             "title": "测试须知",
#         }
#     ],
# }


class BulletinTargetData(Struct):
    topicCid: str = field(name="topicCid", default="")
    type: int = field(name="type", default=1)
    platform: str = field(name="platform", default="Windows")
    server: str = field(name="server", default="#DEFAULT")
    channel: str = field(name="channel", default="#DEFAULT")
    lang: str = field(name="lang", default="zh-cn")
    key: str = field(name="key", default="")
    version: str = field(name="version", default="")
    onlineList: list[str] = field(name="onlineList", default_factory=list)
    popupList: list[Any] = field(name="popupList", default_factory=list)
    popupVersion: int = field(name="popupVersion", default=0)
    updatedAt: int = field(name="updatedAt", default=0)
    list_: list[BulletinTargetDataItem] = field(name="list", default_factory=list)


class BulletinTarget(Struct):
    Windows: BulletinTargetData = field(default_factory=BulletinTargetData)


class BulletinDataData(Struct):
    html: str


class BulletinData(Struct):
    cid: str
    data: BulletinDataData
    displayType: str
    focus: int
    header: str
    jumpButton: str | None
    orderType: int
    orderWeight: int
    startAt: int
    tab: str
    title: str
    type: int


class BulletinAggregate(Struct):
    data: dict[str, BulletinData] = field(default_factory=dict)
    update: dict[str, BulletinData] = field(default_factory=dict)
    target: BulletinTarget = field(default_factory=BulletinTarget)

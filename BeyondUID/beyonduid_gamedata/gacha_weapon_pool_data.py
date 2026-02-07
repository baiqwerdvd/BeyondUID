from enum import Enum

from pydantic import BaseModel

from .i18n_text import I18nText


class WeaponGachaPoolType(Enum):
    Normal = "Normal"


class GachaWeaponPoolData(BaseModel):
    clientTopTimeId: str
    doublePoolNodeUIPrefab: str
    finalIndex: int
    id: str
    index: int
    intervalAutoRewardIds: list[str]
    loopRewardShowTag: I18nText
    loopRewardShowTitle: I18nText
    name: I18nText
    poolNodeUIPrefab: str
    smallPoolIcon: str
    smallPoolIconFar: str
    sortId: int
    ticketGachaTenLt: str
    type: str
    upWeaponDoublePoolIcon: str
    upWeaponIcon: str
    upWeaponIds: list[str]

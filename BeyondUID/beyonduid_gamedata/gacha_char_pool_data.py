from enum import Enum

from pydantic import BaseModel

from .i18n_text import I18nText


class CharacterGachaPoolType(Enum):
    Special = "Special"
    Beginner = "Beginner"
    Standard = "Standard"


class GachaCharPoolData(BaseModel):
    color: str
    cumulativeRewardIds: list[str]
    desc: I18nText
    id: str
    intervalAutoRewardIds: list[str]
    mailBannerImage: str
    name: I18nText
    nameImage: str
    sortId: int
    tabGradientColor: str
    tabImage: str
    testimonialRewardItemId: str
    textColor: str
    ticketGachaSingleLt: str
    ticketGachaTenLt: str
    trialActivityJumpId: str
    type: str
    uiPrefab: str
    upCharDesc: I18nText
    upCharIds: list[str]

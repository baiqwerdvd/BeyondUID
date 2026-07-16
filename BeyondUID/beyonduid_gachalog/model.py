from enum import Enum
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field


class BaseGachaRecordItem(BaseModel):
    """Base gacha record item model."""

    poolId: str
    poolName: str
    rarity: int
    gachaTs: str
    seqId: str


class CharRecordItem(BaseGachaRecordItem):
    """Single gacha record item model."""

    charId: str
    charName: str
    isFree: bool
    isNew: bool


class WeaponRecordItem(BaseGachaRecordItem):
    """Single gacha record item model."""

    weaponId: str
    weaponName: str
    weaponType: str
    isNew: bool


T = TypeVar("T")


class GachaRecordEvent(BaseModel):
    """Common fields shared by draw and non-draw gacha events."""

    model_config = ConfigDict(extra="allow")

    kind: str = "draw"
    nameText: str | None = None
    poolId: str
    poolName: str
    gachaTs: str
    seqId: str


class GiftRecordItem(GachaRecordEvent):
    """Non-draw reward event stored separately from draw records."""

    source: Literal["char", "weapon"]


class GachaRecordList(BaseModel):
    """Gacha record list model."""

    list: list[GachaRecordEvent]
    hasMore: bool


class EFResponse(BaseModel, Generic[T]):
    code: int
    msg: str
    data: T


class CharacterGachaPoolType(Enum):
    Special = "E_CharacterGachaPoolType_Special"
    Joint = "E_CharacterGachaPoolType_Joint"
    Beginner = "E_CharacterGachaPoolType_Beginner"
    Standard = "E_CharacterGachaPoolType_Standard"


class GachaPoolAllCharacterItem(BaseModel):
    id: str
    name: str
    rarity: int


class GachaPoolRotateItem(BaseModel):
    name: str
    times: int


class GachaPoolInfo(BaseModel):
    pool_gacha_type: str
    pool_name: str
    pool_type: str
    up6_name: str
    up6_image: str
    up5_name: str
    up5_image: str
    up6_item_name: str
    rotate_image: str
    ticket_name: str
    ticket_ten_name: str
    all: list[GachaPoolAllCharacterItem]
    rotate_list: list[GachaPoolRotateItem]


class GachaPoolInfoData(BaseModel):
    pool: dict
    timezone: int


class PoolExportInfo(BaseModel):
    uid: str
    lang: str
    timezone: int
    exportTimestamp: int
    version: str


class GachaPoolExport(BaseModel):
    info: PoolExportInfo
    charList: list[CharRecordItem]
    weaponList: list[WeaponRecordItem]
    giftList: list[GiftRecordItem] = Field(default_factory=list)


class WeaponGachaPoolItem(BaseModel):
    poolId: str
    poolName: str

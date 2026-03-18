import json
from typing import Any, ClassVar

from pydantic import BaseModel

from ..utils.resource.RESOURCE_PATH import TABLE_CFG_PATH
from .gacha_char_pool_data import GachaCharPoolData
from .gacha_weapon_pool_data import GachaWeaponPoolData


class GachaCharPoolTable(BaseModel):
    data: dict[str, GachaCharPoolData]


class GachaWeaponPoolTable(BaseModel):
    data: dict[str, GachaWeaponPoolData]


class TableCfg:
    _cache: ClassVar[dict[str, Any]] = {}

    @classmethod
    def _load_json(cls, filename: str) -> dict[str, Any]:
        with open(TABLE_CFG_PATH / filename, encoding="utf-8") as f:
            return json.load(f)

    @classmethod
    def GachaCharPoolTable(cls) -> dict[str, GachaCharPoolData]:
        if "GachaCharPoolTable" not in cls._cache:
            data = cls._load_json("GachaCharPoolTable.json")
            table = GachaCharPoolTable.model_validate({"data": data})
            cls._cache["GachaCharPoolTable"] = table.data
        return cls._cache["GachaCharPoolTable"]

    @classmethod
    def GachaWeaponPoolTable(cls) -> dict[str, GachaWeaponPoolData]:
        if "GachaWeaponPoolTable" not in cls._cache:
            data = cls._load_json("GachaWeaponPoolTable.json")
            table = GachaWeaponPoolTable.model_validate({"data": data})
            cls._cache["GachaWeaponPoolTable"] = table.data
        return cls._cache["GachaWeaponPoolTable"]

    @classmethod
    def reload(cls) -> None:
        cls._cache.clear()

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
    def _load_raw_table(cls, cache_key: str, filename: str) -> dict[str, Any]:
        if cache_key not in cls._cache:
            cls._cache[cache_key] = cls._load_json(filename)
        return cls._cache[cache_key]

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
    def CharacterTable(cls) -> dict[str, dict[str, Any]]:
        return cls._load_raw_table("CharacterTable", "CharacterTable.json")

    @classmethod
    def WeaponBasicTable(cls) -> dict[str, dict[str, Any]]:
        return cls._load_raw_table("WeaponBasicTable", "WeaponBasicTable.json")

    @classmethod
    def ItemTable(cls) -> dict[str, dict[str, Any]]:
        return cls._load_raw_table("ItemTable", "ItemTable.json")

    @classmethod
    def CharWpnRecommendTable(cls) -> dict[str, dict[str, Any]]:
        return cls._load_raw_table("CharWpnRecommendTable", "CharWpnRecommendTable.json")

    @classmethod
    def CharWpnSkillRecommendTable(cls) -> dict[str, dict[str, Any]]:
        return cls._load_raw_table("CharWpnSkillRecommendTable", "CharWpnSkillRecommendTable.json")

    @classmethod
    def GemTable(cls) -> dict[str, dict[str, Any]]:
        return cls._load_raw_table("GemTable", "GemTable.json")

    @classmethod
    def RewardTable(cls) -> dict[str, dict[str, Any]]:
        return cls._load_raw_table("RewardTable", "RewardTable.json")

    @classmethod
    def DomainDataTable(cls) -> dict[str, dict[str, Any]]:
        return cls._load_raw_table("DomainDataTable", "DomainDataTable.json")

    @classmethod
    def WorldEnergyPointTable(cls) -> dict[str, dict[str, Any]]:
        return cls._load_raw_table("WorldEnergyPointTable", "WorldEnergyPointTable.json")

    @classmethod
    def GachaPoolWeaponPresetTable(cls) -> dict[str, dict[str, Any]]:
        return cls._load_raw_table("GachaPoolWeaponPresetTable", "GachaPoolWeaponPresetTable.json")

    @classmethod
    def GachaPoolCharPresetTable(cls) -> dict[str, dict[str, Any]]:
        return cls._load_raw_table("GachaPoolCharPresetTable", "GachaPoolCharPresetTable.json")

    @classmethod
    def GemPresetTable(cls) -> dict[str, dict[str, Any]]:
        return cls._load_raw_table("GemPresetTable", "GemPresetTable.json")

    @classmethod
    def WorldEnergyPointGroupTable(cls) -> dict[str, dict[str, Any]]:
        return cls._load_raw_table("WorldEnergyPointGroupTable", "WorldEnergyPointGroupTable.json")

    @classmethod
    def reload(cls) -> None:
        from .i18n_text import clear_i18n_text_cache

        cls._cache.clear()
        clear_i18n_text_cache()
        for cache_cls_name in ("CharacterInfoTable", "WeaponInfoTable", "WeaponGemInfoTable"):
            cache_cls = globals().get(cache_cls_name)
            if cache_cls is not None:
                cache_cls.clear_cache()


from .character_weapon_info import CharacterDetailData  # noqa: E402
from .character_weapon_info import CharacterInfoTable, WeaponDetailData, WeaponInfoTable
from .weapon_gem_info import WeaponGemInfoTable  # noqa: E402
from .weapon_gem_info import WeaponGemRecommendationData

__all__ = [
    "CharacterDetailData",
    "CharacterInfoTable",
    "GachaCharPoolTable",
    "GachaWeaponPoolTable",
    "TableCfg",
    "WeaponDetailData",
    "WeaponGemInfoTable",
    "WeaponGemRecommendationData",
    "WeaponInfoTable",
]

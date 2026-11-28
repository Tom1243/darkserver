"""Extract treasure reference IDs and English labels from the seed SQL dump."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Iterator


CLASS_NAMES = [
    "MOTORCYCLE", "POTION", "WATER", "HOLYWATER", "MAGAZINE", "BOMB_MATERIAL", "ETC", "KEY",
    "RING", "BRACELET", "NECKLACE", "COAT", "TROUSER", "SHOES", "SWORD", "BLADE", "SHIELD",
    "CROSS", "GLOVE", "HELM", "SG", "SMG", "AR", "SR", "BOMB", "MINE", "BELT", "LEARNINGITEM",
    "MONEY", "CORPSE", "VAMPIRE_RING", "VAMPIRE_BRACELET", "VAMPIRE_NECKLACE", "VAMPIRE_COAT",
    "SKULL", "MACE", "SERUM", "VAMPIRE_ETC", "SLAYER_PORTAL_ITEM", "VAMPIRE_PORTAL_ITEM",
    "EVENT_GIFT_BOX", "EVENT_STAR", "VAMPIRE_EARRING", "RELIC", "VAMPIRE_WEAPON", "VAMPIRE_AMULET",
    "QUEST_ITEM", "EVENT_TREE", "EVENT_ETC", "BLOOD_BIBLE", "CASTLE_SYMBOL", "COUPLE_RING",
    "VAMPIRE_COUPLE_RING", "EVENT_ITEM", "DYE_POTION", "RESURRECT_ITEM", "MIXING_ITEM",
    "OUSTERS_ARMSBAND", "OUSTERS_BOOTS", "OUSTERS_CHAKRAM", "OUSTERS_CIRCLET", "OUSTERS_COAT",
    "OUSTERS_PENDENT", "OUSTERS_RING", "OUSTERS_STONE", "OUSTERS_WRISTLET", "LARVA", "PUPA",
    "COMPOS_MEI", "OUSTERS_SUMMON_ITEM", "EFFECT_ITEM", "CODE_SHEET", "MOON_CARD", "SWEEPER",
    "PET_ITEM", "PET_FOOD", "PET_ENCHANT_ITEM", "LUCKY_BAG", "SMS_ITEM", "CORE_ZAP", "GQUEST_ITEM",
    "TRAP_ITEM", "BLOOD_BIBLE_SIGN", "WAR_ITEM", "CARRYING_RECEIVER", "SHOULDER_ARMOR", "DERMIS",
    "PERSONA", "FASCIA", "MITTEN",
]

# Only classes present in the original treasure resources need a table mapping.
# Keep this mapping explicit so special DB table names remain reviewable.
TREASURE_ITEM_TABLES = {
    1: "PotionInfo", 6: "ETCInfo", 7: "KeyInfo", 8: "RingInfo", 9: "BraceletInfo",
    10: "NecklaceInfo", 11: "CoatInfo", 12: "TrouserInfo", 13: "ShoesInfo", 14: "SwordInfo",
    15: "BladeInfo", 16: "ShieldInfo", 17: "CrossInfo", 18: "GloveInfo", 19: "HelmInfo",
    20: "SGInfo", 21: "SMGInfo", 22: "ARInfo", 23: "SRInfo", 26: "BeltInfo",
    30: "VampireRingInfo", 31: "VampireBraceletInfo", 32: "VampireNecklaceInfo", 33: "VampireCoatInfo",
    34: "SkullInfo", 35: "MaceInfo", 36: "SerumInfo", 37: "VampireETCInfo", 39: "VampirePortalItemInfo",
    41: "EventStarInfo", 42: "VampireEarringInfo", 44: "VampireWeaponInfo", 45: "VampireAmuletInfo",
    48: "EventETCInfo", 55: "ResurrectItemInfo", 57: "OustersArmsbandInfo", 58: "OustersBootsInfo",
    59: "OustersChakramInfo", 60: "OustersCircletInfo", 61: "OustersCoatInfo", 62: "OustersPendentInfo",
    63: "OustersRingInfo", 64: "OustersStoneInfo", 65: "OustersWristletInfo", 66: "LarvaInfo",
    67: "PupaInfo", 68: "ComposMeiInfo", 69: "OustersSummonItemInfo", 70: "EffectItemInfo",
    84: "CarryingReceiverInfo", 85: "ShoulderArmorInfo", 86: "DermisInfo", 87: "PersonaInfo",
    88: "FasciaInfo", 89: "MittenInfo",
}


def _table_columns(sql: str, table: str) -> list[str]:
    match = re.search(rf"CREATE TABLE `{re.escape(table)}` \((.*?)\) ENGINE=", sql, re.DOTALL)
    if not match:
        raise ValueError(f"CREATE TABLE for {table} not found")
    return re.findall(r"^\s*`([^`]+)`\s+", match.group(1), re.MULTILINE)


def _rows(sql: str, table: str) -> Iterator[list[str | None]]:
    match = re.search(rf"INSERT INTO `{re.escape(table)}` VALUES\s*", sql)
    if not match:
        return
    i = match.end()
    while i < len(sql):
        while i < len(sql) and sql[i].isspace():
            i += 1
        if i >= len(sql) or sql[i] == ";":
            return
        if sql[i] == ",":
            i += 1
            continue
        if sql[i] != "(":
            raise ValueError(f"unexpected SQL in INSERT {table} at offset {i}")
        i += 1
        fields: list[str | None] = []
        token: list[str] = []
        quoted = False
        while i < len(sql):
            char = sql[i]
            if quoted:
                if char == "\\" and i + 1 < len(sql):
                    token.append(sql[i + 1])
                    i += 2
                    continue
                if char == "'":
                    if i + 1 < len(sql) and sql[i + 1] == "'":
                        token.append("'")
                        i += 2
                        continue
                    quoted = False
                else:
                    token.append(char)
                i += 1
                continue
            if char == "'":
                quoted = True
                i += 1
            elif char == ",":
                fields.append("".join(token).strip())
                token.clear()
                i += 1
            elif char == ")":
                fields.append("".join(token).strip())
                i += 1
                yield [None if value == "NULL" else value for value in fields]
                break
            else:
                token.append(char)
                i += 1
        else:
            raise ValueError(f"unterminated SQL tuple in INSERT {table}")


def make_catalog(sql_path: Path) -> dict:
    raw = sql_path.read_bytes()
    sql = raw.decode("latin1")
    item_labels: dict[str, dict[str, str]] = {}
    item_ids: dict[str, list[int]] = {}
    for class_id, table in TREASURE_ITEM_TABLES.items():
        columns = _table_columns(sql, table)
        if "ItemType" not in columns:
            raise ValueError(f"{table} has no ItemType column")
        id_index = columns.index("ItemType")
        label_index = columns.index("EName") if "EName" in columns else columns.index("Name")
        entries: dict[str, str] = {}
        for row in _rows(sql, table):
            type_id = int(row[id_index] or "0")
            label = row[label_index]
            if label:
                entries[str(type_id)] = label
            else:
                entries.setdefault(str(type_id), "")
        item_ids[str(class_id)] = sorted(int(value) for value in entries)
        item_labels[str(class_id)] = {key: value for key, value in entries.items() if value}

    option_columns = _table_columns(sql, "OptionInfo")
    option_id_index = option_columns.index("OptionType")
    option_label_index = option_columns.index("Nickname")
    options = {}
    for row in _rows(sql, "OptionInfo"):
        option_id = int(row[option_id_index] or "0")
        label = row[option_label_index]
        if label:
            options[str(option_id)] = label
        else:
            options.setdefault(str(option_id), "")
    return {
        "catalog_version": 1,
        "provenance": f"Extracted from {sql_path.name}; sha256={hashlib.sha256(raw).hexdigest()}",
        "item_classes": {str(i): name for i, name in enumerate(CLASS_NAMES)},
        "items_by_class": item_ids,
        "item_labels_by_class": item_labels,
        "options": sorted(int(value) for value in options),
        "option_labels": {key: value for key, value in options.items() if value},
    }

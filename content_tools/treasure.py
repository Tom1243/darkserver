"""Lossless codec and validator for legacy Dark Eden treasure tables."""

from __future__ import annotations

import hashlib
import hashlib
import json
import struct
from pathlib import Path
from typing import Any


FORMAT = "darkeden-treasure"
SCHEMA_VERSION = 1
INT32_MIN = -(2**31)
INT32_MAX = 2**31 - 1
MAX_RECORDS = 100_000


class ContentError(ValueError):
    """Invalid source or legacy resource data."""


def _read_int(data: bytes, offset: int, where: str) -> tuple[int, int]:
    if offset + 4 > len(data):
        raise ContentError(f"truncated treasure binary while reading {where} at byte {offset}")
    return struct.unpack_from("<i", data, offset)[0], offset + 4


def _count(data: bytes, offset: int, where: str) -> tuple[int, int]:
    value, offset = _read_int(data, offset, where)
    if not 0 <= value <= MAX_RECORDS:
        raise ContentError(f"{where} must be between 0 and {MAX_RECORDS}, got {value}")
    return value, offset


def decode_binary(data: bytes, source_file: str) -> dict[str, Any]:
    offset = 0
    treasure_count, offset = _count(data, offset, "treasure count")
    treasures = []
    for ti in range(treasure_count):
        item_chance, offset = _read_int(data, offset, f"treasure[{ti}].item_chance")
        option_chance, offset = _read_int(data, offset, f"treasure[{ti}].option_chance")
        class_count, offset = _count(data, offset, f"treasure[{ti}].item_classes count")
        item_classes = []
        for ci in range(class_count):
            class_id, offset = _read_int(data, offset, f"treasure[{ti}].item_classes[{ci}].id")
            class_weight, offset = _read_int(data, offset, f"treasure[{ti}].item_classes[{ci}].weight")
            item_count, offset = _count(data, offset, f"treasure[{ti}].item_classes[{ci}].items count")
            items = []
            for ii in range(item_count):
                type_id, offset = _read_int(data, offset, f"item type id at {ti}/{ci}/{ii}")
                weight, offset = _read_int(data, offset, f"item type weight at {ti}/{ci}/{ii}")
                option_count, offset = _count(data, offset, f"options count at {ti}/{ci}/{ii}")
                options = []
                for oi in range(option_count):
                    option_id, offset = _read_int(data, offset, f"option id at {ti}/{ci}/{ii}/{oi}")
                    option_weight, offset = _read_int(data, offset, f"option weight at {ti}/{ci}/{ii}/{oi}")
                    options.append({"id": option_id, "weight": option_weight})
                items.append({"type_id": type_id, "weight": weight, "options": options})
            item_classes.append({"id": class_id, "weight": class_weight, "items": items})
        treasures.append({"item_chance": item_chance, "option_chance": option_chance, "item_classes": item_classes})
    if offset != len(data):
        raise ContentError(f"{source_file}: {len(data) - offset} trailing byte(s) after treasure data")
    return {
        "$schema": "../../schema/treasure.schema.json",
        "format": FORMAT,
        "schema_version": SCHEMA_VERSION,
        "source_file": source_file,
        "treasures": treasures,
    }


def _integer(value: Any, path: str, minimum: int = INT32_MIN, maximum: int = INT32_MAX) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContentError(f"{path} must be an integer")
    if not minimum <= value <= maximum:
        raise ContentError(f"{path} must be in [{minimum}, {maximum}], got {value}")
    return value


def validate_document(doc: Any, source_file: str, catalog: dict[str, Any] | None = None) -> None:
    if not isinstance(doc, dict):
        raise ContentError(f"{source_file}: document must be an object")
    if not isinstance(doc.get("$schema"), str):
        raise ContentError(f"{source_file}: $schema must be a string")
    if (doc.get("format") != FORMAT or isinstance(doc.get("schema_version"), bool)
            or doc.get("schema_version") != SCHEMA_VERSION):
        raise ContentError(f"{source_file}: expected {FORMAT} schema version {SCHEMA_VERSION}")
    if doc.get("source_file") != source_file:
        raise ContentError(f"{source_file}: source_file must match the original filename")
    if set(doc) - {"$schema", "format", "schema_version", "source_file", "treasures", "labels"}:
        raise ContentError(f"{source_file}: unexpected top-level properties")
    labels = doc.get("labels", {})
    if not isinstance(labels, dict) or set(labels) - {"item_class"}:
        raise ContentError(f"{source_file}: labels may only contain item_class")
    if "item_class" in labels and not isinstance(labels["item_class"], str):
        raise ContentError(f"{source_file}: labels.item_class must be a string")
    treasures = doc.get("treasures")
    if not isinstance(treasures, list):
        raise ContentError(f"{source_file}: treasures must be an array")

    classes = (catalog or {}).get("item_classes", {})
    items_by_class = (catalog or {}).get("items_by_class", {})
    options = set((catalog or {}).get("options", []))
    for ti, treasure in enumerate(treasures):
        path = f"{source_file}.treasures[{ti}]"
        if not isinstance(treasure, dict):
            raise ContentError(f"{path} must be an object")
        _integer(treasure.get("item_chance"), f"{path}.item_chance")
        _integer(treasure.get("option_chance"), f"{path}.option_chance")
        groups = treasure.get("item_classes")
        if not isinstance(groups, list):
            raise ContentError(f"{path}.item_classes must be an array")
        for ci, group in enumerate(groups):
            gp = f"{path}.item_classes[{ci}]"
            if not isinstance(group, dict):
                raise ContentError(f"{gp} must be an object")
            if set(group) - {"id", "weight", "items", "label"}:
                raise ContentError(f"{gp} has unexpected properties")
            if "label" in group and not isinstance(group["label"], str):
                raise ContentError(f"{gp}.label must be a string")
            class_id = _integer(group.get("id"), f"{gp}.id", 0, 89)
            _integer(group.get("weight"), f"{gp}.weight", 0)
            if classes and str(class_id) not in classes:
                raise ContentError(f"{gp}.id references unknown item class {class_id}")
            item_list = group.get("items")
            if not isinstance(item_list, list):
                raise ContentError(f"{gp}.items must be an array")
            known_types = set(items_by_class.get(str(class_id), []))
            for ii, item in enumerate(item_list):
                ip = f"{gp}.items[{ii}]"
                if not isinstance(item, dict):
                    raise ContentError(f"{ip} must be an object")
                if set(item) - {"type_id", "weight", "options", "label"}:
                    raise ContentError(f"{ip} has unexpected properties")
                if "label" in item and not isinstance(item["label"], str):
                    raise ContentError(f"{ip}.label must be a string")
                type_id = _integer(item.get("type_id"), f"{ip}.type_id", 0, 255)
                _integer(item.get("weight"), f"{ip}.weight", 0)
                if items_by_class and type_id not in known_types:
                    raise ContentError(f"{ip}.type_id references unknown type {type_id} for class {class_id}")
                option_list = item.get("options")
                if not isinstance(option_list, list):
                    raise ContentError(f"{ip}.options must be an array")
                for oi, option in enumerate(option_list):
                    op = f"{ip}.options[{oi}]"
                    if not isinstance(option, dict):
                        raise ContentError(f"{op} must be an object")
                    if set(option) - {"id", "weight", "label"}:
                        raise ContentError(f"{op} has unexpected properties")
                    if "label" in option and not isinstance(option["label"], str):
                        raise ContentError(f"{op}.label must be a string")
                    option_id = _integer(option.get("id"), f"{op}.id", 0, 2**31 - 1)
                    _integer(option.get("weight"), f"{op}.weight", 0)
                    if options and option_id not in options:
                        raise ContentError(f"{op}.id references unknown option {option_id}")


def encode_binary(doc: dict[str, Any], source_file: str, catalog: dict[str, Any] | None = None) -> bytes:
    validate_document(doc, source_file, catalog)
    out = bytearray()

    def put(value: Any, path: str, minimum: int = INT32_MIN, maximum: int = INT32_MAX) -> None:
        out.extend(struct.pack("<i", _integer(value, path, minimum, maximum)))

    treasures = doc["treasures"]
    put(len(treasures), "treasures count", 0, MAX_RECORDS)
    for ti, treasure in enumerate(treasures):
        path = f"{source_file}.treasures[{ti}]"
        put(treasure["item_chance"], f"{path}.item_chance")
        put(treasure["option_chance"], f"{path}.option_chance")
        groups = treasure["item_classes"]
        put(len(groups), f"{path}.item_classes count", 0, MAX_RECORDS)
        for ci, group in enumerate(groups):
            gp = f"{path}.item_classes[{ci}]"
            put(group["id"], f"{gp}.id")
            put(group["weight"], f"{gp}.weight")
            items = group["items"]
            put(len(items), f"{gp}.items count", 0, MAX_RECORDS)
            for ii, item in enumerate(items):
                ip = f"{gp}.items[{ii}]"
                put(item["type_id"], f"{ip}.type_id")
                put(item["weight"], f"{ip}.weight")
                opts = item["options"]
                put(len(opts), f"{ip}.options count", 0, MAX_RECORDS)
                for oi, option in enumerate(opts):
                    op = f"{ip}.options[{oi}]"
                    put(option["id"], f"{op}.id")
                    put(option["weight"], f"{op}.weight")
    return bytes(out)


def load_catalog(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContentError(f"cannot read reference catalog {path}: {exc}") from exc
    if not isinstance(data, dict) or data.get("catalog_version") != 1:
        raise ContentError(f"{path}: unsupported reference catalog")
    return data


def load_json(path: Path) -> dict[str, Any]:
    try:
        def no_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ContentError(f"{path}: duplicate JSON property {key!r}")
                result[key] = value
            return result
        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=no_duplicate_pairs)
    except (OSError, json.JSONDecodeError) as exc:
        raise ContentError(f"cannot read JSON source {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ContentError(f"{path}: top level must be an object")
    return data


def source_digest(source_dir: Path, schema_path: Path, catalog_path: Path) -> str:
    digest = hashlib.sha256()
    toolkit_dir = Path(__file__).resolve().parent
    files = sorted([*source_dir.glob("*.json"), *toolkit_dir.glob("*.py"), schema_path, catalog_path], key=lambda p: str(p))
    for path in files:
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def compile_directory(source_dir: Path, output_dir: Path, catalog: dict[str, Any]) -> list[str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    sources = sorted(source_dir.glob("*.json"))
    if not sources:
        raise ContentError(f"no treasure JSON files found in {source_dir}")
    manifest_path = output_dir / "content-treasure-files.json"
    if manifest_path.exists():
        try:
            old_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            old_names = old_manifest["files"]
            if not isinstance(old_names, list) or any(not isinstance(name, str) for name in old_names):
                raise ValueError("invalid files list")
        except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
            raise ContentError(f"invalid prior output manifest {manifest_path}: {exc}") from exc
    else:
        old_names = []
    names = set()
    generated: dict[str, bytes] = {}
    for path in sources:
        doc = load_json(path)
        source_file = doc.get("source_file", "")
        if (not isinstance(source_file, str) or not source_file.endswith(".bin")
                or Path(source_file).name != source_file or "\\" in source_file
                or any(ord(c) < 32 for c in source_file)):
            raise ContentError(f"{path}: invalid source_file")
        if source_file in names:
            raise ContentError(f"duplicate output filename {source_file}")
        names.add(source_file)
        generated[source_file] = encode_binary(doc, source_file, catalog)
    for name, payload in generated.items():
        (output_dir / name).write_bytes(payload)
    for stale_name in set(old_names) - names:
        if Path(stale_name).name == stale_name and stale_name.endswith(".bin"):
            stale_file = output_dir / stale_name
            if stale_file.exists():
                stale_file.unlink()
    manifest_path.write_text(json.dumps({"files": sorted(names)}, indent=2) + "\n", encoding="utf-8")
    return sorted(names)

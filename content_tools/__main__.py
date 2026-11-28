"""Command line entry point for the Dark Eden content compiler."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

from . import __version__
from .catalog import make_catalog
from .treasure import ContentError, compile_directory, decode_binary, load_catalog, load_json, source_digest


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "content" / "src" / "treasure"
DEFAULT_REFERENCE = ROOT / "content" / "reference" / "treasure"
DEFAULT_CATALOG = ROOT / "content" / "catalogs" / "treasure-reference-ids.json"
DEFAULT_SCHEMA = ROOT / "content" / "schema" / "treasure.schema.json"


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ensure_safe_output(source_dir: Path, output_dir: Path) -> None:
    resolved_output = output_dir.resolve()
    protected_dirs = [ROOT / "data", ROOT / "content" / "src", ROOT / "content" / "reference"]
    for protected in protected_dirs:
        resolved_protected = protected.resolve()
        if resolved_output == resolved_protected or resolved_protected in resolved_output.parents:
            raise ContentError(f"output {output_dir} is inside protected source/reference resources; use a build staging directory")
    resolved_source = source_dir.resolve()
    if resolved_source == resolved_output or resolved_source in resolved_output.parents:
        raise ContentError(f"output {output_dir} cannot be inside the JSON source directory")


def export(args: argparse.Namespace) -> int:
    input_dir = Path(args.input)
    source_dir = Path(args.output)
    reference_dir = Path(args.reference_output)
    catalog_path = Path(args.catalog_output)
    binaries = sorted(input_dir.glob("*.bin"))
    if not binaries:
        raise ContentError(f"no .bin treasure files found in {input_dir}")
    try:
        catalog = make_catalog(Path(args.sql))
    except (OSError, ValueError) as exc:
        raise ContentError(f"cannot build item reference catalog from {args.sql}: {exc}") from exc
    # Keep copies as immutable regression fixtures; JSON remains the editable source.
    reference_dir.mkdir(parents=True, exist_ok=True)
    source_dir.mkdir(parents=True, exist_ok=True)
    for path in binaries:
        document = decode_binary(path.read_bytes(), path.name)
        for treasure in document["treasures"]:
            for group in treasure["item_classes"]:
                group["label"] = catalog["item_classes"][str(group["id"])]
                for item in group["items"]:
                    label = catalog["item_labels_by_class"].get(str(group["id"]), {}).get(str(item["type_id"]))
                    if label:
                        item["label"] = label
                    for option in item["options"]:
                        label = catalog["option_labels"].get(str(option["id"]))
                        if label:
                            option["label"] = label
        # Verify the original files against the SQL-derived identifiers before
        # treating either the text source or the catalog as authoritative.
        from .treasure import validate_document
        validate_document(document, path.name, catalog)
        write_json(source_dir / f"{path.stem}.json", document)
        shutil.copy2(path, reference_dir / path.name)
    write_json(catalog_path, catalog)
    print(f"Exported {len(binaries)} BIN files, JSON sources, and reference fixtures.")
    print(f"JSON: {source_dir}\nFixtures: {reference_dir}\nCatalog: {catalog_path}")
    return 0


def catalog_from_sql(args: argparse.Namespace) -> int:
    try:
        catalog = make_catalog(Path(args.sql))
    except (OSError, ValueError) as exc:
        raise ContentError(f"cannot build item reference catalog from {args.sql}: {exc}") from exc
    output = Path(args.output)
    write_json(output, catalog)
    print(f"Wrote item/option reference catalog from {args.sql} to {output}")
    return 0


def compile_cmd(args: argparse.Namespace) -> int:
    source_dir = Path(args.source)
    output_dir = Path(args.output)
    ensure_safe_output(source_dir, output_dir)
    catalog_path = Path(args.catalog)
    catalog = load_catalog(catalog_path)
    names = compile_directory(source_dir, output_dir, catalog)
    digest = source_digest(source_dir, Path(args.schema), catalog_path)
    provenance = (
        f"toolkit_version={__version__}\n"
        f"schema_version=1\n"
        f"source_count={len(names)}\n"
        f"source_sha256={digest}\n"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "content-build-info.txt").write_text(provenance, encoding="utf-8")
    print(f"Compiled {len(names)} treasure JSON files to {output_dir}")
    print(f"Source SHA-256: {digest}")
    return 0


def verify(args: argparse.Namespace) -> int:
    source_dir = Path(args.source)
    reference_dir = Path(args.reference)
    catalog = load_catalog(Path(args.catalog))
    sources = sorted(source_dir.glob("*.json"))
    references = sorted(reference_dir.glob("*.bin"))
    if len(sources) != len(references):
        raise ContentError(f"source/reference file count differs: {len(sources)} JSON vs {len(references)} BIN")
    with tempfile.TemporaryDirectory(prefix="darkeden-treasure-verify-") as temp:
        out = Path(temp)
        compile_directory(source_dir, out, catalog)
        compiled = sorted(p.name for p in out.glob("*.bin"))
        fixture_names = sorted(p.name for p in references)
        if compiled != fixture_names:
            missing = sorted(set(fixture_names) - set(compiled))
            extra = sorted(set(compiled) - set(fixture_names))
            raise ContentError(f"compiled filenames differ; missing={missing}, extra={extra}")
        mismatches = []
        for name in compiled:
            actual, expected = (out / name).read_bytes(), (reference_dir / name).read_bytes()
            if actual != expected:
                mismatches.append(name)
        if mismatches:
            raise ContentError(f"byte mismatch in {len(mismatches)} file(s): {', '.join(mismatches[:20])}")
    print(f"PASS: all {len(sources)} JSON sources compile byte-for-byte to their original BIN fixtures.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="python3 -m content_tools", description="Dark Eden build-time content tools")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("export", help="export original BIN fixtures to JSON and retain reference copies")
    p.add_argument("--input", default=str(ROOT / "data"))
    p.add_argument("--output", default=str(DEFAULT_SOURCE))
    p.add_argument("--reference-output", default=str(DEFAULT_REFERENCE))
    p.add_argument("--catalog-output", default=str(DEFAULT_CATALOG))
    p.add_argument("--sql", default=str(ROOT / "initdb" / "DARKEDEN.sql"), help="database seed used for item/option ID validation and labels")
    p.set_defaults(run=export)
    p = sub.add_parser("catalog-from-sql", help="build reference ID catalog and labels from a DARKEDEN SQL dump")
    p.add_argument("--sql", default=str(ROOT / "initdb" / "DARKEDEN.sql"))
    p.add_argument("--output", default=str(DEFAULT_CATALOG))
    p.set_defaults(run=catalog_from_sql)
    p = sub.add_parser("compile", help="compile JSON sources into legacy BIN resources")
    p.add_argument("--source", default=str(DEFAULT_SOURCE))
    p.add_argument("--output", default=str(ROOT / "build" / "content" / "data"))
    p.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    p.add_argument("--schema", default=str(DEFAULT_SCHEMA))
    p.set_defaults(run=compile_cmd)
    p = sub.add_parser("verify", help="check all source files against immutable original BIN fixtures")
    p.add_argument("--source", default=str(DEFAULT_SOURCE))
    p.add_argument("--reference", default=str(DEFAULT_REFERENCE))
    p.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    p.set_defaults(run=verify)
    args = parser.parse_args()
    try:
        return args.run(args)
    except ContentError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

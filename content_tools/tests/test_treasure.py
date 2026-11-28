from __future__ import annotations

import json
import struct
import tempfile
import unittest
from pathlib import Path
import shutil

from content_tools.treasure import ContentError, compile_directory, decode_binary, encode_binary, load_catalog, load_json, validate_document
from content_tools.__main__ import ensure_safe_output


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "content" / "src" / "treasure"
REFERENCE = ROOT / "content" / "reference" / "treasure"
CATALOG = ROOT / "content" / "catalogs" / "treasure-reference-ids.json"


class TreasureCodecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_catalog(CATALOG)

    def test_all_249_original_files_round_trip_byte_for_byte(self) -> None:
        source_files = sorted(SOURCE.glob("*.json"))
        reference_files = sorted(REFERENCE.glob("*.bin"))
        self.assertEqual(249, len(source_files))
        self.assertEqual([p.stem for p in reference_files], [p.stem for p in source_files])
        for json_path in source_files:
            doc = load_json(json_path)
            actual = encode_binary(doc, json_path.stem + ".bin", self.catalog)
            self.assertEqual((REFERENCE / (json_path.stem + ".bin")).read_bytes(), actual, json_path.name)

    def test_labels_do_not_change_binary(self) -> None:
        path = next(iter(sorted(SOURCE.glob("*.json"))))
        doc = load_json(path)
        baseline = encode_binary(doc, doc["source_file"], self.catalog)
        doc["treasures"][0]["item_classes"][0]["items"][0]["label"] = "editor note"
        if doc["treasures"][0]["item_classes"][0]["items"][0]["options"]:
            doc["treasures"][0]["item_classes"][0]["items"][0]["options"][0]["label"] = "option note"
        self.assertEqual(baseline, encode_binary(doc, doc["source_file"], self.catalog))

    def test_unknown_item_reference_is_rejected(self) -> None:
        path = next(iter(sorted(SOURCE.glob("*.json"))))
        doc = load_json(path)
        doc["treasures"][0]["item_classes"][0]["items"][0]["type_id"] = 255
        with self.assertRaisesRegex(ContentError, "unknown type"):
            validate_document(doc, doc["source_file"], self.catalog)

    def test_truncated_and_trailing_binary_are_rejected(self) -> None:
        with self.assertRaisesRegex(ContentError, "truncated"):
            decode_binary(struct.pack("<i", 1), "broken.bin")
        with self.assertRaisesRegex(ContentError, "trailing"):
            decode_binary(struct.pack("<i", 0) + b"x", "broken.bin")

    def test_duplicate_json_properties_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "broken.json"
            path.write_text('{"format":"x","format":"y"}', encoding="utf-8")
            with self.assertRaisesRegex(ContentError, "duplicate JSON property"):
                load_json(path)

    def test_recompile_removes_only_previously_managed_stale_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            output = Path(temp) / "output"
            source.mkdir()
            output.mkdir()
            shutil.copy2(next(iter(sorted(SOURCE.glob("*.json")))), source / "one.json")
            doc = load_json(source / "one.json")
            doc["source_file"] = "one.bin"
            (source / "one.json").write_text(json.dumps(doc), encoding="utf-8")
            (output / "unrelated.smp").write_bytes(b"keep")
            compile_directory(source, output, self.catalog)
            shutil.copy2(next(iter(sorted(SOURCE.glob("*.json")))), source / "two.json")
            doc2 = load_json(source / "two.json")
            doc2["source_file"] = "two.bin"
            (source / "two.json").write_text(json.dumps(doc2), encoding="utf-8")
            compile_directory(source, output, self.catalog)
            (source / "one.json").unlink()
            compile_directory(source, output, self.catalog)
            self.assertFalse((output / "one.bin").exists())
            self.assertTrue((output / "two.bin").exists())
            self.assertEqual(b"keep", (output / "unrelated.smp").read_bytes())

    def test_compiler_refuses_reference_and_source_tree_outputs(self) -> None:
        with self.assertRaisesRegex(ContentError, "protected source/reference"):
            ensure_safe_output(SOURCE, ROOT / "data")
        with self.assertRaisesRegex(ContentError, "protected source/reference"):
            ensure_safe_output(SOURCE, SOURCE / "generated")


if __name__ == "__main__":
    unittest.main()

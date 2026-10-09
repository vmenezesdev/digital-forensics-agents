"""Synthetic conformance for inventory text-size bounds (issue #2)."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from dfa.store import Case


class InventoryBoundsTests(unittest.TestCase):
    def test_reducing_text_limit_removes_cached_hits_without_resetting_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            (source / "sample.txt").write_text("synthetic_unique_marker")
            case = Case(root / "case")
            case.init()
            case.source_add("sample", source)

            self.assertEqual(case.ingest("sample")["indexed"], 1)
            self.assertEqual(len(case.search("synthetic_unique_marker")["results"]), 1)
            with sqlite3.connect(case.db) as db:
                baseline = db.execute("SELECT sha256 FROM evidence").fetchone()[0]

            bounded = case.ingest("sample", max_text_bytes=4)
            self.assertEqual(bounded["scan_status"], "complete")
            self.assertEqual(bounded["excluded"], 1)
            self.assertEqual(bounded["errors"], 0)
            self.assertEqual(case.search("synthetic_unique_marker")["results"], [])
            self.assertFalse(case.search("synthetic_unique_marker")["complete"])
            with sqlite3.connect(case.db) as db:
                self.assertEqual(
                    db.execute("SELECT sha256,status,reason FROM evidence").fetchone(),
                    (baseline, "excluded", "oversized")
                )

            self.assertEqual(case.ingest("sample")["indexed"], 1)
            self.assertEqual(len(case.search("synthetic_unique_marker")["results"]), 1)

    def test_invalid_size_bound_rejected_without_starting_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            case = Case(root / "case")
            case.init()
            case.source_add("sample", source)
            for limit in (-1, 4194305):
                with self.subTest(limit=limit):
                    with self.assertRaisesRegex(ValueError, "Invalid limit"):
                        case.ingest("sample", max_text_bytes=limit)
            with sqlite3.connect(case.db) as db:
                self.assertEqual(
                    db.execute("SELECT COUNT(*) FROM inventory_runs").fetchone()[0], 0
                )


if __name__ == "__main__":
    unittest.main()

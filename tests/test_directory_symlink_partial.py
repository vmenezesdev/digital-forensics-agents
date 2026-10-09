"""Synthetic regression: a replaced directory is not evidence of absent children."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from dfa.store import Case


class DirectorySymlinkInventoryTests(unittest.TestCase):
    def test_nested_directory_replacement_is_partial_not_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            nested = source / "nested"
            nested.mkdir(parents=True)
            (nested / "known.txt").write_text("synthetic known_nested_marker")
            case = Case(root / "case")
            case.init()
            case.source_add("sample", source)
            self.assertEqual(case.ingest("sample")["scan_status"], "complete")
            with sqlite3.connect(case.db) as db:
                baseline = db.execute(
                    "SELECT sha256 FROM evidence WHERE relpath='nested/known.txt'"
                ).fetchone()[0]

            moved = root / "moved"
            replacement = root / "replacement"
            replacement.mkdir()
            (replacement / "foreign.txt").write_text("synthetic foreign_nested_marker")
            nested.rename(moved)
            try:
                nested.symlink_to(replacement, target_is_directory=True)
            except (OSError, NotImplementedError):
                moved.rename(nested)
                self.skipTest("Directory symlinks unavailable")

            partial = case.ingest("sample")
            self.assertEqual(partial["scan_status"], "partial")
            self.assertEqual(partial["errors"], 1)
            self.assertIsNone(partial["missing"])
            with sqlite3.connect(case.db) as db:
                self.assertEqual(
                    db.execute(
                        "SELECT sha256,status FROM evidence WHERE relpath='nested/known.txt'"
                    ).fetchone(), (baseline, "indexed")
                )
                self.assertEqual(
                    db.execute(
                        "SELECT status,reason FROM evidence WHERE relpath='nested'"
                    ).fetchone(), ("error", "symlink_directory")
                )
            self.assertEqual(case.search("known_nested_marker")["results"], [])
            self.assertEqual(case.search("foreign_nested_marker")["results"], [])

            nested.unlink()
            moved.rename(nested)
            self.assertEqual(case.ingest("sample")["scan_status"], "complete")
            self.assertEqual(len(case.search("known_nested_marker")["results"]), 1)


if __name__ == "__main__":
    unittest.main()

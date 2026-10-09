"""Failure-driven synthetic conformance for changing and inaccessible inventories."""
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dfa import store
from dfa.store import Case


class InventoryAdversarialTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "synthetic-source"
        self.source.mkdir()
        self.case = Case(self.root / "case")
        self.case.init()
        self.case.source_add("sample", self.source)

    def test_disappearing_file_before_inspection_causes_partial_not_excluded(self):
        target = self.source / "disappearing.txt"
        target.write_text("synthetic before_read")
        self.case.ingest("sample")
        with sqlite3.connect(self.case.db) as db:
            original = db.execute(
                "SELECT sha256 FROM evidence WHERE relpath='disappearing.txt'"
            ).fetchone()[0]

        real_lstat = Path.lstat
        def vanishing_stat(path, *args, **kwargs):
            if path == target:
                raise FileNotFoundError("synthetic disappeared between discovery and stat")
            return real_lstat(path, *args, **kwargs)

        with mock.patch("dfa.store.Path.lstat", autospec=True, side_effect=vanishing_stat):
            partial = self.case.ingest("sample")

        self.assertEqual(partial["scan_status"], "partial")
        self.assertEqual(partial["errors"], 1)
        self.assertIsNone(partial["missing"])
        self.assertEqual(self.case.search("before_read")["results"], [])
        with sqlite3.connect(self.case.db) as db:
            actual = db.execute(
                "SELECT sha256,status,reason FROM evidence WHERE relpath='disappearing.txt'"
            ).fetchone()
        self.assertEqual(actual, (original, "error", "unavailable_during_inventory"))
        self.assertEqual(self.case.ingest("sample")["scan_status"], "complete")
        self.assertEqual(len(self.case.search("before_read")["results"]), 1)

    def test_changed_while_reading_does_not_reset_first_digest(self):
        target = self.source / "unstable.txt"
        target.write_text("synthetic stabletoken")
        self.case.ingest("sample")
        with sqlite3.connect(self.case.db) as db:
            original = db.execute("SELECT sha256 FROM evidence").fetchone()[0]
        real_inspect = store._inspect_file

        def changed_during_read(*args, **kwargs):
            digest, size, raw, _ = real_inspect(*args, **kwargs)
            return digest, size, raw, True

        with mock.patch("dfa.store._inspect_file", side_effect=changed_during_read):
            partial = self.case.ingest("sample")
        self.assertEqual(partial["scan_status"], "partial")
        self.assertEqual(partial["errors"], 1)
        with sqlite3.connect(self.case.db) as db:
            digest, status, reason = db.execute(
                "SELECT sha256,status,reason FROM evidence"
            ).fetchone()
        self.assertEqual((digest, status, reason), (original, "error", "changed_during_read"))
        self.assertEqual(self.case.search("stabletoken")["results"], [])

    def test_real_directory_source_root_swap_rolls_back_instead_of_indexing_replacement(self):
        (self.source / "original.txt").write_text("synthetic original_only")
        self.case.ingest("sample")
        replacement = self.root / "replacement"
        replacement.mkdir()
        (replacement / "foreign.txt").write_text("synthetic foreign_marker")
        moved = self.root / "moved-source"
        real_walk = os.walk
        swapped = False

        def substitute_real_directory(*args, **kwargs):
            nonlocal swapped
            self.source.rename(moved)
            replacement.rename(self.source)
            swapped = True
            yield from real_walk(*args, **kwargs)

        with mock.patch("dfa.store.os.walk", side_effect=substitute_real_directory):
            with self.assertRaisesRegex(ValueError, "rolled back"):
                self.case.ingest("sample")

        self.assertTrue(swapped)
        self.assertEqual(self.case.status()["latest_inventory"]["sample"]["status"], "failed")
        with sqlite3.connect(self.case.db) as db:
            records = db.execute(
                "SELECT relpath,status FROM evidence ORDER BY id"
            ).fetchall()
        self.assertEqual(records, [("original.txt", "indexed")])
        self.assertEqual(self.case.search("foreign_marker")["results"], [])
        self.assertEqual(self.case.search("original_only")["results"], [])

    def test_denied_directory_aborts_without_claiming_complete_coverage(self):
        target = self.source / "retained.txt"
        target.write_text("synthetic retainedtoken")
        self.case.ingest("sample")
        target.unlink()
        real_walk = os.walk

        def denied_walk(*args, **kwargs):
            yield from real_walk(*args, **kwargs)
            kwargs["onerror"](PermissionError("synthetic denied subdirectory"))

        with mock.patch("dfa.store.os.walk", side_effect=denied_walk):
            with self.assertRaisesRegex(ValueError, "rolled back"):
                self.case.ingest("sample")
        self.assertEqual(self.case.status()["latest_inventory"]["sample"]["status"], "failed")
        with sqlite3.connect(self.case.db) as db:
            self.assertEqual(
                db.execute("SELECT status FROM evidence WHERE relpath='retained.txt'").fetchone()[0],
                "indexed"
            )
        self.assertEqual(self.case.search("retainedtoken")["results"], [])

    def test_cli_reports_counts_and_non_acquisition_limitations(self):
        (self.source / "synthetic.txt").write_text("synthetic evidence")
        run = subprocess.run(
            [sys.executable, "-m", "dfa", "--case", str(self.case.root), "ingest", "sample"],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(run.returncode, 0, run.stderr)
        import json
        result = json.loads(run.stdout)
        self.assertEqual(result["scan_status"], "complete")
        self.assertEqual(result["errors"], 0)
        self.assertEqual(result["indexed"], 1)
        self.assertIn("not forensic acquisition", result["limitation"])


if __name__ == "__main__":
    unittest.main()

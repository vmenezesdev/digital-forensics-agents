"""Synthetic tests for transactional FTS5 reconstruction and independent CLI invocation."""
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dfa.store import Case


class IndexRebuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "synthetic-source"
        self.source.mkdir()
        self.case = Case(self.root / "case")
        self.case.init()
        self.case.source_add("sample", self.source)

    def test_rebuild_repairs_disposable_projection_without_changing_baseline(self):
        (self.source / "one.txt").write_text("synthetic searchable alpha")
        self.case.ingest("sample")
        self.case.search("alpha")  # Keep an existing receipt.
        with sqlite3.connect(self.case.db) as db:
            initial = db.execute(
                "SELECT id,sha256,size,status FROM evidence"
            ).fetchall()
            db.execute("DELETE FROM search_index")
        self.assertEqual(self.case.search("alpha")["results"], [])
        first = self.case.index_rebuild()
        second = self.case.index_rebuild()
        self.assertEqual(first["rebuilt"], 1)
        self.assertEqual(second["rebuilt"], 1)
        self.assertEqual(len(self.case.search("alpha")["results"]), 1)
        with sqlite3.connect(self.case.db) as db:
            self.assertEqual(
                db.execute("SELECT id,sha256,size,status FROM evidence").fetchall(),
                initial
            )
            self.assertEqual(db.execute("SELECT COUNT(*) FROM search_index").fetchone()[0], 1)
            self.assertGreaterEqual(db.execute("SELECT COUNT(*) FROM receipts").fetchone()[0], 1)

    def test_changed_source_aborts_and_rolls_back_index_rebuild(self):
        target = self.source / "one.txt"
        target.write_text("synthetic originaltoken")
        self.case.ingest("sample")
        with sqlite3.connect(self.case.db) as db:
            before = db.execute(
                "SELECT sha256 FROM evidence WHERE relpath='one.txt'"
            ).fetchone()[0]
            indexed_before = db.execute("SELECT body FROM search_index").fetchall()
        target.write_text("synthetic modifiedtoken")
        with self.assertRaisesRegex(ValueError, "changed/incompatible"):
            self.case.index_rebuild()
        with sqlite3.connect(self.case.db) as db:
            self.assertEqual(
                db.execute("SELECT sha256 FROM evidence WHERE relpath='one.txt'").fetchone()[0],
                before
            )
            self.assertEqual(db.execute("SELECT body FROM search_index").fetchall(), indexed_before)
        self.assertFalse(self.case.verify("sample")["ok"])

    def test_unreadable_file_aborts_rebuild_without_index_loss(self):
        (self.source / "one.txt").write_text("synthetic originaltoken")
        self.case.ingest("sample")
        with mock.patch("dfa.store._inspect_file", side_effect=OSError("synthetic unreadable")):
            with self.assertRaisesRegex(ValueError, "unreadable"):
                self.case.index_rebuild()
        self.assertEqual(len(self.case.search("originaltoken")["results"]), 1)

    def test_rebuild_skips_incomplete_source_but_keeps_other_source_searchable(self):
        (self.source / "sample.txt").write_text("synthetic sharedterm")
        unseen = self.source / "unseen.txt"
        unseen.write_text("synthetic retainedtext")
        self.case.ingest("sample")
        other = self.root / "other-synthetic-source"
        other.mkdir()
        (other / "other.txt").write_text("synthetic sharedterm")
        self.case.source_add("other", other)
        self.case.ingest("other")
        unseen.unlink()  # Prior row remains indexed until a complete traversal.
        with mock.patch("dfa.store._inspect_file", side_effect=OSError("synthetic failure")):
            partial = self.case.ingest("sample")
        self.assertEqual(partial["scan_status"], "partial")
        report = self.case.index_rebuild()
        self.assertEqual(report["rebuilt"], 1)
        self.assertEqual(report["skipped_unverified"], 1)
        self.assertEqual(
            [x["source_id"] for x in self.case.search("sharedterm")["results"]],
            ["other"]
        )

    def test_cli_rebuild_runs_in_separate_process(self):
        (self.source / "one.txt").write_text("synthetic clirebuild")
        self.case.ingest("sample")
        with sqlite3.connect(self.case.db) as db:
            db.execute("DELETE FROM search_index")
        process = subprocess.run(
            [sys.executable, "-m", "dfa", "--case", str(self.case.root), "index-rebuild"],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout)["rebuilt"], 1)
        self.assertEqual(len(self.case.search("clirebuild")["results"]), 1)


if __name__ == "__main__":
    unittest.main()

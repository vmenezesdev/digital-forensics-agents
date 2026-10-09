"""Synthetic cross-operation audit and process-level integrity exit-code tests."""
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dfa import audit
from dfa.store import Case


class IntegrityCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.case = Case(self.root / "case")
        self.case.init()
        self.source = self.root / "source"
        self.source.mkdir()
        self.case.source_add("sample", self.source)

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "dfa", "--case", str(self.case.root), *args],
            capture_output=True, text=True, check=False,
        )

    def test_search_receipt_and_event_roll_back_together_on_audit_failure(self):
        (self.source / "one.txt").write_text("synthetic auditableword")
        self.case.ingest("sample")
        with sqlite3.connect(self.case.db) as db:
            receipts_before = db.execute("SELECT COUNT(*) FROM receipts").fetchone()[0]
            events_before = db.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]

        original_append = audit.append
        def failing_append(*args, **kwargs):
            original_append(*args, **kwargs)
            raise RuntimeError("synthetic audit failure")

        with mock.patch("dfa.store.audit.append", side_effect=failing_append):
            with self.assertRaisesRegex(RuntimeError, "synthetic audit failure"):
                self.case.search("auditableword")

        with sqlite3.connect(self.case.db) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM receipts").fetchone()[0], receipts_before)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0], events_before)

        self.case.search("auditableword")
        with sqlite3.connect(self.case.db) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM receipts").fetchone()[0], receipts_before + 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0], events_before + 1)

    def test_broken_audit_link_has_explicit_trust_boundary(self):
        self.case.task_add("synthetic first task")
        self.case.task_add("synthetic second task")
        with sqlite3.connect(self.case.db) as db:
            db.execute("DELETE FROM audit_events WHERE id=1")
        report = self.case.audit_verify()
        self.assertEqual(report["reason"], "broken_link")
        self.assertFalse(report["ok"])
        self.assertIn("Local mutable", report["trust_boundary"])

    def test_failed_audit_checkpoint_check_sets_exit_code_two(self):
        self.case.task_add("synthetic task")
        checkpoint = self.case.audit_checkpoint()
        manifest = self.root / "checkpoint.json"
        manifest.write_text(json.dumps(checkpoint), encoding="utf-8")
        with sqlite3.connect(self.case.db) as db:
            db.execute("DELETE FROM audit_events WHERE id=(SELECT MAX(id) FROM audit_events)")
        process = self.cli("audit-verify", "--checkpoint", str(manifest))
        self.assertEqual(process.returncode, 2)
        self.assertEqual(json.loads(process.stdout)["reason"], "checkpoint_count_mismatch")

    def test_failed_evidence_verification_sets_exit_code_two(self):
        file = self.source / "one.txt"
        file.write_text("synthetic expected")
        self.case.ingest("sample")
        file.write_text("synthetic different")
        process = self.cli("verify", "sample")
        self.assertEqual(process.returncode, 2)
        self.assertFalse(json.loads(process.stdout)["ok"])


if __name__ == "__main__":
    unittest.main()

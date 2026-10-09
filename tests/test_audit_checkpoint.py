"""Synthetic conformance tests for local, explicitly non-immutable audit checkpoints."""
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


class AuditCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.case = Case(Path(self.tmp.name) / "case")
        self.case.init()

    def test_exported_checkpoint_detects_tail_deletion(self):
        self.case.task_add("synthetic task A")
        self.case.task_add("synthetic task B")
        manifest = self.case.audit_checkpoint()
        self.assertEqual(manifest["event_count"], 2)
        with sqlite3.connect(self.case.db) as db:
            db.execute("DELETE FROM audit_events WHERE id=(SELECT MAX(id) FROM audit_events)")
        # A local hash chain alone cannot detect a deleted tail.
        self.assertTrue(self.case.audit_verify()["ok"])
        verification = self.case.audit_verify(manifest)
        self.assertFalse(verification["ok"])
        self.assertEqual(verification["reason"], "checkpoint_count_mismatch")
        self.assertIn("mutable", verification["trust_boundary"])

    def test_external_checkpoint_detects_locally_rehashed_history(self):
        self.case.task_add("synthetic task")
        manifest = self.case.audit_checkpoint()
        with sqlite3.connect(self.case.db) as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM audit_events WHERE id=1").fetchone()
            new_actor = "rewritten"
            forged_hash = audit._checksum(
                row["previous_hash"], row["created"], new_actor,
                row["action"], row["payload"]
            )
            db.execute(
                "UPDATE audit_events SET actor=?,event_hash=? WHERE id=1",
                (new_actor, forged_hash)
            )
        self.assertTrue(self.case.audit_verify()["ok"])
        self.assertEqual(
            self.case.audit_verify(manifest)["reason"],
            "checkpoint_head_mismatch"
        )

    def test_cannot_export_inconsistent_chain_or_accept_invalid_checkpoint(self):
        self.case.task_add("synthetic task")
        with self.assertRaisesRegex(ValueError, "Invalid audit checkpoint"):
            self.case.audit_verify({"format": "fake", "event_count": 1, "head": "0" * 64})
        with sqlite3.connect(self.case.db) as db:
            db.execute("UPDATE audit_events SET payload='modified' WHERE id=1")
        self.assertEqual(self.case.audit_verify()["reason"], "digest_mismatch")
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            self.case.audit_checkpoint()

    def test_failed_audit_append_rolls_back_corresponding_case_mutation(self):
        real_append = audit.append

        def append_then_fail(*args, **kwargs):
            real_append(*args, **kwargs)
            raise RuntimeError("synthetic audit failure")

        with mock.patch("dfa.store.audit.append", side_effect=append_then_fail):
            with self.assertRaisesRegex(RuntimeError, "synthetic audit failure"):
                self.case.task_add("must roll back")
        with sqlite3.connect(self.case.db) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0], 0)

    def test_checkpoint_cli_roundtrip_across_processes(self):
        def cli(*args):
            return subprocess.run(
                [sys.executable, "-m", "dfa", "--case", str(self.case.root), *args],
                text=True, capture_output=True, check=False,
            )
        self.assertEqual(cli("task-add", "synthetic").returncode, 0)
        exported = cli("audit-checkpoint")
        self.assertEqual(exported.returncode, 0, exported.stderr)
        manifest = json.loads(exported.stdout)
        checkpoint_file = Path(self.tmp.name) / "external-checkpoint.json"
        checkpoint_file.write_text(json.dumps(manifest), encoding="utf-8")
        result = cli("audit-verify", "--checkpoint", str(checkpoint_file))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["ok"])


if __name__ == "__main__":
    unittest.main()

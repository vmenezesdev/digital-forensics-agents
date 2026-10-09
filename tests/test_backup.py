"""Synthetic snapshot and restore conformance, with explicit no-overwrite boundaries."""
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from dfa.store import Case


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.case = Case(self.root / "case")
        self.case.init()
        self.case.source_add("synthetic", self.source)

    def test_backup_cli_and_restored_workspace_preserve_catalog_and_index(self):
        evidence = self.source / "example.txt"
        evidence.write_text("synthetic backupsearchterm", encoding="utf-8")
        self.case.ingest("synthetic")
        self.case.task_add("synthetic task")
        self.case.search("backupsearchterm")
        original_audit = self.case.audit_checkpoint()
        destination = self.root / "snapshot.sqlite3"
        process = subprocess.run(
            [sys.executable, "-m", "dfa", "--case", str(self.case.root),
             "backup", str(destination)],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        result = json.loads(process.stdout)
        self.assertEqual(result["sha256"], hashlib.sha256(destination.read_bytes()).hexdigest())
        self.assertTrue(destination.is_file())
        self.assertEqual(evidence.read_text(encoding="utf-8"), "synthetic backupsearchterm")
        with sqlite3.connect(destination) as db:
            self.assertEqual(db.execute("PRAGMA quick_check").fetchone()[0], "ok")
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 1)

        restored_path = self.root / "restored"
        restored_path.mkdir()
        shutil.copyfile(destination, restored_path / "case.sqlite3")
        restored = Case(restored_path)
        self.assertEqual(restored.status()["tasks"]["available"], 1)
        self.assertEqual(len(restored.search("backupsearchterm")["results"]), 1)
        self.assertTrue(restored.audit_verify(original_audit)["ok"])

    def test_backup_refuses_existing_destination_or_paths_within_case_or_source(self):
        (self.source / "example.txt").write_text("synthetic")
        self.case.ingest("synthetic")
        target = self.root / "existing.sqlite3"
        target.write_text("do not overwrite", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.case.backup(target)
        self.assertEqual(target.read_text(encoding="utf-8"), "do not overwrite")
        with self.assertRaisesRegex(ValueError, "outside the case"):
            self.case.backup(self.case.root / "backup.sqlite3")
        with self.assertRaisesRegex(ValueError, "registered source"):
            self.case.backup(self.source / "backup.sqlite3")
        self.assertFalse((self.source / "backup.sqlite3").exists())
        alias = self.root / "source-alias"
        try:
            alias.symlink_to(self.source, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink aliases unavailable on this runner")
        with self.assertRaisesRegex(ValueError, "registered source"):
            self.case.backup(alias / "nested-backup.sqlite3")
        self.assertFalse((self.source / "nested-backup.sqlite3").exists())


if __name__ == "__main__":
    unittest.main()

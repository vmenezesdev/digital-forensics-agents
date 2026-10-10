"""Synthetic, isolated registration-identity contract tests (issue #6)."""
import sqlite3
import unittest
from dfa import audit
from dfa.source_registration import inspect_source_registration


class SourceRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.execute("CREATE TABLE sources(id TEXT PRIMARY KEY, root TEXT NOT NULL)")
        self.db.executescript(audit.SCHEMA)
        self.db.execute("INSERT INTO sources VALUES (?,?)", ("synthetic", "/synthetic/source-a"))
        self.event_id = audit.append(self.db, "operator", "source.add", {
            "source_id": "synthetic", "root": "/synthetic/source-a"
        })

    def tearDown(self):
        self.db.close()

    def test_registration_stable_after_other_events(self):
        first = inspect_source_registration(self.db, "synthetic")
        self.assertTrue(first["ok"], first)
        self.assertEqual(first["registration_id"], self.event_id)
        audit.append(self.db, "operator", "index.rebuild", {"rebuilt": 1})
        self.assertEqual(inspect_source_registration(self.db, "synthetic"), first)

    def test_remap_same_bytes_cannot_inherit_registration(self):
        self.db.execute("UPDATE sources SET root=? WHERE id=?", (
            "/synthetic/source-b", "synthetic"
        ))
        self.assertEqual(inspect_source_registration(self.db, "synthetic"), {
            "ok": False, "reason": "registration_changed"
        })

    def test_missing_source_and_missing_event_fail_closed(self):
        self.assertEqual(inspect_source_registration(self.db, "unknown"), {
            "ok": False, "reason": "unknown_source"
        })
        self.db.execute("INSERT INTO sources VALUES (?,?)", ("legacy", "/synthetic/legacy"))
        self.assertEqual(inspect_source_registration(self.db, "legacy"), {
            "ok": False, "reason": "registration_unavailable"
        })

    def test_duplicate_registration_fails_closed(self):
        audit.append(self.db, "operator", "source.add", {
            "source_id": "synthetic", "root": "/synthetic/source-a"
        })
        self.assertEqual(inspect_source_registration(self.db, "synthetic"), {
            "ok": False, "reason": "ambiguous_registration"
        })

    def test_audit_integrity_failure_fails_closed(self):
        self.db.execute("UPDATE audit_events SET payload=? WHERE id=1", ('{}',))
        self.assertEqual(inspect_source_registration(self.db, "synthetic"), {
            "ok": False, "reason": "audit_log_inconsistent"
        })

    def test_malformed_registration_event_fails_closed(self):
        audit.append(self.db, "operator", "source.add", ["not", "a", "mapping"])
        self.assertEqual(inspect_source_registration(self.db, "synthetic"), {
            "ok": False, "reason": "malformed_registration_event"
        })

    def test_invalid_identifier_rejected(self):
        for value in (None, "", False, 42):
            with self.subTest(value=value):
                self.assertEqual(inspect_source_registration(self.db, value), {
                    "ok": False, "reason": "invalid_source_id"
                })


if __name__ == "__main__":
    unittest.main()

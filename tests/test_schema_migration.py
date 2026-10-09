"""Synthetic compatibility and migration tests for the local SQLite workspace."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from dfa import audit
from dfa.store import Case, SCHEMA, SCHEMA_VERSION


class SchemaMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.case = Case(self.root / "case")
        self.case.root.mkdir()

    def test_new_workspace_is_versioned_and_init_is_idempotent(self):
        self.assertEqual(self.case.init()["schema_version"], SCHEMA_VERSION)
        self.assertEqual(self.case.init()["schema_version"], SCHEMA_VERSION)
        with sqlite3.connect(self.case.db) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
        self.assertEqual(self.case.status()["sources"], 0)

    def test_upgrade_from_unversioned_trunk_preserves_records(self):
        source = self.root / "synthetic-source"
        source.mkdir()
        with sqlite3.connect(self.case.db) as db:
            db.executescript(SCHEMA + audit.SCHEMA)
            db.execute("INSERT INTO sources(id,root) VALUES(?,?)", ("legacy", str(source)))
            db.execute("INSERT INTO tasks(id,title,status) VALUES(7,'synthetic review','available')")
            db.execute(
                "INSERT INTO receipts(id,query,created,report) VALUES(8,'term',1.0,'{}')"
            )
            db.execute(
                "INSERT INTO evidence(source_id,relpath,sha256,size,status) "
                "VALUES('legacy','synthetic.txt','aaa',4,'indexed')"
            )
            audit.append(db, "tester", "legacy.synthetic", {"test": True})
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 0)
        with self.assertRaisesRegex(ValueError, "run 'dfa"):
            self.case.status()
        self.case.init()
        self.case.init()
        with sqlite3.connect(self.case.db) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
            self.assertEqual(db.execute("SELECT title FROM tasks WHERE id=7").fetchone()[0], "synthetic review")
            self.assertEqual(db.execute("SELECT query FROM receipts WHERE id=8").fetchone()[0], "term")
            self.assertEqual(db.execute("SELECT COUNT(*) FROM evidence").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0], 1)
        self.assertTrue(self.case.audit_verify()["ok"])

    def test_unknown_future_version_fails_closed(self):
        self.case.init()
        with sqlite3.connect(self.case.db) as db:
            db.execute("PRAGMA user_version=99")
        with self.assertRaisesRegex(ValueError, "version 99 unsupported"):
            self.case.status()
        with self.assertRaisesRegex(ValueError, "version 99 unsupported"):
            self.case.init()
        with sqlite3.connect(self.case.db) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 99)

    def test_known_version_with_fake_fts_table_fails_closed(self):
        self.case.init()
        with sqlite3.connect(self.case.db) as db:
            db.execute("DROP TABLE search_index")
            db.execute("CREATE TABLE search_index(evidence_id TEXT,body TEXT)")
        with self.assertRaisesRegex(ValueError, "expected FTS5"):
            self.case.status()
        with self.assertRaisesRegex(ValueError, "expected FTS5"):
            self.case.init()

    def test_unknown_partial_layout_is_not_silently_repaired(self):
        with sqlite3.connect(self.case.db) as db:
            db.execute("CREATE TABLE sources(id TEXT PRIMARY KEY, root TEXT)")
        with self.assertRaisesRegex(ValueError, "layout"):
            self.case.init()
        with sqlite3.connect(self.case.db) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='evidence'").fetchone()[0], 0)

    def test_failed_migration_rolls_back_created_tables_and_version(self):
        with sqlite3.connect(self.case.db) as db:
            db.executescript(SCHEMA)
            db.execute("CREATE TABLE audit_events(broken INTEGER)")
        with self.assertRaisesRegex(ValueError, "audit_events"):
            self.case.init()
        with sqlite3.connect(self.case.db) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 0)
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='audit_events'").fetchone()[0], 1
            )


if __name__ == "__main__":
    unittest.main()

"""Synthetic source-ID validation at the persistent registration boundary (#6)."""
import tempfile
import unittest
from pathlib import Path

from dfa.source_registration import inspect_source_registration
from dfa.store import Case


class SourceIdentifierTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.source = root / "synthetic-source"
        self.source.mkdir()
        self.case = Case(root / "case")
        self.case.init()

    def test_invalid_ids_fail_before_any_database_write(self):
        for source_id in ("", None, False, 0, 42, [], {}, "bad\x00id", "bad\ud800id", "bad\udfffid"):
            with self.subTest(source_id=source_id):
                with self.assertRaisesRegex(ValueError, "Source identifier"):
                    self.case.source_add(source_id, self.source)
                with self.case.connect() as db:
                    self.assertEqual(db.execute("SELECT COUNT(*) FROM sources").fetchone()[0], 0)
                    self.assertEqual(db.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0], 0)

    def test_valid_supplementary_unicode_id_is_registered_and_inspectable(self):
        identifier = "synthetic-\U0001f600"
        self.assertEqual(self.case.source_add(identifier, self.source), {"source": identifier})
        with self.case.connect() as db:
            self.assertTrue(inspect_source_registration(db, identifier)["ok"])

    def test_valid_text_id_is_registered_and_inspectable(self):
        self.assertEqual(self.case.source_add("synthetic", self.source), {"source": "synthetic"})
        with self.case.connect() as db:
            report = inspect_source_registration(db, "synthetic")
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["source_id"], "synthetic")


if __name__ == "__main__":
    unittest.main()

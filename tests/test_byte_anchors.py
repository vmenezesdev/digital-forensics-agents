"""Synthetic conformance tests for the first catalog-bound typed anchor."""
import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

from dfa.anchors import make_byte_range_anchor, validate_byte_range_anchor


class ByteRangeAnchorTests(unittest.TestCase):
    def setUp(self):
        self.record = {
            "id": 7, "source_id": "synthetic", "sha256": hashlib.sha256(b"synthetic anchor bytes").hexdigest(),
            "size": len(b"synthetic anchor bytes"), "status": "indexed", "relpath": "note.txt",
        }
        self.anchor = make_byte_range_anchor(self.record, 0, 9)

    def test_valid_half_open_span_and_no_path_dependency(self):
        self.assertEqual(self.anchor["type"], "byte_range")
        self.assertEqual(self.anchor["start"], 0)
        self.assertEqual(self.anchor["end"], 9)
        self.assertNotIn("relpath", self.anchor)
        renamed = dict(self.record, relpath="renamed.txt")
        self.assertEqual(validate_byte_range_anchor(self.anchor, renamed), self.anchor)

    def test_wrong_source_id_digest_or_evidence_id_rejected(self):
        for field, value in (("source_id", "other"), ("sha256", "0" * 64), ("evidence_id", 8)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_byte_range_anchor(dict(self.anchor, **{field: value}), self.record)

    def test_bad_ranges_and_bool_offsets_rejected(self):
        for start, end in ((-1, 2), (2, 2), (3, 2), (0, self.record["size"] + 1), (False, 2), (0, True)):
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                make_byte_range_anchor(self.record, start, end)

    def test_unsupported_versions_types_and_extra_fields_rejected(self):
        for change in ({"version": 2}, {"type": "text_span"}, {"extra": "untrusted"}, {"sha256": "not-a-digest"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_byte_range_anchor(dict(self.anchor, **change), self.record)

    def test_unreferenceable_or_unhashed_records_rejected(self):
        for status in ("missing", "drift", "error"):
            with self.subTest(status=status), self.assertRaises(ValueError):
                make_byte_range_anchor(dict(self.record, status=status), 0, 1)
        with self.assertRaises(ValueError):
            make_byte_range_anchor(dict(self.record, sha256=None), 0, 1)

    def test_catalog_identity_survives_reopen_and_disposable_index_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "synthetic.sqlite3"
            with sqlite3.connect(db_path) as db:
                db.execute("CREATE TABLE evidence(id INTEGER PRIMARY KEY,source_id TEXT,sha256 TEXT,size INTEGER,status TEXT,relpath TEXT)")
                db.execute("CREATE TABLE disposable_index(evidence_id INTEGER,body TEXT)")
                db.execute("INSERT INTO evidence VALUES (?,?,?,?,?,?)", tuple(self.record[k] for k in ("id", "source_id", "sha256", "size", "status", "relpath")))
                db.execute("INSERT INTO disposable_index VALUES (7,'synthetic')")
            with sqlite3.connect(db_path) as db:
                db.row_factory = sqlite3.Row
                db.execute("DELETE FROM disposable_index")
                db.execute("INSERT INTO disposable_index VALUES (7,'rebuilt')")
                db.execute("UPDATE evidence SET relpath='renamed.txt' WHERE id=7")
                row = db.execute("SELECT * FROM evidence WHERE id=7").fetchone()
                self.assertEqual(validate_byte_range_anchor(self.anchor, row), self.anchor)


if __name__ == "__main__":
    unittest.main()

"""Synthetic regression tests for local-registration-bound v2 byte anchors."""
import tempfile
import unittest
from pathlib import Path
from dfa import audit
from dfa.anchors import (
    inspect_catalog_byte_range, make_byte_range_anchor,
    make_registered_byte_range_anchor, read_verified_byte_range,
    validate_byte_range_anchor,
)
from dfa.store import Case


class RegisteredAnchorTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.source = root / "source"
        self.source.mkdir()
        self.payload = b"synthetic registered anchor bytes"
        (self.source / "note.txt").write_bytes(self.payload)
        self.case = Case(root / "case")
        self.case.init()
        self.case.source_add("synthetic", self.source)
        self.assertEqual(self.case.ingest("synthetic")["scan_status"], "complete")
        with self.case.connect() as db:
            self.row = db.execute(
                "SELECT id,source_id,sha256,size,status FROM evidence "
                "WHERE source_id='synthetic' AND relpath='note.txt'"
            ).fetchone()

    def test_v2_survives_second_session_and_index_rebuild(self):
        anchor = make_registered_byte_range_anchor(self.case, self.row, 0, 9)
        self.assertEqual(anchor["version"], 2)
        self.assertEqual(len(anchor["registration_id"]), 64)
        self.assertTrue(inspect_catalog_byte_range(self.case, anchor)["ok"])
        self.assertEqual(read_verified_byte_range(self.case, anchor)["data"], self.payload[:9])
        reopened = Case(self.case.root)
        self.assertEqual(reopened.index_rebuild()["rebuilt"], 1)
        self.assertTrue(inspect_catalog_byte_range(reopened, anchor)["ok"])
        self.assertEqual(read_verified_byte_range(reopened, anchor)["data"], self.payload[:9])

    def test_same_bytes_root_remap_invalidates_v2_catalog_resolution(self):
        anchor = make_registered_byte_range_anchor(self.case, self.row, 0, 9)
        other = self.source.parent / "replacement"
        other.mkdir()
        (other / "note.txt").write_bytes(self.payload)
        with self.case.connect() as db:
            db.execute("UPDATE sources SET root=? WHERE id='synthetic'", (str(other),))
        self.assertEqual(inspect_catalog_byte_range(self.case, anchor),
                         {"ok": False, "reason": "registration_changed"})
        self.assertEqual(read_verified_byte_range(self.case, anchor),
                         {"ok": False, "reason": "registration_changed"})

    def test_duplicate_source_registration_fails_closed(self):
        anchor = make_registered_byte_range_anchor(self.case, self.row, 0, 9)
        with self.case.connect() as db:
            audit.append(db, "operator", "source.add", {
                "source_id": "synthetic", "root": str(self.source)
            })
        self.assertEqual(inspect_catalog_byte_range(self.case, anchor),
                         {"ok": False, "reason": "ambiguous_registration"})
        with self.assertRaisesRegex(ValueError, "ambiguous_registration"):
            make_registered_byte_range_anchor(self.case, self.row, 0, 9)

    def test_wrong_event_and_malformed_hash_are_rejected(self):
        anchor = make_registered_byte_range_anchor(self.case, self.row, 0, 9)
        for value in ("INVALID", "A" * 64, "", None, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_byte_range_anchor({**anchor, "registration_id": value}, self.row)
        wrong = {**anchor, "registration_id": "f" * 64}
        self.assertEqual(inspect_catalog_byte_range(self.case, wrong),
                         {"ok": False, "reason": "registration_changed"})

    def test_legacy_v1_stays_compatible(self):
        old = make_byte_range_anchor(self.row, 0, 9)
        self.assertEqual(validate_byte_range_anchor(old, self.row), old)
        self.assertTrue(inspect_catalog_byte_range(self.case, old)["ok"])
        with self.assertRaises(ValueError):
            validate_byte_range_anchor({**old, "registration_id": "a" * 64}, self.row)


if __name__ == "__main__":
    unittest.main()

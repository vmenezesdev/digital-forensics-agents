"""Synthetic conformance tests for the first catalog-bound typed anchor."""
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from dfa.store import Case

from dfa.anchors import make_byte_range_anchor, validate_byte_range_anchor, inspect_catalog_byte_range


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

    def test_sqlite_identifier_bounds_rejected_by_constructor_and_validator(self):
        for value in (0, -1, 1 << 63, 1 << 100, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_byte_range_anchor(dict(self.anchor, evidence_id=value), self.record)
        with self.assertRaises(ValueError):
            make_byte_range_anchor(dict(self.record, id=1 << 100), 0, 1)

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


    def test_normative_json_fixture_matches_runtime_contract(self):
        fixture = json.loads((Path(__file__).resolve().parents[1] /
                              "specs/evidence-model/byte-range-anchor.examples.json").read_text())
        record = fixture["catalog_record"]
        self.assertEqual(record["sha256"], hashlib.sha256(fixture["payload_utf8"].encode()).hexdigest())
        anchor = fixture["valid_anchor"]
        self.assertEqual(make_byte_range_anchor(record, anchor["start"], anchor["end"]), anchor)
        for invalid in fixture["invalid_anchors"]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_byte_range_anchor(invalid, record)
        schema = json.loads((Path(__file__).resolve().parents[1] /
                             "specs/evidence-model/byte-range-anchor.schema.json").read_text())
        self.assertEqual(set(schema["required"]), set(anchor))
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["version"]["const"], 1)
        self.assertEqual(schema["properties"]["type"]["const"], "byte_range")

    def test_real_case_anchor_survives_second_session_and_index_rebuild(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "synthetic-source"
            source.mkdir()
            (source / "note.txt").write_text("synthetic stable anchor text", encoding="utf-8")
            case = Case(root / "case")
            case.init()
            case.source_add("sample", source)
            self.assertEqual(case.ingest("sample")["scan_status"], "complete")
            with case.connect() as db:
                record = db.execute(
                    "SELECT id,source_id,sha256,size,status FROM evidence "
                    "WHERE source_id=? AND relpath=?", ("sample", "note.txt")
                ).fetchone()
                anchor = make_byte_range_anchor(record, 0, 9)

            reopened = Case(case.root)
            self.assertEqual(reopened.index_rebuild()["rebuilt"], 1)
            with reopened.connect() as db:
                after = db.execute(
                    "SELECT id,source_id,sha256,size,status FROM evidence "
                    "WHERE source_id=? AND relpath=?", ("sample", "note.txt")
                ).fetchone()
                self.assertEqual(validate_byte_range_anchor(anchor, after), anchor)

    def test_real_case_anchor_fails_closed_after_recorded_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "synthetic-source"
            source.mkdir()
            target = source / "note.txt"
            target.write_text("synthetic original marker", encoding="utf-8")
            case = Case(root / "case")
            case.init()
            case.source_add("sample", source)
            case.ingest("sample")
            with case.connect() as db:
                record = db.execute(
                    "SELECT id,source_id,sha256,size,status FROM evidence "
                    "WHERE source_id=? AND relpath=?", ("sample", "note.txt")
                ).fetchone()
                anchor = make_byte_range_anchor(record, 0, 9)

            target.write_text("synthetic modified marker", encoding="utf-8")
            self.assertEqual(case.ingest("sample")["drift"], 1)
            with Case(case.root).connect() as db:
                drifted = db.execute(
                    "SELECT id,source_id,sha256,size,status FROM evidence "
                    "WHERE source_id=? AND relpath=?", ("sample", "note.txt")
                ).fetchone()
                self.assertEqual(drifted["status"], "drift")
                with self.assertRaises(ValueError):
                    validate_byte_range_anchor(anchor, drifted)


    def test_catalog_resolution_fails_closed_for_incomplete_latest_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "catalog.sqlite3"
            with sqlite3.connect(db_path) as db:
                db.execute("CREATE TABLE evidence(id INTEGER PRIMARY KEY,source_id TEXT,sha256 TEXT,size INTEGER,status TEXT,relpath TEXT)")
                db.execute("CREATE TABLE inventory_runs(id INTEGER PRIMARY KEY,source_id TEXT,status TEXT)")
                db.execute("CREATE TABLE sources(id TEXT PRIMARY KEY,root TEXT NOT NULL)")
                db.execute("INSERT INTO sources VALUES ('synthetic','/synthetic/source')")
                db.execute("INSERT INTO evidence VALUES (?,?,?,?,?,?)", tuple(self.record[k] for k in ("id", "source_id", "sha256", "size", "status", "relpath")))
                db.execute("INSERT INTO inventory_runs VALUES (1,'synthetic','complete')")

            class SyntheticCase:
                def connect(self):
                    connection = sqlite3.connect(db_path)
                    connection.row_factory = sqlite3.Row
                    return connection

            case = SyntheticCase()
            valid = inspect_catalog_byte_range(case, self.anchor)
            self.assertTrue(valid["ok"])
            self.assertEqual(valid["status"], "catalog_consistent")
            self.assertEqual(valid["catalog_relpath"], "note.txt")
            with sqlite3.connect(db_path) as db:
                db.execute("INSERT INTO inventory_runs VALUES (2,'synthetic','partial')")
            self.assertEqual(inspect_catalog_byte_range(case, self.anchor),
                             {"ok": False, "reason": "inventory_incomplete"})
            with sqlite3.connect(db_path) as db:
                db.execute("INSERT INTO inventory_runs VALUES (3,'synthetic','complete')")
            self.assertTrue(inspect_catalog_byte_range(case, self.anchor)["ok"])

    def test_catalog_resolution_rejects_orphaned_source(self):
        """A retained evidence row is not a resolvable source after deletion."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "catalog.sqlite3"
            with sqlite3.connect(db_path) as db:
                db.execute("CREATE TABLE evidence(id INTEGER PRIMARY KEY,source_id TEXT,sha256 TEXT,size INTEGER,status TEXT,relpath TEXT)")
                db.execute("CREATE TABLE inventory_runs(id INTEGER PRIMARY KEY,source_id TEXT,status TEXT)")
                db.execute("CREATE TABLE sources(id TEXT PRIMARY KEY,root TEXT NOT NULL)")
                db.execute("INSERT INTO sources VALUES ('synthetic','/synthetic/source')")
                db.execute("INSERT INTO evidence VALUES (?,?,?,?,?,?)", tuple(self.record[k] for k in ("id", "source_id", "sha256", "size", "status", "relpath")))
                db.execute("INSERT INTO inventory_runs VALUES (1,'synthetic','complete')")

            class SyntheticCase:
                def connect(self):
                    db = sqlite3.connect(db_path)
                    db.row_factory = sqlite3.Row
                    return db

            self.assertTrue(inspect_catalog_byte_range(SyntheticCase(), self.anchor)["ok"])
            with sqlite3.connect(db_path) as db:
                db.execute("DELETE FROM sources WHERE id='synthetic'")
            self.assertEqual(inspect_catalog_byte_range(SyntheticCase(), self.anchor),
                             {"ok": False, "reason": "unknown_source"})

    def test_catalog_resolution_rejects_ambiguous_or_invalid_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "catalog.sqlite3"
            with sqlite3.connect(db_path) as db:
                db.execute("CREATE TABLE evidence(id INTEGER PRIMARY KEY,source_id TEXT,sha256 TEXT,size INTEGER,status TEXT,relpath TEXT)")
                db.execute("CREATE TABLE inventory_runs(id INTEGER PRIMARY KEY,source_id TEXT,status TEXT)")
                db.execute("CREATE TABLE sources(id TEXT PRIMARY KEY,root TEXT NOT NULL)")
                db.execute("INSERT INTO sources VALUES ('synthetic','/synthetic/source')")
                db.execute("INSERT INTO evidence VALUES (?,?,?,?,?,?)", tuple(self.record[k] for k in ("id", "source_id", "sha256", "size", "status", "relpath")))
                db.execute("INSERT INTO inventory_runs VALUES (1,'synthetic','complete')")

            class SyntheticCase:
                def connect(self):
                    connection = sqlite3.connect(db_path)
                    connection.row_factory = sqlite3.Row
                    return connection

            case = SyntheticCase()
            for change, reason in (({"evidence_id": 8}, "unknown_evidence"),
                                   ({"source_id": "other"}, "unknown_evidence"),
                                   ({"sha256": "0" * 64}, "anchor_catalog_mismatch"),
                                   ({"start": 99}, "anchor_catalog_mismatch"),
                                   ({"evidence_id": True}, "invalid_anchor"),
                                   ({"evidence_id": -1}, "invalid_anchor"),
                                   ({"evidence_id": 1 << 100}, "invalid_anchor")):
                with self.subTest(change=change):
                    self.assertEqual(inspect_catalog_byte_range(case, dict(self.anchor, **change)),
                                     {"ok": False, "reason": reason})

    def test_original_byte_span_verified_against_full_digest(self):
        from dfa.anchors import read_verified_byte_range
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            content = b"synthetic-original-byte-anchor-0123456789"
            (source / "original.bin").write_bytes(content)
            case = Case(root / "case")
            case.init()
            case.source_add("sample", source)
            self.assertEqual(case.ingest("sample")["scan_status"], "complete")
            with case.connect() as db:
                row = db.execute("SELECT id,source_id,sha256,size,status FROM evidence WHERE relpath='original.bin'").fetchone()
                anchor = make_byte_range_anchor(row, 10, 18)
            reopened = Case(case.root)
            self.assertEqual(reopened.index_rebuild()["rebuilt"], 1)
            result = read_verified_byte_range(reopened, anchor)
            self.assertTrue(result["ok"], result)
            self.assertEqual(result["data"], content[10:18])
            self.assertEqual(result["status"], "bytes_verified_against_catalog_digest")
            self.assertEqual(read_verified_byte_range(reopened, anchor, max_bytes=3),
                             {"ok": False, "reason": "range_too_large"})

    def test_byte_reader_detects_unrecorded_same_length_drift(self):
        from dfa.anchors import read_verified_byte_range
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            target = source / "note.txt"
            target.write_bytes(b"synthetic-AAA")
            case = Case(root / "case")
            case.init()
            case.source_add("sample", source)
            case.ingest("sample")
            with case.connect() as db:
                row = db.execute("SELECT id,source_id,sha256,size,status FROM evidence WHERE relpath='note.txt'").fetchone()
                anchor = make_byte_range_anchor(row, 0, 9)
            self.assertEqual(read_verified_byte_range(case, anchor)["data"], b"synthetic")
            target.write_bytes(b"synthetic-BBB")
            self.assertEqual(read_verified_byte_range(case, anchor),
                             {"ok": False, "reason": "source_changed"})

    def test_byte_reader_refuses_replaced_symlink_and_partial_scan(self):
        from dfa.anchors import read_verified_byte_range
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            target = source / "note.txt"
            target.write_bytes(b"synthetic known bytes")
            outside = root / "outside.txt"
            outside.write_bytes(b"synthetic known bytes")
            case = Case(root / "case")
            case.init()
            case.source_add("sample", source)
            case.ingest("sample")
            with case.connect() as db:
                row = db.execute("SELECT id,source_id,sha256,size,status FROM evidence WHERE relpath='note.txt'").fetchone()
                anchor = make_byte_range_anchor(row, 0, 9)
            target.unlink()
            try:
                target.symlink_to(outside)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")
            self.assertEqual(read_verified_byte_range(case, anchor),
                             {"ok": False, "reason": "source_unavailable"})
            target.unlink()
            target.write_bytes(b"synthetic known bytes")
            with case.connect() as db:
                db.execute("INSERT INTO inventory_runs(source_id,started,finished,status) "
                           "VALUES('sample',1,2,'partial')")
            self.assertEqual(read_verified_byte_range(case, anchor),
                             {"ok": False, "reason": "inventory_incomplete"})


    def test_byte_reader_detects_source_root_remap_during_read(self):
        """A changed source mapping must not masquerade as verified current bytes."""
        from unittest.mock import patch
        from dfa.anchors import read_verified_byte_range
        from dfa import store

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = root / "original-source"
            replacement = root / "replacement-source"
            original.mkdir()
            replacement.mkdir()
            content = b"synthetic source root mapping"
            (original / "note.txt").write_bytes(content)
            (replacement / "note.txt").write_bytes(content)
            case = Case(root / "case")
            case.init()
            case.source_add("sample", original)
            self.assertEqual(case.ingest("sample")["scan_status"], "complete")
            with case.connect() as db:
                row = db.execute(
                    "SELECT id,source_id,sha256,size,status FROM evidence "
                    "WHERE source_id='sample' AND relpath='note.txt'"
                ).fetchone()
                anchor = make_byte_range_anchor(row, 0, 9)

            original_open = store._open_confined_file
            swapped = False

            def remap_after_open(*args, **kwargs):
                nonlocal swapped
                fd = original_open(*args, **kwargs)
                if not swapped:
                    swapped = True
                    with case.connect() as db:
                        db.execute("UPDATE sources SET root=? WHERE id='sample'",
                                   (str(replacement),))
                return fd

            with patch.object(store, "_open_confined_file", side_effect=remap_after_open):
                result = read_verified_byte_range(case, anchor)
            self.assertTrue(swapped)
            self.assertEqual(result, {"ok": False, "reason": "catalog_changed"})


if __name__ == "__main__":
    unittest.main()

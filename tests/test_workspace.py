import os
import sqlite3
from unittest import mock
import tempfile
import unittest
from pathlib import Path
from dfa.store import Case

class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        self.source=root/"source"
        self.source.mkdir()
        self.case=Case(root/"case")
        self.case.init()
        self.case.source_add("sample",self.source)

    def test_receipts_and_incomplete_coverage(self):
        (self.source/"message.txt").write_text("synthetic evidence alpha")
        (self.source/"media.bin").write_bytes(bytes([0,1,2]))
        counts=self.case.ingest("sample")
        self.assertEqual(counts["indexed"],1)
        self.assertEqual(counts["excluded"],1)
        result=self.case.search("alpha")
        self.assertEqual(len(result["results"]),1)
        self.assertFalse(result["complete"])
        self.assertEqual(result["coverage"]["sample"]["excluded"],1)
        with sqlite3.connect(self.case.db) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM receipts").fetchone()[0],1)

    def test_missing_file_is_not_searchable(self):
        p=self.source/"gone.txt"
        p.write_text("disappearingword")
        self.case.ingest("sample")
        self.assertEqual(len(self.case.search("disappearingword")["results"]),1)
        p.unlink()
        self.case.ingest("sample")
        self.assertEqual(self.case.search("disappearingword")["results"],[])
        with sqlite3.connect(self.case.db) as db:
            self.assertEqual(db.execute("SELECT status FROM evidence WHERE relpath='gone.txt'").fetchone()[0],"missing")

    def test_reindex_is_idempotent(self):
        p=self.source/"memo.txt"
        p.write_text("findable")
        self.case.ingest("sample")
        self.case.ingest("sample")
        self.assertEqual(len(self.case.search("findable")["results"]),1)
        with sqlite3.connect(self.case.db) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM search_index").fetchone()[0],1)

    def test_drift_removes_outdated_index(self):
        p=self.source/"old.txt"
        p.write_text("olderterm")
        self.case.ingest("sample")
        p.write_text("newerterm")
        self.assertEqual(self.case.ingest("sample")["drift"],1)
        self.assertEqual(self.case.search("olderterm")["results"],[])
        self.assertEqual(self.case.search("newerterm")["results"],[])

    def test_search_limit_exposes_truncation(self):
        for n in range(3):
            (self.source/f"{n}.txt").write_text("sharedtoken")
        self.case.ingest("sample")
        receipt=self.case.search("sharedtoken",limit=1)
        self.assertTrue(receipt["truncated"])
        self.assertEqual(len(receipt["results"]),1)

    def test_drift_does_not_overwrite_baseline(self):
        p=self.source/"sample.txt"
        p.write_text("first")
        self.case.ingest("sample")
        p.write_text("second")
        self.assertFalse(self.case.verify("sample")["ok"])
        self.assertEqual(self.case.ingest("sample")["drift"],1)

    def test_task_lease_prevents_stale_worker(self):
        task=self.case.task_add("review")["id"]
        lease=self.case.task_claim(task,"worker1")
        with self.assertRaises(ValueError):
            self.case.task_claim(task,"worker2")
        with self.assertRaises(ValueError):
            self.case.task_complete(task,"wrong")
        self.assertEqual(self.case.task_complete(task,lease["token"])["status"],"done")

    def test_persistent_board_and_case_status(self):
        task=self.case.task_add("Review synthetic material")["id"]
        self.case.message_post(task,"reviewer","Needs source verification")
        self.assertEqual(self.case.task_list()["tasks"][0]["id"],task)
        self.assertEqual(self.case.message_list(task)["messages"][0]["author"],"reviewer")
        self.assertEqual(self.case.status()["tasks"]["available"],1)
        lease=self.case.task_claim(task,"worker")
        self.assertEqual(self.case.status()["tasks"]["working"],1)
        self.case.task_complete(task,lease["token"])
        self.assertEqual(self.case.status()["tasks"]["done"],1)
        other=Case(self.case.root)
        self.assertEqual(other.task_list()["tasks"][0]["status"],"done")

    def test_audit_checksums_detect_row_modification(self):
        task=self.case.task_add("audit work")["id"]
        self.case.message_post(task,"worker","note")
        self.assertTrue(self.case.audit_verify()["ok"])
        with sqlite3.connect(self.case.db) as db:
            db.execute("UPDATE audit_events SET action='tampered' WHERE id=1")
        report=self.case.audit_verify()
        self.assertFalse(report["ok"])
        self.assertEqual(report["reason"],"digest_mismatch")

    def test_file_symlink_not_followed_during_ingest(self):
        outside=Path(self.tmp.name)/"outside.txt"
        outside.write_text("outside_secret")
        link=self.source/"linked.txt"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("Symbolic links not available")
        result=self.case.ingest("sample")
        self.assertEqual(result["excluded"],1)
        self.assertEqual(self.case.search("outside_secret")["results"],[])
        with sqlite3.connect(self.case.db) as db:
            record=db.execute(
                "SELECT status,reason FROM evidence WHERE relpath='linked.txt'"
            ).fetchone()
            self.assertEqual(record,("excluded","not_regular"))

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"), "Requires O_NOFOLLOW")
    def test_swapped_final_symlink_at_open_is_not_read(self):
        from dfa.store import _inspect_file
        target=self.source/"candidate.txt"
        target.write_text("original")
        outside=Path(self.tmp.name)/"outside.txt"
        outside.write_text("secret")
        real_open=os.open
        def swap_before_open(path, flags, *args, **kwargs):
            if str(path)==str(target):
                target.unlink()
                target.symlink_to(outside)
            return real_open(path, flags, *args, **kwargs)
        with mock.patch("dfa.store.os.open",side_effect=swap_before_open):
            with self.assertRaises(OSError):
                _inspect_file(target,1024)

    def test_read_is_bounded_and_verification_errors_are_reported(self):
        from dfa.store import _inspect_file
        target=self.source/"long.txt"
        target.write_text("abcdefghij")
        digest,size,content,changed=_inspect_file(target,3)
        self.assertEqual(size,10)
        self.assertIsNone(content)
        self.assertFalse(changed)
        self.case.ingest("sample")
        with mock.patch("dfa.store.sha256_file",side_effect=OSError("unreadable")):
            report=self.case.verify("sample")
        self.assertFalse(report["ok"])
        self.assertIn({"path":"long.txt","reason":"unreadable_or_changed"},report["issues"])

    def test_interrupted_walk_rolls_back_and_records_failure(self):
        old=self.source/"existing.txt"
        old.write_text("stabletoken")
        self.case.ingest("sample")
        old.unlink()
        fresh=self.source/"uncommitted.txt"
        fresh.write_text("newtoken")
        normal_walk=os.walk

        def interrupted_walk(*args, **kwargs):
            yield from normal_walk(*args, **kwargs)
            kwargs["onerror"](PermissionError("synthetic unreadable directory"))

        with mock.patch("dfa.store.os.walk", side_effect=interrupted_walk):
            with self.assertRaisesRegex(ValueError,"rolled back"):
                self.case.ingest("sample")
        with sqlite3.connect(self.case.db) as db:
            rows=db.execute("SELECT relpath,status FROM evidence").fetchall()
            self.assertEqual(rows,[("existing.txt","indexed")])
            run=db.execute(
                "SELECT status,error FROM inventory_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()
            self.assertEqual(run,("failed","PermissionError"))
        receipt=self.case.search("stabletoken")
        self.assertEqual(receipt["inventory"]["sample"]["status"],"failed")
        self.assertFalse(receipt["complete"])
        self.assertEqual(self.case.status()["latest_inventory"]["sample"]["status"],"failed")

    def test_file_read_failure_creates_partial_inventory(self):
        (self.source/"unreadable.txt").write_text("secret")
        with mock.patch("dfa.store._inspect_file", side_effect=OSError("synthetic read error")):
            result=self.case.ingest("sample")
        self.assertEqual(result["scan_status"],"partial")
        self.assertEqual(result["errors"],1)
        self.assertEqual(self.case.search("secret")["results"],[])
        self.assertEqual(self.case.status()["latest_inventory"]["sample"]["status"],"partial")

    def test_replaced_source_root_fails_without_reading_target(self):
        moved=Path(self.tmp.name)/"moved-source"
        try:
            self.source.rename(moved)
            self.source.symlink_to(moved, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Cannot create symlink for this test")
        with self.assertRaises(ValueError):
            self.case.ingest("sample")
        self.assertEqual(self.case.status()["latest_inventory"]["sample"]["status"],"failed")
        verification=self.case.verify("sample")
        self.assertFalse(verification["ok"])
        self.assertEqual(verification["issues"][0]["reason"],"source_root_unavailable_or_symlink")

    def test_reject_nested_source(self):
        with self.assertRaises(ValueError):
            self.case.source_add("bad",Path(self.tmp.name))

if __name__=="__main__":
    unittest.main()

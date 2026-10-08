import sqlite3
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

    def test_reject_nested_source(self):
        with self.assertRaises(ValueError):
            self.case.source_add("bad",Path(self.tmp.name))

if __name__=="__main__":
    unittest.main()

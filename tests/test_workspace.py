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
        self.assertEqual(result["coverage"]["excluded"],1)
        with sqlite3.connect(self.case.db) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM receipts").fetchone()[0],1)

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

    def test_reject_nested_source(self):
        with self.assertRaises(ValueError):
            self.case.source_add("bad",Path(self.tmp.name))

if __name__=="__main__":
    unittest.main()

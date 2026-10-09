"""Synthetic failure and concurrency gates for the persistent local task board."""
import concurrent.futures
import json
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from dfa.store import Case


class CoordinationConformanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.case = Case(Path(self.tmp.name) / "case")
        self.case.init()

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "dfa", "--case", str(self.case.root), *args],
            text=True, capture_output=True, check=False,
        )

    def test_expired_lease_can_be_reclaimed_but_old_token_cannot_complete(self):
        task = self.case.task_add("synthetic review")["id"]
        first = self.case.task_claim(task, "worker-A", duration=10)
        with sqlite3.connect(self.case.db) as db:
            db.execute(
                "UPDATE tasks SET lease_until=? WHERE id=?", (time.time() - 1, task)
            )
        fresh_session = Case(self.case.root)
        second = fresh_session.task_claim(task, "worker-B", duration=10)
        self.assertNotEqual(first["token"], second["token"])
        with self.assertRaisesRegex(ValueError, "Invalid or expired"):
            self.case.task_complete(task, first["token"])
        self.assertEqual(
            fresh_session.task_complete(task, second["token"])["status"],
            "done"
        )

    def test_concurrent_processes_have_at_most_one_successful_claim(self):
        task = self.case.task_add("synthetic one-owner task")["id"]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            attempts = list(pool.map(
                lambda worker: self.cli("task-claim", str(task), worker),
                ("worker-A", "worker-B"),
            ))
        self.assertEqual(sorted(p.returncode for p in attempts), [0, 1])
        owners = self.case.task_list()["tasks"]
        self.assertEqual(len(owners), 1)
        self.assertIn(owners[0]["owner"], ("worker-A", "worker-B"))
        for failed in (p for p in attempts if p.returncode != 0):
            self.assertIn("Unavailable task", json.loads(failed.stderr)["error"])

    def test_malformed_search_or_invalid_limit_is_rejected(self):
        source = Path(self.tmp.name) / "synthetic-source"
        source.mkdir()
        self.case.source_add("synthetic", source)
        (source / "one.txt").write_text("synthetic example")
        self.case.ingest("synthetic")
        with self.assertRaisesRegex(ValueError, "Invalid query"):
            self.case.search(" ")
        with self.assertRaisesRegex(ValueError, "Invalid query"):
            self.case.search("example", limit=0)
        with self.assertRaisesRegex(ValueError, "Invalid FTS query"):
            self.case.search('"unterminated')
        cli = self.cli("search", '"unterminated')
        self.assertEqual(cli.returncode, 1)
        self.assertIn("Invalid FTS query", json.loads(cli.stderr)["error"])


if __name__ == "__main__":
    unittest.main()

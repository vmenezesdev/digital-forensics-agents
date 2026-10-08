"""Local experimental evidence workspace (synthetic material only)."""
import hashlib
import json
import sqlite3
import time
import secrets
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY, root TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS evidence(id INTEGER PRIMARY KEY,source_id TEXT,relpath TEXT,sha256 TEXT,size INTEGER,status TEXT,reason TEXT,UNIQUE(source_id,relpath));
CREATE VIRTUAL TABLE IF NOT EXISTS search_index USING fts5(evidence_id UNINDEXED,body);
CREATE TABLE IF NOT EXISTS receipts(id INTEGER PRIMARY KEY,query TEXT,created REAL,report TEXT);
CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY,title TEXT,status TEXT DEFAULT 'available',owner TEXT,token TEXT,lease_until REAL);
CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY,task_id INTEGER,author TEXT,body TEXT,created REAL);
"""

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

class Case:
    def __init__(self, root):
        self.root = Path(root).expanduser().absolute()
        if self.root.is_symlink():
            raise ValueError("Symlink case root prohibited")
        self.db = self.root / "case.sqlite3"

    def connect(self):
        if not self.db.is_file():
            raise ValueError("Case not initialized")
        db = sqlite3.connect(self.db, timeout=30)
        db.row_factory = sqlite3.Row
        return db

    def init(self):
        self.root.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db) as db:
            db.executescript(SCHEMA)
        return {"case": str(self.root)}

    def source_add(self, source_id, folder):
        p = Path(folder).expanduser().absolute()
        if p.is_symlink() or not p.is_dir():
            raise ValueError("Source must be a real directory")
        p = p.resolve()
        case = self.root.resolve()
        if p == case or p in case.parents or case in p.parents:
            raise ValueError("Case and source must be separate")
        with self.connect() as db:
            db.execute("INSERT INTO sources VALUES (?,?)", (source_id, str(p)))
        return {"source": source_id}

    def ingest(self, source_id, max_text_bytes=1048576):
        """Inventory a source, preserving initial digests and replacing stale index entries.

        Not a forensic acquisition. A completed scan is an inventory of reachable
        paths at that moment; it is not proof of an exhaustive acquisition.
        """
        import os
        if not 0 <= max_text_bytes <= 4194304:
            raise ValueError("Invalid limit")
        with self.connect() as db:
            row = db.execute("SELECT root FROM sources WHERE id=?", (source_id,)).fetchone()
            if row is None:
                raise ValueError("Unknown source")
            root = Path(row["root"])
            if root.is_symlink() or not root.is_dir():
                raise ValueError("Source directory unavailable or replaced by symlink")
            db.execute("CREATE TEMP TABLE seen_paths(relpath TEXT PRIMARY KEY)")
            counts = {"indexed": 0, "excluded": 0, "drift": 0, "errors": 0, "missing": 0}
            def walk_error(error):
                raise error
            for folder, dirs, files in os.walk(root, followlinks=False, onerror=walk_error):
                for directory in list(dirs):
                    if (Path(folder)/directory).is_symlink():
                        dirs.remove(directory)
                        files.append(directory)
                for filename in files:
                    path = Path(folder)/filename
                    rel = path.relative_to(root).as_posix()
                    db.execute("INSERT INTO seen_paths(relpath) VALUES(?)", (rel,))
                    prior = db.execute(
                        "SELECT id,sha256 FROM evidence WHERE source_id=? AND relpath=?",
                        (source_id, rel)
                    ).fetchone()
                    digest, size, body, reason = None, None, None, None
                    if path.is_symlink() or not path.is_file():
                        status, reason = "excluded", "not_regular"
                    else:
                        try:
                            before = path.stat()
                            digest = sha256_file(path)
                            after = path.stat()
                            size = after.st_size
                            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                                status, reason = "error", "changed_during_hash"
                            elif prior and prior["sha256"] and digest != prior["sha256"]:
                                status, reason = "drift", "baseline_mismatch"
                            elif size > max_text_bytes:
                                status, reason = "excluded", "oversized"
                            else:
                                raw = path.read_bytes()
                                if hashlib.sha256(raw).hexdigest() != digest:
                                    status, reason = "error", "changed_during_read"
                                elif bytes([0]) in raw:
                                    status, reason = "excluded", "binary"
                                else:
                                    try:
                                        body = raw.decode("utf-8")
                                        status = "indexed"
                                    except UnicodeDecodeError:
                                        status, reason = "excluded", "not_utf8"
                        except OSError:
                            status, reason = "error", "unreadable"
                    counts["errors" if status == "error" else status] += 1
                    if prior:
                        evidence_id = prior["id"]
                        db.execute(
                            "UPDATE evidence SET sha256=COALESCE(sha256,?),"
                            "size=COALESCE(size,?),status=?,reason=? WHERE id=?",
                            (digest, size, status, reason, evidence_id)
                        )
                    else:
                        db.execute(
                            "INSERT INTO evidence(source_id,relpath,sha256,size,status,reason)"
                            " VALUES(?,?,?,?,?,?)",
                            (source_id, rel, digest, size, status, reason)
                        )
                        evidence_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
                    # FTS is a disposable projection. Remove stale text for drift,
                    # errors, reclassified files and repeated inventories.
                    db.execute("DELETE FROM search_index WHERE evidence_id=?", (str(evidence_id),))
                    if status == "indexed" and body is not None:
                        db.execute(
                            "INSERT INTO search_index(evidence_id,body) VALUES(?,?)",
                            (str(evidence_id), body)
                        )
            vanished = db.execute(
                "SELECT id FROM evidence WHERE source_id=? AND relpath NOT IN "
                "(SELECT relpath FROM seen_paths) AND status!='missing'",
                (source_id,)
            ).fetchall()
            for record in vanished:
                db.execute("DELETE FROM search_index WHERE evidence_id=?", (str(record["id"]),))
                db.execute(
                    "UPDATE evidence SET status='missing',reason='not_in_latest_inventory' WHERE id=?",
                    (record["id"],)
                )
            counts["missing"] = db.execute(
                "SELECT COUNT(*) FROM evidence WHERE source_id=? AND status='missing'",
                (source_id,)
            ).fetchone()[0]
            return {"source": source_id, **counts,
                    "limitation": "Inventory of reachable paths only; UTF-8 text indexing, no OCR/STT"}

    def search(self, query, limit=20):
        if not query or not query.strip() or not 1 <= limit <= 100:
            raise ValueError("Invalid query or result limit")
        with self.connect() as db:
            try:
                rows = db.execute(
                    "SELECT e.id,e.source_id,e.relpath FROM search_index i "
                    "JOIN evidence e ON e.id=CAST(i.evidence_id AS INTEGER) "
                    "WHERE search_index MATCH ? AND e.status='indexed' "
                    "ORDER BY e.id LIMIT ?", (query, limit + 1)
                ).fetchall()
            except sqlite3.OperationalError as error:
                raise ValueError("Invalid FTS query") from error
            coverage = {
                source["source_id"]: {r["status"]: r["n"] for r in db.execute(
                    "SELECT status,COUNT(*) AS n FROM evidence "
                    "WHERE source_id=? GROUP BY status", (source["source_id"],)
                )}
                for source in db.execute("SELECT id AS source_id FROM sources")
            }
            selected = rows[:limit]
            receipt = {
                "query": query, "results": [dict(r) for r in selected],
                "coverage": coverage,
                "result_limit": limit, "truncated": len(rows) > limit,
                "complete": False,
                "limitation": "Only indexed UTF-8 text was searched. Inventory may be incomplete; "
                              "no-match does not prove absence."
            }
            db.execute("INSERT INTO receipts(query,created,report) VALUES(?,?,?)",
                       (query, time.time(), json.dumps(receipt, sort_keys=True)))
            receipt["receipt_id"] = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            return receipt

    def verify(self, source_id):
        with self.connect() as db:
            row=db.execute("SELECT root FROM sources WHERE id=?",(source_id,)).fetchone()
            if row is None:
                raise ValueError("Unknown source")
            issues=[]
            for r in db.execute("SELECT relpath,sha256 FROM evidence WHERE source_id=?",(source_id,)):
                p=Path(row["root"])/r["relpath"]
                if p.is_symlink() or not p.is_file():
                    issues.append({"path":r["relpath"],"reason":"missing_or_symlink"})
                elif r["sha256"] and sha256_file(p)!=r["sha256"]:
                    issues.append({"path":r["relpath"],"reason":"digest_mismatch"})
        return {"ok":not issues,"issues":issues}

    def task_add(self, title):
        with self.connect() as db:
            db.execute("INSERT INTO tasks(title) VALUES(?)",(title,))
            return {"id":db.execute("SELECT last_insert_rowid()").fetchone()[0]}

    def task_claim(self, task_id, actor, duration=600):
        if not actor or not 1 <= duration <= 86400:
            raise ValueError("Invalid lease")
        token=secrets.token_urlsafe(24)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("SELECT status,lease_until FROM tasks WHERE id=?",(task_id,)).fetchone()
            if not row or not (row["status"]=="available" or row["status"]=="working" and row["lease_until"] is not None and row["lease_until"]<time.time()):
                raise ValueError("Unavailable task")
            db.execute("UPDATE tasks SET status='working',owner=?,token=?,lease_until=? WHERE id=?",(actor,token,time.time()+duration,task_id))
        return {"task_id":task_id,"token":token}

    def task_complete(self, task_id, token):
        with self.connect() as db:
            changed=db.execute("UPDATE tasks SET status='done',token=NULL WHERE id=? AND status='working' AND token=? AND lease_until>?",(task_id,token,time.time())).rowcount
            if not changed:
                raise ValueError("Invalid or expired lease")
        return {"task_id":task_id,"status":"done","note":"Not a human forensic review"}

    def message_post(self, task_id, actor, body):
        with self.connect() as db:
            db.execute("INSERT INTO messages(task_id,author,body,created) VALUES(?,?,?,?)",(task_id,actor,body,time.time()))
        return {"task_id":task_id,"posted":True}

    def task_list(self):
        with self.connect() as db:
            rows=db.execute("SELECT id,title,status,owner,lease_until FROM tasks ORDER BY id").fetchall()
            return {"tasks":[dict(row) for row in rows]}

    def message_list(self, task_id):
        with self.connect() as db:
            rows=db.execute(
                "SELECT id,task_id,author,body,created FROM messages WHERE task_id=? ORDER BY id",
                (task_id,)
            ).fetchall()
            return {"task_id":task_id,"messages":[dict(row) for row in rows]}

    def status(self):
        with self.connect() as db:
            sources=db.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
            evidence={row["status"]:row["n"] for row in db.execute(
                "SELECT status,COUNT(*) AS n FROM evidence GROUP BY status"
            )}
            tasks={row["status"]:row["n"] for row in db.execute(
                "SELECT status,COUNT(*) AS n FROM tasks GROUP BY status"
            )}
            return {"sources":sources,"evidence":evidence,"tasks":tasks,
                    "scope":"Recorded catalog state, not evidence acquisition completeness"}

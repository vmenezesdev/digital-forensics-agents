"""Local experimental evidence workspace (synthetic material only)."""
import hashlib
import json
import sqlite3
import time
import secrets
import os
import stat
from pathlib import Path
from . import audit

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY, root TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS evidence(id INTEGER PRIMARY KEY,source_id TEXT,relpath TEXT,sha256 TEXT,size INTEGER,status TEXT,reason TEXT,UNIQUE(source_id,relpath));
CREATE VIRTUAL TABLE IF NOT EXISTS search_index USING fts5(evidence_id UNINDEXED,body);
CREATE TABLE IF NOT EXISTS receipts(id INTEGER PRIMARY KEY,query TEXT,created REAL,report TEXT);
CREATE TABLE IF NOT EXISTS inventory_runs(id INTEGER PRIMARY KEY,source_id TEXT NOT NULL,started REAL NOT NULL,finished REAL,status TEXT NOT NULL,error TEXT,counts TEXT);
CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY,title TEXT,status TEXT DEFAULT 'available',owner TEXT,token TEXT,lease_until REAL);
CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY,task_id INTEGER,author TEXT,body TEXT,created REAL);
"""

SCHEMA_VERSION = 1
# Minimum columns required by the legacy unversioned workspace.
_REQUIRED_COLUMNS = {
    "sources": {"id", "root"},
    "evidence": {"id", "source_id", "relpath", "sha256", "size", "status", "reason"},
    "search_index": {"evidence_id", "body"},
    "receipts": {"id", "query", "created", "report"},
    "tasks": {"id", "title", "status", "owner", "token", "lease_until"},
    "messages": {"id", "task_id", "author", "body", "created"},
}
_VERSIONED_COLUMNS = {
    **_REQUIRED_COLUMNS,
    "inventory_runs": {"id", "source_id", "started", "finished", "status", "error", "counts"},
    "audit_events": {"id", "created", "actor", "action", "payload", "previous_hash", "event_hash"},
}


def _check_layout(db, required):
    for table, columns in required.items():
        actual = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
        if not columns.issubset(actual):
            raise ValueError(
                f"Unsupported or damaged workspace layout: {table}; "
                "restore a known-good backup before retrying"
            )
    definition = db.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='search_index'"
    ).fetchone()
    if not definition or not definition[0] or (
        "VIRTUAL TABLE" not in definition[0].upper()
        or "USING FTS5" not in definition[0].upper()
    ):
        raise ValueError(
            "Unsupported or damaged workspace search_index: expected FTS5; "
            "restore a known-good backup"
        )


_SECURE_DIR_FD = (
    os.open in os.supports_dir_fd
    and hasattr(os, "O_DIRECTORY")
    and hasattr(os, "O_NOFOLLOW")
)


def _open_confined_file(path, root, flags, root_identity=None):
    """Open beneath a source root without following intermediate symlinks.

    This guards file reads, not the separate directory-name discovery by
    os.walk. If the platform lacks descriptor-relative no-follow opens,
    fail closed instead of claiming containment.
    """
    if not _SECURE_DIR_FD:
        raise OSError("Secure descriptor-relative opens unavailable on this platform")
    try:
        relative = Path(path).relative_to(root)
    except ValueError as error:
        raise OSError("File path is outside the registered source root") from error
    if not relative.parts or any(part in (".", "..") for part in relative.parts):
        raise OSError("Invalid evidence-relative path")
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    directory_fd = os.open(root, directory_flags)
    try:
        if root_identity is not None:
            actual = os.fstat(directory_fd)
            if (actual.st_dev, actual.st_ino) != root_identity:
                raise OSError("Registered source root changed during inspection")
        for component in relative.parts[:-1]:
            next_fd = os.open(component, directory_flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_fd
        return os.open(relative.parts[-1], flags, dir_fd=directory_fd)
    finally:
        os.close(directory_fd)


def _inspect_file(path, max_text_bytes=None, root=None, root_identity=None):
    """Read one regular file through one descriptor, without following its final symlink.

    Memory is bounded by max_text_bytes when textual bytes are requested.
    When root is supplied, every component below root is opened via a
    no-follow directory descriptor. Source-root ancestors and the separate
    directory walk remain outside this boundary; not forensic acquisition.
    """
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    elif Path(path).is_symlink():
        raise OSError("Symbolic links are not allowed")
    fd = (_open_confined_file(path, root, flags, root_identity=root_identity) if root is not None
          else os.open(path, flags))
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise OSError("Not a regular file")
        hasher = hashlib.sha256()
        collect = max_text_bytes is not None and before.st_size <= max_text_bytes
        captured = bytearray() if collect else None
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
            if captured is not None:
                if len(captured) + len(chunk) > max_text_bytes:
                    captured = None
                else:
                    captured.extend(chunk)
        after = os.fstat(fd)
        attributes = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        changed = attributes(before) != attributes(after)
        return hasher.hexdigest(), after.st_size, bytes(captured) if captured is not None else None, changed
    finally:
        os.close(fd)


def sha256_file(path, root=None, root_identity=None):
    digest, _, _, changed = _inspect_file(path, root=root, root_identity=root_identity)
    if changed:
        raise OSError("File changed while hashing")
    return digest

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
        try:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version != SCHEMA_VERSION:
                raise ValueError(
                    f"Workspace schema version {version} unsupported; "
                    "run 'dfa --case CASE_PATH init' to upgrade a legacy v0 "
                    "workspace, or restore a compatible backup"
                )
            _check_layout(db, _VERSIONED_COLUMNS)
        except Exception:
            db.close()
            raise
        db.row_factory = sqlite3.Row
        return db

    def init(self):
        self.root.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db, timeout=30) as db:
            db.execute("BEGIN IMMEDIATE")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, SCHEMA_VERSION):
                raise ValueError(
                    f"Workspace schema version {version} unsupported; "
                    "restore a compatible backup instead of downgrading"
                )
            if version == 0:
                existing = db.execute(
                    "SELECT COUNT(*) FROM sqlite_master "
                    "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                ).fetchone()[0]
                if existing:
                    _check_layout(db, _REQUIRED_COLUMNS)
                # Execute statements individually; executescript() would commit
                # early and defeat atomic migration/rollback.
                for statement in (SCHEMA + audit.SCHEMA).split(";"):
                    if statement.strip():
                        db.execute(statement)
                _check_layout(db, _VERSIONED_COLUMNS)
                db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            else:
                _check_layout(db, _VERSIONED_COLUMNS)
        return {"case": str(self.root), "schema_version": SCHEMA_VERSION}

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
            audit.append(db, "operator", "source.add", {"source_id": source_id, "root": str(p)})
        return {"source": source_id}

    def ingest(self, source_id, max_text_bytes=1048576):
        """Inventory reachable paths and record partial/failed attempts separately.

        This is not forensic acquisition; a successful walk still says nothing
        about the authenticity or completeness of the acquired evidence.
        """
        if not 0 <= max_text_bytes <= 4194304:
            raise ValueError("Invalid limit")
        with self.connect() as db:
            row = db.execute("SELECT root FROM sources WHERE id=?", (source_id,)).fetchone()
            if row is None:
                raise ValueError("Unknown source")
            db.execute(
                "INSERT INTO inventory_runs(source_id,started,status) VALUES(?,?,'running')",
                (source_id, time.time())
            )
            run_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            db.commit()  # Record the attempt even if the inventory rolls back.
            counts = {"indexed": 0, "excluded": 0, "drift": 0, "errors": 0, "missing": 0}
            try:
                root = Path(row["root"])
                if root.is_symlink() or not root.is_dir():
                    raise ValueError("Source directory unavailable or replaced by symlink")
                root_stat = root.stat(follow_symlinks=False)
                if not stat.S_ISDIR(root_stat.st_mode):
                    raise ValueError("Registered source root is not a directory")
                root_identity = (root_stat.st_dev, root_stat.st_ino)
                db.execute("BEGIN IMMEDIATE")
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
                        try:
                            discovered_mode = path.lstat().st_mode
                        except OSError:
                            status, reason = "error", "unavailable_during_inventory"
                        else:
                            if not stat.S_ISREG(discovered_mode):
                                status, reason = "excluded", "not_regular"
                            else:
                                try:
                                    digest, size, raw, changed = _inspect_file(
                                        path, max_text_bytes, root=root, root_identity=root_identity
                                    )
                                    if changed:
                                        status, reason = "error", "changed_during_read"
                                    elif prior and prior["sha256"] and digest != prior["sha256"]:
                                        status, reason = "drift", "baseline_mismatch"
                                    elif size > max_text_bytes:
                                        status, reason = "excluded", "oversized"
                                    elif raw is None:
                                        status, reason = "error", "content_unavailable"
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
                ending_root = root.stat(follow_symlinks=False)
                if ((ending_root.st_dev, ending_root.st_ino) != root_identity
                        or not stat.S_ISDIR(ending_root.st_mode)):
                    raise OSError("Registered source root changed during traversal")
                # Missing paths can only be inferred after an error-free traversal.
                if counts["errors"] == 0:
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
                # A partial scan cannot establish the number of absent paths.
                if counts["errors"]:
                    counts["missing"] = None
                scan_status = "partial" if counts["errors"] else "complete"
                db.execute(
                    "UPDATE inventory_runs SET finished=?,status=?,counts=? WHERE id=?",
                    (time.time(), scan_status, json.dumps(counts, sort_keys=True), run_id)
                )
                audit.append(db, "operator", "source.ingest", {
                    "source_id": source_id, "run_id": run_id,
                    "scan_status": scan_status, "counts": counts
                })
                return {
                    "source": source_id, "scan_run_id": run_id,
                    "scan_status": scan_status, **counts,
                    "limitation": "Reachable-path inventory only; not forensic acquisition; no OCR/STT"
                }
            except (OSError, ValueError) as error:
                # The partial catalog/index/vanished-file changes must never commit.
                db.rollback()
                db.execute(
                    "UPDATE inventory_runs SET finished=?,status='failed',error=?,counts=? WHERE id=?",
                    (time.time(), type(error).__name__, json.dumps(counts, sort_keys=True), run_id)
                )
                audit.append(db, "operator", "source.ingest_failed", {
                    "source_id": source_id, "run_id": run_id,
                    "error_type": type(error).__name__
                })
                db.commit()
                raise ValueError(
                    f"Inventory run {run_id} failed ({type(error).__name__}); "
                    "catalog changes rolled back. Coverage may be outdated."
                ) from error

    def backup(self, destination):
        """Create a consistent SQLite snapshot outside the case and source trees."""
        target = Path(destination).expanduser().absolute()
        if target.exists() or target.is_symlink():
            raise ValueError("Backup destination already exists")
        if not target.parent.is_dir():
            raise ValueError("Backup parent directory does not exist")
        # Also reject aliases through parent-directory symlinks. These checks
        # cannot defend against hostile concurrent changes to the filesystem.
        canonical_target = target.parent.resolve() / target.name
        case_root = self.root.resolve()
        if canonical_target == case_root or case_root in canonical_target.parents:
            raise ValueError("Backup must be stored outside the case workspace")
        with self.connect() as db:
            for row in db.execute("SELECT root FROM sources"):
                source = Path(row["root"]).resolve()
                if canonical_target == source or source in canonical_target.parents:
                    raise ValueError("Backup must not modify a registered source")
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(target, flags, 0o600)
            os.close(fd)
            try:
                backup_db = sqlite3.connect(target)
                try:
                    db.backup(backup_db)
                    if backup_db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                        raise ValueError("Backup integrity check failed")
                finally:
                    backup_db.close()
                digest = sha256_file(target)
            except BaseException:
                target.unlink(missing_ok=True)
                raise
        return {
            "backup": str(target), "sha256": digest,
            "limitation": (
                "SQLite snapshot only; externally referenced source bytes are not copied. "
                "Store separately with access controls and a documented retention policy."
            )
        }

    def index_rebuild(self, max_text_bytes=1048576):
        """Atomically reconstruct disposable FTS from unchanged, verified source bytes.

        Never edits source files, baseline digests, evidence statuses, or receipts.
        A failed source read or digest mismatch leaves the previous FTS intact.
        Sources without a complete latest scan are deliberately excluded.
        """
        if not 0 <= max_text_bytes <= 4194304:
            raise ValueError("Invalid limit")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM search_index")
            rebuilt = 0
            skipped_unverified = 0
            for row in db.execute(
                "SELECT e.id,e.relpath,e.sha256,e.size,e.source_id,s.root "
                "FROM evidence e JOIN sources s ON s.id=e.source_id "
                "WHERE e.status='indexed' ORDER BY e.id"
            ):
                latest = db.execute(
                    "SELECT status FROM inventory_runs WHERE source_id=? "
                    "ORDER BY id DESC LIMIT 1", (row["source_id"],)
                ).fetchone()
                if not latest or latest["status"] != "complete":
                    skipped_unverified += 1
                    continue
                root = Path(row["root"])
                if root.is_symlink() or not root.is_dir():
                    raise ValueError(
                        f"Cannot rebuild index for unavailable source {row['source_id']}; "
                        "previous index retained"
                    )
                try:
                    digest, size, raw, changed = _inspect_file(
                        root / row["relpath"], max_text_bytes, root=root
                    )
                except OSError as error:
                    raise ValueError(
                        f"Cannot rebuild index for unreadable evidence id {row['id']}; "
                        "previous index retained"
                    ) from error
                if (changed or not row["sha256"] or digest != row["sha256"]
                        or size != row["size"] or raw is None or bytes([0]) in raw):
                    raise ValueError(
                        f"Cannot rebuild index for changed/incompatible evidence id {row['id']}; "
                        "previous index retained"
                    )
                try:
                    body = raw.decode("utf-8")
                except UnicodeDecodeError as error:
                    raise ValueError(
                        f"Cannot rebuild index for non-UTF8 evidence id {row['id']}; "
                        "previous index retained"
                    ) from error
                db.execute(
                    "INSERT INTO search_index(evidence_id,body) VALUES(?,?)",
                    (str(row["id"]), body)
                )
                rebuilt += 1
            audit.append(db, "operator", "index.rebuild", {
                "rebuilt": rebuilt, "skipped_unverified": skipped_unverified,
                "max_text_bytes": max_text_bytes
            })
            return {
                "rebuilt": rebuilt,
                "skipped_unverified": skipped_unverified,
                "limitation": (
                    "Source bytes were reread only where the latest scan is complete; "
                    "this is an index projection, not evidence acquisition"
                )
            }

    def search(self, query, limit=20):
        if not query or not query.strip() or not 1 <= limit <= 100:
            raise ValueError("Invalid query or result limit")
        with self.connect() as db:
            try:
                rows = db.execute(
                    "SELECT e.id,e.source_id,e.relpath FROM search_index i "
                    "JOIN evidence e ON e.id=CAST(i.evidence_id AS INTEGER) "
                    "WHERE search_index MATCH ? AND e.status='indexed' "
                    "AND EXISTS ("
                    "SELECT 1 FROM inventory_runs r "
                    "WHERE r.source_id=e.source_id AND r.status='complete' "
                    "AND r.id=(SELECT MAX(latest.id) FROM inventory_runs latest "
                    "WHERE latest.source_id=e.source_id)"
                    ") "
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
            inventory = {
                row["source_id"]: {
                    "run_id": row["id"], "status": row["status"],
                    "finished": row["finished"]
                }
                for row in db.execute(
                    "SELECT r.id,r.source_id,r.status,r.finished FROM inventory_runs r "
                    "WHERE r.id=(SELECT MAX(id) FROM inventory_runs WHERE source_id=r.source_id)"
                )
            }
            for source_id in coverage:
                inventory.setdefault(source_id, {"run_id": None, "status": "never_scanned"})
            selected = rows[:limit]
            receipt = {
                "query": query, "results": [dict(r) for r in selected],
                "coverage": coverage,
                "inventory": inventory,
                "result_limit": limit, "truncated": len(rows) > limit,
                "complete": False,
                "limitation": "Only indexed UTF-8 text from sources with a complete latest scan was searched. "
                              "no-match does not prove absence."
            }
            db.execute("INSERT INTO receipts(query,created,report) VALUES(?,?,?)",
                       (query, time.time(), json.dumps(receipt, sort_keys=True)))
            receipt["receipt_id"] = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            audit.append(db, "operator", "search.query", {
                "receipt_id": receipt["receipt_id"],
                "result_count": len(receipt["results"]),
                "truncated": receipt["truncated"],
            })
            return receipt

    def verify(self, source_id):
        with self.connect() as db:
            row = db.execute("SELECT root FROM sources WHERE id=?", (source_id,)).fetchone()
            if row is None:
                raise ValueError("Unknown source")
            source_root = Path(row["root"])
            if source_root.is_symlink() or not source_root.is_dir():
                return {"ok": False, "issues": [
                    {"path": ".", "reason": "source_root_unavailable_or_symlink"}
                ]}
            try:
                initial_root = source_root.stat(follow_symlinks=False)
            except OSError:
                return {"ok": False, "issues": [
                    {"path": ".", "reason": "source_root_unavailable_or_symlink"}
                ]}
            root_identity = (initial_root.st_dev, initial_root.st_ino)
            issues = []
            for r in db.execute(
                "SELECT relpath,sha256 FROM evidence WHERE source_id=?", (source_id,)
            ):
                path = source_root / r["relpath"]
                if path.is_symlink() or not path.is_file():
                    issues.append({"path": r["relpath"], "reason": "missing_or_symlink"})
                elif r["sha256"]:
                    try:
                        if sha256_file(path, root=source_root,
                                       root_identity=root_identity) != r["sha256"]:
                            issues.append({"path": r["relpath"], "reason": "digest_mismatch"})
                    except OSError:
                        issues.append({"path": r["relpath"], "reason": "unreadable_or_changed"})
            try:
                ending_root = source_root.stat(follow_symlinks=False)
                unchanged = (
                    stat.S_ISDIR(ending_root.st_mode)
                    and (ending_root.st_dev, ending_root.st_ino) == root_identity
                )
            except OSError:
                unchanged = False
            if not unchanged:
                issues.append({"path": ".", "reason": "source_root_changed_during_verification"})
        return {"ok": not issues, "issues": issues}

    def task_add(self, title):
        with self.connect() as db:
            db.execute("INSERT INTO tasks(title) VALUES(?)",(title,))
            task_id=db.execute("SELECT last_insert_rowid()").fetchone()[0]
            audit.append(db, "operator", "task.add", {"task_id": task_id})
            return {"id":task_id}

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
            audit.append(db, actor, "task.claim", {"task_id": task_id})
        return {"task_id":task_id,"token":token}

    def task_complete(self, task_id, token):
        with self.connect() as db:
            changed=db.execute("UPDATE tasks SET status='done',token=NULL WHERE id=? AND status='working' AND token=? AND lease_until>?",(task_id,token,time.time())).rowcount
            if not changed:
                raise ValueError("Invalid or expired lease")
            audit.append(db, "operator", "task.complete", {"task_id": task_id})
        return {"task_id":task_id,"status":"done","note":"Not a human forensic review"}

    def message_post(self, task_id, actor, body):
        with self.connect() as db:
            db.execute("INSERT INTO messages(task_id,author,body,created) VALUES(?,?,?,?)",(task_id,actor,body,time.time()))
            audit.append(db, actor, "message.post", {"task_id": task_id})
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
            scans={row["source_id"]: {"run_id":row["id"],"status":row["status"]}
                   for row in db.execute(
                       "SELECT id,source_id,status FROM inventory_runs r "
                       "WHERE id=(SELECT MAX(id) FROM inventory_runs WHERE source_id=r.source_id)"
                   )}
            return {"sources":sources,"evidence":evidence,"tasks":tasks,"latest_inventory":scans,
                    "scope":"Recorded catalog state, not evidence acquisition completeness"}

    def audit_verify(self, checkpoint=None):
        with self.connect() as db:
            return (audit.verify_checkpoint(db, checkpoint)
                    if checkpoint is not None else audit.verify(db))

    def audit_checkpoint(self):
        with self.connect() as db:
            return audit.checkpoint(db)

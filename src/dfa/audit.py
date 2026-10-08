"""Application event checksums; not an independent custody or tamper-proof log."""
import hashlib
import json
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_events (
  id INTEGER PRIMARY KEY,
  created REAL NOT NULL,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  payload TEXT NOT NULL,
  previous_hash TEXT NOT NULL,
  event_hash TEXT NOT NULL
);
"""
ZERO = "0" * 64

def _checksum(previous, created, actor, action, payload):
    raw = json.dumps([previous, created, actor, action, payload],
                     separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def append(db, actor, action, details):
    previous = db.execute(
        "SELECT event_hash FROM audit_events ORDER BY id DESC LIMIT 1"
    ).fetchone()
    previous_hash = previous[0] if previous else ZERO
    created = time.time()
    payload = json.dumps(details, sort_keys=True, separators=(",", ":"))
    digest = _checksum(previous_hash, created, actor, action, payload)
    db.execute(
        "INSERT INTO audit_events(created,actor,action,payload,previous_hash,event_hash)"
        " VALUES(?,?,?,?,?,?)",
        (created, actor, action, payload, previous_hash, digest)
    )
    return digest

def verify(db):
    expected = ZERO
    count = 0
    for row in db.execute(
        "SELECT id,created,actor,action,payload,previous_hash,event_hash"
        " FROM audit_events ORDER BY id"
    ):
        if row["previous_hash"] != expected:
            return {"ok": False, "checked": count,
                    "invalid_event_id": row["id"], "reason": "broken_link"}
        actual = _checksum(expected, row["created"], row["actor"],
                           row["action"], row["payload"])
        if row["event_hash"] != actual:
            return {"ok": False, "checked": count,
                    "invalid_event_id": row["id"], "reason": "digest_mismatch"}
        expected = row["event_hash"]
        count += 1
    return {"ok": True, "checked": count, "head": expected,
            "limitation": "Database administrators can rewrite both events and hashes"}

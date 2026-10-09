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
                    "invalid_event_id": row["id"], "reason": "broken_link",
                    "trust_boundary": TRUST_BOUNDARY}
        actual = _checksum(expected, row["created"], row["actor"],
                           row["action"], row["payload"])
        if row["event_hash"] != actual:
            return {"ok": False, "checked": count,
                    "invalid_event_id": row["id"], "reason": "digest_mismatch",
                    "trust_boundary": TRUST_BOUNDARY}
        expected = row["event_hash"]
        count += 1
    return {"ok": True, "checked": count, "head": expected,
            "limitation": "Database administrators can rewrite both events and hashes",
            "trust_boundary": TRUST_BOUNDARY}

# A manifest is only useful when copied outside this mutable case database.
CHECKPOINT_FORMAT = "dfa-audit-checkpoint-v1"
TRUST_BOUNDARY = (
    "Local mutable application log; independent retention and authentication "
    "of the exported checkpoint are the operator's responsibility. "
    "This is not chain-of-custody certification."
)

def checkpoint(db):
    """Export an independently storable reference to the verified local log head."""
    report = verify(db)
    if not report["ok"]:
        raise ValueError("Audit log is inconsistent; cannot issue checkpoint")
    return {
        "format": CHECKPOINT_FORMAT,
        "event_count": report["checked"],
        "head": report["head"],
        "trust_boundary": TRUST_BOUNDARY,
    }

def verify_checkpoint(db, manifest):
    """Check the local chain and compare it with an externally retained manifest."""
    if (
        not isinstance(manifest, dict)
        or manifest.get("format") != CHECKPOINT_FORMAT
        or type(manifest.get("event_count")) is not int
        or manifest["event_count"] < 0
        or not isinstance(manifest.get("head"), str)
        or len(manifest["head"]) != 64
        or any(char not in "0123456789abcdef" for char in manifest["head"])
    ):
        raise ValueError("Invalid audit checkpoint manifest (expected dfa-audit-checkpoint-v1)")
    report = verify(db)
    report["trust_boundary"] = TRUST_BOUNDARY
    report["checkpoint_checked"] = True
    if not report["ok"]:
        return report
    if report["checked"] != manifest["event_count"]:
        return {**report, "ok": False, "reason": "checkpoint_count_mismatch"}
    if report["head"] != manifest["head"]:
        return {**report, "ok": False, "reason": "checkpoint_head_mismatch"}
    return report

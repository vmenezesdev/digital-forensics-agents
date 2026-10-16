"""Fail-closed, case-local source-registration checks against application audit events.

This is an interim identity binding for issue #6, not an authenticated custody record.
The audit log is mutable by a local database administrator.
"""
import json
import sqlite3
from . import audit


def inspect_source_registration(db, source_id):
    """Bind a current source row to exactly one locally verified source.add event.

    Read the event chain and source row from one SQLite snapshot. The event
    hash is a case-local reference, not custody proof. A legacy source without
    a matching event cannot be asserted as registered.
    """
    if not isinstance(source_id, str) or not source_id or "\x00" in source_id:
        return {"ok": False, "reason": "invalid_source_id"}
    try:
        source_id.encode("utf-8")
    except UnicodeEncodeError:
        return {"ok": False, "reason": "invalid_source_id"}
    db.execute("SAVEPOINT dfa_source_registration_snapshot")
    try:
        return _inspect_snapshot(db, source_id)
    finally:
        db.execute("RELEASE SAVEPOINT dfa_source_registration_snapshot")


def _inspect_snapshot(db, source_id):
    # Corrupt SQLite cells can make the checksum serializer raise instead of
    # returning a structured failure. Never treat such an audit as registered.
    try:
        integrity = audit.verify(db)
    except (sqlite3.DatabaseError, TypeError, ValueError, UnicodeError):
        return {"ok": False, "reason": "audit_log_inconsistent"}
    if not integrity["ok"]:
        return {"ok": False, "reason": "audit_log_inconsistent"}
    source = db.execute("SELECT root FROM sources WHERE id=?", (source_id,)).fetchone()
    if source is None:
        return {"ok": False, "reason": "unknown_source"}
    registrations = []
    for event in db.execute(
        "SELECT event_hash,payload FROM audit_events WHERE action='source.add' ORDER BY id"
    ):
        try:
            payload = json.loads(event["payload"])
        except (ValueError, TypeError, UnicodeError):
            return {"ok": False, "reason": "malformed_registration_event"}
        if not isinstance(payload, dict):
            return {"ok": False, "reason": "malformed_registration_event"}
        if payload.get("source_id") == source_id:
            registrations.append((event["event_hash"], payload.get("root")))
            if len(registrations) > 1:
                return {"ok": False, "reason": "ambiguous_registration"}
    if not registrations:
        return {"ok": False, "reason": "registration_unavailable"}
    registration_id, original_root = registrations[0]
    if (not isinstance(original_root, str) or not original_root
            or original_root != source["root"]):
        return {"ok": False, "reason": "registration_changed"}
    return {
        "ok": True,
        "status": "local_registration_consistent",
        "source_id": source_id,
        "registration_id": registration_id,
        "limitation": "Mutable local audit event; not source acquisition or custody proof",
    }

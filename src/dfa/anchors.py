"""Versioned byte-range anchors and bounded source checks (not custody assurance)."""
import re

_FIELDS = frozenset({"version", "type", "source_id", "evidence_id", "sha256", "start", "end"})
_FIELDS_V2 = _FIELDS | {"registration_id"}
_SQLITE_MAX_ROWID = (1 << 63) - 1


def validate_byte_range_anchor(anchor, evidence):
    """Check a half-open byte span against one catalog record, without reading files.

    An accepted anchor is *catalog-consistent*, not proof that external source
    bytes still exist or match the digest. IDs are local to a single case DB.
    """
    if not isinstance(anchor, dict):
        raise ValueError("Invalid byte-range anchor fields")
    version = anchor.get("version")
    if type(version) is not int or version not in (1, 2):
        raise ValueError("Unsupported anchor version")
    if set(anchor) != (_FIELDS if version == 1 else _FIELDS_V2):
        raise ValueError("Invalid byte-range anchor fields")
    if version == 2 and (
        not isinstance(anchor["registration_id"], str)
        or re.fullmatch(r"[0-9a-f]{64}", anchor["registration_id"]) is None
    ):
        raise ValueError("Invalid source registration reference")
    if anchor["type"] != "byte_range":
        raise ValueError("Unsupported anchor type")
    if not isinstance(anchor["source_id"], str) or not anchor["source_id"]:
        raise ValueError("Invalid source identifier")
    if (type(anchor["evidence_id"]) is not int
            or not 1 <= anchor["evidence_id"] <= _SQLITE_MAX_ROWID):
        raise ValueError("Invalid evidence identifier")
    if not isinstance(anchor["sha256"], str) or re.fullmatch(r"[0-9a-f]{64}", anchor["sha256"]) is None:
        raise ValueError("Invalid SHA-256 digest")
    if (type(anchor["start"]) is not int or type(anchor["end"]) is not int
            or anchor["start"] < 0 or anchor["end"] <= anchor["start"]):
        raise ValueError("Invalid half-open byte range")
    try:
        evidence_id = evidence["id"]
        source_id = evidence["source_id"]
        digest = evidence["sha256"]
        size = evidence["size"]
        status = evidence["status"]
    except (KeyError, IndexError, TypeError) as error:
        raise ValueError("Incomplete catalog record") from error
    if (type(evidence_id) is not int or evidence_id != anchor["evidence_id"]
            or source_id != anchor["source_id"] or digest != anchor["sha256"]):
        raise ValueError("Anchor does not identify this catalog record/version")
    if type(size) is not int or anchor["end"] > size:
        raise ValueError("Byte range exceeds recorded content size")
    if status not in ("indexed", "excluded"):
        raise ValueError("Catalog record is not in a referenceable state")
    return dict(anchor)


def make_byte_range_anchor(evidence, start, end):
    """Construct a validated anchor from a catalog row; no source bytes read."""
    anchor = {
        "version": 1, "type": "byte_range", "source_id": evidence["source_id"],
        "evidence_id": evidence["id"], "sha256": evidence["sha256"],
        "start": start, "end": end,
    }
    return validate_byte_range_anchor(anchor, evidence)


def make_registered_byte_range_anchor(case, evidence, start, end):
    """Bind a v2 citation to one verified case-local source.add event.

    This is not immutable physical-source identity or custody assurance.
    """
    from .source_registration import inspect_source_registration

    base = make_byte_range_anchor(evidence, start, end)
    inspected = inspect_catalog_byte_range(case, base)
    if not inspected["ok"]:
        raise ValueError("Cannot bind source registration: " + inspected["reason"])
    with case.connect() as db:
        registration = inspect_source_registration(db, base["source_id"])
    if not registration["ok"]:
        raise ValueError("Cannot bind source registration: " + registration["reason"])
    bound = {**base, "version": 2, "registration_id": registration["registration_id"]}
    inspected = inspect_catalog_byte_range(case, bound)
    if not inspected["ok"]:
        raise ValueError("Cannot bind source registration: " + inspected["reason"])
    return bound


def inspect_catalog_byte_range(case, anchor):
    """Resolve a byte-range anchor against one *current catalog snapshot*.

    Returns a typed, deterministic failure reason or a catalog-consistent
    reference. It never reads original bytes or authenticates source custody.
    An incomplete latest inventory prevents treating an old row as current.
    """
    if (not isinstance(anchor, dict)
            or type(anchor.get("evidence_id")) is not int
            or not 1 <= anchor["evidence_id"] <= _SQLITE_MAX_ROWID
            or not isinstance(anchor.get("source_id"), str)
            or not anchor["source_id"]):
        return {"ok": False, "reason": "invalid_anchor"}
    with case.connect() as db:
        row = db.execute(
            "SELECT id,source_id,relpath,sha256,size,status FROM evidence "
            "WHERE id=? AND source_id=?",
            (anchor["evidence_id"], anchor["source_id"]),
        ).fetchone()
        if row is None:
            return {"ok": False, "reason": "unknown_evidence"}
        # Evidence rows do not have an enforced foreign key to sources in the
        # current workspace schema. An orphan must not resolve successfully.
        source = db.execute(
            "SELECT 1 FROM sources WHERE id=?", (anchor["source_id"],)
        ).fetchone()
        if source is None:
            return {"ok": False, "reason": "unknown_source"}
        try:
            validated = validate_byte_range_anchor(anchor, row)
        except ValueError:
            return {"ok": False, "reason": "anchor_catalog_mismatch"}
        latest = db.execute(
            "SELECT status FROM inventory_runs WHERE source_id=? "
            "ORDER BY id DESC LIMIT 1", (anchor["source_id"],)
        ).fetchone()
        if latest is None or latest["status"] != "complete":
            return {"ok": False, "reason": "inventory_incomplete"}
        if validated["version"] == 2:
            from .source_registration import inspect_source_registration
            registration = inspect_source_registration(db, anchor["source_id"])
            if not registration["ok"]:
                return {"ok": False, "reason": registration["reason"]}
            if registration["registration_id"] != anchor["registration_id"]:
                return {"ok": False, "reason": "registration_changed"}
        return {
            "ok": True,
            "status": "catalog_consistent",
            "anchor": validated,
            "catalog_relpath": row["relpath"],
        }

def read_verified_byte_range(case, anchor, *, max_bytes=1048576):
    """Read a bounded original-byte span after checking its *whole-file* digest.

    Only works on platforms supporting descriptor-relative no-follow opens.
    This is point-in-time source verification against a case-local catalog
    digest, not acquisition, custody authentication, or an immutable snapshot.
    """
    import hashlib
    import os
    import stat
    from pathlib import Path
    from .store import _open_confined_file
    from .source_registration import inspect_source_registration

    if type(max_bytes) is not int or not 1 <= max_bytes <= 1048576:
        raise ValueError("max_bytes must be between 1 and 1048576")
    inspected = inspect_catalog_byte_range(case, anchor)
    if not inspected["ok"]:
        return inspected
    if anchor["end"] - anchor["start"] > max_bytes:
        return {"ok": False, "reason": "range_too_large"}

    # A catalog root can be remapped to identical bytes without a new scan.
    # Require a consistent source.add registration before reading the file.
    with case.connect() as db:
        registration = inspect_source_registration(db, anchor["source_id"])
    if not registration["ok"]:
        return {"ok": False, "reason": registration["reason"]}

    with case.connect() as db:
        row = db.execute(
            "SELECT e.id,e.source_id,e.relpath,e.sha256,e.size,e.status,s.root "
            "FROM evidence e JOIN sources s ON s.id=e.source_id "
            "WHERE e.id=? AND e.source_id=?",
            (anchor["evidence_id"], anchor["source_id"]),
        ).fetchone()
        if row is None or row["relpath"] != inspected["catalog_relpath"]:
            return {"ok": False, "reason": "catalog_changed"}
        try:
            validate_byte_range_anchor(anchor, row)
        except ValueError:
            return {"ok": False, "reason": "catalog_changed"}
        if (not isinstance(row["root"], str) or not row["root"]
                or not isinstance(row["relpath"], str) or not row["relpath"]):
            return {"ok": False, "reason": "catalog_changed"}
        source_root = Path(row["root"])
        relpath = row["relpath"]
        expected_size = row["size"]
        expected_digest = row["sha256"]

    try:
        root_stat = source_root.stat(follow_symlinks=False)
        if not stat.S_ISDIR(root_stat.st_mode):
            raise OSError("Source root is not a directory")
        root_identity = (root_stat.st_dev, root_stat.st_ino)
        flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
        path = source_root / relpath
        fd = _open_confined_file(path, source_root, flags, root_identity=root_identity)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode):
                raise OSError("Not a regular file")
            digest = hashlib.sha256()
            selected = bytearray()
            position = 0
            while True:
                chunk = os.read(fd, 1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                low = max(anchor["start"], position)
                high = min(anchor["end"], position + len(chunk))
                if low < high:
                    selected.extend(chunk[low - position:high - position])
                position += len(chunk)
            after = os.fstat(fd)
        finally:
            os.close(fd)
        # Confirm the same inode is still reachable through the confined path.
        check_fd = _open_confined_file(path, source_root, flags, root_identity=root_identity)
        try:
            current = os.fstat(check_fd)
        finally:
            os.close(check_fd)
        ending_root = source_root.stat(follow_symlinks=False)
        if not stat.S_ISDIR(ending_root.st_mode) or (
            ending_root.st_dev, ending_root.st_ino
        ) != root_identity:
            return {"ok": False, "reason": "source_changed"}
    except (OSError, ValueError):
        return {"ok": False, "reason": "source_unavailable"}

    fingerprint = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    if (fingerprint(before) != fingerprint(after)
            or fingerprint(current) != fingerprint(after)
            or position != expected_size or digest.hexdigest() != expected_digest
            or len(selected) != anchor["end"] - anchor["start"]):
        return {"ok": False, "reason": "source_changed"}

    rechecked = inspect_catalog_byte_range(case, anchor)
    if not rechecked["ok"]:
        return rechecked
    if rechecked["catalog_relpath"] != relpath:
        return {"ok": False, "reason": "catalog_changed"}
    # The source-to-root mapping is mutable catalog state too. Re-check it
    # after the byte read: a remap to another root must not be silently
    # represented as a verified citation to the *current* registered source.
    with case.connect() as db:
        current_source = db.execute(
            "SELECT root FROM sources WHERE id=?", (anchor["source_id"],)
        ).fetchone()
    if current_source is None or current_source["root"] != str(source_root):
        return {"ok": False, "reason": "catalog_changed"}
    with case.connect() as db:
        final_registration = inspect_source_registration(db, anchor["source_id"])
    if not final_registration["ok"]:
        return {"ok": False, "reason": final_registration["reason"]}
    if final_registration["registration_id"] != registration["registration_id"]:
        return {"ok": False, "reason": "registration_changed"}
    return {
        "ok": True, "status": "bytes_verified_against_catalog_digest",
        "anchor": dict(anchor), "data": bytes(selected),
        "limitation": "Point-in-time digest check; not forensic acquisition or custody verification",
    }

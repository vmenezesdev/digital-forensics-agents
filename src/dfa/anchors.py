"""Versioned catalog-bound byte-range anchors (not source-byte verification)."""
import re

_FIELDS = frozenset({"version", "type", "source_id", "evidence_id", "sha256", "start", "end"})


def validate_byte_range_anchor(anchor, evidence):
    """Check a half-open byte span against one catalog record, without reading files.

    An accepted anchor is *catalog-consistent*, not proof that external source
    bytes still exist or match the digest. IDs are local to a single case DB.
    """
    if not isinstance(anchor, dict) or set(anchor) != _FIELDS:
        raise ValueError("Invalid byte-range anchor fields")
    if type(anchor["version"]) is not int or anchor["version"] != 1:
        raise ValueError("Unsupported anchor version")
    if anchor["type"] != "byte_range":
        raise ValueError("Unsupported anchor type")
    if not isinstance(anchor["source_id"], str) or not anchor["source_id"]:
        raise ValueError("Invalid source identifier")
    if type(anchor["evidence_id"]) is not int or anchor["evidence_id"] <= 0:
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

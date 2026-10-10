# Interim source-registration binding (issue #6)

`dfa.source_registration.inspect_source_registration(db, source_id)` derives a
**case-local registration reference** from the `source.add` audit event and
compares the event's original `root` with the current `sources.root` within one
SQLite read snapshot. This
catches a catalog root reassignment **even when replacement files have identical
bytes**. The returned `registration_id` is the original event hash and remains
stable when later inventory, search and index events are appended.

The original-byte reader now checks this local registration before and after
reading a byte range. A catalog root remapped to a different directory with
identical bytes is rejected as `registration_changed` even if the digest still
matches. **Version 1 anchors do not carry a registration reference; version 2 anchors do**:
source-generation identity, same-path deletion/recreation, and migration of
legacy catalogs remain unresolved. The catalog-only inspector is not a
source-registration or custody verification.

Fail-closed reasons: `invalid_source_id`, `unknown_source`,
`registration_unavailable` (including pre-audit legacy sources),
`ambiguous_registration`, `malformed_registration_event`,
`registration_changed`, `audit_log_inconsistent`. No legacy event is fabricated.

**Trust and compatibility limits:** the application audit chain is locally
mutable; an administrator can rewrite its events and recompute hashes. The
reference is neither an immutable physical-source ID nor acquisition/custody
attestation. Root relocation currently requires an explicit new registration
and cannot silently preserve current validity. Deleting and recreating a
source row with the same ID/root cannot be distinguished by this check alone.
The snapshot prevents mixing concurrent catalog states during one lookup, but
a writer can remap a source immediately after the lookup; callers must recheck
after reading original bytes. A proper future schema should persist immutable registration generations,
link inventory/evidence revisions to them, and specify safe migration of
legacy workspaces. This interim lookup verifies the whole audit chain and is
O(number of audit events); performance and an externally anchored trust model
remain separate work. No real evidence belongs in the public repository.

Synthetic tests: `python -m unittest tests.test_source_registration -v`.
The reader integration has a synthetic `Case` regression for same-bytes root
remapping in `tests/test_byte_anchors.py`. Neither the isolated checks nor
reader integration alone meet the complete issue #6 acceptance criteria.

## Registration-bound byte-range anchor v2 (incremental)

`make_registered_byte_range_anchor(case, evidence_row, start, end)` produces
a v2 byte-range anchor with the existing v1 fields plus `registration_id`,
the verified case-local `source.add` event hash. It requires a complete
latest inventory and rechecks the catalog and registration before returning.
`validate_byte_range_anchor` accepts v1 or v2 exact fields and rejects
malformed registration hashes. `inspect_catalog_byte_range` additionally
checks that the v2 event hash still identifies the current registration,
failing closed on mismatches, missing/ambiguous registrations and inconsistent
audit logs. The verified byte reader rechecks after source reads.

The v2 identifier is **not** an immutable physical source generation:
same-path replacement with identical bytes, rewritten local audit history,
and legacy source migration remain unresolved. No acquisition/custody
attestation is made. The v2 JSON Schema and normative examples remain
to be integrated; see issue #6. Existing v1 anchors remain supported.

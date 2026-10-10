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
matches. **The anchor itself does not yet carry the registration reference**:
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

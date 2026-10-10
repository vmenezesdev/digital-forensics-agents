# Evidence catalog contract — design draft 0.1

This is a proposed semantic model, **not** a validated forensic standard.

| Entity | Purpose |
| --- | --- |
| Case | Independent authorization, scope and retention boundary. |
| Source | Acquired/referenced medium or evidence collection. |
| EvidenceObject | Stable logical reference to an item within a source. |
| Blob | Hash-addressed bytes; may be external or a bounded range. |
| ActivityRun | Input IDs, tool/model versions, parameters, outcome, failures. |
| Observation | Extracted or measured data. |
| Finding | Reviewable analytical claim with supporting and contradicting anchors. |
| Review | Authenticated review action with author and timestamp. |
| CustodyEvent | Transfer, possession, access or handling event; not synonymous with processing. |
| AuditEvent | Application action record, separately anchored where assurance is needed. |
| IndexBuild | Which input universe was indexed, using which versions and failures. |
| QueryReceipt | Query, filters, index generation, returned IDs and coverage limitations. |

Evidence anchors must be typed: byte range, document page and region, audio interval, video frame, or record ID. Do not rely on filename-only pointers. Preserve versions and superseded conclusions.

**First implementation profile:** local filesystem for externally held originals, SQLite for metadata and FTS5 for bounded text search. Indexes are derived, disposable projections, not authoritative evidence. SQLite on a network share is not an acceptable distributed message board. Future distributed profile may use PostgreSQL and object storage.

Modeling references: [W3C PROV](https://www.w3.org/TR/prov-o/) and [CASE/UCO](https://caseontology.org/). No conformance is claimed yet.

## First executable typed anchor — issue #6 (incremental)

`dfa.anchors.make_byte_range_anchor(row, start, end)` constructs a **version 1**
`byte_range` anchor from an existing catalog row; `validate_byte_range_anchor(anchor, row)`
checks it against that row without touching source files. The normative fields are
`version`, `type`, `source_id`, `evidence_id`, `sha256`, `start`, `end`. The span is
zero-based, half-open (`start` inclusive, `end` exclusive), nonempty, and must fit
within the cataloged byte length. Unknown fields, incorrect hashes/IDs, negative or
boolean offsets, out-of-range SQLite evidence IDs (outside 1..2^63-1),
unsupported versions/types, and missing/drift/error records fail closed.

The anchor is **scoped to one case database**. It is independent of the file path
and disposable search index, but SQLite integer evidence IDs are not portable
across independently created case databases. The constructor and catalog validator check only a *catalog assertion*.
A separate bounded source-byte resolver is described below; neither API
authenticates acquisition or custody, nor makes an externally mutable source
immutable. Globally stable IDs and additional anchor types remain open work
under issue #6.

Example with synthetic data (the digest must be the cataloged SHA-256):

```python
from dfa.anchors import make_byte_range_anchor
anchor = make_byte_range_anchor(catalog_row, start=0, end=9)
# {'version': 1, 'type': 'byte_range', 'source_id': ..., 'evidence_id': ...,
#  'sha256': ..., 'start': 0, 'end': 9}
```


### Machine-checkable byte-range contract

The normative v1 JSON shape is in [`byte-range-anchor.schema.json`](byte-range-anchor.schema.json),
with synthetic positive and negative fixtures in
[`byte-range-anchor.examples.json`](byte-range-anchor.examples.json).
JSON Schema checks individual field types, formats and allowed keys; it cannot
express the standard cross-field requirement `end > start` in this dialect, nor
can it verify source identity, catalog status or SHA-256 equality. Those
requirements are enforced by `dfa.anchors.validate_byte_range_anchor(anchor, row)`.
A JSON Schema validation alone is **not** successful citation resolution.
Other anchor types (PDF region, UTF-8 span, audio/video timespan, structured
record) remain design-only and must not be accepted as byte-range anchors.

### Current catalog lookup (not original-byte verification)

`dfa.anchors.inspect_catalog_byte_range(case, anchor)` returns a
`catalog_consistent` reference with the catalog's *unverified* relative path
only when the referenced evidence row matches the anchor and the source's
latest inventory run is `complete`. Otherwise it returns a machine-readable
reason: `invalid_anchor`, `unknown_evidence`, `unknown_source`,
`anchor_catalog_mismatch`, or `inventory_incomplete`. An orphaned evidence row
without a registered source cannot resolve even if a past inventory was complete. This check avoids treating retained rows after partial
scans as current. A positive result is **not** a verified citation to original
bytes: file existence, live digest, path containment and custody are not
verified by this lookup. Use a separate secure source-byte resolver before
asserting that a citation was reproduced from source material.

### Bounded source-byte resolution (local, issue #6)

`dfa.anchors.read_verified_byte_range(case, anchor, max_bytes=1048576)`
returns at most 1 MiB of original bytes (`data`, a Python `bytes` value),
**only after** streaming and comparing the *entire* current file SHA-256 to
the catalog baseline. The resolver uses descriptor-relative no-follow opens
and rechecks the file inode, root identity, registered source-root mapping and catalog state; it refuses
symlink/path escapes, missing sources, drift, invalid spans and incomplete
latest inventories. Result reasons include `range_too_large`,
`source_unavailable`, `source_changed` and `catalog_changed`.

This verification does **not** authenticate an acquisition or custodian.
The source may change immediately after the check; even two no-follow opens
cannot make an externally mutable source into an immutable snapshot. Callers
must not treat the returned bytes as a reviewed finding or execute them as
instructions. The API is intentionally not a general-purpose file reader.

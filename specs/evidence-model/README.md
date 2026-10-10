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
boolean offsets, unsupported versions/types, and missing/drift/error records fail closed.

The anchor is **scoped to one case database**. It is independent of the file path
and disposable search index, but SQLite integer evidence IDs are not portable
across independently created case databases. This validator checks only a
*catalog assertion*; it does **not** read or authenticate original bytes, verify
acquisition/custody, or guarantee that the referenced file still exists. A secure
source-byte resolver, globally stable IDs, additional anchor types and their
cross-session tests remain open work under issue #6.

Example with synthetic data (the digest must be the cataloged SHA-256):

```python
from dfa.anchors import make_byte_range_anchor
anchor = make_byte_range_anchor(catalog_row, start=0, end=9)
# {'version': 1, 'type': 'byte_range', 'source_id': ..., 'evidence_id': ...,
#  'sha256': ..., 'start': 0, 'end': 9}
```

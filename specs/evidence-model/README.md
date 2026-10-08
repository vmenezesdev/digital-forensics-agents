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

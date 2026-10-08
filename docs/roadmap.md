# Implementation roadmap

This is an experimental OSS initiative. Avoid building a full forensic platform or swarm runtime before conformant end-to-end workflows.

## Implemented

- Local case database and explicitly registered source roots.
- Per-file baseline SHA-256 and drift checks.
- Text-only FTS search, reconciliation of stale entries and source-specific coverage receipts.
- Bounded query results and persisted receipts.
- Atomic local task leases, persistent board messages, task/status commands.
- Synthetic tests and trunk CI.

## Immediate quality gates

- Safer traversal against symlink replacement and filesystem races.
- Explicit scan history and per-file failure provenance.
- Authentication/authorization before sharing cases with other users.
- Independent append-only or externally anchored audit checkpoints.
- Data migration contracts, retention, backup and controlled deletion.
- Negative testing for inconsistent sources and partially failed scans.

## Next interoperability slice

- Stable typed evidence anchors (bytes, audio range, PDF page, record ID).
- Activity runs with versioned tools, inputs and outputs; provenance export.
- Reviewed findings separate from automated observations.
- Deterministic synthetic audio/text fixtures and independent review tasks.
- Adapter validation in at least two agent environments.

## Scale — only after demand

- Batched workers for large volumes, manifest pagination and resource budgets.
- External full-text indexes and PostgreSQL-backed authenticated board.
- Reliable external references to existing forensic tools.
- Explicit policy gates for sensitive data and any remote model processing.

## Go/no-go

Continue expansion only if the workflow delivers demonstrably verifiable results and produces adoption by actual practitioners or maintainers. GitHub stars alone are not evidence of revenue, qualified use or correctness.

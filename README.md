# Digital Forensics Agents

Open-source workflows, skills, and protocols for auditable AI-assisted digital forensics.

**Experimental project — synthetic cases only.** This repository does not certify an agent as a forensic examiner or establish legal admissibility.

## Design

The public repository stores specifications, tools, and tests. Each investigation maintains its own private files and database. The core model separates original sources, processing records, analytical findings, and task coordination.

Start with [agent instructions](AGENTS.md) and the [evidence model](specs/evidence-model/README.md).

The first milestone is a local, testable case workspace with hashing, searchable metadata, explicit coverage, and a task board. Integration with ChatGPT Work and Claude Cowork will be explored only after the portable core works.

Apache-2.0 licensed.

## Try the experimental local CLI

Requires Python 3.11+ with SQLite FTS5. Use **synthetic data only**:

```sh
python -m pip install -e .
mkdir -p /tmp/dfa-demo/source
printf 'Synthetic transcript containing alpha.\n' > /tmp/dfa-demo/source/sample.txt
dfa --case /tmp/dfa-demo/workspace init
dfa --case /tmp/dfa-demo/workspace source-add sample /tmp/dfa-demo/source
dfa --case /tmp/dfa-demo/workspace ingest sample
dfa --case /tmp/dfa-demo/workspace search alpha
dfa --case /tmp/dfa-demo/workspace verify sample
dfa --case /tmp/dfa-demo/workspace task-add 'Inspect transcript'
dfa --case /tmp/dfa-demo/workspace task-list
dfa --case /tmp/dfa-demo/workspace status
dfa --case /tmp/dfa-demo/workspace audit-verify
python -m unittest discover -s tests -v
```

The current implementation is a learning prototype: local SQLite is **not** a hardened evidence store, no agent identity is authenticated, no independent custody log is produced, and the search index is limited to small UTF-8 files. Query receipts describe the indexed universe; they cannot prove exhaustive absence. No external services are invoked.

**Development policy:** accelerated trunk-based development. Commit tested, reversible increments directly to `trunk`. Delay long-lived branches and release processes until stabilization.

## Development snapshot

The local implementation records the first successfully read SHA-256 baseline for each path, reconciles vanished files during a successful inventory, removes stale FTS results for drifted/excluded items, and reports per-source indexed/excluded/drift/missing coverage. Search receipts include limits and a truncation flag. Task and message listings survive separate agent sessions that access the same local case database.

**Not yet present:** authenticated agents or reviewers, external immutable audit anchors, activity/derivation graph, verified acquisition workflows, scalable OCR/STT/media processing, or multi-host collaboration. FTS text is a sensitive copy; protect the case directory. Source inventories can race with external filesystem modification. Do not use real case data with this prototype.

## Application audit events

The case database stores hash-linked events for source registration, inventory, searches, and task/board operations. `dfa --case CASE_PATH audit-verify` checks event payload digests and ordering. This detects some accidental or unauthorized edits **provided the expected database state is trustworthy**. Because the hashes and events are in the same mutable database, a privileged actor can rewrite both. This is not WORM, an externally anchored log, independent human certification, or chain-of-custody compliance. Existing workspaces may need to run `dfa --case CASE_PATH init` to initialize newly added tables.

The initial reusable skill is [evidence intake](skills/evidence-intake/SKILL.md); further work is tracked in the [roadmap](docs/roadmap.md).

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
python -m unittest discover -s tests -v
```

The current implementation is a learning prototype: local SQLite is **not** a hardened evidence store, no agent identity is authenticated, no independent custody log is produced, and the search index is limited to small UTF-8 files. Query receipts describe the indexed universe; they cannot prove exhaustive absence. No external services are invoked.

**Development policy:** accelerated trunk-based development. Commit tested, reversible increments directly to `trunk`. Delay long-lived branches and release processes until stabilization.

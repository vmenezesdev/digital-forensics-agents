# Digital Forensics Agents

Open-source workflows, skills, and protocols for auditable AI-assisted digital forensics.

**Experimental project — synthetic cases only.** This repository does not certify an agent as a forensic examiner or establish legal admissibility.

## Design

The public repository stores specifications, tools, and tests. Each investigation maintains its own private files and database. The core model separates original sources, processing records, analytical findings, and task coordination.

Start with [agent instructions](AGENTS.md) and the [evidence model](specs/evidence-model/README.md).

The first milestone is a local, testable case workspace with hashing, searchable metadata, explicit coverage, and a task board. Integration with ChatGPT Work and Claude Cowork will be explored only after the portable core works.

Apache-2.0 licensed.

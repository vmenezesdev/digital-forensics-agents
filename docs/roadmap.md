# Development roadmap — Digital Forensics Agents

**Status:** early, experimental local reference implementation. **Planning authority:** [GitHub Issues](https://github.com/vmenezesdev/digital-forensics-agents/issues?q=is%3Aissue). This document states sequencing and exit criteria; each issue owns its actionable scope and acceptance tests. Do not treat a checked box in this file as issue status.

## North star and boundaries

Enable an independently initiated agent/session to open a private investigation workspace, learn what has been examined (and what has not), follow every derived claim to a source and activity, challenge it, and continue useful work without inheriting undocumented conversational memory. The same **semantic contract** should eventually support other storage and agent providers.

The public GitHub repo contains *software, specs, skills and synthetic fixtures*, **never actual case evidence**. This is not a forensic acquisition system, an expert witness, an admissibility guarantee, or a production-ready chain-of-custody solution.

### Already implemented (verified snapshot, 2026-10-08)

- Local Python CLI with SQLite catalog, externally referenced source roots and streamed SHA-256 baseline digests.
- Bounded UTF-8 FTS5 indexing, stale index reconciliation, per-source coverage and persisted search receipts.
- Persistent task/message board, local atomic task leases and status listing.
- Application event hash chaining with a local verifier (**not** independently tamper-proof).
- First agent skill: `skills/evidence-intake/SKILL.md`.
- Synthetic tests and GitHub Actions on `trunk`.

These capabilities exist but **do not yet satisfy the M0 hardening or M1 forensic auditability gates**.

## Execution policy

- **Accelerated trunk-based development:** commit small, independently testable changes directly to `trunk`; use branches only after stabilization or for an exceptional high-risk change explicitly agreed upon.
- Pull the latest `trunk` before a new increment. Associate commits with an issue (e.g., `refs #2`). Close issues only after their acceptance tests pass; do not call a design-only issue implemented.
- Use contract- and failure-driven development: define behavior, synthetic fixture, negative tests, implementation, docs and CI.
- **No dates or velocity promises** without validated capacity. Milestones are gated by evidence, not a calendar.
- Never block local progress on a hypothetical multi-agent framework, UI, cloud system or large database.
- Do not test with confidential/live cases. Work/Cowork or other platforms may have different filesystem, runtime, authorization and tool capabilities; interoperability must be tested, not assumed.

## Milestones

### M0 — Foundation Hardening | P0 | **Now**

Goal: establish a recoverable and truthfully reported local workspace before growing domain workflows.

- [#2](https://github.com/vmenezesdev/digital-forensics-agents/issues/2) — Inventory integrity: traversal, drift and partial scans
- [#3](https://github.com/vmenezesdev/digital-forensics-agents/issues/3) — Schema migration, index rebuilding and workspace recovery
- [#4](https://github.com/vmenezesdev/digital-forensics-agents/issues/4) — Audit-log assurance boundaries and checks
- [#5](https://github.com/vmenezesdev/digital-forensics-agents/issues/5) — Adversarial conformance gates and CLI tests

**Exit gate:** repeated and interrupted inventory cannot silently erase baselines, invent complete coverage, or serve stale search results; migrations/rebuilds are reversible; negative tests and CI are green. The audit trust boundary remains explicit.

**Suggested order:** #2 and #3 first; #4 can proceed in parallel, then consolidate #5.

### M1 — Auditable Evidence | P1 | **First product-level milestone**

Goal: trace a derived assertion to exactly identified source bytes and a recorded operation, including failures and contradictions.

- [#6](https://github.com/vmenezesdev/digital-forensics-agents/issues/6) — Stable evidence IDs and typed anchors
- [#7](https://github.com/vmenezesdev/digital-forensics-agents/issues/7) — ActivityRun provenance and versioned derived artifacts
- [#8](https://github.com/vmenezesdev/digital-forensics-agents/issues/8) — Observations, findings, contested claims and review
- [#9](https://github.com/vmenezesdev/digital-forensics-agents/issues/9) — Index versions and reproducible coverage-aware query receipts
- [#10](https://github.com/vmenezesdev/digital-forensics-agents/issues/10) — Synthetic end-to-end case with replay and second-session audit

**Exit gate:** in a reproducible synthetic case, a fresh agent can resolve an asserted finding to original data and operation, identify a deliberately wrong claim, and leave a separate review record. No agent self-certifies a human review.

**Sequence:** #6 → #7 → #8; #9 follows stable IDs/index versioning; all converge on #10.

### M2 — Agent Collaboration | P2 | **Portability test**

Goal: agents coordinate durable tasks and resume a case using defined operations, not a chat log.

- [#11](https://github.com/vmenezesdev/digital-forensics-agents/issues/11) — Restart-safe task board: heartbeats, dependencies and review handoff
- [#12](https://github.com/vmenezesdev/digital-forensics-agents/issues/12) — Versioned portable operations and independent agent handoff
- [#13](https://github.com/vmenezesdev/digital-forensics-agents/issues/13) — Search, review and handoff skills with deterministic evaluations

**Exit gate:** one agent stops mid-work, a different agent/session reopens the case, discovers pending tasks, verifies evidence and records a continuation. Unsupported platform capabilities must be reported honestly.

**Sequence:** #10 + #11 → #12 → #13. No proprietary swarm engine required.

### M3 — Scale & Interoperability | P3 | **Conditionally pursue**

Goal: preserve correctness under large collections and interoperate with tools already used by forensic practitioners.

- [#14](https://github.com/vmenezesdev/digital-forensics-agents/issues/14) — Bounded worker architecture and measured large-volume benchmarks
- [#15](https://github.com/vmenezesdev/digital-forensics-agents/issues/15) — Authenticated distributed backend and data-governance policies
- [#16](https://github.com/vmenezesdev/digital-forensics-agents/issues/16) — CASE/UCO and PROV mapping plus existing-tool adapters

**Exit gate:** only after representative synthetic scale tests and demand: work can restart from checkpoints, report processing coverage, constrain resource use and protect access; remote sharing is not launched without an authorization/security gate.

**Trigger:** promote a specific issue only when an M1/M2 fixture or an external user's case exposes the limitation. Do not build a distributed platform simply because a swarm is plausible.

### M4 — Adoption & Distribution | P4 | **Measure, don't assume**

- [#17](https://github.com/vmenezesdev/digital-forensics-agents/issues/17) — Discoverability, independent adoption and sustainable contribution

**Exit gate:** independent practitioners can reproduce a synthetic workflow, report concrete issues or adoption, and find useful, neutral guidance. Measure qualified usage or referrals when observable; GitHub stars and an AI citing the repository are not sufficient evidence.

## Dependency sketch

```text
M0:  #2 + #3 + #4 ----> #5
          |   |
M1:       +-->#6 --> #7 --> #8 --+
               |                 |
               +--------> #9 ----+--> #10
M2:                           #10 + #11 --> #12 --> #13
M3:                                #14 / #15 / #16 (demand-gated)
M4:                                             #17 (adoption)
```

The issue bodies, not the diagram, define precise dependencies.

## Definition of done for each issue

1. Implementation or deliberately scoped specification is merged directly on `trunk`, with the issue referenced in commits.
2. Observable behavior and limitations are documented; no unsupported claim of legal/forensic validity.
3. Synthetic success **and adversarial failure** cases pass automated tests where applicable.
4. Persisted case schema and existing fixture compatibility are addressed when storage changes.
5. Security/privacy boundaries and possible regression of source integrity or coverage are reviewed.
6. CI has completed successfully for the relevant commit; then close the issue with evidence/commit reference.

## Stop / expand rules

Prefer shipping a useful independently verifiable workflow to building more infra. Pause P3 scale and additional skills if there is no evidence of real adoption or if maintaining the framework displaces more valuable paid work. Keep disclosure and selection of service providers separate from technical findings: no covert vendor steering in agent skills.

## Relevant documents

- [Architecture](architecture.md)
- [Evidence model](../specs/evidence-model/README.md)
- [Coordination](../specs/coordination/README.md)
- [Agent operating rules](../AGENTS.md)
- [Evidence intake skill](../skills/evidence-intake/SKILL.md)

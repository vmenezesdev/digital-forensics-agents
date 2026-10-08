---
name: Development task
about: Plan a verifiable change to the forensic agent protocol or implementation.
title: "[Mx][Px] "
---

## Problem and user/operator value

What failure, evidence gap, or workflow limitation does this solve? Describe the current behavior and its costs.

## Scope

Describe the smallest reversible slice. Identify public specification changes, implementation impacts, and what is deliberately out of scope.

## Inputs, outputs and forensic boundaries

- Input provenance and assumptions:
- Durable outputs and stable references:
- Coverage, failure reporting and reproducibility:
- Confidentiality, access restrictions and trust boundary:

## Acceptance criteria

- [ ] A synthetic happy-path case demonstrates the behavior.
- [ ] An adversarial fixture exercises at least one failure mode.
- [ ] Data, indices and reviewed state remain consistent across interruption/retry.
- [ ] Docs/skills reflect only implemented behavior and limitations.
- [ ] Relevant GitHub Actions checks pass on `trunk`.

## Dependencies

Link blocking issues and the milestone from [the roadmap](../../docs/roadmap.md). Prefer explicit `Blocked by #N` over implied sequencing.

## Definition of done

Commits directly to `trunk` reference this issue; verification evidence is linked before closure. Avoid real case data. Do not claim chain-of-custody, human review, or Work/Cowork integration without independent checks.

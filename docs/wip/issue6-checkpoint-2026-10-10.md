# Work-in-progress checkpoint — 2026-10-10

Branch: `wip/issue-6-evidence-anchors-20261010` — created specifically for preserving work without changing `trunk`.
Baseline: `9362da1b2e27a280328645087e95c4a42cbe0808` (CI: 58 passed for **baseline only**).
Source issues: [#6](https://github.com/vmenezesdev/digital-forensics-agents/issues/6), [#9](https://github.com/vmenezesdev/digital-forensics-agents/issues/9).

## Saved as working files

- `src/dfa/anchors.py`, `tests/test_byte_anchors.py`, JSON Schema, examples and evidence-model documentation from consolidated **issue #6 v8** patch.
- `src/dfa/source_registration.py`, isolated synthetic test suite and contract from the **source-registration audit-binding preparation** patch.

These two modules are **not yet integrated**: the v8 anchor still does not bind the source registration identity. An unimplemented regression for this vulnerability is archived below rather than suppressed or marked passing.

## Additional preserved research / regressions

- `docs/wip/patches/issue6_source_registration_red_test.patch`: intentionally failing (RED) regression for same-bytes source replacement, not applied to the main test suite.
- `docs/wip/patches/issue9_receipt_snapshot_tests.patch`: draft tests for immutable historical receipts; not executed nor integrated here.
- `docs/wip/patches/issue6_v8.patch` and `issue6_source_registration.patch`: exact source snapshots to aid reconciliation/replay.

## Verification and cautions

This branch is a **checkpoint, not a reviewed change or release**. Previous isolated synthetic unit tests were reported as passing, but the complete tests against real `Case` and a full CI run have **not yet been confirmed for this branch**. Historical `trunk` CI is not validation for this WIP commit.

No real investigative records were used or included. No issue is closed by this checkpoint. No branch merge/PR is implied.

## Next steps

1. Run `python -m unittest discover -s tests -v` in a full checkout and fix regressions.
2. Integrate immutable source registration/generation identity into byte-range anchor creation, catalog resolution and verified reads; make the RED regression pass.
3. Review schema compatibility/migrations, additional typed anchors and reproducibility acceptance for #6, then use CI evidence before considering closure.
4. Integrate and validate issue #9 receipts work independently when its dependencies are met.

## 2026-10-10 update — v2 landed on trunk; operational blocker ledger

The original WIP branch checkpoint above is historical. Its interim
source-registration code was integrated into `trunk` before this update.

- Base `c8a14f573519f9e70c3a121b0ec7dfa92198d06f`: push CI
  [38061501798](https://github.com/vmenezesdev/digital-forensics-agents/actions/runs/38061501798),
  success (83 tests).
- `bc3bd0ec396e117bd7438683371a31dd53d12334`: additive v2 byte anchors
  bound to the verified local `source.add` event hash, 5 new synthetic tests,
  v1 compatibility and limitation notes. Push CI
  [38069723464](https://github.com/vmenezesdev/digital-forensics-agents/actions/runs/38069723464),
  success (88 tests).
- `7d423f634978a282bc581140069b1b3709f71af4`: normative v2 JSON
  Schema/examples, a fixture-to-runtime test, and evidence-model docs. Push CI
  [38069778472](https://github.com/vmenezesdev/digital-forensics-agents/actions/runs/38069778472),
  success (89 tests). The Node.js 20 deprecation warning is nonblocking.
- Issue #6 remains **open**. This is an interim case-local event binding,
  not immutable physical-source generation, acquisition or custody assurance.
  Same-path recreation with identical bytes, stable logical object/generation
  semantics, additional typed anchor specifications and complete acceptance
  mapping remain unfinished.

### Operational blockers (persisted here because issue comments were refused)

**2026-10-10, issue #6, issue-comment publication.**
Action: add a progress/CI-evidence comment to
[issue #6](https://github.com/vmenezesdev/digital-forensics-agents/issues/6).
Verifiable error: `This tool call was blocked by OpenAI's safety checks. Please double check what you are sending.`
At attempt: `bc3bd0e`, run `38069723464` queued.
Impact: issue discussion cannot be updated from this execution; commits, tests,
documentation and this ledger are published independently.
Unblock condition: authorized GitHub issue-comment capability that accepts
this ordinary engineering status update.
Next action: link CI/acceptance evidence in issue #6 when allowed; do not
repeat the same denied comment attempt without a material change.

**2026-10-10, cloud checkout / local full-suite tests.**
Action: `git ls-remote https://github.com/vmenezesdev/digital-forensics-agents.git refs/heads/trunk`
in the available container. Verifiable error:
`Could not resolve host: github.com`.
At attempt: `c8a14f5`, CI run `38061501798` green.
Impact: local checkout and local test execution were unavailable; do not
misrepresent GitHub Actions results as locally executed tests.
Unblock condition: DNS/network access from an authorized cloud checkout or
configured Codex Cloud environment.
Next action: continue using SHA-specific push CI for published increments;
run local tests when an authorized checkout becomes available. Do not require
the user's personal machine as an automatic fallback.

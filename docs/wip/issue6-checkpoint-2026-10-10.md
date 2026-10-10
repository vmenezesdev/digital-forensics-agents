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

# Synthetic conformance coverage (M0)

This is a **test inventory**, not a certification. The public repository and CI contain only synthetic material. A green pipeline means these named invariants passed on the configured runner; it does **not** establish lawful collection, an authenticated custodian, complete extraction, non-repudiation or legal admissibility.

Run locally (Python 3.11+ with SQLite FTS5):

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
```

GitHub Actions runs the same suite after every push to `trunk`; some tests also launch a second Python CLI process to expose persistence and exit-code failures.

## Inventory and search — issue #2

| Contract | Synthetic test |
| --- | --- |
| First baseline digest is not silently replaced by drift | `test_drift_does_not_overwrite_baseline`, `test_changed_while_reading_does_not_reset_first_digest` |
| Completed traversal confirms missing paths and removes stale FTS hits | `test_missing_file_is_not_searchable`, `test_partial_inventory_preserves_unseen_evidence_until_complete_scan` |
| Partial reads do not mark unseen files absent; number missing remains unknown | `test_partial_inventory_preserves_unseen_evidence_until_complete_scan` |
| Failed traversal rolls back catalog/index while persisting failure state | `test_interrupted_walk_rolls_back_and_records_failure`, `test_denied_directory_aborts_without_claiming_complete_coverage` |
| Disappearing files, unreadable files and in-flight changes cannot look complete | `test_disappearing_file_before_inspection_causes_partial_not_excluded`, `test_file_read_failure_creates_partial_inventory`, `test_changed_while_reading_does_not_reset_first_digest` |
| Final and intermediate symlinks cannot silently escape a registered source | `test_file_symlink_not_followed_during_ingest`, `test_swapped_final_symlink_at_open_is_not_read`, `test_intermediate_directory_swap_cannot_escape_source_root` |
| Latest partial/failed source does not serve cached hits as current; other sources continue | `test_failed_latest_inventory_suppresses_prior_search_hits`, `test_partial_source_does_not_hide_other_complete_sources` |
| No-match is never exhaustive absence; limits and coverage are disclosed | `test_receipts_and_incomplete_coverage`, `test_search_limit_exposes_truncation`, `test_cli_reports_counts_and_non_acquisition_limitations` |

## Storage, recovery and audit — issues #3 and #4

| Contract | Synthetic test |
| --- | --- |
| Legacy v0 schema upgrades without dropping evidence, task, receipt or event records | `test_upgrade_from_unversioned_trunk_preserves_records` |
| Unknown/corrupt layout fails closed; interrupted migration rolls back | `test_unknown_future_version_fails_closed`, `test_unknown_partial_layout_is_not_silently_repaired`, `test_failed_migration_rolls_back_created_tables_and_version` |
| FTS index can be rebuilt idempotently without modifying baseline or prior receipts | `test_rebuild_repairs_disposable_projection_without_changing_baseline` |
| Source mismatch or unreadable files abort rebuild without partially replacing FTS | `test_changed_source_aborts_and_rolls_back_index_rebuild`, `test_unreadable_file_aborts_rebuild_without_index_loss` |
| Incomplete sources are excluded from reconstruction without blocking independent sources | `test_rebuild_skips_incomplete_source_but_keeps_other_source_searchable` |
| SQLite snapshot restores catalog, task board and indexes; refuses unsafe destinations | `test_backup_cli_and_restored_workspace_preserve_catalog_and_index`, `test_backup_refuses_existing_destination_or_paths_within_case_or_source` |
| Local verifier detects changed payloads and broken chain links | `test_audit_checksums_detect_row_modification`, `test_broken_audit_link_has_explicit_trust_boundary` |
| Externally retained checkpoint detects removed tail or locally recomputed chain | `test_exported_checkpoint_detects_tail_deletion`, `test_external_checkpoint_detects_locally_rehashed_history` |
| Checkpoint remains verifiable after later legitimate events | `test_checkpoint_still_verifies_after_legitimate_new_events` |
| Failures during mutation/search audit roll back both event and case update | `test_failed_audit_append_rolls_back_corresponding_case_mutation`, `test_search_receipt_and_event_roll_back_together_on_audit_failure` |
| CLI integrity failures return nonzero status | `test_failed_audit_checkpoint_check_sets_exit_code_two`, `test_failed_evidence_verification_sets_exit_code_two` |

## Portable sessions and misuse — issue #5

The suites `test_integrity_cli.py`, `test_audit_checkpoint.py`, `test_index_rebuild.py`, `test_backup.py` and `test_coordination_conformance.py` invoke the CLI or reopen the case across sessions. The latter covers concurrent task claims, reclaim after lease expiry, stale completion tokens, malformed queries and invalid limits. Existing `test_workspace.py` covers duplicate ingest and truncated receipts.

## What is **not** proved

- No attestation of the filesystem, registered-root ancestors, external source copies, permissions, disk firmware, time or operator identity.
- Race-free enumeration of arbitrary live source trees is not guaranteed. `os.walk` discovers names separately from secured file reads; changes between syscalls and in-place writes can still escape metadata detection in some conditions.
- No known-complete universe of every document/page/audio segment, no OCR/STT pipeline, and no proof that an empty search result means absent evidence.
- SQLite is a private single-machine prototype, not a multi-user transaction server or immutable evidence repository.
- Local audit digests can be recomputed by privileged attackers. Exported checkpoints help **only if stored and authenticated outside the attacked database**; no WORM or external timestamp is provided.
- No adversarial scale, crash-consistency/fsync injection, cross-filesystem portability or broad interpreter/OS matrix has been certified.
- A successful CLI `verify` compares against an application-recorded baseline, **not** a verified external acquisition image.

See [recovery and checkpoints](workspace-recovery.md), [architectural boundaries](architecture.md) and [issue tracker](https://github.com/vmenezesdev/digital-forensics-agents/issues).

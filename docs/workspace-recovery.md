# Local workspace recovery and assurance (experimental)

**Scope:** synthetic workspaces only. SQLite snapshots and checksums here are **not** forensic acquisition, immutable custody records, or authenticated timestamps. Original files remain external to the case database.

## Versioning and safe migration (issue #3)

The supported workspace schema is **version 1**, stored in SQLite `PRAGMA user_version`.

- Existing unversioned (`user_version=0`) workspaces with the recognized legacy table layout can run `dfa --case CASE_PATH init` to migrate in one SQLite transaction. Repeating `init` is idempotent.
- Unknown future versions, missing required columns, or unexpected partial layouts fail closed. **Do not downgrade `user_version` manually** or use `init` to silently repair corrupted storage.
- The migration preserves sources, evidence baseline digests, receipts, tasks, board messages and audit events. SQLite DDL and the version bump commit together or roll back together.
- Stop all writers before taking an offline backup or replacing the workspace database. Never edit the original source directory as part of migration.

Before upgrading a legacy (v0) workspace, create a consistent backup using Python's SQLite backup API while no other case writers are running:

```sh
python -c 'import sqlite3,sys; src=sqlite3.connect(sys.argv[1]); dst=sqlite3.connect(sys.argv[2]); src.backup(dst); dst.close(); src.close()' \
  /private/synthetic-case/case.sqlite3 /private/backup-pre-migration.sqlite3
dfa --case /private/synthetic-case init
```

For a current versioned workspace, use the explicit non-overwriting backup command:

```sh
dfa --case /private/synthetic-case backup /private/synthetic-case-backup.sqlite3
```

The backup destination must already have a parent directory, must not already exist and must lie outside the case directory and registered source trees. The command creates a consistent SQLite snapshot with restrictive file permissions, runs `PRAGMA quick_check`, and prints the snapshot SHA-256.

**Important:** the backup does **not** copy the original external files. It **does** contain sensitive metadata, search receipts and copied UTF-8 index text. Treat snapshots as private case data; secure access and retention separately. A restored case still points to its recorded source roots. Copy or mount those roots separately only under a documented authorization process.

## Restoring a snapshot

1. Stop case writers; preserve the damaged workspace for diagnosis instead of overwriting it.
2. Create a **new empty private** case directory, copy the backed-up SQLite file to `case.sqlite3`, and verify its SHA-256 against the recorded backup digest.
3. Run `dfa --case NEW_CASE_PATH status` and `dfa --case NEW_CASE_PATH audit-verify` (with a separately protected checkpoint, if available).
4. Ensure external source paths are appropriately available and authorized. Re-run source `verify` or inventory only after deciding how any source drift should be recorded. Do not silently replace or reset original digests.

## Rebuilding the disposable FTS5 search index

```sh
dfa --case /private/synthetic-case index-rebuild
# For previously indexed larger UTF-8 inputs:
dfa --case /private/synthetic-case index-rebuild --max-text-bytes 4194304
```

The rebuild rereads source bytes **through confined file descriptors**, compares their hashes and sizes to the recorded baseline, and atomically recreates searchable UTF-8 rows. It does not modify originals, digests, evidence classifications or prior query receipts. If a source file becomes inaccessible or its bytes disagree with the baseline, the rebuild aborts and the former index transactionally remains intact; investigate and inventory the drift rather than silently treating it as safe.

Indexed items from sources whose *most recent* inventory is partial/failed are deliberately not rebuilt; their historical catalog entries and baseline digests remain, and searches do not return them until a complete new inventory. A successful rebuild is **not** evidence acquisition or proof of current filesystem immutability.

## Externally retained audit checkpoints (issue #4)

```sh
dfa --case /private/synthetic-case audit-checkpoint > /private/checkpoint-v1.json
dfa --case /private/synthetic-case audit-verify --checkpoint /private/checkpoint-v1.json
```

An exported manifest contains the event count and head digest of a locally verified audit-chain **prefix**. Verification of that prefix remains valid even after new legitimate events are appended; the result reports the number of events added since the checkpoint. If stored independently and authenticated by the operator, it can detect deletion of the anchored tail or rewriting earlier hashes to a different chain head. A local verifier without an external checkpoint **cannot** detect all such attacks. Neither the manifest nor the local hash chain provides WORM retention, verified identity, independently trusted time or chain-of-custody compliance.

Never commit snapshots, checkpoints from real workspaces, or case metadata to this public repository.

# Architecture

The public repository specifies procedures. Cases keep their own private data.

Core layers: original sources, evidence catalog, search indexes, task board, and agent integrations.

Use local SQLite for a single-machine prototype. Distributed use needs a server-side transactional database and authorization.

## Current file-read safety boundary (refs #2)

The local ingest path now opens each regular file once through a single descriptor, combines streaming SHA-256 with a bounded UTF-8 capture, and compares `fstat` metadata on that descriptor before and after reading. On platforms providing `O_NOFOLLOW`, the final path component cannot be replaced by a symlink and silently read as another file. The verifier reports unreadable or changing sources rather than a successful check.

**Residual limitations:** replacing parent directories during traversal, filesystem changes outside the file's metadata checks, scanning an uncontrolled mount, partial filesystem walks, and permission/authorization issues are not yet resolved. This mitigates a specific file-open race but **does not authenticate acquisition, guarantee an exhaustive inventory, or replace documented chain of custody**. Work on these cases remains open in [issue #2](https://github.com/vmenezesdev/digital-forensics-agents/issues/2). Only synthetic fixtures are supported.


## Descriptor-anchored file reads (refs #2)

For source inventory and verification, the reference now opens each path component **below the registered source root** using descriptor-relative `os.open(..., dir_fd=...)` and `O_NOFOLLOW`/`O_DIRECTORY`. The final file is also opened with `O_NOFOLLOW`; hashing and bounded text capture use the same descriptor. On platforms without these secure operations, the inventory must report read failures rather than silently falling back to unsafe path-following.

**What this does not cover:** `os.walk` still discovers names through normal paths and may encounter changes during traversal, so name discovery and completeness are not race-free. Directory components **above** the registered root can be replaced; the root mount and filesystem are not attested, and an attacker who can rewrite source bytes in place may still race reads. No chain-of-custody or exhaustive acquisition claim is justified. Further race-safe traversal and scan conformance tests are tracked in [#2](https://github.com/vmenezesdev/digital-forensics-agents/issues/2).

## Inventory run status (refs #2)

Every ingest attempt records a row in `inventory_runs` with its source identifier, start/end timestamps, final state and attempt counts. A successful directory traversal with unreadable files is **partial**, not complete. An unsuccessful traversal is **failed**: catalog/index edits from that attempt roll back, and the failed attempt itself remains recorded. Vanished files are reconciled only after a traversal with no reported read or walk errors. During a partial scan, the count of missing files is **unknown** (null), not zero. Search receipts expose the latest scan state, and cached hits from partial or failed sources are **not returned** until a complete new scan; unrelated complete sources remain searchable.

Here `complete` means *the directory walk finished without reported read failures*. It **does not** mean a complete forensic acquisition, unchanged underlying media, no directory races, exhaustive extraction, or a complete search universe.

Workspace compatibility: the reference now uses SQLite schema version 1. A recognized legacy version 0 layout can be upgraded transactionally with `dfa --case CASE_PATH init`, after an independently retained backup; unknown layouts are rejected. `index-rebuild` recreates FTS5 only from unchanged, baseline-matching bytes; failed rebuilding rolls back its projection. See [workspace recovery](workspace-recovery.md) for backup, restore and checkpoint procedures. Do not run the prototype on real evidence.

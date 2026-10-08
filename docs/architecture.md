# Architecture

The public repository specifies procedures. Cases keep their own private data.

Core layers: original sources, evidence catalog, search indexes, task board, and agent integrations.

Use local SQLite for a single-machine prototype. Distributed use needs a server-side transactional database and authorization.

## Current file-read safety boundary (refs #2)

The local ingest path now opens each regular file once through a single descriptor, combines streaming SHA-256 with a bounded UTF-8 capture, and compares `fstat` metadata on that descriptor before and after reading. On platforms providing `O_NOFOLLOW`, the final path component cannot be replaced by a symlink and silently read as another file. The verifier reports unreadable or changing sources rather than a successful check.

**Residual limitations:** replacing parent directories during traversal, filesystem changes outside the file's metadata checks, scanning an uncontrolled mount, partial filesystem walks, and permission/authorization issues are not yet resolved. This mitigates a specific file-open race but **does not authenticate acquisition, guarantee an exhaustive inventory, or replace documented chain of custody**. Work on these cases remains open in [issue #2](https://github.com/vmenezesdev/digital-forensics-agents/issues/2). Only synthetic fixtures are supported.

## Inventory run status (refs #2)

Every ingest attempt records a row in `inventory_runs` with its source identifier, start/end timestamps, final state and attempt counts. A successful directory traversal with unreadable files is **partial**, not complete. An unsuccessful traversal is **failed**: catalog/index edits from that attempt roll back, and the failed attempt itself remains recorded. Vanished files are reconciled only after the walker reaches the end without a traversal error. Search receipts and case status expose the most recent scan state, so cached search results after a failed rescan are visibly **potentially stale**.

Here `complete` means *the directory walk finished without reported read failures*. It **does not** mean a complete forensic acquisition, unchanged underlying media, no directory races, exhaustive extraction, or a complete search universe.

Workspace compatibility: existing experimental workspaces must run `dfa --case CASE_PATH init` once to create the new table before using ingest/search/status with this version. Full versioned migrations and backup/restore semantics remain planned under [issue #3](https://github.com/vmenezesdev/digital-forensics-agents/issues/3). Do not run the prototype on real evidence.

# Inventory text-size boundary (synthetic conformance)

Issue #2: `Case.ingest(source_id, max_text_bytes=1048576)` limits how many
bytes of a regular file can be retained for UTF-8 search indexing. The
accepted range is 0 through 4,194,304 bytes. SHA-256 hashing still streams
the entire file; this limit is **not** a bound on bytes read or on source size.

Files larger than the bound are recorded as `excluded / oversized` rather
than silently omitted. A later inventory with a lower bound must remove
previously indexed text without resetting the original digest. Raising the
bound and re-ingesting can restore search results if the source still matches
its recorded baseline. Invalid bounds fail before starting an inventory run.

The synthetic regressions in `tests/test_inventory_bounds.py` check the
exclusion, search projection, preserved digest, recovery and invalid bounds.

**Limits:** an inventory can finish traversal with status `complete` while
its search coverage is incomplete due to exclusions. No search result does
not prove absence. The public implementation is not forensic acquisition.

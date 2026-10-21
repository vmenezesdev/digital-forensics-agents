# Exact audit action matching — issue #6

`source.add` is a case-local application event type. Its name is an exact
identifier, not a case-insensitive search term. Source registration therefore
selects events with `action COLLATE BINARY = 'source.add'`, independent of the
column collation in a recovered/rebuilt SQLite catalog.

A checksum-valid `SOURCE.ADD` event must not authorize a registration or
create false ambiguity alongside a genuine `source.add` event. The synthetic
regressions in `tests/test_registration_action_collation.py` simulate a
case-insensitive action column, verify both negative cases and a positive
control, and do not use actual case data.

This is only a query-semantics guard. Local audit checksums are mutable by a
database administrator and do not prove acquisition or chain of custody.
A full product-suite run, Python 3.11 verification, and SHA-specific push CI
are required before considering the change integrated.

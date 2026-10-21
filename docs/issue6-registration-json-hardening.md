# Strict source registration event JSON — issue #6

A `source.add` audit event is an identity-bearing application record, not
arbitrary JSON that may be interpreted differently by different decoders.
`inspect_source_registration` now rejects duplicate JSON keys (including
nested objects), non-finite constants (`NaN`/`Infinity`), overflowing numeric
exponents and excessive nesting as `malformed_registration_event`. A checksum-
valid but semantically ambiguous payload must never authorize registration.

Synthetic tests cover maliciously crafted checksum-valid event payloads and
positive controls, without real evidence. This is a parser guard, not an
authenticated audit log or proof of source acquisition/custody. Local SQLite
administrators can still rewrite event history and hashes. Other source-
identity, catalog-integrity and generation issues remain open under #6.

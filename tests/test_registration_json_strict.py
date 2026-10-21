"""Synthetic audit-payload ambiguity regressions (issue #6)."""
import sqlite3
import unittest
from dfa import audit
from dfa.source_registration import inspect_source_registration


class RegistrationJsonStrictTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(audit.SCHEMA)
        self.db.execute('CREATE TABLE sources(id TEXT PRIMARY KEY,root TEXT NOT NULL)')
        self.db.execute("INSERT INTO sources VALUES ('synthetic','/synthetic')")

    def append_raw(self, payload):
        created = 1234.0
        digest = audit._checksum(audit.ZERO, created, 'operator', 'source.add', payload)
        self.db.execute(
            'INSERT INTO audit_events(created,actor,action,payload,previous_hash,event_hash) '
            'VALUES(?,?,?,?,?,?)',
            (created, 'operator', 'source.add', payload, audit.ZERO, digest),
        )
        self.assertTrue(audit.verify(self.db)['ok'])

    def test_ambiguous_or_nonfinite_payload_fails_closed(self):
        bad = (
            '{"source_id":"other","source_id":"synthetic","root":"/synthetic"}',
            '{"source_id":"synthetic","root":"/wrong","root":"/synthetic"}',
            '{"source_id":"synthetic","root":"/synthetic","meta":{"a":1,"a":2}}',
            '{"source_id":"synthetic","root":"/synthetic","extra":NaN}',
            '{"source_id":"synthetic","root":"/synthetic","extra":Infinity}',
            '{"source_id":"synthetic","root":"/synthetic","extra":1e10000}',
            '{"source_id":"synthetic","root":"/synthetic","extra":-1e10000}',
        )
        for payload in bad:
            with self.subTest(payload=payload):
                self.db.execute('DELETE FROM audit_events')
                self.append_raw(payload)
                self.assertEqual(inspect_source_registration(self.db, 'synthetic'),
                                 {'ok': False, 'reason': 'malformed_registration_event'})

    def test_excessive_nesting_is_structured_failure(self):
        payload = ('{"source_id":"synthetic","root":"/synthetic","extra":'
                   + '[' * 10000 + '0' + ']' * 10000 + '}')
        self.append_raw(payload)
        self.assertEqual(inspect_source_registration(self.db, 'synthetic'),
                         {'ok': False, 'reason': 'malformed_registration_event'})

    def test_valid_json_remains_resolvable(self):
        self.append_raw('{"source_id":"synthetic","root":"/synthetic","extra":1.5e2}')
        self.assertTrue(inspect_source_registration(self.db, 'synthetic')['ok'])

    def test_application_event_remains_resolvable(self):
        audit.append(self.db, 'operator', 'source.add',
                     {'source_id': 'synthetic', 'root': '/synthetic'})
        self.assertTrue(inspect_source_registration(self.db, 'synthetic')['ok'])


if __name__ == '__main__':
    unittest.main()

"""Issue #6: source.add registration must not inherit SQLite column collation."""
import sqlite3
import unittest
from dfa import audit
from dfa.source_registration import inspect_source_registration


class RegistrationActionCollationTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)
        self.db.row_factory = sqlite3.Row
        # Simulate a rebuilt catalog with case-insensitive action comparison.
        self.db.execute('CREATE TABLE sources(id TEXT PRIMARY KEY, root TEXT NOT NULL)')
        self.db.execute('INSERT INTO sources VALUES (?, ?)', ('synthetic', '/synthetic'))
        self.db.executescript(audit.SCHEMA.replace('action TEXT NOT NULL', 'action TEXT COLLATE NOCASE NOT NULL'))

    def test_uppercase_action_cannot_authorize_registration(self):
        audit.append(self.db, 'operator', 'SOURCE.ADD', {
            'source_id': 'synthetic', 'root': '/synthetic'
        })
        self.assertTrue(audit.verify(self.db)['ok'])
        self.assertEqual(inspect_source_registration(self.db, 'synthetic'),
                         {'ok': False, 'reason': 'registration_unavailable'})

    def test_real_source_add_still_resolves_with_nocase_catalog(self):
        audit.append(self.db, 'operator', 'source.add', {
            'source_id': 'synthetic', 'root': '/synthetic'
        })
        self.assertTrue(inspect_source_registration(self.db, 'synthetic')['ok'])

    def test_case_variant_event_cannot_become_ambiguous_registration(self):
        audit.append(self.db, 'operator', 'source.add', {
            'source_id': 'synthetic', 'root': '/synthetic'
        })
        audit.append(self.db, 'operator', 'SOURCE.ADD', {
            'source_id': 'synthetic', 'root': '/synthetic'
        })
        self.assertTrue(audit.verify(self.db)['ok'])
        self.assertTrue(inspect_source_registration(self.db, 'synthetic')['ok'])


if __name__ == '__main__':
    unittest.main()

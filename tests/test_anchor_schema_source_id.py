"""Synthetic, dependency-free v1/v2 schema source-ID conformance (#6).

JSON Schema's `pattern` is a search, not a fullmatch. This regression checks
that both public schemas reject embedded NUL while retaining Unicode text.
The runtime's separate UTF-8 encoder must reject unpaired surrogates.
"""
import json
import re
import unittest
from pathlib import Path


SCHEMAS = Path(__file__).resolve().parents[1] / "specs" / "evidence-model"


class AnchorSchemaSourceIdTests(unittest.TestCase):
    def test_both_versions_reject_nul_and_accept_unicode(self):
        for filename in ("byte-range-anchor.schema.json", "byte-range-anchor-v2.schema.json"):
            with self.subTest(schema=filename):
                schema = json.loads((SCHEMAS / filename).read_text(encoding="utf-8"))
                source = schema["properties"]["source_id"]
                self.assertEqual(source["type"], "string")
                self.assertGreaterEqual(source["minLength"], 1)
                self.assertIn("pattern", source, "Schema must constrain NUL, not only length")
                pattern = re.compile(source["pattern"])
                for valid in ("source", "fonte-ação", "emoji-\U0001f600", "line\nbreak"):
                    self.assertIsNotNone(pattern.search(valid), valid)
                for invalid in ("bad\x00id", "\x00", "before\x00after"):
                    self.assertIsNone(pattern.search(invalid), invalid)


if __name__ == "__main__":
    unittest.main()

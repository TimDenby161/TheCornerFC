"""T-098 (2026-11-25): the public site functions that take lists answer nothing when a list is far
longer than any page sends, and are otherwise unchanged."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "db/migrations/20261125_site_list_limits.sql"
NAMES = ("site_players", "site_matches", "site_prediction_record", "site_lineup_history")
GUARD = re.compile(r"\n    -- T-098:.*?\n    END IF;", re.S)


def definitions(text, name):
    out, at = [], 0
    while (start := text.find(f"CREATE OR REPLACE FUNCTION public.{name}(", at)) >= 0:
        end = text.index("$$;", text.index("AS $$", start) + 5) + 3
        out.append(text[start:end])
        at = end
    return out


class SiteListLimits(unittest.TestCase):
    def test_the_migration_is_in_the_schema_word_for_word(self):
        self.assertIn(MIGRATION.read_text(), (ROOT / "db/schema.sql").read_text())

    def test_each_function_is_the_one_before_with_only_the_check_added(self):
        schema, migration = (ROOT / "db/schema.sql").read_text(), MIGRATION.read_text()
        for name in NAMES:
            with self.subTest(function=name):
                (new,) = definitions(migration, name)
                before = definitions(schema, name)[-2]          # the version this one replaces
                self.assertEqual(len(GUARD.findall(new)), 1)
                self.assertEqual(GUARD.sub("", new), before)
                self.assertIn("RETURN NULL;", GUARD.search(new).group())

    def test_the_limits_sit_above_what_the_site_sends(self):
        text = MIGRATION.read_text()
        self.assertIn("cardinality(p_ids), 0) > 2000", text)              # the fantasy page sends up to 1,000
        self.assertIn("cardinality(p_words), 0) > 40", text)                 # an 80-character search: at most 40 words
        self.assertIn("cardinality(p_teams), 0) > 2000", text)              # the cup filter: every club still in a cup
        self.assertTrue(text.startswith("-- Repeatable."))
        self.assertNotIn("GRANT", text)                                    # CREATE OR REPLACE keeps the grants


if __name__ == "__main__":
    unittest.main()

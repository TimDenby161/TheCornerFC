"""T-102 (owner, 2026-11-25): a league's next round is free however far off, in the database's
site_matches as in the export's league files."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "db/migrations/20261125_free_next_round.sql"


class FreeNextRound(unittest.TestCase):
    def test_the_migration_is_in_the_schema_word_for_word(self):
        self.assertIn(MIGRATION.read_text(), (ROOT / "db/schema.sql").read_text())

    def test_it_is_repeatable_and_keeps_the_grants(self):
        text = MIGRATION.read_text()
        self.assertTrue(text.startswith("-- Repeatable."))
        self.assertIn("CREATE OR REPLACE FUNCTION public.site_matches(", text)
        self.assertIn("SET search_path = ''", text)
        self.assertIn("REVOKE ALL ON FUNCTION public.site_matches(timestamptz, timestamptz, integer[], integer, integer[]) FROM PUBLIC;", text)
        self.assertIn("ARRAY['anon','authenticated']", text)

    def test_the_rule_matches_the_export(self):
        from thecornerfc.publish import site_clubs
        text = MIGRATION.read_text()
        self.assertIn("interval '7 days'", text)                                   # site_clubs.FREE_DAYS
        self.assertIn(f"+ interval '{site_clubs.NEXT_ROUND_DAYS} days'", text)
        self.assertEqual(site_clubs.FREE_DAYS, 7)
        # only for a league whose next kick-off is beyond the 7 days, and never the projected goals
        self.assertIn("ORDER BY n.kickoff LIMIT 1) > soon", text)
        self.assertIn("THEN coalesce(m.data_free, m.data_locked)", text)
        # the round's last moment is free in both (the export hides only kick-offs after it)
        self.assertIn("AND m.kickoff <= (SELECT n.kickoff FROM site.matches n", text)
        import inspect
        self.assertIn('f[at("kickoff")] > limit', inspect.getsource(site_clubs.cut_league_fixtures))


if __name__ == "__main__":
    unittest.main()

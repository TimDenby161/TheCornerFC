"""Beat the Model (T-095) and the Fantasy points page for signed-in accounts (T-104): the
migrations are in the schema word for word, and nothing is reachable with the public key alone."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT / "db/migrations/20261123_beat_the_model.sql"
POINTS = ROOT / "db/migrations/20261123_fantasy_points_public.sql"
TABLES = ("btm_players", "btm_picks", "btm_model", "btm_rounds", "btm_seasons")
PLAYER_FUNCTIONS = ("btm_round(integer)", "btm_pick(integer, integer, integer)", "btm_set_name(text)",
                    "btm_table(integer)")


class MigrationsTest(unittest.TestCase):
    def test_they_are_in_the_schema_word_for_word(self):
        schema = (ROOT / "db/schema.sql").read_text()
        self.assertIn(GAME.read_text(), schema)
        self.assertIn(POINTS.read_text(), schema)

    def test_every_game_table_has_row_level_security_and_is_shut(self):
        sql = GAME.read_text()
        for table in TABLES:
            self.assertIn(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY;", sql)
            self.assertRegex(sql, rf"REVOKE ALL ON [^;]*public\.{table}\b[^;]*FROM %I")

    def test_players_reach_only_their_four_functions_and_only_when_signed_in(self):
        sql = GAME.read_text()
        grant = re.search(r"GRANT EXECUTE ON FUNCTION (.*?) TO authenticated;", sql, re.S).group(1)
        self.assertEqual(sorted(re.findall(r"public\.(\w+\([^)]*\))", re.sub(r"\s+", " ", grant))),
                         sorted(PLAYER_FUNCTIONS))
        self.assertNotIn("TO anon", sql)
        self.assertIn("REVOKE ALL ON FUNCTION public.btm_score() FROM PUBLIC;", sql)

    def test_every_function_pins_its_search_path(self):
        for path in (GAME, POINTS):
            sql = path.read_text()
            functions = re.findall(r"CREATE OR REPLACE FUNCTION (public\.\w+)\(", sql)
            self.assertTrue(functions)
            self.assertEqual(len(re.findall(r"SET search_path = ''", sql)), len(functions), path.name)

    def test_the_points_page_opens_only_the_predictions_to_signed_in_callers(self):
        sql = POINTS.read_text()
        self.assertNotIn("TO anon", sql)
        self.assertEqual(sql.count("auth.uid() IS NULL OR coalesce((auth.jwt()->>'is_anonymous')::boolean, false)"), 2)
        self.assertNotIn("fpl_team", sql.replace("fpl_team_owners", ""))
        self.assertNotIn("efl_predictions", sql.split("BEGIN;", 1)[1])
        self.assertEqual(set(re.findall(r"d\.name = '(\w+)'", sql)), {"fpl_predictions"})


if __name__ == "__main__":
    unittest.main()

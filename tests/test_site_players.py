import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from thecornerfc.publish import export
from thecornerfc.publish.export import PLAYER_FIELDS, SITE_PLAYER_FIELDS, site_player_rows, store_players

ROOT = Path(__file__).resolve().parents[1]


def player(pid, name="A. Player", **over):
    row = dict.fromkeys(PLAYER_FIELDS)
    row.update({"id": pid, "name": name, "position": "ST", "rank": 80.0, "minutes": 900, "team": 1, "league": 39,
                "seasons": [80.0, None], "estimated": [], "positions_12m": ["ST"], "position_ranks": {"ST": 80.0},
                "future": [81.0], "season": [900, 3, 2], **over})
    return [row[k] for k in PLAYER_FIELDS]


def by_name(rows):
    return {r["player_id"]: dict(zip(SITE_PLAYER_FIELDS, r["data"])) for r in rows}


class SitePlayerRows(unittest.TestCase):
    def test_places_are_counted_as_the_site_counted_them(self):
        rows = site_player_rows([
            player(1, seasons=[90.0, None], rank=91.0),
            player(2, seasons=[88.0, None], rank=88.0),
            player(3, seasons=[88.0, None], rank=92.0),                        # a tie shares the higher place
            player(4, seasons=[70.0, None], rank=70.0, league=140, team=9),
            player(5, seasons=[None, None], rank=60.0),                        # no Ability: no world or league place
            player(6, seasons=[95.0, None], rank=95.0, team=None),             # no club: counted by Ability, not on his page
            player(7, seasons=[99.0, None], rank=99.0, team=None, league=None),
        ])
        got = by_name(rows)
        self.assertEqual([got[i]["world"] for i in range(1, 8)], [3, 4, 4, 6, None, 2, 1])
        self.assertEqual([(got[i]["lg"], got[i]["lg_of"]) for i in range(1, 8)],
                         [(2, 4), (3, 4), (3, 4), (1, 1), (None, None), (1, 4), (None, None)])
        # on his page: by current rank among his league's players who have a club
        self.assertEqual([(got[i]["lg_rank"], got[i]["lg_n"]) for i in range(1, 8)],
                         [(2, 4), (3, 4), (1, 4), (1, 1), (4, 4), (None, None), (None, None)])
        self.assertEqual([got[i]["ord"] for i in range(1, 8)], list(range(7)))
        self.assertEqual([r["ord"] for r in rows], list(range(7)))

    def test_the_columns_the_queries_filter_and_sort_on(self):
        rankings = [[1, 39, 0, 0, 1100.0], [2, 39, 0, 0, 1100.0], [3, 39, 0, 0, 1000.0], [4, 39, 0, 0, None]]
        (a, b, c) = site_player_rows([
            player(1, "N. O&apos;Reilly", seasons=[87.5, 80.0], position="LB", positions_12m=["LB", "CM", "LB"], team=3),
            player(2, "Kylian Mbappé", seasons=[86.49, None], season=None, team=4, position=None, positions_12m=[]),
            player(3, "Ø. Ødegård-Smith", seasons=[None, 70.0], team=None, season=[0, 0, 0]),
        ], rankings)
        self.assertEqual((a["name_lc"], a["name_fold"]), ("n. o'reilly", "n o reilly"))       # as the site decodes and folds it
        self.assertEqual((b["name_lc"], b["name_fold"]), ("kylian mbappé", "kylian mbappe"))
        self.assertEqual(c["name_fold"], "degard smith")                                         # a letter with no plain form is a gap, as on the site
        self.assertEqual((a["ability"], b["ability"], c["ability"]), (88, 86, None))             # rounded as shown: halves up
        self.assertEqual((a["club_world"], b["club_world"], c["club_world"]), (3, None, None))   # two clubs tie for first
        self.assertEqual((a["plays"], b["plays"]), (["LB", "CM"], []))
        self.assertEqual((a["ga"], b["ga"], c["ga"]), (5.003, None, 0))                          # goals break ties
        self.assertEqual(a["data"][:len(PLAYER_FIELDS)], player(1, "N. O&apos;Reilly", seasons=[87.5, 80.0], position="LB",
                                                                positions_12m=["LB", "CM", "LB"], team=3))
        self.assertEqual(len(a["data"]), len(SITE_PLAYER_FIELDS))

    def test_players_are_stored_as_rows(self):
        conn, cur = Mock(), MagicMock()
        conn.execute.return_value.fetchone.return_value = ("site.players",)
        cur.__enter__.return_value = cur
        conn.cursor.return_value = cur
        copy = cur.copy.return_value.__enter__.return_value
        rows = site_player_rows([player(1), player(2, team=None)] + [player(i) for i in range(3, 61)])
        cur.execute.return_value.fetchone.return_value = (70,)
        with patch.object(export.config, "require_db_write"):
            self.assertTrue(store_players(conn, rows))
        self.assertEqual(cur.execute.call_args_list[1][0][0], "delete from site.players")        # rewritten whole
        first, second = [c[0][0] for c in copy.write_row.call_args_list][:2]
        self.assertEqual(first[:8], [1, 0, "a. player", "a player", 1, 39, None, None])
        self.assertEqual(first[8], ["ST"])                         # an array column, not text
        self.assertEqual(json.loads(first[14]), {"ST": 80.0})
        self.assertEqual(json.loads(first[16]), rows[0]["data"])
        self.assertIsNone(second[4])
        conn.commit.assert_called_once()

    def test_too_few_players_or_most_of_them_gone_leaves_the_table_alone(self):
        conn, cur = Mock(), MagicMock()
        conn.execute.return_value.fetchone.return_value = ("site.players",)
        cur.__enter__.return_value = cur
        conn.cursor.return_value = cur
        cur.execute.return_value.fetchone.return_value = (7500,)
        with patch.object(export.config, "require_db_write"):
            with self.assertRaisesRegex(export.ExportValidationError, "only 2 players"):
                store_players(conn, site_player_rows([player(1), player(2)]))
            with self.assertRaisesRegex(export.ExportValidationError, "site.players would collapse from 7500 to 60 rows"):
                store_players(conn, site_player_rows([player(i) for i in range(1, 61)]))
        cur.copy.assert_not_called()
        self.assertNotIn("delete from site.players", [c[0][0] for c in cur.execute.call_args_list])

    def test_without_the_table_nothing_is_stored(self):
        conn = Mock()
        conn.execute.return_value.fetchone.return_value = (None,)
        with patch.object(export.config, "require_db_write"), self.assertLogs(export.log, "WARNING"):
            self.assertFalse(store_players(conn, site_player_rows([player(1)])))
        conn.cursor.assert_not_called()
        with patch.object(export.config, "require_db_write", side_effect=export.config.SafetyError("read-only")):
            self.assertFalse(store_players(conn, []))
        # the site is told the order of a player's row, which it needs to read any of them
        source = Path(export.__file__).read_text()
        self.assertIn('site.update(player_fields=SITE_PLAYER_FIELDS', source)

    def test_the_functions_are_the_only_way_in(self):
        sql = (ROOT / "db/migrations/20261005_site_players.sql").read_text()
        self.assertIn(sql, (ROOT / "db/schema.sql").read_text())
        players = ("site_players(integer[], integer[], integer[], text[], integer[], text[], integer[], integer[], integer[], "
                   "integer[], text, text[], text, text[], integer, integer, boolean)")
        for fn in (players, "site_player_facets()", "site_next_xi(integer)"):
            self.assertIn(f"REVOKE ALL ON FUNCTION public.{fn} FROM PUBLIC", sql)
            self.assertIn(f"GRANT EXECUTE ON FUNCTION public.{fn} TO %I", sql)
        self.assertEqual(sql.count("SET search_path = ''"), 3)
        self.assertIn("REVOKE ALL ON site.players FROM PUBLIC", sql)
        self.assertIn("ALTER TABLE site.players ENABLE ROW LEVEL SECURITY", sql)
        self.assertNotIn("GRANT SELECT", sql.upper().replace("GRANT EXECUTE", ""))
        self.assertIn("LIMIT least(greatest(coalesce(p_limit, 100), 0), 2000)", sql)        # never every player
        self.assertNotIn("EXECUTE format('SELECT", sql)                                     # fixed SQL: no query built from an argument

    def test_a_clubs_next_xi_starts_from_the_clubs_own_fixtures(self):
        # joined to fixtures and sorted by kick-off with LIMIT 1, the database walked every fixture
        # from the oldest (20261005_site_next_xi_fast.sql): the club's fixtures are taken first
        sql = (ROOT / "db/migrations/20261005_site_next_xi_fast.sql").read_text()
        self.assertIn(sql, (ROOT / "db/schema.sql").read_text())
        self.assertIn("FROM (SELECT DISTINCT pl.fixture_id FROM public.predicted_lineups pl WHERE pl.team_id = p_team OFFSET 0) mine", sql)
        self.assertIn("REVOKE ALL ON FUNCTION public.site_next_xi(integer) FROM PUBLIC", sql)
        self.assertIn("SET search_path = ''", sql)
        schema = (ROOT / "db/schema.sql").read_text()
        # in the schema it comes after the first version, so a new database ends up with this one
        self.assertGreater(schema.index("next_fixture integer"), schema.index("CREATE OR REPLACE FUNCTION public.site_player_facets()"))

    def test_the_export_writes_no_list_of_every_player(self):
        # there is no list of every player any more
        self.assertNotIn('"players.json"', Path(export.__file__).read_text())


if __name__ == "__main__":
    unittest.main()

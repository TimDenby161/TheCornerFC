import json
import tempfile
import unittest
import unittest.mock
from datetime import datetime, timedelta, timezone
from pathlib import Path

from thecornerfc import tables

DAY = datetime(2026, 8, 1, tzinfo=timezone.utc)


def match(day, rnd, home, away, hg, ag):
    return (DAY + timedelta(days=day), rnd, home, away, hg, ag)


def by_team(rows):
    return {r[2]: dict(zip(tables.FIELDS, r)) for r in rows}


class LeagueTableTests(unittest.TestCase):
    def setUp(self):
        self.standing = [("League", 1, 1, "Promotion"), ("League", 2, 2, None), ("League", 3, 3, "Relegation")]
        self.fixtures = [match(0, "Regular Season - 1", 1, 2, 2, 0), match(7, "Regular Season - 2", 2, 3, 1, 1),
                         match(14, "Regular Season - 3", 3, 1, 0, 3), match(21, "Regular Season - 4", 2, 1, 1, 0)]

    def test_figures_order_form_and_places(self):
        rows = tables.league_table(self.standing, self.fixtures)
        self.assertEqual([r[2] for r in rows], [1, 2, 3])
        self.assertEqual([r[1] for r in rows], [1, 2, 3])
        t = by_team(rows)
        self.assertEqual([t[1][k] for k in ("played", "win", "draw", "lose", "gf", "ga", "gd", "points")], [3, 2, 0, 1, 5, 1, 4, 6])
        self.assertEqual(t[1]["form"], "LWW")                  # newest first
        self.assertEqual(t[2]["form"], "WDL")
        self.assertEqual([r[12] for r in rows], ["Promotion", None, "Relegation"])   # by place, not by club

    def test_place_descriptions_follow_the_computed_order(self):
        standing = [("League", 3, 1, "Promotion"), ("League", 2, 2, None), ("League", 1, 3, "Relegation")]   # (group, club, its place in the feed, what the place leads to)
        rows = tables.league_table(standing, self.fixtures)
        self.assertEqual([(r[2], r[12]) for r in rows], [(1, "Promotion"), (2, None), (3, "Relegation")])

    def test_points_adjustment_and_annulled_club(self):
        rows = by_team(tables.league_table(self.standing, self.fixtures, {"points": {1: -4}, "void": set()}))
        self.assertEqual(rows[1]["points"], 2)
        self.assertEqual(rows[1]["rank"], 2)
        rows = by_team(tables.league_table(self.standing, self.fixtures, {"points": {}, "void": {3}}))
        self.assertEqual((rows[1]["played"], rows[2]["played"], rows[3]["played"]), (2, 2, 0))

    def test_only_regular_season_rounds_count_in_a_league(self):
        fixtures = self.fixtures + [match(30, "Promotion Play-offs - Final", 1, 2, 0, 5)]
        self.assertEqual(by_team(tables.league_table(self.standing, fixtures))[1]["played"], 3)

    def test_named_rounds_count_when_there_is_no_regular_season(self):
        fixtures = [match(0, "National League North - 1", 1, 2, 1, 0)]
        self.assertEqual(by_team(tables.league_table(self.standing, fixtures))[1]["points"], 3)

    def test_a_cup_counts_only_its_league_or_group_stage(self):
        standing = [("Cup", 1, 1, None), ("Cup", 2, 2, None)]
        qualifiers = [match(0, "2nd Qualifying Round", 1, 2, 3, 0)]
        rows = by_team(tables.league_table(standing, qualifiers, cup=True))
        self.assertEqual((rows[1]["played"], rows[1]["form"]), (0, None))
        rows = by_team(tables.league_table(standing, qualifiers + [match(9, "League Stage - 1", 2, 1, 2, 0)], cup=True))
        self.assertEqual((rows[2]["played"], rows[2]["points"], rows[1]["played"]), (1, 3, 1))

    def test_a_group_named_after_a_stage_counts_that_stage(self):
        standing = [("Apertura - Group A", 1, 1, None), ("Apertura - Group A", 2, 2, None),
                    ("Clausura - Group A", 1, 1, None), ("Clausura - Group A", 2, 2, None)]
        fixtures = [match(0, "Apertura - 1", 1, 2, 1, 0), match(5, "Apertura - Quarter-finals", 1, 2, 4, 0),
                    match(60, "Clausura - 1", 2, 1, 2, 0), match(67, "Clausura - 2", 1, 2, 1, 1)]
        rows = {(r[0], r[2]): r for r in tables.league_table(standing, fixtures)}
        self.assertEqual(rows[("Apertura - Group A", 1)][3:11], [1, 1, 0, 0, 1, 0, 1, 3])
        self.assertEqual(rows[("Clausura - Group A", 2)][3:11], [2, 1, 1, 0, 3, 1, 2, 4])

    def test_a_split_league_counts_every_match_in_its_second_groups(self):
        standing = [("League", i, i, None) for i in (1, 2, 3, 4)] + [("Championship Round", 1, 1, None), ("Championship Round", 2, 2, None)]
        fixtures = [match(0, "Regular Season - 1", 1, 2, 1, 0), match(1, "Regular Season - 1", 3, 4, 0, 0),
                    match(40, "Championship Group - 1", 2, 1, 2, 2)]
        rows = {(r[0], r[2]): r for r in tables.league_table(standing, fixtures)}
        self.assertEqual(rows[("League", 1)][3], 1)
        self.assertEqual(rows[("Championship Round", 1)][3], 2)

    def test_conferences_share_the_regular_season(self):
        standing = [("East", 1, 1, None), ("East", 2, 2, None), ("West", 3, 1, None), ("West", 4, 2, None)]
        fixtures = [match(0, "Regular Season - 1", 1, 3, 2, 0), match(1, "Regular Season - 1", 4, 2, 1, 1)]
        rows = by_team(tables.league_table(standing, fixtures))
        self.assertEqual([rows[t]["points"] for t in (1, 2, 3, 4)], [3, 1, 0, 1])

    def test_wins_first_and_head_to_head_orders(self):
        standing = [("League", i, i, None) for i in (1, 2, 3)]
        # 1 and 2 finish level on 4 points; 1 has the better goal difference, 2 beat 1
        fixtures = [match(0, "Regular Season - 1", 2, 1, 1, 0), match(7, "Regular Season - 2", 1, 3, 5, 0),
                    match(14, "Regular Season - 3", 2, 3, 0, 0), match(21, "Regular Season - 4", 3, 1, 1, 1)]
        self.assertEqual([r[2] for r in tables.league_table(standing, fixtures)][:2], [1, 2])
        self.assertEqual([r[2] for r in tables.league_table(standing, fixtures, order="h2h")][:2], [2, 1])
        # 1: W L L (3 points, +3); 2: D D D (3 points, 0): wins first puts 1 top either way, so
        # make 2 the better on goal difference
        fixtures = [match(0, "Regular Season - 1", 1, 3, 1, 0), match(7, "Regular Season - 2", 3, 1, 4, 0),
                    match(14, "Regular Season - 3", 2, 3, 0, 0), match(21, "Regular Season - 4", 2, 3, 1, 1),
                    match(28, "Regular Season - 5", 3, 2, 2, 2)]
        self.assertEqual(tables.league_table(standing, fixtures)[1][2], 2)
        self.assertEqual(tables.league_table(standing, fixtures, order="wins")[1][2], 1)

    def test_differences_against_the_feed(self):
        rows = tables.league_table(self.standing, self.fixtures)
        same = [(r[0], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[10]) for r in rows]
        self.assertEqual(tables.differences(rows, same), [])
        other = [same[0][:8] + (2,)] + same[1:]
        self.assertEqual(tables.differences(rows, other), [("League", 1, (3, 2, 0, 1, 5, 1, 6), (3, 2, 0, 1, 5, 1, 2))])

    def test_adjustments_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "adjust.json"
            path.write_text(json.dumps({"40:2026": {"points": {"41": -4}, "void": [7]}}))
            self.assertEqual(tables.adjustments(40, 2026, path), {"points": {41: -4}, "void": {7}})
            self.assertEqual(tables.adjustments(40, 2025, path), {"points": {}, "void": set()})
        shipped = json.loads(tables.PATH.read_text())
        for key, entry in shipped.items():
            league, season = key.split(":")
            self.assertTrue(league.isdigit() and season.isdigit())
            self.assertLessEqual(set(entry), {"points", "void"})


if __name__ == "__main__":
    unittest.main()


class PaidLeagueFileTests(unittest.TestCase):
    """A league's free file once the paid tier's function is there: chances for the next 7 days
    only and no projected goals; the whole file is a paid row (20261006_site_league.sql)."""
    def test_cut_league_fixtures(self):
        from thecornerfc import export
        now = datetime(2026, 10, 6, 12, tzinfo=timezone.utc)
        row = lambda fid, days, status, hg=None: [fid, (now + timedelta(days=days)).isoformat(), "Regular Season - 9", 1, 2, status,
                                                  hg, hg, None, None, None if hg is not None else 1.6, None if hg is not None else 1.1,
                                                  None if hg is not None else 0.5, None if hg is not None else 0.3, None if hg is not None else 0.2]
        played, soon, later = row(1, -3, "FT", 2), row(2, 3, "NS"), row(3, 30, "NS")
        cut = export.cut_league_fixtures([played, soon, later], now)
        self.assertEqual(cut[0], played)
        self.assertEqual(cut[1], soon[:10] + [None, None, 0.5, 0.3, 0.2])
        self.assertEqual(cut[2], later[:10] + [None] * 5)
        self.assertEqual(soon[10], 1.6)                                    # the whole rows are untouched

    def test_paid_files_are_stored_as_paid_rows(self):
        from unittest.mock import MagicMock, Mock, patch
        from thecornerfc import export
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "leagues").mkdir()
            (out / "paid_leagues").mkdir(parents=True)
            (out / "leagues" / "39.json").write_text('{"cut":true}')
            (out / "paid_leagues" / "39.json").write_text('{"id":39}')
            conn, cur = Mock(), MagicMock()
            conn.execute.return_value.fetchall.return_value = []
            cur.__enter__.return_value = cur
            conn.cursor.return_value = cur
            with patch.object(export.config, "require_db_write"):
                export.mirror_site_docs(conn, out)
            sql, rows = cur.executemany.call_args[0]
            self.assertIn("paid = excluded.paid", sql)
            self.assertEqual({r[0]: r[3] for r in rows}, {"leagues/39": False, "paid_leagues/39": True})

    def test_the_league_function_never_gives_the_paid_row_to_the_unentitled(self):
        sql = (Path(__file__).resolve().parents[1] / "db/migrations/20261006_site_league.sql").read_text()
        self.assertIn("IF site.entitled() THEN", sql)
        self.assertIn("d.key = 'paid_leagues/' || p_id AND d.paid", sql)
        self.assertIn("d.key = 'leagues/' || p_id AND NOT d.paid", sql)


class PaidLineupsMigrationTests(unittest.TestCase):
    """20261006_paid_lineups.sql is the two live functions with the lock added and nothing else."""
    ROOT = Path(__file__).resolve().parents[1] / "db/migrations"

    def body(self, name, function):
        sql = (self.ROOT / name).read_text()
        start = sql.index(f"CREATE OR REPLACE FUNCTION public.{function}")
        return sql[start:sql.index("END; $$;", start)]

    def test_lineups_differ_only_by_the_lock(self):
        new = self.body("20261006_paid_lineups.sql", "site_lineups")
        for added in ("DECLARE\n    -- the predicted XI of a match that hasn't kicked off is for the entitled\n    whole boolean := site.entitled()\n"
                      "        OR coalesce((SELECT f.kickoff <= pg_catalog.now() FROM public.fixtures f WHERE f.fixture_id = p_fixture), true);\n",
                      "            'locked', NOT whole,\n"):
            self.assertIn(added, new)
            new = new.replace(added, "")
        new = new.replace("'xi', CASE WHEN whole THEN (SELECT", "'xi', (SELECT").replace("GROUP BY pl.team_id) t) END,", "GROUP BY pl.team_id) t),")
        self.assertEqual(new, self.body("20261005_site_lineups.sql", "site_lineups"))

    def test_next_xi_differs_only_by_the_lock(self):
        new = self.body("20261006_paid_lineups.sql", "site_next_xi")
        added = ("    IF next_fixture IS NOT NULL AND NOT site.entitled() THEN\n"
                 "        RETURN pg_catalog.json_build_object('fixture', next_fixture, 'players', NULL, 'locked', true);\n    END IF;\n")
        self.assertIn(added, new)
        self.assertEqual(new.replace(added, ""), self.body("20261005_site_next_xi_fast.sql", "site_next_xi"))


class PaidPlayersTests(unittest.TestCase):
    """The paid tier's players: a free slice, a blanked row for the rest, a cut-down page file
    (db/migrations/20261006_paid_players.sql)."""
    def rows(self, n=120):
        from thecornerfc import export
        raw = [[i + 1, f"Player {i:03d}", "CM", 95 - i * 0.5, 900, 100 + i % 6, 39 + i % 2, [95 - i * 0.5, None], 24, [],
                "England", ["CM"], {"CM": 95 - i * 0.5}, [90.0], [900, 3, 2]] for i in range(n)]
        return export.site_player_rows(raw)

    def test_the_free_slice_is_the_top_50_and_each_leagues_top_10(self):
        rows = self.rows()
        free = [p["player_id"] for p in rows if p["free"]]
        self.assertEqual(free, list(range(1, 51)))            # two leagues' top 10s fall inside the overall 50 here
        from thecornerfc import export
        with unittest.mock.patch.object(export, "FREE_WORLD", 4), unittest.mock.patch.object(export, "FREE_LEAGUE", 3):
            free = {p["player_id"] for p in self.rows() if p["free"]}
        self.assertEqual(free, {1, 2, 3, 4, 5, 6})            # the top 4, and the third of each league (5 and 6)

    def test_the_blanked_row_keeps_who_he_is_and_loses_every_rank(self):
        from thecornerfc import export
        p = self.rows()[70]
        got = dict(zip(export.SITE_PLAYER_FIELDS, p["data_free"]))
        whole = dict(zip(export.SITE_PLAYER_FIELDS, p["data"]))
        for f in export.SITE_PLAYER_FIELDS:
            self.assertEqual(got[f], None if f in export.PLAYER_PAID_FIELDS else whole[f], f)
        self.assertEqual((got["name"], got["team"], got["age"], got["minutes"], got["season"]), ("Player 070", 104, 24, 900, [900, 3, 2]))

    def test_the_migration_blanks_the_same_fields_and_marks_the_same_slice(self):
        from thecornerfc import export
        sql = (Path(__file__).resolve().parents[1] / "db/migrations/20261006_paid_players.sql").read_text()
        at = export.SITE_PLAYER_FIELDS.index
        self.assertIn(f"ARRAY[{','.join(str(i) for i in sorted(at(f) for f in export.PLAYER_PAID_FIELDS))}]", sql)
        self.assertIn(f"(p.data->>{at('world')})::integer <= {export.FREE_WORLD}", sql)
        self.assertIn(f"(p.data->>{at('lg')})::integer <= {export.FREE_LEAGUE}", sql)
        self.assertIn("WHERE (whole OR p.free OR p.data_free IS NOT NULL)", sql)      # never the whole row for want of a blanked one

    def test_the_cut_down_page_has_no_rank_per_match_or_movement(self):
        from thecornerfc import export
        match = dict.fromkeys(export.MATCH_FIELDS, 1)
        match["rank"] = 71.5
        page = {"id": 9, "matches": [list(match.values())], "seasons": [[2026, 1, 39, 5, 5, 450, 1, 0, 1, 0]], "movement": {"rows": [[7, 0.4, 2, "x"]]}, "born": "2000-01-01"}
        cut = export.cut_player_page(page)
        self.assertEqual(dict(zip(export.MATCH_FIELDS, cut["matches"][0]))["rank"], None)
        self.assertNotIn("movement", cut)
        self.assertEqual((cut["cut"], cut["seasons"], cut["born"]), (True, page["seasons"], "2000-01-01"))
        self.assertEqual(page["matches"][0][export.MATCH_FIELDS.index("rank")], 71.5)      # the whole page is untouched


class HeadlineProjectionTests(unittest.TestCase):
    """The free projected table: places and points only (export.headline_projection)."""
    def test_points_so_far_plus_expected_points_and_the_order(self):
        from thecornerfc import export
        table = [["League", 1, 1, 10, 6, 2, 2, 20, 10, 10, 20, "WWW", None], ["League", 2, 2, 10, 6, 1, 3, 15, 10, 5, 19, "WLW", None],
                 ["League", 3, 3, 10, 2, 2, 6, 8, 16, -8, 8, "LLD", None]]
        fx = lambda fid, home, away, ph, pd, pa, hx=1.5, ax=1.0: [fid, "2026-11-01T15:00:00+00:00", "Regular Season - 11", home, away, "NS", None, None, None, None, hx, ax, ph, pd, pa]
        fixtures = [fx(1, 2, 3, 0.8, 0.1, 0.1), fx(2, 2, 1, 0.5, 0.25, 0.25), fx(3, 3, 1, 0.2, 0.3, 0.5),
                    [4, "2026-10-01T15:00:00+00:00", "Regular Season - 9", 1, 2, "FT", 1, 0, None, None, None, None, None, None, None]]
        got = export.headline_projection(table, fixtures)
        # club 2: 19 + (2.4 + 0.1) + (1.5 + 0.25) = 23.25; club 1: 20 + (0.75 + 0.25) + (1.5 + 0.3) = 22.8
        self.assertEqual(got, [["League", 1, 2, 2, 23], ["League", 2, 1, 2, 23], ["League", 3, 3, 2, 9]])

    def test_nothing_without_projections(self):
        from thecornerfc import export
        self.assertEqual(export.headline_projection([["League", 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, None, None]], []), [])

    def test_the_rank_migration_differs_from_the_line_ups_one_only_by_the_ranks(self):
        root = Path(__file__).resolve().parents[1] / "db/migrations"
        body = lambda name: (lambda sql: sql[sql.index("CREATE OR REPLACE FUNCTION public.site_lineups"):sql.index("END; $$;")])((root / name).read_text())
        new = body("20261006_paid_lineup_ranks.sql")
        for a, b in (("    paid boolean := site.entitled();\n    whole boolean := paid\n", "    whole boolean := site.entitled()\n"),
                     ("CASE WHEN paid THEN coalesce(r.player_rank, p.current_rank)::float8 END)", "coalesce(r.player_rank, p.current_rank)::float8)"),
                     ("CASE WHEN paid THEN (e.v->>'player_rating')::float8 END)", "(e.v->>'player_rating')::float8)"),
                     ("    -- the predicted XI of a match that hasn't kicked off is for the entitled (whole), and so is\n    -- each player's rank in the line-ups of one that has (paid)\n",
                      "    -- the predicted XI of a match that hasn't kicked off is for the entitled\n")):
            self.assertEqual(new.count(a), 1, a)
            new = new.replace(a, b)
        self.assertEqual(new, body("20261006_paid_lineups.sql"))

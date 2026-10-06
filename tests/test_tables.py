import json
import tempfile
import unittest
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

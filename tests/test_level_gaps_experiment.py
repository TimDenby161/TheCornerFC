"""The level-gaps experiment (experiments/level_gaps/run.py) on made-up fixtures: no database."""
import importlib.util
import random
import unittest
from pathlib import Path

from thecornerfc.models import predictions

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("level_gaps", ROOT / "experiments/level_gaps/run.py")
run = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run)

LEAGUES = {"1": {"name": "Top", "country": "X", "type": "League", "starting_rank": 1000.0},
           "2": {"name": "Second", "country": "X", "type": "League", "starting_rank": 800.0},
           "3": {"name": "No level", "country": "X", "type": "League", "starting_rank": None},
           "9": {"name": "Cup", "country": "X", "type": "Cup", "starting_rank": 500.0}}


def fx(fixture_id, day, league, home, away, **more):
    return {"fixture_id": fixture_id, "kickoff": f"{day}T15:00:00+00:00", "league_id": league,
            "home_team_id": home, "away_team_id": away, "status_short": "FT", "ft_home": 1, "ft_away": 0,
            "home_xg": 1.5, "away_xg": 1.1, **more}


class Classify(unittest.TestCase):
    def setUp(self):
        self.fixtures = [
            fx(1, "2024-08-01", 1, "a", "b"),        # a and b are in the top league
            fx(2, "2024-08-01", 2, "c", "d"),        # c and d in the second
            fx(3, "2024-08-10", 9, "c", "a"),        # cup: second v top
            fx(4, "2024-08-11", 9, "a", "b"),        # cup: same league
            fx(5, "2024-08-12", 9, "a", "z"),        # cup: z has no league
            fx(6, "2024-08-13", 9, "z", "c"),
            fx(7, "2024-08-14", 9, "y", "z"),        # cup: neither has one
            fx(8, "2024-08-15", 3, "e", "f"),
            fx(9, "2024-08-20", 9, "e", "a"),        # cup: e's league has no starting rank
            fx(10, "2026-01-01", 9, "c", "a"),       # both sides' league matches are over 400 days old
            fx(11, "2024-08-21", 1, "c", "a"),       # a league match is never changed
        ]
        self.kinds = run.classify(self.fixtures, LEAGUES)

    def test_cross_league_carries_the_gap_home_minus_away(self):
        self.assertEqual(self.kinds[3], ("cross", -200.0, 0))

    def test_same_league_and_league_matches_are_unchanged(self):
        self.assertIsNone(self.kinds[4][0])
        self.assertIsNone(self.kinds[1][0])
        self.assertIsNone(self.kinds[11][0])

    def test_one_sided_points_at_the_side_with_a_league(self):
        self.assertEqual(self.kinds[5], ("one_sided", 0.0, 1))
        self.assertEqual(self.kinds[6], ("one_sided", 0.0, -1))

    def test_neither_side_or_no_starting_rank_is_unchanged(self):
        self.assertIsNone(self.kinds[7][0])
        self.assertIsNone(self.kinds[9][0])

    def test_an_old_league_match_does_not_count(self):
        self.assertIsNone(self.kinds[10][0])

    def test_nothing_later_than_the_kickoff_is_used(self):
        # fixture 11 moves c into the top league, after the cup tie of 10 August
        self.assertEqual(self.kinds[3][0], "cross")
        early = run.classify([fx(20, "2024-07-01", 9, "c", "a")] + self.fixtures, LEAGUES)
        self.assertIsNone(early[20][0])

    def test_order_of_the_input_does_not_matter(self):
        shuffled = list(self.fixtures)
        random.Random(3).shuffle(shuffled)
        self.assertEqual(run.classify(shuffled, LEAGUES), self.kinds)


class Shift(unittest.TestCase):
    def test_shift_by_kind(self):
        self.assertAlmostEqual(run.shift({"kind": "cross", "gap": -200.0, "side": 0}, 0.1, 50), -0.2)
        self.assertAlmostEqual(run.shift({"kind": "one_sided", "gap": 0.0, "side": 1}, 0.1, 50), 0.5)
        self.assertAlmostEqual(run.shift({"kind": "one_sided", "gap": 0.0, "side": -1}, 0.1, 50), -0.5)
        self.assertEqual(run.shift({"kind": None, "gap": 0.0, "side": 0}, 0.1, 50), 0.0)

    def test_favoured_side(self):
        self.assertEqual(run.favoured({"kind": "cross", "gap": -200.0, "side": 0}), -1)
        self.assertEqual(run.favoured({"kind": "cross", "gap": 150.0, "side": 0}), 1)
        self.assertEqual(run.favoured({"kind": "one_sided", "gap": 0.0, "side": -1}), -1)
        self.assertEqual(run.favoured({"kind": None, "gap": 0.0, "side": 0}), 0)

    def test_moving_the_margin_is_what_project_returns(self):
        home, away = predictions.project(1.5, 1.2, 0.4)
        want = predictions.project(1.5, 1.2, 0.4 + 0.3)
        got = run.moved(home, away, 0.3)
        self.assertAlmostEqual(got[0], want[0])
        self.assertAlmostEqual(got[1], want[1])
        self.assertEqual(run.moved(home, away, 0.0), (home, away))


def _rows(n, start, seed):
    rnd = random.Random(seed)
    rows = []
    for i in range(n):
        kind = (None, "cross", "one_sided")[i % 3]
        rows.append({"fixture_id": seed * 1000 + i, "kickoff": f"{start[:8]}{1 + i % 28:02d}T15:00:00+00:00",
                     "league_id": 9 if kind else 1, "home_xg": 0.6 + 2 * rnd.random(), "away_xg": 0.5 + 1.5 * rnd.random(),
                     "ft_home": rnd.randrange(4), "ft_away": rnd.randrange(3), "kind": kind,
                     "gap": (200.0 if i % 2 else -200.0) if kind == "cross" else 0.0,
                     "side": (1 if i % 2 else -1) if kind == "one_sided" else 0})
    return rows


class Compare(unittest.TestCase):
    def test_zero_changes_nothing(self):
        r = run.compare(_rows(150, "2024-08-01", 1), 0, 0, ("cross", "one_sided"))
        self.assertEqual(r["difference"]["all"]["log_loss"], 0.0)
        self.assertEqual(r["difference"]["changed"]["log_loss"], 0.0)
        self.assertEqual(r["changed"]["baseline"]["n"], 100)
        self.assertEqual(r["all"]["baseline"]["n"], 150)

    def test_only_the_named_kinds_are_changed(self):
        rows = _rows(150, "2024-08-01", 2)
        r = run.compare(rows, 0.2, 100, ("cross",))
        self.assertEqual(r["changed"]["baseline"]["n"], 50)
        only_delta = run.compare(rows, 0, 100, ("cross",))
        self.assertEqual(only_delta["difference"]["changed"]["log_loss"], 0.0)

    def test_the_whole_difference_is_the_changed_matches_share(self):
        r = run.compare(_rows(150, "2024-08-01", 4), 0.2, 100, ("cross", "one_sided"))
        self.assertAlmostEqual(r["difference"]["all"]["log_loss"] * 150, r["difference"]["changed"]["log_loss"] * 100)

    def test_grid_and_pick(self):
        rows = _rows(90, "2023-09-01", 5)
        grid, n = run.grid_loss(rows, "cross", run.BETA_GRID, lambda v: {"beta": v, "delta": 0})
        self.assertEqual(n, 30)
        self.assertEqual(len(grid), len(run.BETA_GRID))
        self.assertIn(0.0, run.BETA_GRID)
        self.assertIn(0, run.DELTA_GRID)
        self.assertEqual(run.pick([{"value": -0.05, "log_loss": 1.0}, {"value": 0.0, "log_loss": 1.0},
                                   {"value": 0.05, "log_loss": 1.0}]), 0.0)


class Verdict(unittest.TestCase):
    def _test(self, changed, hi, everything=-0.0001, fall=0.5, fall_lo=0.1, no_worse=4):
        return {"difference": {"all": {"log_loss": everything, "brier": everything},
                               "changed": {"log_loss": changed, "brier": changed, "calibration_error": -0.001},
                               "ends_gap_fall": {"changed": fall}, "goal_markets": {"over25": 0.0}},
                "intervals": {"all": {"log_loss": [everything * 2, everything / 2]},
                              "changed": {"log_loss": [changed * 2, hi]}, "ends_gap_fall": {"changed": [fall_lo, 0.9]}},
                "by_season": {"2024/25": {"log_loss": -0.001}, "2025/26": {"log_loss": -0.001}},
                "competitions": {"n": 5, "no_worse": no_worse}}

    def _holdout(self, value, hi):
        return {"difference": {"changed": {"log_loss": value}}, "intervals": {"changed": {"log_loss": [value * 2, hi]}}}

    def test_labels(self):
        good = self._holdout(-0.004, -0.001)
        self.assertEqual(run.verdict(self._test(-0.01, -0.002), good)["label"], "meets B only")
        self.assertEqual(run.verdict(self._test(-0.03, -0.01, everything=-0.003), good)["label"], "meets A")
        self.assertEqual(run.verdict(self._test(-0.01, -0.002), self._holdout(-0.004, 0.001))["label"], "meets neither")
        self.assertEqual(run.verdict(self._test(-0.01, 0.001), good)["label"], "meets neither")
        self.assertEqual(run.verdict(self._test(-0.01, -0.002, fall_lo=-0.1), good)["label"], "meets neither")
        self.assertEqual(run.verdict(self._test(-0.01, -0.002, no_worse=2), good)["label"], "meets neither")


if __name__ == "__main__":
    unittest.main()

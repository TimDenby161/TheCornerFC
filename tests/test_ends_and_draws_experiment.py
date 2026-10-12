"""The ends-and-draws experiment (experiments/ends_and_draws/run.py) on made-up rows: no database."""
import importlib.util
import random
import unittest
from pathlib import Path

from thecornerfc.models import predictions

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("ends_and_draws", ROOT / "experiments/ends_and_draws/run.py")
run = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run)


def _rows(n, start="2023-07-01", seed=1):
    rnd = random.Random(seed)
    year, month = int(start[:4]), int(start[5:7])
    rows = []
    for i in range(n):
        rows.append({"fixture_id": seed * 100000 + i, "kickoff": f"{year}-{month:02d}-{1 + i % 28:02d}T15:00:00+00:00",
                     "league_id": 39 + i % 2, "home_xg": 0.4 + 2.4 * rnd.random(), "away_xg": 0.3 + 2.0 * rnd.random(),
                     "p_home": 0.4, "p_draw": 0.3, "p_away": 0.3, "source": "backfill",
                     "ft_home": rnd.randrange(4), "ft_away": rnd.randrange(3)})
    return rows


class ModelStep(unittest.TestCase):
    def test_the_copy_matches_production_at_production_values(self):
        for row in _rows(200):
            mine = run.finish(run.raw_outcomes(row["home_xg"], row["away_xg"]), row["home_xg"] - row["away_xg"],
                              predictions.DRAW_INFLATION, predictions.DRAW_FADE_MARGIN)
            theirs = predictions.outcome_probabilities(row["home_xg"], row["away_xg"])[:3]
            for a, b in zip(mine, theirs):
                self.assertAlmostEqual(a, b, places=12)

    def test_the_baseline_reads_productions_constants(self):
        self.assertEqual(run.BASELINE["inflation"], predictions.DRAW_INFLATION)
        self.assertEqual(run.BASELINE["fade"], predictions.DRAW_FADE_MARGIN)

    def test_no_stretch_leaves_the_goals_alone(self):
        self.assertEqual(run.restretch(1.7, 1.1, "quadratic", 0.0), (1.7, 1.1))
        self.assertEqual(run.restretch(1.7, 1.1, "linear", 1.0), (1.7, 1.1))
        self.assertEqual(run.restretch(1.7, 1.1, "power", 1.1), (1.7, 1.1))
        self.assertEqual(run.restretch(1.7, 1.1, None, None), (1.7, 1.1))

    def test_a_stretch_keeps_the_product_and_sets_the_margin(self):
        home, away = run.restretch(2.0, 0.8, "quadratic", 0.1)
        self.assertAlmostEqual(home - away, 1.2 * (1 + 0.1 * 1.2))
        self.assertAlmostEqual(home * away, 1.6)
        home, away = run.restretch(0.8, 2.0, "linear", 1.1)
        self.assertAlmostEqual(home - away, -1.32)
        self.assertAlmostEqual(home * away, 1.6)

    def test_a_stretch_is_what_project_returns_for_the_new_margin(self):
        base_home, base_away = 1.5, 1.2
        home, away = predictions.project(base_home, base_away, 0.9)
        want = predictions.project(base_home, base_away, 0.9 * (1 + 0.08 * 0.9))
        got = run.restretch(home, away, "quadratic", 0.08)
        self.assertAlmostEqual(got[0], want[0])
        self.assertAlmostEqual(got[1], want[1])

    def test_power_one_changes_nothing_and_a_higher_power_sharpens(self):
        p = (0.6, 0.25, 0.15)
        for a, b in zip(run.power(p, 1.0), p):
            self.assertAlmostEqual(a, b)
        sharp = run.power(p, 1.2)
        self.assertAlmostEqual(sum(sharp), 1.0)
        self.assertGreater(sharp[0], p[0])
        self.assertLess(sharp[2], p[2])

    def test_less_inflation_means_fewer_draws(self):
        raw = run.raw_outcomes(1.4, 1.3)
        self.assertLess(run.finish(raw, 0.1, 1.0, 1.5)[1], run.finish(raw, 0.1, 1.1, 1.5)[1])
        self.assertAlmostEqual(run.finish(raw, 0.1, 1.0, 1.5)[1], raw[1])


class Measures(unittest.TestCase):
    def test_stats_add_up(self):
        stats = [0.0] * run.N_STATS
        run.add_stats(stats, (0.75, 0.15, 0.10), 0, 1.6)
        run.add_stats(stats, (0.15, 0.25, 0.60), 1, -0.9)
        m = run.measures(stats)
        self.assertEqual(m["n"], 2)
        self.assertAlmostEqual(m["log_loss"], (run.log_loss(0.75) + run.log_loss(0.25)) / 2)
        self.assertAlmostEqual(m["accuracy"], 0.5)
        # ends: home 0.75 (won), home 0.15 (lost), away 0.10 (lost); away 0.60 is not an end
        self.assertAlmostEqual(m["ends_gap"], (0.25 + 0.15 + 0.10) / 3)
        # draws: one band each, 0.15 against 0 and 0.25 against 1
        self.assertAlmostEqual(m["draw_gap"], (0.15 + 0.75) / 2)

    def test_margin_bands(self):
        self.assertEqual([run.margin_band(d) for d in (0.0, -0.3, 0.7, -1.2, 2.0)], [0, 1, 2, 3, 4])

    def test_seasons_run_july_to_june(self):
        self.assertEqual(run.season({"kickoff": "2024-07-01T00:00:00+00:00"}), "2024/25")
        self.assertEqual(run.season({"kickoff": "2025-06-30T00:00:00+00:00"}), "2024/25")

    def test_periods_do_not_overlap(self):
        rows = [{"kickoff": d + "T12:00:00+00:00"} for d in
                ("2021-06-30", "2021-07-01", "2023-06-30", "2023-07-01", "2024-06-30", "2024-07-01", "2026-10-11", "2026-10-12")]
        split = run.periods(rows)
        self.assertEqual([len(split[k]) for k in ("holdout", "validation", "test")], [2, 2, 2])


class Selection(unittest.TestCase):
    def test_settings_are_chosen_on_the_rows_given_and_ties_go_to_production(self):
        rows = _rows(60)
        scorer = run.Scorer()
        best, grid = run.choose(rows, scorer, run.h2_specs())
        self.assertEqual(len(grid), len(run.INFLATION_GRID) * len(run.FADE_GRID))
        self.assertEqual(min(g["log_loss"] for g in grid), run.mean_log_loss(rows, scorer, best))
        # inflation 1.0 gives the same probabilities at every fade margin: the tie goes to 1.5
        flat = [s for s in run.h2_specs() if s["inflation"] == 1.0]
        self.assertEqual(run.choose(rows, scorer, flat)[0]["fade"], predictions.DRAW_FADE_MARGIN)

    def test_every_grid_holds_production(self):
        for form, (grid, neutral) in run.FORMS.items():
            self.assertIn(neutral, grid)
        self.assertIn(predictions.DRAW_INFLATION, run.INFLATION_GRID)
        self.assertIn(predictions.DRAW_FADE_MARGIN, run.FADE_GRID)

    def test_the_baseline_against_itself_changes_nothing(self):
        rows = _rows(120, "2024-08-01", seed=2)
        r = run.paired(rows, run.Scorer(), run.BASELINE, run.BASELINE)
        self.assertEqual(r["difference"]["log_loss"], 0.0)
        self.assertEqual(r["goal_markets"]["over25"], 0.0)
        self.assertEqual(r["baseline"]["n"], 120)


class Verdict(unittest.TestCase):
    def _result(self, log_loss, hi, fall, fall_lo, seasons=(-0.001, -0.001), goal=0.0, no_worse=8):
        return {"difference": {"log_loss": log_loss, "brier": log_loss / 2, "calibration_error": -0.001},
                "intervals": {"difference": {"log_loss": [log_loss * 2, hi]},
                              "gap_fall": {"ends_gap": [fall_lo, 0.9], "draw_gap": [fall_lo, 0.9]}},
                "gap_fall": {"ends_gap": fall, "draw_gap": fall},
                "by_season": {"2024/25": {"log_loss": seasons[0]}, "2025/26": {"log_loss": seasons[1]}},
                "goal_markets": {"over25": goal}, "competitions": {"n": 10, "no_worse": no_worse}}

    def test_labels(self):
        holdout = {"difference": {"log_loss": -0.0005}}
        self.assertEqual(run.verdict("h1", self._result(-0.0025, -0.001, 0.5, 0.2), holdout)["label"], "meets A")
        self.assertEqual(run.verdict("h1", self._result(-0.0007, -0.0002, 0.5, 0.2), holdout)["label"], "meets B only")
        self.assertEqual(run.verdict("h1", self._result(-0.0007, 0.0001, 0.5, 0.2), holdout)["label"], "meets neither")
        self.assertEqual(run.verdict("h1", self._result(-0.0007, -0.0002, 0.2, 0.1), holdout)["label"], "meets neither")
        self.assertEqual(run.verdict("h1", self._result(-0.0007, -0.0002, 0.5, 0.2, goal=0.001), holdout)["label"], "meets neither")
        self.assertEqual(run.verdict("h1", self._result(-0.0007, -0.0002, 0.5, 0.2, no_worse=5), holdout)["label"], "meets neither")
        self.assertEqual(run.verdict("h1", self._result(-0.0007, -0.0002, 0.5, 0.2),
                                     {"difference": {"log_loss": 0.0001}})["label"], "meets neither")


if __name__ == "__main__":
    unittest.main()

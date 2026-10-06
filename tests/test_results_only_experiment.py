import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "results_only_experiment", Path(__file__).resolve().parents[1] / "experiments/results_only/run.py")
experiment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(experiment)


def fixtures(xg):
    """Four clubs playing each other twice a week from August 2023: (fixture, kickoff, league,
    type, home, away, home goals, away goals, country, home xG, away xG)."""
    start = datetime(2023, 8, 1, tzinfo=timezone.utc)
    pairs = [(1, 2), (3, 4), (2, 3), (4, 1), (1, 3), (2, 4)]
    out = []
    for i in range(60):
        home, away = pairs[i % len(pairs)]
        hg, ag = (i * 7 + 1) % 4, (i * 5 + 1) % 3
        out.append((i + 1, start + timedelta(days=3 * i), 39, "League", home, away, hg, ag, "England",
                    hg + 0.4 if xg else None, ag - 0.2 if xg and ag else (0.3 if xg else None)))
    return out


def data(xg=False, lines=None, missing=None):
    return {"fixtures": fixtures(xg), "levels": {39: 900.0}, "leagues": {39: ("Premier League", "England", "League")},
            "lines": lines or {}, "missing": missing or {}, "teams": {}}


RESULTS_ONLY = dict(xg=False, lineups=False, injuries=False)


class ResultsOnlyExperimentTests(unittest.TestCase):
    def test_same_as_the_full_model_when_only_results_exist(self):
        full, ranks, _ = experiment.replay(data())
        bare, bare_ranks, _ = experiment.replay(data(), **RESULTS_ONLY)
        self.assertEqual(full, bare)
        self.assertEqual(ranks, bare_ranks)
        self.assertEqual(len(full), 60)

    def test_results_only_ignores_xg_lineups_and_injuries(self):
        lines = {(f, t): [70.0, 60.0 + t, 65.0, 55.0 + f % 5] for f in range(1, 61) for t in (1, 2, 3, 4)}
        missing = {(f, 1): 0.8 for f in range(1, 61)}
        rich = data(xg=True, lines=lines, missing=missing)
        bare, bare_ranks, _ = experiment.replay(data(), **RESULTS_ONLY)
        stripped, stripped_ranks, _ = experiment.replay(rich, **RESULTS_ONLY)
        self.assertEqual(bare, stripped)
        self.assertEqual(bare_ranks, stripped_ranks)
        full, full_ranks, _ = experiment.replay(rich)
        self.assertNotEqual(full, bare)
        self.assertNotEqual(full_ranks, bare_ranks)

    def test_another_k_is_put_back_afterwards(self):
        was = experiment.ranking.K_FACTOR
        _, ranks, _ = experiment.replay(data(), **RESULTS_ONLY, k=10)
        self.assertEqual(experiment.ranking.K_FACTOR, was)
        self.assertNotEqual(ranks, experiment.replay(data(), **RESULTS_ONLY)[1])

    def test_score_of_a_certain_right_call(self):
        f = (1, datetime(2025, 1, 1, tzinfo=timezone.utc), 39, "League", 1, 2, 2, 0, "England", None, None)
        s = experiment.score((0.7, 0.2, 0.1, 2.0, 0.0, 0.4), f)
        self.assertAlmostEqual(s["brier"], 0.09 + 0.04 + 0.01)
        self.assertEqual((s["hit"], s["goals_se"], s["margin_ae"]), (1, 0.0, 0.0))


if __name__ == "__main__":
    unittest.main()

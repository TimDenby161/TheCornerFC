"""A18 beside the base match model (thecornerfc/models/match_trees.py, MC-0029).

Before release the whole port was run on every fixture of the research inputs beside the research
code it copies (research_frame/features.py, architectures/run.py, experiments/a18_on_release):
largest gaps 2e-14 in the reprojected goals, 0 in the Poisson rates, 5e-12 in the features, 1e-13
in the trees' corrections and A18's goals, and every missing value in the same place. The inputs
are feed data and not in git, so these pin the parts that can be checked small."""
import math
import unittest
from datetime import date

from thecornerfc.models import match_trees as mt

try:
    import numpy as np
    import scipy  # noqa: F401
    NUMERIC = True
except ImportError:
    NUMERIC = False


class Conn:
    """Answers the switch questions; anything else is a mistake."""
    def __init__(self, switch_exists, live='base'):
        self.switch_exists, self.live = switch_exists, live

    def execute(self, sql, *args):
        if 'to_regclass' in sql:
            return Rows([('public.match_model_switch' if self.switch_exists else None,)])
        if 'from match_model_switch' in sql:
            return Rows([(self.live,)])
        raise AssertionError(sql)


class Rows:
    def __init__(self, rows): self.rows = rows
    def fetchone(self): return self.rows[0]
    def fetchall(self): return self.rows


class PlainTest(unittest.TestCase):
    def test_half_seasons(self):
        self.assertEqual(mt.half_seasons('2024-07-01', '2026-01-15'), ['2024-07-01', '2025-01-01', '2025-07-01', '2026-01-01'])
        self.assertEqual(mt.half_seasons('2021-07-01', '2026-10-14')[-1], '2026-07-01')

    def test_the_switch_before_and_after_the_migration(self):
        self.assertIsNone(mt.live_model(Conn(False)))
        self.assertEqual(mt.live_model(Conn(True, 'a18')), 'a18')

    def test_nothing_runs_before_the_migration(self):
        mt.update(Conn(False))          # reads the switch, finds none, and stops

    def test_a_failure_leaves_the_base_model_live(self):
        class Broken(Conn):
            rolled = False
            def rollback(self): self.rolled = True
        conn = Broken(True)
        mt.update_safely(conn)          # the next question is not one Conn answers: it raises inside
        self.assertTrue(conn.rolled)

    def test_the_recipe_is_the_one_fixed(self):
        self.assertEqual(len(mt.FEATURES), 44)
        self.assertEqual(len(set(mt.FEATURES)), 44)
        self.assertEqual(mt.TREES['max_depth'], 3)
        self.assertEqual(mt.TREES['max_iter'], 300)
        self.assertEqual(mt.POISSON, {'half_life': 250.0, 'ridge_team': 10.0, 'use_xg': 1})


def matches(rows, stored=None, ranks=None):
    leagues = {1: ('England', 'League', 1000.0), 2: ('England', 'League', 800.0), 9: ('England', 'Cup', None)}
    return mt.Matches(rows, leagues, {}, stored or {}, ranks or {})


def row(fid, day, home, away, hg=None, ag=None, league=1, status='FT'):
    return (fid, f'{day}T15:00:00+00:00', league, home, away, status, hg, ag, hg, ag,
            None, None, None, None, None, None, None, None)


@unittest.skipUnless(NUMERIC, 'needs numpy and scipy')
class NumericTest(unittest.TestCase):
    def test_moving_the_margin_keeps_the_product(self):
        h, a = mt.moved(np.array([1.6]), np.array([1.1]), np.array([0.3]))
        self.assertAlmostEqual(float(h[0] - a[0]), 0.8)
        self.assertAlmostEqual(float(h[0] * a[0]), 1.76)

    def test_the_total_is_scaled_within_its_limits(self):
        h, a = mt.corrected(np.array([1.5]), np.array([1.0]), np.array([0.0]), np.array([10.0]))
        self.assertAlmostEqual(float(h[0] + a[0]), 2.5 * 1.4)
        h, a = mt.corrected(np.array([1.5]), np.array([1.0]), np.array([0.0]), np.array([0.25]))
        self.assertAlmostEqual(float(h[0] + a[0]), 2.75)

    def test_features_use_only_earlier_matches(self):
        rows = [row(1, '2025-08-01', 10, 20, 2, 0), row(2, '2025-08-08', 10, 30, 1, 1),
                row(3, '2025-08-15', 20, 10, 0, 3), row(4, '2025-08-20', 10, 20, status='NS')]
        stored = {f: (1000.0, 1000.0, 1.4, 1.1, 0.45, 0.0, 0.0) for f in (1, 2, 3, 4)}
        m = matches(rows, stored)
        f = mt.features(m, np.full(4, 1.4), np.full(4, 1.1))
        self.assertEqual(f['h_rest'][3], 5.0)                # club 10 last played on the 15th
        self.assertEqual(f['h_last14'][3], 2.0)              # the 8th and the 15th
        self.assertTrue(math.isnan(f['h_rest'][0]))          # nothing before its first match
        # club 10's residual margins: +1.7, -0.3, +3.3 (it was away on the 15th, so its side of -3.3)
        self.assertAlmostEqual(f['h_res5'][3], (1.7 - 0.3 + 3.3) / 3)
        self.assertTrue(math.isnan(f['h_res5'][2]))          # fewer than 3 matches: no mean

    def test_the_poisson_model_gives_rates_for_a_coming_fixture(self):
        rows, fid, day = [], 1, date(2021, 7, 5).toordinal()
        for week in range(40):
            for home, away, hg, ag in ((10, 20, 2, 1), (30, 40, 0, 0), (20, 30, 1, 2), (40, 10, 1, 3)):
                rows.append(row(fid, date.fromordinal(day + 7 * week).isoformat(), home, away, hg, ag))
                fid += 1
        rows.append(row(fid, date.fromordinal(day + 7 * 40).isoformat(), 10, 40, status='NS'))
        m = matches(rows)
        lam, mu = mt.Poisson(m, **mt.POISSON).run(mt.FIRST_DAY, date.fromordinal(day + 7 * 41).isoformat(),
                                                    today=date.fromordinal(day + 7 * 40 - 1).isoformat())
        self.assertTrue(np.isfinite(lam[-1]) and np.isfinite(mu[-1]))
        self.assertGreater(lam[-1], mu[-1])                  # club 10 scores more and concedes less than 40


if __name__ == '__main__':
    unittest.main()

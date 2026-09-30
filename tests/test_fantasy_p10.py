"""P10's evaluator (experiments/prospective/fantasy_p10.py) on synthetic snapshots: no database."""
from datetime import timedelta
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('fantasy_p10', ROOT / 'experiments/prospective/fantasy_p10.py')
p10 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p10)
import test_fantasy_p9 as t9


class P10Tests(unittest.TestCase):
    def data(self):
        snaps = [t9.snap(p10.OLD, [t9.pred(7, 'D', 4.0, dc=0.4), t9.pred(8, 'G', 3.5)]),
                 t9.snap(p10.NEW, [dict(t9.pred(7, 'D', 4.4, dc=1.2), fpl_dc_minutes=450), dict(t9.pred(8, 'G', 3.5), fpl_dc_minutes=0)])]
        _, lines, rounds, fpl = t9.P9Tests().data()
        fpl[2026]['positions'] = {101: 'DEF', 102: 'GKP'}
        return snaps, lines, rounds, fpl

    def test_dc_brier_for_fpl_defenders_and_midfielders(self):
        rows = p10.build(self.data())
        self.assertEqual({r['fpl_position'] for r in rows}, {'D', 'G'})
        res = p10.analyse(rows)
        # he reached FPL's threshold: P(DC) 0.6 beats 0.2
        self.assertAlmostEqual(res['dc_brier']['diff'], (0.6 - 1) ** 2 - (0.2 - 1) ** 2)
        self.assertEqual(res['dc_brier']['n'], 1)                       # the keeper isn't in it
        self.assertEqual(res['dc_by_record'][0]['minutes'], '270-540')
        self.assertTrue(res['criteria']['supported'])
        self.assertEqual((p10.TARGET_ROUNDS, p10.TARGET_ROWS, p10.MAE_MARGIN), (10, 3000, 0.02))


if __name__ == '__main__':
    unittest.main()

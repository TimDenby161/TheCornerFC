"""P11's evaluator (experiments/prospective/fantasy_p11.py) on synthetic snapshots: no database."""
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('fantasy_p11', ROOT / 'experiments/prospective/fantasy_p11.py')
p11 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p11)

KICKOFF = datetime(2026, 10, 10, 14, tzinfo=timezone.utc)


def pred(pid, position, goals, assists, pen=0.0, miss=0.0, fpl=0.0, xp=4.0):
    p = {'player_id': pid, 'position': position, 'exp_goals': goals, 'exp_assists': assists, 'expected_points': xp}
    if pen or miss or fpl:
        p.update(exp_pen_goals=pen, exp_pen_misses=miss, exp_fpl_pen_assists=0.0, exp_fpl_other_assists=fpl)
    return p


def snap(fid, team, version, preds, captured=KICKOFF - timedelta(hours=3)):
    return (fid, team, captured, captured, KICKOFF, preds, version, 2026, 'Regular Season - 7', 10, 20)


def fpl(results, fixtures=None):
    return {2026: {'fixtures': fixtures or [{'event_id': 7, 'fpl_team_h': 1, 'fpl_team_a': 2}],
                   'teams': {1: 10, 2: 20}, 'players': {101: 7, 102: 8}, 'positions': {101: 'MID', 102: 'FWD'},
                   'results': results}}


class P11Tests(unittest.TestCase):
    def data(self, fixtures=None, late=False):
        old = [pred(7, 'M', 0.4, 0.2), pred(8, 'F', 0.3, 0.1)]
        new = [pred(7, 'M', 0.45, 0.2, pen=0.08, miss=0.02, fpl=0.05), pred(8, 'F', 0.25, 0.1, pen=0.0, fpl=0.03)]
        captured = KICKOFF + timedelta(minutes=5) if late else KICKOFF - timedelta(hours=3)
        snaps = [snap(1, 10, p11.OLD, old), snap(1, 10, p11.NEW, new, captured)]
        results = [(7, 101, 90, {'goals_scored': 1, 'assists': 1, 'penalties_missed': 0, 'total_points': 11}),
                   (7, 102, 90, {'goals_scored': 0, 'assists': 0, 'penalties_missed': 1, 'total_points': 0})]
        return snaps, [(2026, 'Regular Season - 7', KICKOFF)], [(1, 10, 7, 2)], fpl(results, fixtures)

    def test_rows_pair_versions_and_score_fpl_attacking_points_at_fpl_positions(self):
        rows, takers = p11.build(*self.data())
        self.assertEqual(len(rows), 2)
        mid = next(r for r in rows if r['share'] > 0.5)
        self.assertEqual(mid['actual'], 5 + 3)                                   # FPL's MID: 5 a goal
        self.assertAlmostEqual(mid['old'], 5 * 0.4 + 3 * 0.2)
        self.assertAlmostEqual(mid['new'], 5 * 0.45 + 3 * 0.25 - 2 * 0.02)
        fwd = next(r for r in rows if r['share'] == 0)
        self.assertEqual(fwd['actual'], -2)                                      # a penalty miss
        self.assertEqual(takers[0]['took'], {7: 2})
        self.assertEqual(p11.taker_log_loss(takers, 'new')['log_loss'], 0.0)     # all of the club's penalty goals were his

    def test_double_gameweeks_late_snapshots_and_unpaired_versions_are_left_out(self):
        double = [{'event_id': 7, 'fpl_team_h': 1, 'fpl_team_a': 2}, {'event_id': 7, 'fpl_team_h': 1, 'fpl_team_a': 2}]
        self.assertEqual(p11.build(*self.data(fixtures=double))[0], [])
        self.assertEqual(p11.build(*self.data(late=True))[0], [])

    def test_blinded_constants_match_the_protocol(self):
        text = (ROOT / 'experiments/prospective/PROTOCOLS.md').read_text()
        self.assertIn('| P11 |', text)
        self.assertEqual((p11.TARGET_ROUNDS, p11.TARGET_ROWS, p11.OLD, p11.NEW), (10, 3000, 'fantasy-v1.4', 'fantasy-v1.5'))
        self.assertEqual(p11.MAE_MARGIN, 0.02)


if __name__ == '__main__':
    unittest.main()

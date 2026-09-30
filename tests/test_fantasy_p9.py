"""P9's evaluator (experiments/prospective/fantasy_p9.py) on synthetic snapshots: no database."""
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('fantasy_p9', ROOT / 'experiments/prospective/fantasy_p9.py')
p9 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p9)

KICKOFF = datetime(2026, 10, 10, 14, tzinfo=timezone.utc)


def pred(pid, position, xp, bonus=0.0, dc=0.0, p_start=0.9):
    return {'player_id': pid, 'position': position, 'expected_points': xp, 'bonus_points': bonus, 'dc_points': dc,
            'p_start': p_start}


def snap(version, preds, captured=KICKOFF - timedelta(hours=3)):
    # fixture, team, captured, created, kickoff, predictions, version, season, round, home, away, home goals, away goals
    return (1, 10, captured, captured, KICKOFF, preds, version, 2026, 'Regular Season - 7', 10, 20, 2, 0)


def explain(**points):
    return [{'fixture': 1, 'stats': [{'identifier': k, 'points': v, 'value': 1} for k, v in points.items()]}]


class P9Tests(unittest.TestCase):
    def data(self, fixtures=None):
        snaps = [snap(p9.OLD, [pred(7, 'D', 4.0), pred(8, 'G', 3.5)]),
                 snap(p9.NEW, [pred(7, 'D', 5.0, bonus=0.4, dc=0.6), pred(8, 'G', 3.8, bonus=0.2)])]
        lines = [(1, 10, 7, 90, True, 1, 0, 0, 0, 0, 0), (1, 10, 8, 90, True, 0, 0, 4, 0, 0, 0)]
        fpl = {2026: {'fixtures': fixtures or [{'event_id': 7, 'fpl_team_h': 1, 'fpl_team_a': 2}],
                      'teams': {1: 10, 2: 20}, 'players': {101: 7, 102: 8},
                      'results': [(7, 101, explain(minutes=2, bonus=3, defensive_contribution=2)),
                                  (7, 102, explain(minutes=2, saves=1))]}}
        return snaps, lines, [(2026, 'Regular Season - 7', KICKOFF)], fpl

    def test_target_is_reconstructed_total_plus_fpl_bonus_and_dc(self):
        rows = {r['position']: r for r in p9.build(*self.data())}
        # defender: 2 appearance + 6 goal + 4 clean sheet, then FPL's 3 bonus and 2 DC
        self.assertEqual(rows['D']['actual'], 2 + 6 + 4 + 3 + 2)
        self.assertEqual((rows['D']['new'], rows['D']['old']), (5.0, 4.0))
        self.assertEqual(rows['G']['actual'], 2 + 4 + 1)                      # 4 saves = 1 point, no FPL extras
        res = p9.analyse(list(rows.values()))
        self.assertLess(res['mae']['diff'], 0)
        self.assertEqual(res['bonus_dc_by_position']['D']['bonus_fpl'], 3)

    def test_double_gameweeks_are_left_out_and_constants_match_the_protocol(self):
        double = [{'event_id': 7, 'fpl_team_h': 1, 'fpl_team_a': 2}] * 2
        self.assertEqual(p9.build(*self.data(fixtures=double)), [])
        self.assertEqual((p9.TARGET_ROUNDS, p9.TARGET_ROWS, p9.OLD, p9.NEW), (10, 3000, 'fantasy-v1.1', 'fantasy-v1.3'))


if __name__ == '__main__':
    unittest.main()

from datetime import date, datetime, timezone
import json
import math
from pathlib import Path
import tempfile
import unittest

from thecornerfc import efl_fantasy as ef


def comps(**kw):
    """A starter who always plays 90: the only randomness is in the counts."""
    base = dict(p_start=1.0, p_play=1.0, p60=1.0, exp_minutes=90.0, start_minutes=90.0, sub_minutes=20.0,
                exp_goals=0.0, exp_assists=0.0, exp_pen_misses=0.0, lambda_against=1.0, save_mean=3.0,
                penalty_save_points=0.0, yellow90=0.0, red90=0.0)
    return dict(base, **kw)


RATES = dict(tackles=0.0, blocks=0.0, interceptions=0.0, key_passes=0.0, shots_on=0.0, clearances=0.0)


class EflScoringTests(unittest.TestCase):
    def test_goals_score_by_position(self):
        for pos, pts in (('G', 10), ('D', 7), ('M', 6), ('F', 5)):
            self.assertAlmostEqual(ef.player_points(pos, comps(exp_goals=1.0), RATES)['goal'], pts)

    def test_clean_sheet_and_conceded_only_for_goalkeepers_and_defenders(self):
        for pos in 'GD':
            p = ef.player_points(pos, comps(lambda_against=0.0), RATES)
            self.assertAlmostEqual(p['clean_sheet'], 5)
            self.assertEqual(p['goals_conceded'], 0)
        for pos in 'MF':
            p = ef.player_points(pos, comps(lambda_against=0.0), RATES)
            self.assertEqual((p['clean_sheet'], p['goals_conceded']), (0, 0))

    def test_actions_count_only_for_their_positions(self):
        rates = dict(RATES, interceptions=1.5, shots_on=2.0, tackles=4.0)
        m = ef.player_points('M', comps(), rates)
        self.assertAlmostEqual(m['interception'], 3.0)          # 2 an interception
        self.assertAlmostEqual(m['shot_on_target'], 2.0)        # 1 a shot on target
        self.assertEqual(m['tackle'], 0)
        d = ef.player_points('D', comps(), rates)
        self.assertEqual((d['interception'], d['shot_on_target']), (0, 0))
        self.assertGreater(d['tackle'], 0)
        self.assertLess(d['tackle'], 2.0)                       # E[floor(X / 2)] < E[X] / 2

    def test_saves_are_two_points_per_three(self):
        g = ef.player_points('G', comps(save_mean=60.0), RATES)
        self.assertAlmostEqual(g['save'], 2 * (60 / 3), delta=0.8)
        self.assertEqual(ef.player_points('D', comps(save_mean=60.0), RATES)['save'], 0)

    def test_hat_trick_uses_goals_when_he_plays(self):
        p = ef.player_points('F', comps(exp_goals=1.0), RATES)
        tail = 1 - sum(math.exp(-1) / math.factorial(k) for k in range(3))
        self.assertAlmostEqual(p['hat_trick'], 5 * tail)

    def test_club_points(self):
        home = ef.club_points(2.0, 0.0, 1.0, 0.0, True)
        self.assertEqual((home['win'], home['away_win'], home['clean_sheet']), (5, 0, 2))
        away = ef.club_points(2.0, 0.0, 1.0, 0.0, False)
        self.assertEqual(away['away_win'], 2)
        draw = ef.club_points(0.0, 5.0, 0.0, 1.0, True)
        self.assertEqual((draw['draw'], draw['goals_2'], draw['goals_4']), (3, 0, 0))


class EflInputTests(unittest.TestCase):
    def test_gameweeks_run_thursday_to_wednesday_uk_time(self):
        thu = date(2026, 10, 1)
        self.assertEqual(ef.gameweek_start(datetime(2026, 10, 1, 19, 0, tzinfo=timezone.utc)), thu)
        self.assertEqual(ef.gameweek_start(datetime(2026, 10, 7, 21, 0, tzinfo=timezone.utc)), thu)   # Wednesday night
        self.assertEqual(ef.gameweek_start(datetime(2026, 10, 7, 23, 30, tzinfo=timezone.utc)), date(2026, 10, 8))  # after midnight BST

    def test_position_overrides(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'p.json'
            path.write_text(json.dumps({'_note': 'x', '123': 'd', '456': 'Z'}))
            self.assertEqual(ef.position_overrides(path), {123: 'D'})
            self.assertEqual(ef.position_overrides(Path(tmp) / 'missing.json'), {})

    def test_action_rates_shrink_toward_role_group(self):
        now = datetime(2026, 9, 30, tzinfo=timezone.utc)
        k = datetime(2026, 9, 1, tzinfo=timezone.utc)
        def line(pid, minutes, tackles, role):
            return (1, k, 2026, 10, 10, 0, 0, pid, minutes, True, 'D', role, 0, 0, 0, 0, 0, 0, 0, 0, tackles, 0, 0)
        rates, priors = ef.action_rates([line(1, 900, 30, 'CB'), line(2, 90, 0, 'CB')], now)
        self.assertAlmostEqual(priors['CB']['tackles'], 90 * 30 / 990)
        self.assertEqual(rates[1]['group'], 'CB')
        self.assertEqual(rates[1]['clearances'], ef.CLEARANCES_PER_90['CB'])
        self.assertGreater(rates[2]['tackles'], 0)                     # pulled up from his 0
        self.assertLess(rates[2]['tackles'], priors['CB']['tackles'])


if __name__ == '__main__':
    unittest.main()

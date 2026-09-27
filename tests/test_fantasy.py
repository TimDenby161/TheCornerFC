import math
import unittest

from thecornerfc import fantasy as fm
from thecornerfc.predictions import _pmf


def poisson(lam, x):
    return math.exp(-lam) * lam ** x / math.factorial(x)


class ScoringTests(unittest.TestCase):
    def test_actual_points_follow_fpl_rules_by_position(self):
        d = fm.actual_points('D', 90, goals=1, assists=1, team_conceded=0)
        self.assertEqual((d['appearance_points'], d['goal_points'], d['assist_points'], d['clean_sheet_points']), (2, 6, 3, 4))
        self.assertEqual(d['v1'], 15)
        m = fm.actual_points('M', 90, goals=1, team_conceded=0)
        self.assertEqual((m['goal_points'], m['clean_sheet_points'], m['goals_conceded_points']), (5, 1, 0))
        self.assertEqual(fm.actual_points('F', 90, goals=2, team_conceded=0)['v1'], 2 + 8)
        g = fm.actual_points('G', 90, team_conceded=5, saves=7, penalties_saved=1, yellow=1)
        self.assertEqual((g['goals_conceded_points'], g['save_points'], g['clean_sheet_points']), (-2, 2, 0))
        self.assertEqual(g['total'], g['v1'] + 5 - 1)

    def test_clean_sheet_and_conceded_need_sixty_minutes(self):
        sub = fm.actual_points('D', 59, team_conceded=0)
        self.assertEqual((sub['appearance_points'], sub['clean_sheet_points']), (1, 0))
        self.assertEqual(fm.actual_points('D', 30, team_conceded=4)['goals_conceded_points'], 0)
        self.assertEqual(fm.actual_points('D', 0, team_conceded=0)['v1'], 0)


class ProbabilityTests(unittest.TestCase):
    def test_floor_div_mean_matches_direct_sum(self):
        for lam in (0.0, 0.4, 1.3, 3.1, 6.0):
            for k in (2, 3):
                direct = sum((x // k) * poisson(lam, x) for x in range(80))
                self.assertAlmostEqual(fm.floor_div_mean(lam, k), direct, places=10)

    def test_clean_sheet_is_the_match_models_poisson_zero(self):
        mins = fm.minutes_expectation(1.0, 0.0, 90, 1.0, 20, 0.0)
        comps = fm.expected_points('D', mins, 0.1, 0.1, 1.2)
        self.assertAlmostEqual(comps['team_p_clean_sheet'], _pmf(1.2)[0])
        self.assertAlmostEqual(comps['clean_sheet_points'], 4 * _pmf(1.2)[0])

    def test_allocation_adds_up_to_the_team_expectation(self):
        shares = fm.allocate(1.7, [0.2, 0.0, 0.5, 0.3])
        self.assertAlmostEqual(sum(shares), 1.7)
        self.assertEqual(shares[1], 0.0)
        self.assertEqual(fm.allocate(1.7, [0.0, 0.0]), [0.0, 0.0])

    def test_attacking_rate_shrinks_toward_prior_with_little_evidence(self):
        self.assertAlmostEqual(fm.attacking_rate(0, 0, 0.12, 5.0), 0.12)
        self.assertAlmostEqual(fm.attacking_rate(10, 20, 0.12, 1e-9), 0.5, places=6)


class MinutesTests(unittest.TestCase):
    def test_features_weight_recent_matches_and_gap(self):
        s, b = fm.minutes_features([(1, 0), (0, 1), (1, 0)], gap=0, decay=0.5)
        self.assertEqual(s[0], 1.0)
        self.assertAlmostEqual(s[1], (1 + 0.25) / 1.75)
        self.assertEqual((s[2], s[3], s[4]), (1.0, 0.0, 0.0))
        self.assertAlmostEqual(b[1], 0.5 / 1.75)
        self.assertEqual(b[3], 0.0)
        s, b = fm.minutes_features([], gap=4, decay=0.7)
        self.assertEqual(s[1:4], [0.0, 0.0, 0.0])
        self.assertAlmostEqual(s[4], math.log(5))

    def test_minutes_expectation_combines_start_and_bench(self):
        m = fm.minutes_expectation(0.5, 0.4, 84, 0.9, 20, 0.05)
        self.assertAlmostEqual(m['p_play'], 0.7)
        self.assertAlmostEqual(m['exp_minutes'], 0.5 * 84 + 0.2 * 20)
        self.assertAlmostEqual(m['p60'], 0.45 + 0.01)

    def test_expected_points_is_the_sum_of_stored_components(self):
        mins = fm.minutes_expectation(0.8, 0.5, 85, 0.9, 20, 0.0)
        for pos in 'GDMF':
            c = fm.expected_points(pos, mins, 0.2, 0.1, 1.4, save_mean=3.0)
            self.assertAlmostEqual(c['expected_points'], sum(c[k] for k in fm.COMPONENT_POINTS))
            self.assertEqual(c['save_points'] > 0, pos == 'G')
            self.assertEqual(c['goals_conceded_points'] < 0, pos in 'GD')
        self.assertEqual(fm.expected_points('G', mins, 0, 0, 1.4)['save_points'], 0.0)


class SnapshotTests(unittest.TestCase):
    ROWS = [{'player_id': 9, 'fixture_id': 2, 'team_id': 1, 'expected_points': 3.1, 'p_start': 0.9},
            {'player_id': 4, 'fixture_id': 2, 'team_id': 1, 'expected_points': 1.0, 'p_start': 0.2}]

    def test_snapshot_hash_ignores_capture_time_and_row_order(self):
        a = fm.snapshot_record(season=2025, round_name='R1', version_id='mv_x', source='reconstruction',
                               captured_at='t1', rows=self.ROWS, inputs={})
        b = fm.snapshot_record(season=2025, round_name='R1', version_id='mv_x', source='reconstruction',
                               captured_at='t2', rows=self.ROWS[::-1], inputs={})
        self.assertEqual(a['content_hash'], b['content_hash'])
        c = fm.snapshot_record(season=2025, round_name='R1', version_id='mv_x', source='reconstruction',
                               captured_at='t1', rows=[dict(self.ROWS[0], expected_points=3.2)], inputs={})
        self.assertNotEqual(a['content_hash'], c['content_hash'])

    def test_fpl_predictions_sum_double_gameweeks_and_skip_unmapped(self):
        rows = [dict(self.ROWS[0]), dict(self.ROWS[0], fixture_id=3, p_start=0.5), dict(self.ROWS[1])]
        out = fm.fpl_predictions(rows, {9: 101})
        self.assertEqual(len(out), 1)
        self.assertEqual((out[0]['fpl_player_id'], out[0]['fixtures'], out[0]['p_start']), (101, 2, 0.9))
        self.assertAlmostEqual(out[0]['expected_points'], 6.2)


if __name__ == '__main__':
    unittest.main()

from datetime import timedelta
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


class V12Tests(unittest.TestCase):
    def test_bps_splits_events_from_general_play(self):
        b = fm.bps('D', 90, goals=1, team_conceded=0, key_passes=2, tackles=1, blocks=1, interceptions=2,
                   passes=40, passes_accurate=36, shots=3, shots_on=1, fouls=1, yellow=1)
        self.assertEqual(b['base'], 2 + 2 + 1 + 6 - 2 - 1)     # 36 of 40 passes is 90%
        self.assertEqual(b['bps'], 6 + 12 + 12 - 3 + b['base'])
        self.assertEqual(fm.bps('G', 90, saves=4, team_conceded=1)['bps'], 6 + 8)
        self.assertEqual(fm.bps('M', 90, passes=29, passes_accurate=29)['base'], 0)    # under 30 passes
        self.assertEqual(fm.bps('F', 0, goals=1), {'bps': 0, 'base': 0})

    def test_match_bonus_follows_fpl_tie_rules(self):
        self.assertEqual(fm.match_bonus({1: 30, 2: 25, 3: 20, 4: 10}), {1: 3, 2: 2, 3: 1, 4: 0})
        self.assertEqual(fm.match_bonus({1: 30, 2: 30, 3: 20, 4: 10}), {1: 3, 2: 3, 3: 1, 4: 0})
        self.assertEqual(fm.match_bonus({1: 30, 2: 25, 3: 25, 4: 10}), {1: 3, 2: 2, 3: 2, 4: 0})
        self.assertEqual(fm.match_bonus({1: 30, 2: 25, 3: 20, 4: 20}), {1: 3, 2: 2, 3: 1, 4: 1})

    def test_save_multiplier_shrinks_toward_one(self):
        self.assertEqual(fm.save_multiplier([], 1.0, 1.0, 10), 1.0)
        self.assertEqual(fm.save_multiplier([(9, None)], 1.0, 1.0, 10), 1.0)
        m = fm.save_multiplier([(6, 1.0)] * 10, 1.0, 1.0, 10)      # saves at three times the expected 2
        self.assertAlmostEqual(m, (60 + 20) / (20 + 20))

    def test_extras_add_to_expected_points_and_v1_1_params_add_none(self):
        mins = fm.minutes_expectation(0.9, 0.5, 88, 0.98, 20, 0.0)
        extras = {'yellow90': 0.1, 'red90': 0.01, 'base_bps90': 5.0, 'penalty_saves': 0.03,
                  'bonus_beta': {p: [0.1] * 7 for p in 'GDMF'}, 'start_minutes': 88, 'sub_minutes': 20}
        c = fm.expected_points('G', mins, 0.0, 0.0, 1.2, save_mean=3.0, extras=extras)
        self.assertAlmostEqual(c['expected_points'], sum(c[k] for k in fm.COMPONENT_POINTS + fm.EXTRA_POINTS))
        self.assertAlmostEqual(c['bonus_points'], 0.1 * sum(fm.bonus_features('G', c)))
        self.assertLess(c['card_points'], 0)
        self.assertIsNone(fm.player_extras({'K': 450}))
        # rescoring from a stored prediction reuses its own rates
        again = fm.player_extras({'bonus_beta': extras['bonus_beta'], 'penalty_saves_per_team_match': 0.03}, stored=c)
        self.assertEqual((again['yellow90'], again['base_bps90']), (0.1, 5.0))
        self.assertEqual(c['dc_points'], 0.0)          # v1.2: no defensive contributions

    def test_nb_tail_matches_direct_sum_and_poisson_limit(self):
        from math import exp, lgamma, log
        pmf = lambda x, m, r: exp(lgamma(x + r) - lgamma(r) - lgamma(x + 1) + r * log(r / (r + m)) + x * log(m / (r + m)))
        for m, r, t in ((6.0, 8.0, 10), (3.5, 2.0, 12), (0.4, 50.0, 1)):
            self.assertAlmostEqual(fm.nb_tail(t, m, r), 1 - sum(pmf(x, m, r) for x in range(t)), places=10)
        self.assertAlmostEqual(fm.nb_tail(2, 1.5, 1e7), 1 - exp(-1.5) * 2.5, places=5)
        self.assertEqual(fm.nb_tail(10, 0.0, 5.0), 0.0)

    def test_dc_points_weight_starter_and_sub_chances(self):
        dc = {'thresholds': {'D': 10}, 'points': 2, 'D': {'c': 3.0, 'k': 1.5, 'r': 8.0}}
        comps = {'p_start': 0.8, 'p_play': 0.9, 'start_minutes': 88, 'sub_minutes': 20, 'cbit90': 4.0}
        per90 = 3.0 + 1.5 * 4.0
        want = 0.8 * fm.nb_tail(10, 88 / 90 * per90, 8.0) + 0.1 * fm.nb_tail(10, 20 / 90 * per90, 8.0)
        self.assertAlmostEqual(fm.dc_probability('D', comps, dc), want)
        mins = fm.minutes_expectation(0.8, 0.5, 88, 0.95, 20, 0.0)
        extras = {'yellow90': 0.1, 'red90': 0.0, 'base_bps90': 3.0, 'penalty_saves': 0.03, 'start_minutes': 88,
                  'sub_minutes': 20, 'cbit90': 4.0, 'dc': dc, 'bonus_beta': {p: [0.0] * 7 for p in 'GDMF'}}
        d = fm.expected_points('D', mins, 0.05, 0.05, 1.2, extras=extras)
        self.assertAlmostEqual(d['dc_points'], 2 * fm.dc_probability('D', d, dc))
        self.assertEqual(fm.expected_points('G', mins, 0, 0, 1.2, 3.0, extras)['dc_points'], 0.0)

    def test_v1_4_blends_his_own_fpl_record_into_the_rate(self):
        dc = {'thresholds': {'D': 10}, 'points': 2, 'own_pseudo_90s': 3.0, 'D': {'c': 3.0, 'k': 1.5, 'r': 8.0}}
        comps = {'p_start': 1.0, 'p_play': 1.0, 'start_minutes': 90, 'sub_minutes': 20, 'cbit90': 4.0}
        # no record: v1.3's rate; 5 full matches averaging 11 pull it most of the way to 11
        self.assertAlmostEqual(fm.dc_probability('D', dict(comps, fpl_dc_minutes=0, fpl_dc_count=0), dc),
                               fm.nb_tail(10, 9.0, 8.0))
        own = fm.dc_probability('D', dict(comps, fpl_dc_minutes=450, fpl_dc_count=55), dc)
        self.assertAlmostEqual(own, fm.nb_tail(10, (55 + 9.0 * 3) / (5 + 3), 8.0))
        # the record rides through player_extras, expected_points and a stored rescoring
        r = {'position': 'D', 'att_min': 900, 'yellow': 1, 'red': 0, 'bps_base': 30, 'cbit': 40, 'fpl_dc': (450, 55)}
        params = {'bonus_beta': {p: [0.0] * 7 for p in 'GDMF'}, 'rate_pseudo_minutes': 900, 'penalty_saves_per_team_match': 0.03,
                  'rate_priors': {'D': {'yellow90': 0.1, 'red90': 0.0, 'base_bps90': 3.0}},
                  'dc': dict(dc, cbit_priors={'D': 4.0})}
        extras = dict(fm.player_extras(params, r), start_minutes=90, sub_minutes=20)
        d = fm.expected_points('D', fm.minutes_expectation(1.0, 0.0, 90, 1.0, 20, 0.0), 0, 0, 1.2, extras=extras)
        self.assertEqual((d['fpl_dc_minutes'], d['fpl_dc_count']), (450, 55))
        self.assertEqual(fm.player_extras(params, stored=d)['fpl_dc_count'], 55)
        self.assertEqual(fm.player_extras(params, dict(r, fpl_dc=None))['fpl_dc_minutes'], 0)


class V15Tests(unittest.TestCase):
    PEN = {'rate': 0.12, 'lambda_power': 0, 'mean_lambda': 1.5, 'conversion': 0.8, 'alpha': 0.5, 'decay': 0.5,
           'order_weight': 0.75, 'order_ratio': 0.15, 'self_won': 0.2, 'won_per_foul': 0.01,
           'fouls_drawn_prior': dict.fromkeys('GDMF', 1.0), 'shots_prior': dict.fromkeys('GDMF', 1.0),
           'extra_assists_per_goal': 0.2}

    @staticmethod
    def app(days, team, goals=0, sot=0, scored=0, missed=0, team_scored=0):
        from datetime import datetime, timedelta, timezone
        kickoff = datetime(2026, 9, 30, tzinfo=timezone.utc) - timedelta(days=days)
        return (kickoff, True, 90, 'ST', goals, sot, 0, 0, 2, 5, 1, 8, 10, 0, 0, 3,
                team, scored, missed, 0, 3, 1, team_scored)

    def test_penalty_features_drop_penalties_from_goal_evidence_and_keep_this_clubs_record(self):
        from datetime import datetime, timezone
        apps = [self.app(400, 7, scored=1), self.app(30, 8, goals=2, sot=3, scored=1, team_scored=1),
                self.app(10, 8, missed=1)]
        f = fm.player_features(1, datetime(2026, 9, 30, tzinfo=timezone.utc), [], apps, team=8)
        self.assertEqual((f['g'], f['g_np'], f['sot_np']), (2, 1, 2))
        self.assertAlmostEqual(f['tg_np'], 2 + 2 - 1)            # his team's goals less its penalties, per 90
        self.assertEqual(f['pen_hist'], [(30, 1), (10, 1)])        # the other club's penalty doesn't count
        self.assertEqual(fm.player_features(1, datetime(2026, 9, 30, tzinfo=timezone.utc), [], [], team=8)['pen_hist'], [])

    def test_fpl_order_blends_with_history_and_is_ignored_when_absent(self):
        scores = [3.0, 1.0, 0.0]
        self.assertEqual(fm.with_fpl_order(scores, [None] * 3, self.PEN), scores)
        blended = fm.with_fpl_order(scores, [None, 1, 2], self.PEN)
        self.assertAlmostEqual(sum(blended), 1.0)
        self.assertAlmostEqual(blended[1], 0.25 * 0.25 + 0.75 / 1.15)     # FPL's first choice leads
        self.assertGreater(blended[1], blended[0])

    def test_allocation_keeps_team_totals(self):
        players = [{'position': p, 'att_min': 900, 'pen_hist': h, 'won': 1, 'shots': 20, 'fouls_drawn': 10}
                   for p, h in (('F', [(20, 2)]), ('M', []), ('D', []))]
        minutes = [{'exp_minutes': m} for m in (90, 80, 90)]
        out = fm.penalty_allocation(players, minutes, [0.4, 0.2, 0.05], 1.5, 1.45, self.PEN, 5.0)
        self.assertAlmostEqual(out['pen_goals'], 0.12 * 0.8)
        self.assertAlmostEqual(sum(out['pen_share']), 1.0)
        self.assertGreater(out['pen_share'][0], 0.8)                       # the club's taker
        self.assertAlmostEqual(sum(out['exp_pen_goals']), out['pen_goals'])
        self.assertAlmostEqual(sum(out['exp_pen_misses']), 0.12 * 0.2)
        self.assertAlmostEqual(sum(out['exp_fpl_pen_assists']), out['pen_goals'] * 0.8)
        self.assertAlmostEqual(sum(out['exp_fpl_other_assists']), (1.45 - out['pen_goals']) * 0.2)

    def test_penalty_and_fpl_assist_points_and_stored_rescoring(self):
        mins = fm.minutes_expectation(0.9, 0.5, 88, 0.98, 20, 0.0)
        pens = {'exp_pen_goals': 0.08, 'exp_pen_misses': 0.02, 'exp_fpl_pen_assists': 0.01, 'exp_fpl_other_assists': 0.04}
        extras = {'yellow90': 0.1, 'red90': 0.0, 'base_bps90': 5.0, 'penalty_saves': 0.03, 'start_minutes': 88, 'sub_minutes': 20,
                  'bonus_beta': {p: [0.1] * 7 for p in 'GDMF'}, 'penalties': pens}
        c = fm.expected_points('M', mins, 0.3, 0.2, 1.2, extras=extras)
        self.assertAlmostEqual(c['penalty_points'], 5 * 0.08 - 2 * 0.02)
        self.assertAlmostEqual(c['fpl_assist_points'], 3 * 0.05)
        self.assertAlmostEqual(c['goal_points'], 5 * 0.3)                  # open play only
        self.assertAlmostEqual((c['exp_np_goals'], c['exp_goals']), (0.3, 0.38))
        self.assertAlmostEqual(c['expected_points'],
                               sum(c[k] for k in fm.COMPONENT_POINTS + fm.EXTRA_POINTS + fm.PENALTY_POINTS))
        params = {'bonus_beta': extras['bonus_beta'], 'penalty_saves_per_team_match': 0.03, 'penalties': self.PEN}
        f = fm.expected_points('F', mins, c['exp_np_goals'], 0.2, 1.2, extras=fm.player_extras(params, stored=c))
        self.assertAlmostEqual(f['penalty_points'], 4 * 0.08 - 2 * 0.02)   # FPL scores a forward's goal at 4

    def test_frozen_v1_5_predicts_team_goals_split_into_open_play_and_penalties(self):
        import json
        from pathlib import Path
        doc = json.loads((Path(fm.__file__).with_name('fantasy_params_v1_5.json')).read_text())
        from datetime import datetime, timezone
        kickoff = datetime(2026, 9, 30, tzinfo=timezone.utc)
        recent = [{1: (True, 90), 2: (True, 90), 3: (True, 90)}] * 10
        apps = {1: [self.app(d, 8, goals=1, sot=2, scored=1, team_scored=1) for d in range(7, 77, 7)],
                2: [self.app(d, 8, goals=0, sot=1) for d in range(7, 77, 7)],
                3: [self.app(d, 8) for d in range(7, 77, 7)]}
        players = [dict(fm.player_features(p, kickoff, recent, apps[p], team=8), position=pos, injury=None)
                   for p, pos in ((1, 'F'), (2, 'M'), (3, 'D'))]
        out = fm.predict_team(players, 1.6, 1.1, doc['params'])
        goals = 1.6 * (1 - doc['params']['own_goal_share'])
        self.assertAlmostEqual(sum(c['exp_goals'] for c in out), goals, places=6)
        pen_goals = doc['params']['penalties']['rate'] * doc['params']['penalties']['conversion']
        self.assertAlmostEqual(sum(c['exp_pen_goals'] for c in out), pen_goals, places=6)
        self.assertGreater(out[0]['exp_pen_goals'], 0.9 * pen_goals)        # ten penalties for this club


class V16Tests(unittest.TestCase):
    def test_fpl_availability_follows_return_dates_status_and_next_round_chance(self):
        from datetime import datetime, timezone
        k = datetime(2026, 10, 10, 14, tzinfo=timezone.utc)
        later = datetime(2026, 10, 24, 14, tzinfo=timezone.utc)
        self.assertEqual(fm.fpl_availability(None, k), 1.0)
        back = ('i', 0, 'Hamstring injury - Expected back 17 Oct')
        self.assertEqual((fm.fpl_availability(back, k), fm.fpl_availability(back, later)), (0.0, 1.0))
        self.assertEqual(fm.fpl_availability(('i', 0, 'Knee injury - Expected back 10 Oct'), k), 1.0)   # back that day
        self.assertEqual(fm.fpl_availability(('s', 0, 'Suspended until 17 Oct'), k), 0.0)
        unknown = ('i', 0, 'Knee injury - Unknown return date')
        self.assertEqual((fm.fpl_availability(unknown, k), fm.fpl_availability(unknown, later)), (0.0, 0.0))
        doubt = ('d', 75, 'Hamstring injury - 75% chance of playing')
        self.assertEqual(fm.fpl_availability(doubt, k, 7, 7), 0.75)                  # next gameweek only
        self.assertEqual(fm.fpl_availability(doubt, later, 7, 9), 1.0)
        self.assertEqual(fm.fpl_availability(doubt, k), 0.75)                         # gameweek unknown: as the next
        self.assertEqual(fm.fpl_return_date('Expected back 03 Jan', datetime(2026, 12, 20).date()).year, 2027)

    def test_availability_scales_minutes_and_moves_goals_to_teammates(self):
        import json
        from pathlib import Path
        params = json.loads((Path(fm.__file__).with_name('fantasy_params_v1_6.json')).read_text())['params']
        from datetime import datetime, timezone
        kickoff = datetime(2026, 9, 30, tzinfo=timezone.utc)
        recent = [{1: (True, 90), 2: (True, 90)}] * 10
        app = lambda d, g: (kickoff - timedelta(days=d), True, 90, 'ST', g, g, 0, 0, 2, 5, 1, 8, 10, 0, 0, 3, 8, 0, 0, 0, 3, 1, 0)
        players = [dict(fm.player_features(p, kickoff, recent, [app(d, g) for d in range(7, 77, 7)], team=8),
                        position='F', injury=None, fpl_available=a) for p, g, a in ((1, 1, 0.5), (2, 0, 1.0))]
        out = fm.predict_team(players, 1.6, 1.1, params)
        full = fm.predict_team([dict(p, fpl_available=1.0) for p in players], 1.6, 1.1, params)
        self.assertAlmostEqual(out[0]['p_start'], 0.5 * full[0]['p_start'])
        self.assertAlmostEqual(out[0]['exp_minutes'], 0.5 * full[0]['exp_minutes'])
        self.assertGreater(out[1]['exp_goals'], full[1]['exp_goals'])            # his teammate picks up the share


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

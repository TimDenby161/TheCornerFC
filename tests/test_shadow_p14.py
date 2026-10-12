"""P14's evaluator (experiments/prospective/shadow_p14.py): the parts that need no database."""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('shadow_p14', ROOT / 'experiments/prospective/shadow_p14.py')
p14 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p14)


def quote(taken, fair=None):
    return {'taken': taken, 'fair': fair}


def model(result=(0.4, 0.3, 0.3), goal=(0.75, 0.5, 0.3, 0.1, 0.5)):
    return p14.chances(result, goal)


class P14Tests(unittest.TestCase):
    def test_a_bet_needs_the_registered_edge_at_bet365s_price(self):
        prices = {(1, 'Home'): quote(2.70, 0.35), (1, 'Draw'): quote(3.40, 0.28), (1, 'Away'): quote(2.90, 0.37)}
        self.assertEqual(p14.shadow_bets(model(), prices, {}, 1, 0), [])          # 0.4 x 2.70 = 1.08
        prices[(1, 'Home')] = quote(2.80, 0.35)
        bets = p14.shadow_bets(model(), prices, {}, 1, 0)
        self.assertEqual([(b['market'], b['selection'], b['won'], round(b['profit'], 2)) for b in bets],
                         [('1X2', 'Home', True, 1.8)])

    def test_a_selection_with_no_bet365_price_or_a_price_above_ten_is_left_out(self):
        prices = {(1, 'Home'): quote(None, 0.35), (1, 'Away'): quote(12.0, 0.08)}
        self.assertEqual(p14.shadow_bets(model(result=(0.5, 0.3, 0.2)), prices, {}, 0, 1), [])

    def test_one_bet_of_each_kind_and_the_best_is_kept(self):
        prices = {(5, 'Under 1.5'): quote(5.0, 0.2), (5, 'Under 2.5'): quote(2.4, 0.42),
                  (8, 'No'): quote(2.4, 0.42), (1, 'Draw'): quote(4.0, 0.27)}
        bets = {b['group']: b for b in p14.shadow_bets(model(), prices, {}, 0, 0)}
        self.assertEqual(sorted(bets), ['1X2', 'BTTS', 'OU'])
        # under 1.5: (0.25 + 0.2) / 2 x 5 = 1.125; under 2.5: (0.5 + 0.42) / 2 x 2.4 = 1.104
        self.assertEqual(bets['OU']['selection'], 'Under 1.5')
        self.assertTrue(all(b['won'] for b in bets.values()))

    def test_a_losing_bet_costs_its_stake_and_closing_line_value_uses_the_closing_fair_chance(self):
        prices = {(8, 'Yes'): quote(2.5, 0.4), (8, 'No'): quote(1.5, 0.6)}
        closing = {(8, 'Yes'): quote(2.3, 0.44)}
        bet, = p14.shadow_bets(model(), prices, closing, 2, 0)
        self.assertEqual((bet['selection'], bet['won'], bet['profit'], bet['outsider']), ('Yes', False, -1.0, True))
        self.assertAlmostEqual(bet['clv'], 2.5 * 0.44 - 1)
        self.assertIsNone(p14.shadow_bets(model(), prices, {}, 2, 0)[0]['clv'])

    def test_bets_settle_on_the_90_minute_score(self):
        self.assertTrue(p14.won('1X2', 'Draw', 1, 1))
        self.assertTrue(p14.won('OU25', 'Under 2.5', 1, 1))
        self.assertTrue(p14.won('OU25', 'Over 2.5', 2, 1))
        self.assertTrue(p14.won('BTTS', 'No', 3, 0))
        self.assertFalse(p14.won('1X2', 'Away', 1, 1))

    def test_the_goal_chances_are_read_in_the_frames_order(self):
        got = p14.chances((0.5, 0.25, 0.25), (0.8, 0.55, 0.3, 0.12, 0.52))
        self.assertEqual(got['OU15'][0], 0.8)
        self.assertEqual(got['OU45'][0], 0.12)
        self.assertAlmostEqual(got['OU25'][1], 0.45)
        self.assertEqual(got['BTTS'][0], 0.52)

    def test_prices_come_back_by_fixture_and_selection(self):
        table = p14.price_table([(7, 1, 'Home', 0.4, 9, 2.6, 't'), (7, 8, 'Yes', None, 0, 1.9, 't')])
        self.assertEqual(table[7][(1, 'Home')], {'fair': 0.4, 'books': 9, 'taken': 2.6, 'made': 't'})
        self.assertIsNone(table[7][(8, 'Yes')]['fair'])

    def test_the_registered_target_follows_from_the_planning_figures(self):
        self.assertAlmostEqual(p14.fixtures_required(0.0784), p14.TARGET, delta=100)
        self.assertEqual(p14.fixtures_required(0.001), p14.REESTIMATE_AT)

    def test_the_candidate_files_are_as_registered(self):
        p14.check_pins()

    def test_ties_decided_after_90_minutes_are_in_the_population(self):
        for sql in (p14.ACCRUAL_SQL, p14.SNAPSHOT_SQL, p14.PRICES_SQL):
            self.assertIn("'FT', 'AET', 'PEN'", sql)
            self.assertIn('ft_home is not null', sql)

    def test_a_price_seen_after_the_snapshot_never_counts_for_the_bet(self):
        self.assertIn('<= snap.made', p14.CUTOFFS['decision'])
        self.assertIn('< snap.kickoff', p14.CUTOFFS['closing'])
        self.assertEqual(p14.PRICES_SQL.count('{cutoff}'), 1)

    def test_the_accrual_check_reads_no_score_and_no_price(self):
        sql = p14.ACCRUAL_SQL.replace('ft_home is not null', '').replace('ft_away is not null', '')
        for word in ('goals', 'ft_home', 'ft_away', 'odds::', 'o.odds'):
            self.assertNotIn(word, sql)

    def test_the_protocol_is_registered(self):
        text = (ROOT / 'experiments/prospective/PROTOCOLS.md').read_text()
        self.assertIn('## P14: The formula candidates against production, the market and as shadow bets', text)
        self.assertIn(f'{p14.TARGET:,} fixtures', text)
        self.assertIn(p14.START, text)
        for name in p14.CANDIDATES:
            self.assertIn(f'`{name}`', text)


if __name__ == '__main__':
    unittest.main()

from collections import Counter
from datetime import datetime, timezone
import unittest

from thecornerfc.player_ratings import _select_lineup, formation_slots, likely_formation, role_fit


class FormationLineupTests(unittest.TestCase):
    def test_slots_for_back_three(self):
        self.assertEqual(formation_slots('3-4-2-1'),
                         ['GK', 'CB', 'CB', 'CB', 'LWB', 'CM', 'CM', 'RWB', 'AM', 'AM', 'ST'])
        self.assertIsNone(formation_slots('4-4-1'))
        self.assertIsNone(formation_slots(None))

    def test_most_used_formation_latest_wins_ties(self):
        self.assertEqual(likely_formation(['4-4-2', '3-4-2-1', '3-4-2-1', '4-4-2']), '4-4-2')
        self.assertEqual(likely_formation(['3-4-2-1', '3-4-2-1', '4-4-2']), '3-4-2-1')
        self.assertIsNone(likely_formation([]))

    def test_fit_prefers_same_side(self):
        self.assertGreater(role_fit('RB', 'RWB'), role_fit('LWB', 'RWB'))
        self.assertEqual(role_fit('CB', 'GK'), 0.0)

    def test_back_three_gets_one_wing_back_each_side_and_a_striker(self):
        # Two right wing-backs play more minutes than the striker; the old rule took both
        roles = {1: 'GK', 2: 'CB', 3: 'CB', 4: 'CB', 5: 'LWB', 6: 'RWB', 7: 'RWB',
                 8: 'CM', 9: 'CM', 10: 'AM', 11: 'AM', 12: 'ST', 13: 'GK'}
        minutes = Counter({p: 450 for p in roles})
        minutes.update({7: -90, 12: -200, 13: -400})
        score = lambda p, k: ((1., 900.), 'GK' if roles[p] == 'GK' else roles[p], 100)
        _, _, xi = _select_lineup(minutes, set(), score, datetime.now(timezone.utc),
                                  '3-4-2-1', lambda p: Counter({roles[p]: 5}))
        self.assertEqual([r[4] for r in xi], formation_slots('3-4-2-1'))
        picked = {r[0]: r[4] for r in xi}
        self.assertEqual(picked[12], 'ST')
        self.assertEqual(picked[6], 'RWB')
        self.assertNotIn(7, picked)
        self.assertNotIn(13, picked)

    def test_injured_striker_is_covered_by_the_nearest_fit(self):
        roles = {1: 'GK', 2: 'CB', 3: 'CB', 4: 'CB', 5: 'LWB', 6: 'RWB', 7: 'RWB',
                 8: 'CM', 9: 'CM', 10: 'AM', 11: 'AM', 12: 'ST', 14: 'LW'}
        minutes = Counter({p: 450 for p in roles})
        score = lambda p, k: ((1., 900.), 'GK' if roles[p] == 'GK' else roles[p], 100)
        _, _, xi = _select_lineup(minutes, {12}, score, datetime.now(timezone.utc),
                                  '3-4-2-1', lambda p: Counter({roles[p]: 5}))
        self.assertEqual({r[0]: r[4] for r in xi}[14], 'ST')

    def test_without_formation_falls_back_to_minutes(self):
        minutes = Counter({p: 1000 - p for p in range(1, 15)})
        score = lambda p, k: ((1., 900.), 'GK' if p in (1, 2) else 'CM', 100)
        xi = _select_lineup(minutes, set(), score, datetime.now(timezone.utc))[2]
        self.assertEqual([r[0] for r in xi], [1] + list(range(3, 13)))
        self.assertTrue(all(r[4] is None for r in xi))

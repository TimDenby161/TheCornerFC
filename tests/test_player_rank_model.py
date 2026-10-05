"""The player rank model as rebuilt in October 2026: counted stats only, wing-backs their own
group, stats counting more at strong clubs, a level per position, backup keepers."""
import unittest
from datetime import date
from unittest.mock import patch

from thecornerfc import player_ratings as pr, positions


def sums(**stats):
    s = dict.fromkeys(pr.SUMS, 0.0)
    s.update(minutes=900.0, **stats)
    return s


class Weights(unittest.TestCase):
    def test_no_match_rating_or_discipline(self):
        for group, weights in pr.WEIGHTS.items():
            self.assertFalse({"rating", "gk_rating", "discipline"} & set(weights), group)

    def test_every_group_adds_up_to_one(self):
        # a window's score is pulled towards MINUTES_PRIOR, so the scale must be the same
        for group, weights in pr.WEIGHTS.items():
            self.assertAlmostEqual(sum(abs(w) for w in weights.values()), 1.0, places=3, msg=group)

    def test_every_group_has_weights(self):
        self.assertEqual(set(pr.WEIGHTS), set(pr.OUTFIELD_GROUPS) | {"GK"})
        self.assertEqual(set(pr.POSITION_STATS), set(pr.OUTFIELD_GROUPS))
        self.assertEqual(set(pr.POSITION_OFFSET), set(pr.OUTFIELD_GROUPS))

    def test_every_weighted_stat_is_a_metric(self):
        m = pr.metrics(sums())
        for group, weights in pr.WEIGHTS.items():
            self.assertLessEqual(set(weights), set(m), group)


class Metrics(unittest.TestCase):
    def test_failed_dribbles(self):
        m = pr.metrics(sums(dribbles=30.0, dribbles_won=12.0))
        self.assertAlmostEqual(m["dribbles_lost"], 1.8)
        self.assertNotIn("rating", m)

    def test_failed_dribbles_never_negative(self):
        self.assertEqual(pr.metrics(sums(dribbles=0.0, dribbles_won=3.0))["dribbles_lost"], 0.0)

    def test_row_stats_take_the_attempts_and_no_rating(self):
        row = {"stats": [1] * len(pr.STATS[3:]) + [0.7], "minutes": 90, "opp_xg": 0.7}
        d = pr._row_stats(row)
        self.assertEqual(d["dribbles"], 1)
        self.assertNotIn("rating_mins", d)


class WingBacks(unittest.TestCase):
    def test_their_own_group(self):
        self.assertEqual(positions.group("LWB"), "WB")
        self.assertEqual(positions.group("RWB"), "WB")
        self.assertEqual(positions.group("LB"), "FB")
        self.assertIn("WB", positions.GROUP_LABELS)

    def test_fill_slots_as_full_backs_did(self):
        self.assertEqual(pr.role_fit("RB", "RWB"), pr.SAME_GROUP_FIT)
        self.assertEqual(pr.role_fit("LWB", "LB"), pr.SAME_GROUP_FIT)
        self.assertEqual(pr.role_fit("CB", "RWB"), pr.role_fit("CB", "RB"))
        self.assertEqual(pr.role_fit("RWB", "RW"), pr.role_fit("RB", "RW"))


class StrongClubs(unittest.TestCase):
    def test_stats_count_as_before_at_a_weaker_club(self):
        club = pr.TOP_STATS_FROM - 50
        gap = pr.unsoft_ceiling(pr.outfield_rank(60, club, pos="ST")) - pr.unsoft_ceiling(pr.outfield_rank(50, club, pos="ST"))
        self.assertAlmostEqual(gap, pr.OUT_STATS_WEIGHT * 10, places=6)

    def test_stats_count_double_at_the_top(self):
        club = pr.TOP_STATS_FULL
        gap = pr.unsoft_ceiling(pr.outfield_rank(40, club, pos="ST")) - pr.unsoft_ceiling(pr.outfield_rank(50, club, pos="ST"))
        self.assertAlmostEqual(gap, -pr.OUT_STATS_WEIGHT * pr.TOP_STATS * 10, places=6)

    def test_an_average_season_is_unchanged(self):
        self.assertAlmostEqual(pr.outfield_rank(50, 1100, pos="CM"), pr.soft_ceiling(100 * 1100 / pr.CLUB_RANK_MAX - pr.OUT_CLUB_OFFSET))


def app(fixture, player, role, season, *, team=1, minutes=90, goals=0, key_passes=0, passes=40):
    stats = dict.fromkeys(pr.STATS[3:], 0)
    stats.update(goals=goals, key_passes=key_passes, passes=passes, passes_accurate=int(passes * .8), duels=10, duels_won=5,
                 saves=3 + player % 2, goals_conceded=1)
    return (fixture, team, player, minutes, True, "G" if role == "GK" else "M", role, None, season, 39, "FT",
            *stats.values(), 1.0)


class PositionLevels(unittest.TestCase):
    """season_model step 6 on a small made-up league: 20 central mids, 20 wingers and 2 keepers
    over two seasons, with enough young and old players for the age curve to be measured."""
    BORN = ([(p, date(2002, 1, 1)) for p in range(1, 31)] + [(p, date(1992, 1, 1)) for p in range(31, 41)]
            + [(41, date(1994, 1, 1)), (42, date(1990, 1, 1))])

    def model(self, extra=()):
        apps, fid = [], 0
        for season in (2024, 2025):
            for game in range(30):
                fid += 1
                for player in range(1, 41):
                    role = "CM" if player <= 20 else "RW"
                    apps.append(app(fid, player, role, season, goals=player % 3 == 0, key_passes=player % 5, passes=30 + player))
                for keeper in (41, 42):
                    apps.append(app(fid, keeper, "GK", season, passes=20 + keeper))
        apps += list(extra)
        norms = pr._norms(apps)
        team_rank = {(a[0], a[1]): 1000.0 for a in apps}
        ranks = {}
        rows = pr.season_model(norms, apps, team_rank, born=self.BORN, team_level=[(1, 2024, 1000.0, 30), (1, 2025, 1000.0, 30)],
                               careers=[], covered=[(1, 2024), (1, 2025)], team_games=[(1, 2024, 30), (1, 2025, 30)],
                               position_ranks=ranks)
        return rows, ranks

    def test_only_positions_he_has_started_in(self):
        _, ranks = self.model()
        self.assertEqual(set(ranks[5]), {"CM"})
        self.assertEqual(set(ranks[30]), {"W"})

    def test_a_position_he_rarely_plays_is_marked_down(self):
        # player 30, a winger, with one start in central midfield
        one = [app(999, 30, "CM", 2025, goals=1, key_passes=0, passes=60)]
        _, ranks = self.model(one)
        self.assertEqual(set(ranks[30]), {"W", "CM"})
        with patch.object(pr, "FAMILIARITY_PENALTY", 0.0):
            _, free = self.model(one)
        # a winger in central midfield (fit 0.4) pays 1.2 times the penalty, less the little he has played there
        self.assertAlmostEqual(free[30]["CM"] - ranks[30]["CM"], 1.2 * pr.FAMILIARITY_PENALTY, delta=1.0)
        self.assertEqual(free[30]["W"], ranks[30]["W"])          # nothing off his own position

    def test_related_positions_pay_less(self):
        full = pr.FAMILIARITY_PENALTY
        fit = lambda a, b: min(2 * (1 - pr.GROUP_FIT.get(frozenset((a, b)), pr.OFF_ROLE_FIT)), pr.UNRELATED_MAX)
        self.assertAlmostEqual(full * fit("FB", "WB"), 3.0)
        self.assertAlmostEqual(full * fit("W", "WB"), 10.0)
        self.assertAlmostEqual(full * fit("AM", "WB"), 14.0)


if __name__ == "__main__":
    unittest.main()

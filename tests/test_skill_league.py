import unittest
from datetime import datetime, timedelta

from thecornerfc.models import player_ratings as pr

PL, L2 = 39, 42          # a reference league and one that isn't


def unit(player, season, league, finishing):
    return (player, season, league, 1000, {"finishing": finishing})


class LeagueOffsetTests(unittest.TestCase):
    """Skill scores less the offsets of the leagues they were played in (MC-0031,
    experiments/skill_league/DESIGN.md)."""

    def test_movers_set_a_league_apart_and_the_offset_is_shrunk_by_how_many_there_are(self):
        # every mover scores 0.5 higher in League Two than in the Premier League
        units = []
        for p in range(30):
            units += [unit(p, 2023, L2, p / 10 + 0.5), unit(p, 2024, PL, p / 10)]
        units += [unit(100 + p, 2024, PL, 0.0) for p in range(10)]        # players seen in one league only
        off = pr.skill_league_offsets(units)
        self.assertAlmostEqual(off[PL]["finishing"], 0.0, places=6)          # the reference leagues average 0
        self.assertAlmostEqual(off[L2]["finishing"], 0.5 * 30 / (30 + pr.SKILL_OFFSET_MOVERS), places=4)

    def test_a_league_with_no_movers_gets_no_offset(self):
        units = [unit(1, 2024, PL, 0.2), unit(2, 2024, L2, 1.5)]
        self.assertEqual(pr.skill_league_offsets(units)[L2]["finishing"], 0.0)

    def test_a_skill_score_takes_off_his_leagues_offsets_by_minutes(self):
        norms = {k: (0.0, 1.0) for k in {k for r in pr.SKILLS.values() for k in r}}
        base = dict.fromkeys(pr.SUMS, 0.0)
        base.update(minutes=1800, goals=10, shots_on=30, passes=900, passes_accurate=800, duels=200, duels_won=100,
                    dribbles=40, dribbles_won=20, tackles=30, interceptions=20, blocks=10, key_passes=30, assists=5)
        players = {p: ({**base, ("lg", lg): 1800}, "ST") for p, lg in ((1, PL), (2, L2))}
        # a crowd of regulars for the percentiles to be among
        for p in range(3, 60):
            players[p] = ({**base, "goals": p % 20, "shots_on": p % 35, ("lg", PL): 1800}, "ST")
        plain = pr.skill_scores(players, norms)
        offsets = {L2: {skill: 0.8 for skill in pr.SKILLS}}
        adjusted = pr.skill_scores(players, norms, offsets)
        self.assertEqual(plain[1]["finishing"], plain[2]["finishing"])          # the same numbers score the same...
        self.assertLess(adjusted[2]["finishing"], adjusted[1]["finishing"])     # ...until League Two's offset comes off
        self.assertGreaterEqual(adjusted[1]["finishing"], plain[1]["finishing"])   # a percentile: he can only gain a place

    def test_the_window_keeps_and_drops_each_leagues_minutes(self):
        w = pr.Window()
        t = datetime(2026, 1, 1)
        stats = dict.fromkeys(pr.SUMS, 0.0)
        for i in range(pr.WINDOW_APPS + 1):
            w.add(t + timedelta(days=i), {**stats, "minutes": 90, ("lg", PL if i == 0 else L2): 90}, "ST", "F")
        self.assertEqual(w.sums[("lg", PL)], 0.0)                                  # the first appearance has left the window
        self.assertEqual(w.sums[("lg", L2)], 90.0 * pr.WINDOW_APPS)


if __name__ == "__main__":
    unittest.main()

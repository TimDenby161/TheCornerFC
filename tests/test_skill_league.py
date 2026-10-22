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

    def test_the_level_pull_moves_scores_by_club_strength_from_the_reference_level(self):
        # MC-0033: two players with the same numbers, one at reference-league clubs of 1,000, one in
        # League Two at clubs of 800; a crowd at the reference level for the percentiles
        norms = {k: (0.0, 1.0) for k in {k for r in pr.SKILLS.values() for k in r}}
        base = dict.fromkeys(pr.SUMS, 0.0)
        base.update(minutes=1800, goals=10, shots_on=30, passes=900, passes_accurate=800, duels=200, duels_won=100,
                    dribbles=40, dribbles_won=20, tackles=30, interceptions=20, blocks=10, key_passes=30, assists=5)
        players = {1: ({**base, "club_mins": 1000 * 1800, ("lg", PL): 1800}, "W"),
                   2: ({**base, "club_mins": 800 * 1800, ("lg", L2): 1800}, "W")}
        for p in range(3, 60):
            players[p] = ({**base, "dribbles_won": p % 30, "club_mins": 1000 * 1800, ("lg", PL): 1800}, "W")
        self.assertEqual(pr.skill_reference_level(players), 1000)               # League Two isn't in the reference
        flat = pr.skill_scores(players, norms, level_pull=0)
        pulled = pr.skill_scores(players, norms, level_pull=0.5)
        self.assertEqual(flat[1]["dribbling"], flat[2]["dribbling"])
        self.assertLess(pulled[2]["dribbling"], pulled[1]["dribbling"])          # 200 points below: down a whole sd
        self.assertGreaterEqual(pulled[1]["dribbling"], flat[1]["dribbling"])   # at the reference level: only gains a place
        # one way: a player above the reference level is not lifted (kept out of the reference
        # group by his league, so the reference stays where the crowd puts it)
        at = {**players, 1: ({**base, "club_mins": 1000 * 1800, ("lg", L2): 1800}, "W")}
        above = {**players, 1: ({**base, "club_mins": 1300 * 1800, ("lg", L2): 1800}, "W")}
        self.assertEqual(pr.skill_scores(above, norms, level_pull=0.5)[1]["dribbling"],
                         pr.skill_scores(at, norms, level_pull=0.5)[1]["dribbling"])

    def test_a_skill_is_scored_only_where_his_position_uses_it(self):
        # MC-0035: a centre-back has no finishing score and a winger no solidity, and each skill's
        # percentile is among the positions that use it
        norms = {k: (0.0, 1.0) for k in {k for r in pr.SKILLS.values() for k in r}}
        base = dict.fromkeys(pr.SUMS, 0.0)
        base.update(minutes=1800, goals=2, shots_on=5, passes=1500, passes_accurate=1400, duels=200, duels_won=120,
                    dribbles=10, dribbles_won=5, tackles=40, interceptions=30, blocks=20, key_passes=5, assists=1, dribbled_past=5)
        players = {p: ({**base, "goals": p % 7}, "CB") for p in range(1, 30)}
        players.update({p: ({**base, "goals": p % 11}, "W") for p in range(30, 60)})
        scores = pr.skill_scores(players, norms)
        self.assertNotIn("finishing", scores[1])                     # not part of a centre-back's rank
        self.assertIn("solidity", scores[1])
        self.assertNotIn("solidity", scores[30])                     # not part of a winger's rank
        self.assertIn("finishing", scores[30])
        self.assertEqual(set(pr.SKILLS) - set(scores[1]), {s for s in pr.SKILLS if not pr.SKILL_MIX["CB"].get(s)})

    def test_keepers_have_their_own_three_skills_against_other_keepers(self):
        # MC-0037: shot-stopping (save %), goals prevented (team xG conceded less goals conceded,
        # per 90) and distribution (pass accuracy); no outfield skill, and no keeper skill outfield
        norms = {k: (0.0, 1.0) for k in {k for r in pr.SKILLS.values() for k in r}}
        base = dict.fromkeys(pr.SUMS, 0.0)
        base.update(minutes=1800, passes=600, passes_accurate=480, xga=1.2 * 1800, xg_mins=1800)
        players = {p: ({**base, "saves": 40 + p, "goals_conceded": 20, "club_mins": 1000 * 1800, ("lg", PL): 1800}, "GK") for p in range(1, 30)}
        players[99] = ({**base, "goals": 5, "shots_on": 15, "club_mins": 1000 * 1800, ("lg", PL): 1800}, "ST")
        scores = pr.skill_scores(players, norms)
        self.assertEqual(set(scores[10]), set(pr.KEEPER_SKILLS))
        self.assertGreater(scores[29]["shot_stopping"], scores[1]["shot_stopping"])       # more saves, same goals: better
        self.assertFalse(set(scores.get(99, {})) & set(pr.KEEPER_SKILLS))

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

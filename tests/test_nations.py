import unittest
from datetime import date
from unittest import mock

from thecornerfc import nations
from thecornerfc.nations import Result

CSV = """date,home_team,away_team,home_score,away_score,tournament,city,country,neutral
2020-01-01,Spain,France,2,0,FIFA World Cup qualification,Madrid,Spain,FALSE
2020-02-01,France,Spain,1,1,Friendly,Paris,France,FALSE
2020-03-01,Spain,Jersey,9,0,Island Games,St Helier,Jersey,TRUE
2026-10-01,Spain,France,NA,NA,Friendly,Madrid,Spain,FALSE
"""


class NationsTests(unittest.TestCase):
    def test_parse_skips_unplayed_and_tiers(self):
        rows = nations.parse_csv(CSV)
        self.assertEqual(len(rows), 3)
        self.assertEqual([nations.tier(r.tournament) for r in rows], ["competitive", "friendly", None])
        self.assertTrue(rows[2].neutral)

    def test_home_advantage_only_away_from_neutral_venues(self):
        seen = []
        m = lambda neutral: Result("2020-01-01", "A", "B", 1, 1, "Friendly", neutral)
        nations.replay([m(False), m(True)], on_match=lambda m, h, a, e: seen.append((h, a, e)))
        self.assertAlmostEqual(seen[0][2], nations.HOME_ADVANTAGE_POINTS / 100)
        # the draw at home cost A points, so on neutral ground B is now expected to be better
        self.assertAlmostEqual(seen[1][2], (seen[1][0] - seen[1][1]) / 100)
        self.assertLess(seen[1][2], 0)

    def test_goal_difference_cap_and_zero_sum(self):
        history = nations.replay([Result("2020-01-01", "A", "B", 12, 0, "Friendly", True)])
        change = history["A"][-1] - nations.START_RANK
        self.assertAlmostEqual(change, nations.MAX_GOAL_DIFF * nations.K_FACTOR)
        self.assertAlmostEqual(history["B"][-1], nations.START_RANK - change)

    def test_excluded_tournaments_are_not_rated(self):
        history = nations.replay(nations.parse_csv(CSV))
        self.assertNotIn("Jersey", history)
        self.assertEqual(len(history["Spain"]), 3)

    def test_merge_prefers_dataset_within_a_day(self):
        dataset = [Result("2026-06-01", "Spain", "France", 1, 0, "FIFA World Cup", True)]
        extra = [Result("2026-06-02", "France", "Spain", 0, 1, "World Cup", False, "api-football"),
                 Result("2026-09-05", "Spain", "France", 2, 2, "UEFA Nations League", False, "api-football")]
        merged = nations.merge(dataset, extra)
        self.assertEqual([(m.day, m.source) for m in merged],
                         [("2026-06-01", "dataset"), ("2026-09-05", "api-football")])

    def test_load_drops_api_matches_with_unknown_names(self):
        extra = [Result("2026-09-05", "Spain", "Narnia", 2, 0, "Friendlies", False, "api-football"),
                 Result("2026-09-06", "Spain", "France", 2, 0, "Friendlies", False, "api-football")]
        with mock.patch.object(nations, "download", return_value=CSV), \
             mock.patch.object(nations, "api_matches", return_value=extra):
            rows = nations.load()
        self.assertEqual([m.away for m in rows if m.source == "api-football"], ["France"])

    def test_api_names_map_to_dataset(self):
        self.assertEqual(nations.api_name("USA"), "United States")
        self.assertEqual(nations.api_name("Spain"), "Spain")
        self.assertIn("Korea Republic", nations._aliases()["South Korea"])

    def test_build_lists_active_fifa_members_only(self):
        rows = [Result("2025-01-01", "Spain", "France", 2, 0, "FIFA World Cup qualification", False),
                Result("2025-02-01", "France", "Spain", 1, 1, "UEFA Nations League", False),
                Result("2025-03-01", "Spain", "Greenland", 3, 0, "Friendly", False),
                Result("2012-01-01", "Eritrea", "Spain", 0, 3, "FIFA World Cup qualification", False)]
        rows.sort(key=lambda m: m.day)
        out = nations.build(rows, today=date(2026, 1, 1))
        names = [r["name"] for r in out["nations"]]
        self.assertEqual(names, ["Spain", "France"])   # Greenland isn't a member, Eritrea inactive
        spain = out["nations"][0]
        self.assertEqual((spain["w"], spain["d"], spain["l"]), (2, 1, 0))
        self.assertEqual(spain["confed"], "UEFA")
        self.assertEqual(spain["flag"], "es")
        self.assertEqual(spain["last"]["opp"], "Greenland")


if __name__ == "__main__":
    unittest.main()

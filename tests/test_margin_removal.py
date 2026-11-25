"""The bookmakers' chances on the Stats and Model pages: each bookmaker's margin removed by the
power method (2026-11-25), in Python for match pages and in the database for the Stats page."""
import inspect
import unittest

from thecornerfc.publish import site_matches, site_record


class PowerMethod(unittest.TestCase):
    def test_the_chances_add_to_one(self):
        for odds in ((1.5, 4.2, 7.0), (2.6, 3.3, 2.9), (1.08, 11.0, 26.0), (1.9, 1.95)):
            p = site_matches.without_margin(tuple(1 / o for o in odds))
            self.assertAlmostEqual(sum(p), 1.0, places=12)

    def test_it_takes_more_off_the_long_shot_than_proportional_scaling(self):
        inverse = (1 / 1.5, 1 / 4.2, 1 / 7.0)
        power = site_matches.without_margin(inverse)
        proportional = tuple(q / sum(inverse) for q in inverse)
        self.assertGreater(power[0], proportional[0])      # the favourite keeps more
        self.assertLess(power[2], proportional[2])         # the outsider loses more

    def test_a_book_without_margin_is_left_as_it_is(self):
        fair = (0.5, 0.3, 0.2)
        for got, want in zip(site_matches.without_margin(fair), fair):
            self.assertAlmostEqual(got, want, places=12)

    def test_the_stats_query_uses_the_same_method_and_steps(self):
        self.assertIn("_newton_steps(POWER_STEPS)", inspect.getsource(site_record.market_consensus))
        self.assertGreaterEqual(site_matches.POWER_STEPS, 6)

    def test_the_steps_are_written_out_not_recursive(self):
        # a recursive query would store every step of every bookmaker's set (temp files, Disk IO)
        sql = site_record._newton_steps(3)
        self.assertNotIn("recursive", sql)
        self.assertEqual(sql.count("cross join lateral"), 5)          # start, three steps, the answer
        self.assertIn("k2 - ((select sum(power(x, k2)) from unnest(q) x) - 1) / (select sum(power(x, k2) * ln(x)) from unnest(q) x) as k3", sql)
        self.assertIn("case when all_open then o2 - ((select sum(power(x, o2)) from unnest(q_open) x) - 1)", sql)
        self.assertTrue(sql.endswith("(select k3 as k, o3 as k_open) sk"))
        # each step is fenced, or Postgres inlines it into the next and the expression doubles
        self.assertEqual(sql.count("offset 0)"), 4)


if __name__ == "__main__":
    unittest.main()

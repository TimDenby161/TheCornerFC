import unittest
from unittest.mock import Mock

from thecornerfc.pipeline import ingest


class RetirementCheckTests(unittest.TestCase):
    def test_a_night_checks_at_most_the_cap_longest_unchecked_first(self):
        season, due, countries = Mock(), [(7,), (8,)], []
        season.fetchone.return_value = (2026,)
        conn = Mock()
        conn.execute.side_effect = [season, due, countries] + [Mock()] * 10
        api = Mock()
        api.get.return_value = {"response": []}

        ingest.check_retired(api, conn)

        sql, params = conn.execute.call_args_list[1].args
        self.assertIn("order by c.checked_at nulls first", sql)
        self.assertIn("limit %(n)s", sql)
        self.assertEqual(params["n"], ingest.RETIRED_CHECKS_PER_NIGHT)
        self.assertEqual(params["d"], ingest.RETIRED_RECHECK_DAYS)
        self.assertEqual([c.kwargs["player"] for c in api.get.call_args_list], [7, 8])

    def test_the_cap_clears_a_weeks_checks_inside_the_week(self):
        # About 3,850 players fell due together each week (call log, October 2026)
        self.assertGreater(ingest.RETIRED_CHECKS_PER_NIGHT * ingest.RETIRED_RECHECK_DAYS, 3850)


if __name__ == "__main__":
    unittest.main()

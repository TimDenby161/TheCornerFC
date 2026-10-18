import unittest
from unittest.mock import Mock, patch

from thecornerfc.pipeline.api import QuotaExhausted
from thecornerfc.pipeline.ingest import sync_injuries_fixtures, sync_odds_fixtures

BUG = RuntimeError("API-Football error on odds {'fixture': 2}: {'error': '5xEr'}")


class FixtureCallTests(unittest.TestCase):
    @patch("thecornerfc.pipeline.ingest._store_odds", return_value=3)
    def test_one_failed_odds_call_skips_only_that_fixture(self, store):
        api = Mock()
        api.get.side_effect = [["a"], BUG, ["c"]]
        with self.assertLogs("thecornerfc.pipeline.ingest", level="WARNING") as logs:
            sync_odds_fixtures.__wrapped__(api, Mock(), [1, 2, 3])
        self.assertEqual([c.args[1] for c in store.call_args_list], [["a"], ["c"]])
        self.assertIn("Skipped odds for fixture 2", logs.output[0])

    @patch("thecornerfc.pipeline.ingest._store_odds", return_value=0)
    def test_every_call_failing_still_fails_the_run(self, store):
        api = Mock()
        api.get.side_effect = [BUG, BUG]
        with self.assertLogs("thecornerfc.pipeline.ingest", level="WARNING"):
            with self.assertRaisesRegex(RuntimeError, "Every odds call failed"):
                sync_odds_fixtures.__wrapped__(api, Mock(), [1, 2])
        store.assert_not_called()

    def test_quota_exhausted_is_not_skipped(self):
        api = Mock()
        api.get.side_effect = QuotaExhausted("Daily reserve reached")
        with self.assertRaises(QuotaExhausted):
            sync_odds_fixtures.__wrapped__(api, Mock(), [1, 2])
        self.assertEqual(api.get.call_count, 1)

    @patch("thecornerfc.pipeline.ingest.upsert")
    def test_injuries_keep_the_fixtures_that_answered(self, upsert):
        api = Mock()
        player = {"player": {"id": 9, "type": "Missing Fixture", "reason": "Knee"},
                  "team": {"id": 40}, "league": {"id": 39, "season": 2026}}
        api.get.side_effect = [BUG, [player]]
        with self.assertLogs("thecornerfc.pipeline.ingest", level="WARNING"):
            sync_injuries_fixtures.__wrapped__(api, Mock(), [1, 2])
        rows = upsert.call_args.args[2]
        self.assertEqual([(r["fixture_id"], r["player_id"]) for r in rows], [(2, 9)])


if __name__ == "__main__":
    unittest.main()

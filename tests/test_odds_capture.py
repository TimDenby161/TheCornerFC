"""What the odds capture keeps (2026-11-25): the three markets something reads, only the goal
lines the bets and model tests use, and a price only when it has changed."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from thecornerfc import config
from thecornerfc.evidence import paper_evidence
from thecornerfc.pipeline import ingest


def response(bets):
    kickoff = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    return [{"fixture": {"id": 7, "date": kickoff}, "update": kickoff,
             "bookmakers": [{"id": 8, "name": "Bet365", "bets": bets}]}]


class KeptMarkets(unittest.TestCase):
    def stored(self, bets):
        with patch.object(ingest, "record_odds") as record, patch.object(ingest, "upsert"):
            ingest._store_odds(MagicMock(), response(bets))
        return [(r["bet_id"], r["selection"]) for r in record.call_args.args[1]]

    def test_double_chance_is_no_longer_kept(self):
        self.assertNotIn(12, config.ODDS_BET_IDS)
        kept = self.stored([{"id": 12, "name": "Double Chance", "values": [{"value": "Home/Draw", "odd": "1.2"}]},
                            {"id": 1, "name": "Match Winner", "values": [{"value": "Home", "odd": "2.0"}]}])
        self.assertEqual(kept, [(1, "Home")])

    def test_only_the_goal_lines_read_are_kept(self):
        values = [{"value": f"{side} {line}", "odd": "1.9"}
                  for line in ("0.5", "1.5", "2.25", "2.5", "3.5", "4.5", "5.5") for side in ("Over", "Under")]
        kept = self.stored([{"id": 5, "name": "Goals Over/Under", "values": values}])
        self.assertEqual(sorted({s.split(" ")[1] for _, s in kept}), ["1.5", "2.5", "3.5", "4.5"])
        self.assertEqual(len(kept), 8)

    def test_the_other_markets_keep_every_selection(self):
        kept = self.stored([{"id": 8, "name": "Both Teams Score", "values": [{"value": "Yes", "odd": "1.8"},
                                                                            {"value": "No", "odd": "2.0"}]}])
        self.assertEqual(kept, [(8, "Yes"), (8, "No")])


class OnlyChangedPrices(unittest.TestCase):
    def test_a_repeat_price_is_skipped_whatever_the_providers_update_time(self):
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        with patch.object(config, "READ_ONLY", False), patch.object(config, "GITHUB_ACTIONS", True):
            paper_evidence.record_odds(conn, [dict(fixture_id=1, bookmaker_id=8, bet_id=1, selection="Home",
                                                   odd=2.0, api_updated_at=datetime.now(timezone.utc))],
                                       datetime.now(timezone.utc), {1: None})
        sql = cursor.executemany.call_args.args[0]
        check = sql.split("WHERE NOT EXISTS", 1)[1]
        self.assertIn("previous.odds=%(odd)s", check)
        self.assertNotIn("provider_updated_at", check)      # the provider's time is still stored, not compared


if __name__ == "__main__":
    unittest.main()

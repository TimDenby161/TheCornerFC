import unittest
from unittest.mock import Mock, patch

from thecornerfc.ingest import sync_standings


class StandingsIngestTests(unittest.TestCase):
    @patch("thecornerfc.ingest.upsert")
    def test_missing_team_ids_are_skipped_in_both_tables(self, upsert):
        valid = {"team": {"id": 10, "name": "Club"}, "points": 7, "group": "A"}
        invalid = [{"team": {"id": None, "name": "TBD"}},
                   {"team": {}}, {"team": None}, {}]
        api, conn = Mock(), Mock()
        api.get.return_value = [{"league": {"standings": [invalid, [valid, valid]]}}]

        with self.assertLogs("thecornerfc.ingest", level="WARNING") as logs:
            sync_standings.__wrapped__(api, conn, [39], [2026])

        self.assertIn("skipped 4 entries without team IDs", logs.output[0])
        self.assertIn("league=39 season=2026", logs.output[0])
        teams, standings = upsert.call_args_list
        self.assertEqual(teams.args[2], [{"team_id": 10, "name": "Club", "logo": None}])
        self.assertEqual(teams.kwargs, {"update_cols": []})
        self.assertEqual(len(standings.args[2]), 1)
        self.assertEqual(standings.args[2][0]["team_id"], 10)
        self.assertEqual(standings.args[2][0]["points"], 7)
        conn.commit.assert_called_once()

    @patch("thecornerfc.ingest.upsert")
    def test_all_missing_ids_produce_no_insert_rows(self, upsert):
        api, conn = Mock(), Mock()
        api.get.return_value = [{"league": {"standings": [[{"team": {"id": None}}]]}}]
        with self.assertLogs("thecornerfc.ingest", level="WARNING"):
            sync_standings.__wrapped__(api, conn, [39], [2026])
        self.assertEqual([call.args[2] for call in upsert.call_args_list], [[], []])
        conn.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()

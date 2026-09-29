import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from thecornerfc import ingest


def _fixture(fid, days_ago, players=True):
    kickoff = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    return {
        "fixture": {"id": fid, "date": kickoff},
        "lineups": [{"team": {"id": 10}, "formation": "4-3-3", "coach": {"id": 5, "name": "T. Tuchel"},
                     "startXI": [{"player": {"id": 9, "name": "H. Kane", "grid": "4:2"}}]}],
        "players": [{"team": {"id": 10}, "players": [
            {"player": {"id": 9, "name": "H. Kane"},
             "statistics": [{"games": {"minutes": 90, "rating": "7.8", "substitute": False},
                             "goals": {"total": 1, "assists": None}, "cards": {"yellow": 0, "red": 0}}]},
            {"player": {"id": 11, "name": "J. Bellingham"},
             "statistics": [{"games": {"minutes": 15, "substitute": True}, "goals": {"assists": 1}}]}]}]
        if players else [],
    }


class NationalLineupsTests(unittest.TestCase):
    def test_stores_stat_lines_and_names_and_waits_for_them(self):
        conn = mock.Mock()
        conn.execute.return_value = iter([(1,), (2,)])
        api = mock.Mock()
        api.get.return_value = [_fixture(1, 1), _fixture(2, 1, players=False)]
        stored = {}
        with mock.patch.object(ingest, "upsert", side_effect=lambda c, table, rows, *a, **k: stored.setdefault(table, rows)):
            ingest.sync_national_lineups(api, conn)

        self.assertEqual(stored["national_fixture_formations"][0]["coach_name"], "T. Tuchel")
        self.assertEqual(stored["national_fixture_lineups"][0]["player_name"], "H. Kane")
        lines = {r["player_id"]: r for r in stored["national_fixture_players"]}
        self.assertEqual(set(lines), {9, 11})
        self.assertTrue(lines[9]["started"])
        self.assertEqual((lines[9]["goals"], lines[9]["rating"], lines[9]["role"]), (1, 7.8, "ST"))
        self.assertFalse(lines[11]["started"])
        self.assertEqual((lines[11]["assists"], lines[11]["player_name"]), (1, "J. Bellingham"))
        # match 2 has its line-up but no stat lines yet: not marked done inside the retry window
        done = conn.execute.call_args_list[-1].args[1][0]
        self.assertEqual(done, [1])

    def test_club_rows_have_no_name_columns(self):
        formations, lineups = [], []
        ingest._starting_xis(_fixture(1, 1), formations, lineups)
        self.assertNotIn("coach_name", formations[0])
        self.assertNotIn("player_name", lineups[0])
        self.assertNotIn("player_name", ingest._player_lines(_fixture(1, 1), {}, {})[0])


if __name__ == "__main__":
    unittest.main()

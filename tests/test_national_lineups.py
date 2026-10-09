import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from thecornerfc.pipeline import ingest


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
        with mock.patch.object(ingest, "upsert", side_effect=lambda c, table, rows, *a, **k: stored.setdefault(table, rows)), \
                mock.patch.object(ingest, "capture_official") as official:
            ingest.sync_national_lineups(api, conn)

        # each match's official XI is recorded: what its predicted XI is scored against
        self.assertEqual([c.args[1]["fixture"]["id"] for c in official.call_args_list], [1, 2])
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

    def test_national_coach_and_his_start_date(self):
        kick = datetime(2026, 9, 26, tzinfo=timezone.utc)
        conn = mock.Mock()
        conn.execute.side_effect = [
            [(10,)],                                    # national teams that played in the last year
            [(10, kick, 5)],                            # their line-ups' coaches, newest first
            [],                                         # team_coaches: none stored yet
        ]
        api = mock.Mock()
        api.get.return_value = [{"id": 5, "name": "T. Tuchel", "photo": "p.png",
                                 "career": [{"team": {"id": 10}, "start": "2025-01-01", "end": None},
                                            {"team": {"id": 157}, "start": "2023-03-24", "end": "2024-06-30"}]}]
        stored = {}
        with mock.patch.object(ingest, "upsert", side_effect=lambda c, table, rows, *a, **k: stored.setdefault(table, rows)):
            ingest.sync_national_coaches(api, conn)
        api.get.assert_called_once_with("coachs", team=10)
        row = stored["team_coaches"][0]
        self.assertEqual((row["team_id"], row["coach_id"], row["name"], row["since"]), (10, 5, "T. Tuchel", "2025-01-01"))
        self.assertNotIn("photo", row)      # the feed's photo link is never stored

    def test_club_rows_have_no_name_columns(self):
        formations, lineups = [], []
        ingest._starting_xis(_fixture(1, 1), formations, lineups)
        self.assertNotIn("coach_name", formations[0])
        self.assertNotIn("player_name", lineups[0])
        self.assertNotIn("player_name", ingest._player_lines(_fixture(1, 1), {}, {})[0])

    def test_player_lines_keep_penalties_won_scored_and_missed(self):
        f = _fixture(1, 1)
        f["players"][0]["players"][0]["statistics"][0]["penalty"] = {
            "won": 1, "commited": None, "scored": 1, "missed": 0, "saved": None}
        kane, bellingham = ingest._player_lines(f, {}, {})
        self.assertEqual((kane["penalties_won"], kane["penalties_scored"], kane["penalties_missed"]), (1, 1, 0))
        self.assertEqual((bellingham["penalties_scored"], bellingham["penalties_missed"]), (None, None))


if __name__ == "__main__":
    unittest.main()

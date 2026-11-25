import unittest
from unittest.mock import Mock, patch

from thecornerfc.pipeline import matchday

PL, CHAMPIONS_LEAGUE = 39, 2


def run_with_upcoming(upcoming):
    """run_matchday with every fetch and model step stood in; returns the fantasy capture mock."""
    conn = Mock()
    conn.execute.return_value.fetchall.return_value = upcoming
    conn.execute.return_value.__iter__ = lambda self: iter([])
    with patch.object(matchday, "refresh_national_results"), \
         patch.object(matchday, "refresh_match_states"), \
         patch.object(matchday, "national_with_odds", return_value=[]), \
         patch.object(matchday, "capture_prekickoff_lineups"), \
         patch.object(matchday, "sync_odds_fixtures"), \
         patch.object(matchday, "sync_injuries_fixtures"), \
         patch.object(matchday.predictions, "update_predictions"), \
         patch.object(matchday.match_trees, "update_safely"), \
         patch.object(matchday.betting, "place_late"), \
         patch.object(matchday.betting, "settle_bets"), \
         patch.object(matchday.fantasy_snapshots, "capture_safely") as capture:
        matchday.run_matchday(Mock(), conn)
    return capture


class FantasySnapshotTests(unittest.TestCase):
    def test_no_premier_league_match_skips_the_fantasy_step(self):
        run_with_upcoming([(1, CHAMPIONS_LEAGUE), (2, 140)]).assert_not_called()

    def test_only_the_premier_league_fixtures_are_captured(self):
        capture = run_with_upcoming([(1, CHAMPIONS_LEAGUE), (2, PL), (3, PL)])
        self.assertEqual(capture.call_args.args[1], [2, 3])


class CupInjuryTests(unittest.TestCase):
    def run_with(self, upcoming, due):
        conn = Mock()
        conn.execute.return_value.fetchall.return_value = upcoming
        conn.execute.return_value.__iter__ = lambda self: iter([])
        with patch.object(matchday, "refresh_national_results"), \
             patch.object(matchday, "refresh_match_states"), \
             patch.object(matchday, "national_with_odds", return_value=[]), \
             patch.object(matchday, "capture_prekickoff_lineups"), \
             patch.object(matchday, "sync_odds_fixtures"), \
             patch.object(matchday, "cup_injury_due", return_value=due) as cup_due, \
             patch.object(matchday, "player_clubs", return_value={33}), \
             patch.object(matchday, "sync_injuries_fixtures") as sync, \
             patch.object(matchday.predictions, "update_predictions"), \
             patch.object(matchday.match_trees, "update_safely"), \
             patch.object(matchday.betting, "place_late"), \
             patch.object(matchday.betting, "settle_bets"), \
             patch.object(matchday.fantasy_snapshots, "capture_safely"):
            matchday.run_matchday(Mock(), conn)
        return cup_due, sync

    def test_a_champions_league_tie_gets_its_own_injury_list_for_the_clubs_we_rank(self):
        _, sync = self.run_with([(1, CHAMPIONS_LEAGUE), (2, PL)], [1])
        self.assertEqual([c.args[2:] for c in sync.call_args_list], [([2],), ([1], {33})])

    def test_no_cup_tie_in_the_window_asks_for_nothing_more(self):
        cup_due, sync = self.run_with([(2, PL)], [])
        cup_due.assert_not_called()
        self.assertEqual([c.args[2:] for c in sync.call_args_list], [([2],)])

    def test_each_cup_tie_is_due_in_one_half_hour_only(self):
        conn = Mock()
        conn.execute.return_value = iter([(7,)])
        now = matchday.datetime(2026, 11, 25, 18, 0, tzinfo=matchday.timezone.utc)
        self.assertEqual(matchday.cup_injury_due(conn, now), [7])
        params = conn.execute.call_args.args[1]
        self.assertEqual(params["until"] - params["from"], matchday.timedelta(minutes=30))
        self.assertEqual(params["cups"], matchday.config.CUP_INJURY_LEAGUES)


class RecentFixturesTests(unittest.TestCase):
    def test_a_game_still_marked_postponed_just_before_kick_off_is_fetched_and_the_site_rows_refreshed(self):
        conn = Mock()
        conn.execute.return_value.fetchall.return_value = []
        conn.execute.return_value.__iter__ = lambda self: iter([(7,), (8,)])
        api = Mock()
        with patch.object(matchday, "refresh_national_results"), \
             patch.object(matchday, "_store_fixtures"), \
             patch.object(matchday, "refresh_match_states") as refresh, \
             patch.object(matchday, "national_with_odds", return_value=[]), \
             patch.object(matchday, "capture_prekickoff_lineups"), \
             patch.object(matchday.betting, "settle_bets"):
            matchday.run_matchday(api, conn)
        sql = conn.execute.call_args_list[0].args[0]
        self.assertIn("status_short = 'PST'", sql)
        api.get.assert_any_call("fixtures", ids="7-8")
        refresh.assert_called_once_with(conn, [7, 8])


if __name__ == "__main__":
    unittest.main()

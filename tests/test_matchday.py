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


if __name__ == "__main__":
    unittest.main()

from datetime import datetime, timezone
import unittest
from unittest.mock import Mock, patch

from thecornerfc.pipeline import matchday

NOW = datetime(2026, 10, 3, 14, tzinfo=timezone.utc)


class PrekickoffLineupTests(unittest.TestCase):
    def test_batches_of_twenty_capped_and_each_fixture_captured(self):
        conn, api = Mock(), Mock()
        conn.execute.return_value = [(i,) for i in range(1, 246)]
        api.get.side_effect = lambda endpoint, ids: [{'fixture': {'id': int(x)}} for x in ids.split('-')]
        with patch.object(matchday, 'capture_official') as capture:
            matchday.capture_prekickoff_lineups(api, conn, NOW)
        self.assertEqual(api.get.call_count, matchday.MAX_LINEUP_CALLS)
        self.assertEqual(capture.call_count, 20 * matchday.MAX_LINEUP_CALLS)
        self.assertEqual(api.get.call_args_list[0].kwargs['ids'].split('-')[:2], ['1', '2'])
        self.assertEqual(conn.commit.call_count, matchday.MAX_LINEUP_CALLS)

    def test_no_due_fixtures_makes_no_calls(self):
        conn, api = Mock(), Mock()
        conn.execute.return_value = []
        matchday.capture_prekickoff_lineups(api, conn, NOW)
        api.get.assert_not_called()


if __name__ == '__main__':
    unittest.main()

from datetime import datetime, timezone
from decimal import Decimal
import unittest
from unittest.mock import Mock

from thecornerfc.export import _player_movement


def conn_with(view, rows=()):
    conn = Mock()
    regclass, movement = Mock(), Mock()
    regclass.fetchone.return_value = (view,)
    movement.__iter__ = Mock(return_value=iter(rows))
    conn.execute.side_effect = [regclass, movement]
    return conn


class PlayerMovementExportTests(unittest.TestCase):
    def test_nothing_before_the_migration(self):
        conn = conn_with(None)
        self.assertEqual(_player_movement(conn, [1]), {})
        self.assertEqual(conn.execute.call_count, 1)

    def test_rows_grouped_per_player_with_same_model_baselines_only(self):
        now = datetime(2026, 9, 27, 3, tzinfo=timezone.utc)
        base = datetime(2026, 9, 20, 3, tzinfo=timezone.utc)
        conn = conn_with("player_rating_movement", [(7, now, "7d", Decimal("1.25"), 12, base)])
        out = _player_movement(conn, [7])
        self.assertEqual(out[7]["captured_at"], now.isoformat())
        self.assertEqual(out[7]["rows"], [["7d", 1.2, 12, base.isoformat()]])
        sql = conn.execute.call_args_list[1][0][0]
        self.assertIn("not model_changed", sql)
        self.assertIn("baseline_at is not null", sql)


if __name__ == "__main__":
    unittest.main()

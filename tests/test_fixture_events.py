"""Match events kept from the /fixtures?ids= responses (T-074): the migration, the rows and their
storage."""
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from thecornerfc.pipeline import ingest

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "db/migrations/20261030_fixture_events.sql"

ITEM = {"fixture": {"id": 7}, "events": [
    {"time": {"elapsed": 23, "extra": None}, "team": {"id": 1}, "player": {"id": 10}, "assist": {"id": 11},
     "type": "Goal", "detail": "Normal Goal"},
    {"time": {"elapsed": 61, "extra": None}, "team": {"id": 2}, "player": {"id": 20}, "assist": {"id": 99},
     "type": "subst", "detail": "Substitution 1"},
    {"time": {"elapsed": 90, "extra": 3}, "team": {"id": 1}, "player": {"id": None}, "assist": {"id": None},
     "type": "Card", "detail": "Yellow Card"},
]}


class MigrationTest(unittest.TestCase):
    def test_it_is_in_the_schema_word_for_word(self):
        self.assertIn(MIGRATION.read_text(), (ROOT / "db/schema.sql").read_text())

    def test_the_public_key_cannot_reach_it(self):
        sql = MIGRATION.read_text()
        self.assertIn("ALTER TABLE public.fixture_events ENABLE ROW LEVEL SECURITY;", sql)
        self.assertIn("REVOKE ALL ON public.fixture_events FROM %I", sql)


class EventRowsTest(unittest.TestCase):
    def test_each_event_in_the_feeds_order_with_its_minute(self):
        rows = ingest._event_rows(ITEM, set())
        self.assertEqual([r["seq"] for r in rows], [0, 1, 2])
        self.assertEqual(rows[0], {"fixture_id": 7, "seq": 0, "team_id": 1, "player_id": 10, "assist_id": 11,
                                   "elapsed": 23, "extra": None, "type": "Goal", "detail": "Normal Goal"})
        self.assertEqual((rows[2]["elapsed"], rows[2]["extra"], rows[2]["player_id"]), (90, 3, None))

    def test_a_suppressed_player_is_stored_as_null_and_the_event_kept(self):
        rows = ingest._event_rows(ITEM, {11, 99})
        self.assertEqual(len(rows), 3)
        self.assertEqual((rows[0]["player_id"], rows[0]["assist_id"]), (10, None))
        self.assertIsNone(rows[1]["assist_id"])

    def test_no_events_no_rows(self):
        self.assertEqual(ingest._event_rows({"fixture": {"id": 7}}, set()), [])


class StoreEventsTest(unittest.TestCase):
    def test_nothing_is_written_before_the_table_exists(self):
        conn = Mock()
        conn.execute.return_value.fetchone.return_value = (None,)
        with patch.object(ingest, "upsert") as upsert:
            ingest._store_events(conn, [7], ingest._event_rows(ITEM, set()))
        upsert.assert_not_called()
        self.assertEqual(conn.execute.call_count, 1)

    def test_a_fixtures_events_are_replaced_whole(self):
        conn = Mock()
        conn.execute.return_value.fetchone.return_value = ("fixture_events",)
        rows = ingest._event_rows(ITEM, set())
        with patch.object(ingest, "upsert") as upsert:
            ingest._store_events(conn, [7], rows)
        self.assertIn("delete from fixture_events", conn.execute.call_args_list[1].args[0])
        self.assertEqual(conn.execute.call_args_list[1].args[1], [[7]])
        upsert.assert_called_once_with(conn, "fixture_events", rows, ["fixture_id", "seq"], touch_updated_at=False)


if __name__ == "__main__":
    unittest.main()

import unittest
from unittest.mock import MagicMock, patch

from thecornerfc.pipeline.db import upsert


def sql_of(**kwargs):
    conn = MagicMock()
    with patch("thecornerfc.pipeline.db.config.require_db_write"):
        upsert(conn, "players", [{"player_id": 1, "name": "A", "age": 30}], ["player_id"], **kwargs)
    return conn.cursor.return_value.__enter__.return_value.executemany.call_args.args[0]


class UpsertTests(unittest.TestCase):
    def test_unchanged_rows_are_not_rewritten(self):
        sql = sql_of()
        self.assertIn("insert into players as t (player_id, name, age)", sql)
        self.assertIn("set name = excluded.name, age = excluded.age, updated_at = now() "
                      "where row(t.name, t.age) is distinct from row(excluded.name, excluded.age)", sql)

    def test_named_update_columns_alone_decide_a_change(self):
        sql = sql_of(update_cols=["age"], touch_updated_at=False)
        self.assertTrue(sql.endswith("do update set age = excluded.age where row(t.age) is distinct from row(excluded.age)"))

    def test_no_update_columns_do_nothing(self):
        self.assertTrue(sql_of(update_cols=[]).endswith("on conflict (player_id) do nothing"))


if __name__ == "__main__":
    unittest.main()

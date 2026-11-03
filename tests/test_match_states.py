import json
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from thecornerfc.publish import export, site_matches

KICKOFF = datetime(2026, 11, 3, 19, 45, tzinfo=timezone.utc)


def row(fid, status, hg=None, ag=None):
    """A site.matches row in SITE_MATCH_FIELDS order, with a chance in it to tell the copies apart."""
    r = [None] * len(export.SITE_MATCH_FIELDS)
    for name, value in (("id", fid), ("kickoff", KICKOFF.isoformat()), ("status", status), ("hg", hg), ("ag", ag),
                        ("p_home", 0.33)):
        r[export.SITE_MATCH_FIELDS.index(name)] = value
    return r


def connection(fixtures, stored):
    """fixtures: rows of the fixtures query; stored: (fixture_id, data, data_free, data_locked)."""
    conn = MagicMock()
    conn.execute.side_effect = lambda sql, args=None: MagicMock(
        __iter__=lambda self: iter(fixtures),
        fetchall=lambda: [tuple(json.loads(json.dumps(x)) for x in r) for r in stored])
    return conn


class RefreshMatchStatesTests(unittest.TestCase):
    def test_a_stale_postponed_row_takes_the_live_status_and_score_in_every_copy(self):
        locked = row(1563787, "PST")
        locked[export.SITE_MATCH_FIELDS.index("p_home")] = None
        conn = connection([(1563787, KICKOFF, "2H", 1, 0, None, None)],
                          [(1563787, row(1563787, "PST"), row(1563787, "PST"), locked)])
        with patch.object(site_matches.config, "require_db_write"):
            self.assertEqual(export.refresh_match_states(conn, [1563787]), 1)
        cur = conn.cursor.return_value.__enter__.return_value
        sql, args = cur.execute.call_args.args
        self.assertIn("update site.matches", sql)
        self.assertEqual(args[:2], [KICKOFF.isoformat(), "2H"])
        data, free, locked_out = (json.loads(a) for a in args[2:5])
        at = export.SITE_MATCH_FIELDS.index
        for copy in (data, free, locked_out):
            self.assertEqual((copy[at("status")], copy[at("hg")], copy[at("ag")]), ("2H", 1, 0))
        self.assertEqual(data[at("p_home")], 0.33)
        self.assertIsNone(locked_out[at("p_home")])   # the blanked copy stays blanked
        self.assertEqual(args[5], 1563787)

    def test_a_row_already_up_to_date_is_not_written(self):
        conn = connection([(1, KICKOFF, "FT", 2, 1, None, None)], [(1, row(1, "FT", 2, 1), row(1, "FT", 2, 1), row(1, "FT", 2, 1))])
        with patch.object(site_matches.config, "require_db_write"):
            self.assertEqual(export.refresh_match_states(conn, [1]), 0)
        conn.cursor.return_value.__enter__.return_value.execute.assert_not_called()

    def test_nothing_is_written_on_a_read_only_run_or_with_no_matches(self):
        conn = MagicMock()
        with patch.object(site_matches.config, "require_db_write", side_effect=export.config.SafetyError("read-only")):
            self.assertEqual(export.refresh_match_states(conn, [1]), 0)
        self.assertEqual(export.refresh_match_states(conn, []), 0)
        conn.execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()

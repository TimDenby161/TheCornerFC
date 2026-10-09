import unittest
from datetime import datetime, timezone
from unittest.mock import Mock

from thecornerfc.publish.export import site_freshness


def result(row):
    return Mock(fetchone=lambda: row)


class SiteFreshnessTests(unittest.TestCase):
    def test_reports_stored_timestamps_and_latest_match_model(self):
        t = datetime(2026, 9, 27, 9, 30, tzinfo=timezone.utc)
        conn = Mock()
        conn.execute.side_effect = [
            result((t,)), result((t,)), result((t,)),
            result(("model_versions",)),
            result(("match-prediction", "a" * 40, t)),
        ]
        out = site_freshness(conn)
        self.assertEqual(out["predictions"], t.isoformat())
        self.assertEqual(out["injuries"], t.isoformat())
        self.assertEqual(out["odds"], t.isoformat())
        self.assertEqual(out["model"], {"name": "match-prediction", "code": "aaaaaaa", "registered": t.isoformat()})

    def test_leaves_out_what_the_database_does_not_have(self):
        conn = Mock()
        conn.execute.side_effect = [result((None,)), result((None,)), result((None,)), result((None,))]
        self.assertEqual(site_freshness(conn), {})

    def test_no_model_entry_when_none_registered(self):
        t = datetime(2026, 9, 27, tzinfo=timezone.utc)
        conn = Mock()
        conn.execute.side_effect = [result((t,)), result((None,)), result((None,)),
                                    result(("model_versions",)), result(None)]
        self.assertEqual(site_freshness(conn), {"predictions": t.isoformat()})


if __name__ == "__main__":
    unittest.main()

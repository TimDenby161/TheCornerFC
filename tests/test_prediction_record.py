import math
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from thecornerfc.publish import site_record

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "db/migrations/20261021_prediction_record.sql"
T1 = datetime(2026, 9, 26, 15, tzinfo=timezone.utc)
T2 = datetime(2026, 9, 27, 15, tzinfo=timezone.utc)


def snapshot(fixture, p, outcome, when, actual, version="mv_a"):
    """A row as evaluation.load_matches gives it: the snapshot's columns, then its scoring."""
    return {"fixture_id": fixture, "effective_at": when, "captured_at": when.replace(hour=10), "league_id": 39,
            "home_team_id": 1, "away_team_id": 2, "home_xg": 1.6234, "away_xg": 0.9, "likely_score": "1-0",
            "content_hash": f"h{fixture}", "model_version_id": version, "probabilities": p, "outcome": outcome,
            "actual_score": actual}


def conn_with(table=True, names=(("mv_a", "match-prediction", "9afa9ed1234567890abcdef1234567890abcdef0"),)):
    def execute(sql, params=None):
        if "to_regclass(%s)" in sql:
            return Mock(fetchone=lambda: (params[0] if table else None,))
        if "from model_versions where model_version_id" in sql:
            return Mock(fetchall=lambda: list(names))
        return Mock(fetchone=lambda: (0,))
    conn = Mock()
    conn.execute.side_effect = execute
    return conn


class PredictionRecordTests(unittest.TestCase):
    """Every finished match's locked prediction, stored for the Prediction record page
    (site.prediction_record, read through site_prediction_record)."""

    def test_the_migration_is_in_the_schema_and_shut_to_the_public_key(self):
        sql = MIGRATION.read_text()
        self.assertIn(sql, (ROOT / "db/schema.sql").read_text())
        self.assertIn("ALTER TABLE site.prediction_record ENABLE ROW LEVEL SECURITY;", sql)
        self.assertIn("REVOKE ALL ON site.prediction_record FROM PUBLIC;", sql)
        self.assertIn("SECURITY DEFINER SET search_path = ''", sql)
        self.assertIn("LIMIT least(greatest(coalesce(p_limit, 100), 0), 500)", sql)
        # the columns the export writes are the table's, in its order
        table = sql.split("CREATE TABLE IF NOT EXISTS site.prediction_record (")[1].split(");")[0]
        columns = [line.split()[0] for line in table.strip().splitlines()]
        self.assertEqual(columns, site_record.PREDICTION_RECORD_COLUMNS)

    def test_rows_are_scored_as_the_methodology_record_scores_them_oldest_first(self):
        rows = site_record.prediction_record_rows(conn_with(), [
            snapshot(8, [0.2, 0.3, 0.5], 1, T2, "1-1"), snapshot(7, [0.6, 0.25, 0.15], 0, T1, "2-0", version="mv_b")])
        late, early = rows[1], rows[0]
        r = dict(zip(site_record.PREDICTION_RECORD_COLUMNS, early))
        self.assertEqual((r["fixture_id"], r["kickoff"], r["league_id"], r["home_id"], r["away_id"]), (7, T1, 39, 1, 2))
        self.assertEqual((r["p_home"], r["p_draw"], r["p_away"], r["likely"], r["home_xg"]), (0.6, 0.25, 0.15, "1-0", 1.62))
        self.assertEqual((r["hg"], r["ag"], r["outcome"], r["right_call"]), (2, 0, 0, True))
        self.assertEqual(r["log_loss"], round(-math.log(0.6), 4))
        self.assertEqual((r["captured_at"], r["version"], r["hash"]), (T1.replace(hour=10), "mv_b", "h7"))   # an unnamed version by id
        r = dict(zip(site_record.PREDICTION_RECORD_COLUMNS, late))
        self.assertEqual((r["outcome"], r["right_call"], r["version"]), (1, False, "match-prediction 9afa9ed"))

    def test_only_changed_rows_are_written_once_there_is_a_table(self):
        conn = conn_with()
        cur = MagicMock()
        cur.__enter__.return_value = cur
        cur.execute.return_value.fetchone.return_value = (0,)
        conn.cursor.return_value = cur
        with patch.object(site_record.config, "require_db_write"):
            rows = site_record.store_prediction_record(conn, [snapshot(7, [0.6, 0.25, 0.15], 0, T1, "2-0")])
        sent = [c[0][0].split("\n")[0] for c in cur.execute.call_args_list]
        self.assertTrue(any(x.startswith("delete from site.prediction_record t where not exists") for x in sent))
        self.assertTrue(any(x.startswith("insert into site.prediction_record as t (fixture_id, kickoff,") for x in sent))
        cur.copy.return_value.__enter__.return_value.write_row.assert_called_once_with(rows[0])
        conn.commit.assert_called_once()

    def test_nothing_is_stored_on_a_read_only_run_or_before_the_migration(self):
        conn = conn_with()
        with patch.object(site_record.config, "require_db_write", side_effect=site_record.config.SafetyError("read-only")):
            self.assertEqual(len(site_record.store_prediction_record(conn, [snapshot(7, [0.6, 0.25, 0.15], 0, T1, "2-0")])), 1)
        conn.cursor.assert_not_called()
        conn = conn_with(table=False)
        with patch.object(site_record.config, "require_db_write"):
            site_record.store_prediction_record(conn, [snapshot(7, [0.6, 0.25, 0.15], 0, T1, "2-0")])
        conn.cursor.assert_not_called()
        conn.commit.assert_not_called()


if __name__ == "__main__":
    unittest.main()

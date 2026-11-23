"""The match-day step that scores Beat the Model (thecornerfc/pipeline/beat_the_model.py)."""
import unittest
from unittest.mock import MagicMock, patch

from thecornerfc import config
from thecornerfc.pipeline import beat_the_model


def conn_answering(*answers):
    conn = MagicMock()
    conn.execute.return_value.fetchone.side_effect = list(answers)
    return conn


class ScoreTest(unittest.TestCase):
    def test_marks_and_commits(self):
        conn = conn_answering(("btm_score()",), (12,))
        with patch.object(config, "require_db_write"):
            self.assertEqual(beat_the_model.score_safely(conn), 12)
        self.assertIn("public.btm_score()", conn.execute.call_args_list[-1].args[0])
        conn.commit.assert_called_once()

    def test_skips_before_the_migration(self):
        conn = conn_answering((None,))
        with patch.object(config, "require_db_write"):
            self.assertIsNone(beat_the_model.score_safely(conn))
        self.assertEqual(conn.execute.call_count, 1)
        conn.commit.assert_not_called()

    def test_a_failure_is_rolled_back_and_does_not_stop_the_run(self):
        conn = conn_answering(("btm_score()",))
        conn.execute.side_effect = [conn.execute.return_value, RuntimeError("deadlock")]
        with patch.object(config, "require_db_write"), self.assertLogs(beat_the_model.log, "ERROR"):
            self.assertIsNone(beat_the_model.score_safely(conn))
        conn.rollback.assert_called_once()

    def test_read_only_runs_do_not_touch_the_database(self):
        conn = MagicMock()
        with patch.object(config, "require_db_write", side_effect=config.SafetyError("read-only")):
            self.assertIsNone(beat_the_model.score_safely(conn))
        conn.execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()

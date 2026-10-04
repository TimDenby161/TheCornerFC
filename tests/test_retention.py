"""Retention and removal: old injury reasons are blanked, and a person removed on request is
deleted, listed in suppressed.json and never stored again (README: Removing a person)."""
import contextlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from thecornerfc import export, retention, suppression

ROOT = Path(__file__).resolve().parents[1]
NONE = {'players': set(), 'coaches': set()}


class InjuryReasonTests(unittest.TestCase):
    def test_blanks_only_old_medical_reasons(self):
        conn = mock.MagicMock()
        conn.execute.return_value.rowcount = 5
        self.assertEqual(retention.prune_injury_reasons(conn), 5)
        sql, params = conn.execute.call_args.args
        self.assertIn('set reason = null', sql)
        self.assertIn('max(season)', sql)
        self.assertEqual(params, (retention.NOT_MEDICAL, retention.INJURY_REASON_SEASONS))
        conn.commit.assert_called_once()

    def test_keeps_every_reason_the_export_treats_as_not_medical(self):
        self.assertEqual(set(retention.NOT_MEDICAL), export.ONE_MATCH_REASONS)
        self.assertTrue(export.BAN_REASONS <= set(retention.NOT_MEDICAL))

    def test_a_failure_does_not_fail_the_run(self):
        conn = mock.MagicMock()
        conn.execute.side_effect = RuntimeError('boom')
        retention.run(conn)                      # no exception
        self.assertTrue(conn.rollback.called)


class SuppressionTests(unittest.TestCase):
    def test_shipped_list_is_valid(self):
        self.assertEqual(set(suppression.load()), {'players', 'coaches'})

    def test_nothing_suppressed_changes_nothing(self):
        rows = [{'player_id': 1}]
        self.assertIs(suppression.keep_rows(rows, NONE), rows)

    def test_suppressed_player_is_never_stored(self):
        rows = [{'player_id': 1, 'name': 'A'}, {'player_id': 2, 'name': 'B'}, {'team_id': 9}]
        kept = suppression.keep_rows(rows, {'players': {2}, 'coaches': set()})
        self.assertEqual(kept, [{'player_id': 1, 'name': 'A'}, {'team_id': 9}])

    def test_suppressed_coach_is_blanked_but_the_team_row_stays(self):
        rows = [{'team_id': 9, 'coach_id': 7, 'name': 'Coach', 'photo': 'x', 'since': '2026-01-01'}]
        kept = suppression.keep_rows(rows, {'players': set(), 'coaches': {7}})
        self.assertEqual(kept, [{'team_id': 9, 'coach_id': None, 'name': None, 'photo': None, 'since': '2026-01-01'}])

    def _conn(self, counts, refuse=()):
        conn = mock.MagicMock()
        conn.transaction.return_value = contextlib.nullcontext()

        def execute(sql, params=()):
            result = mock.MagicMock()
            if 'information_schema' in sql:
                result.__iter__.return_value = iter([(t,) for t in counts])
            elif sql.startswith('select count'):
                result.fetchone.return_value = (counts[sql.split()[3]],)
            elif any(t in sql for t in refuse):
                raise RuntimeError('Player rating history is append only')
            return result
        conn.execute.side_effect = execute
        return conn

    def test_dry_run_counts_and_changes_nothing(self):
        conn = self._conn({'injuries': 3, 'players': 1, 'odds': 0})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 's.json'
            path.write_text('{"players": [], "coaches": []}')
            report = suppression.remove(conn, 'player', 42, path=path)
            self.assertEqual(report, [('injuries', 3, 'found'), ('players', 1, 'found')])
            self.assertEqual(json.loads(path.read_text()), {'players': [], 'coaches': []})
        self.assertFalse(any(c.args[0].startswith('delete') for c in conn.execute.call_args_list))
        conn.commit.assert_not_called()

    def test_apply_deletes_lists_the_person_and_reports_what_refused(self):
        conn = self._conn({'players': 1, 'player_rating_history': 4}, refuse=('player_rating_history',))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 's.json'
            path.write_text('{"players": [7], "coaches": []}')
            report = suppression.remove(conn, 'player', 42, apply=True, path=path)
            self.assertEqual(json.loads(path.read_text())['players'], [7, 42])
        self.assertEqual(sorted(report), [('player_rating_history', 4, 'kept: Player rating history is append only'),
                                          ('players', 1, 'deleted')])
        conn.commit.assert_called_once()


if __name__ == '__main__':
    unittest.main()

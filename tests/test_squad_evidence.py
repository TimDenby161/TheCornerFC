from datetime import datetime, timezone
from pathlib import Path
import unittest
from unittest.mock import MagicMock, Mock, patch

from thecornerfc import config
from thecornerfc.evidence import player_history, squad_evidence as se

NOW = datetime(2026, 9, 28, 3, tzinfo=timezone.utc)
ITEMS = [{'team': {'id': 5}, 'players': [
    {'id': 11, 'name': 'B', 'age': 24, 'number': 9, 'position': 'Attacker'},
    {'id': 10, 'name': 'A', 'age': 30, 'number': 1, 'position': 'Goalkeeper'}]}]


class SquadEvidenceTests(unittest.TestCase):
    def test_squad_players_sorted_mapped_and_ignore_age_number(self):
        players = se.squad_players(ITEMS, {10: 900})
        self.assertEqual([p['api_player'] for p in players], [10, 11])
        self.assertEqual([p['player'] for p in players], [900, None])
        older = [{'players': [dict(p, age=p['age'] + 1, number=99) for p in ITEMS[0]['players']]}]
        self.assertEqual(se.squad_players(older, {10: 900}), players)

    def test_capture_squad_only_when_changed(self):
        players = se.squad_players(ITEMS, {})
        conn = Mock()
        with patch.object(config, 'require_db_write'):
            conn.execute.return_value.fetchone.return_value = (se._digest(players),)
            self.assertFalse(se.capture_squad(conn, 5, players, NOW))
            conn.execute.return_value.fetchone.return_value = ('other',)
            self.assertTrue(se.capture_squad(conn, 5, players, NOW))
            self.assertIn('INSERT INTO squad_snapshots', conn.execute.call_args[0][0])
            self.assertFalse(se.capture_squad(Mock(), 5, [], NOW))

    def test_transfer_rows_keep_recent_deduplicated_events(self):
        move = {'date': '2026-08-30', 'type': 'Loan', 'teams': {'in': {'id': 7}, 'out': {'id': 5}}}
        items = [{'player': {'id': 11, 'name': 'B'}, 'transfers': [move, dict(move), {'date': '2019-07-01', 'teams': {}}]},
                 {'player': {}, 'transfers': [move]}]
        rows = se.transfer_rows(items, NOW)
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]['team_in'], rows[0]['team_out'], rows[0]['transfer_date']), (7, 5, '2026-08-30'))
        self.assertEqual(rows[0]['content_hash'], se.transfer_rows(items, datetime(2027, 1, 1, tzinfo=timezone.utc))[0]['content_hash'])

    def test_teams_due_prefers_never_fetched_then_changed_squads(self):
        t0, t1, t2 = (datetime(2026, 9, d, tzinfo=timezone.utc) for d in (20, 25, 27))
        conn = Mock()
        conn.execute.return_value.fetchall.return_value = [
            (1, t1, t2),     # squad changed after last fetch
            (2, t2, t1),     # unchanged since fetch
            (3, None, t0),   # never fetched
            (4, t0, t1)]     # changed, fetched longest ago
        self.assertEqual(se.teams_due(conn, [1, 2, 3, 4]), [3, 4, 1])
        self.assertEqual(se.teams_due(conn, [1, 2, 3, 4], limit=2), [3, 4])

    def test_player_capture_writes_components(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.side_effect = [None, (7,)]
        conn.execute.return_value.__iter__.return_value = iter([])
        with patch.object(config, 'require_db_write'), patch('thecornerfc.evidence.player_history.register_version', return_value='mv'):
            player_history.capture(conn, [(1, 60., 'CM', 100), (2, 50., 'CB', 90)], [(1, 2026, 60., 100, 10)],
                                   {1: (72.5, 910., 61.2, 63.4)})
        rows = conn.cursor.return_value.__enter__.return_value.executemany.call_args[0][1]
        self.assertEqual(rows[0][-4:], (72.5, 910., 61.2, 63.4))
        self.assertEqual(rows[1][-4:], (None, None, None, None))

    def test_schema_contains_migration(self):
        root = Path(__file__).resolve().parents[1]
        self.assertIn((root / 'db/migrations/20260927_squad_transfer_capture.sql').read_text(),
                      (root / 'db/schema.sql').read_text())


if __name__ == '__main__':
    unittest.main()

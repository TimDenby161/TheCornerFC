import unittest
from unittest.mock import MagicMock, patch

from thecornerfc import player_ratings


def write(history, table_exists=True):
    """Runs player_ratings._write with nothing but the reconstructed history; returns the text
    copied into reconstructed_lineups (None if it wasn't written)."""
    copies = {}
    cur = MagicMock()

    def execute(sql, *args):
        result = MagicMock()
        result.fetchone.return_value = ("reconstructed_lineups" if table_exists else None,)
        return result
    cur.execute.side_effect = execute

    def copy(sql):
        cp = MagicMock()
        cp.__enter__.return_value.write.side_effect = lambda text: copies.__setitem__(sql.split()[1], text)
        return cp
    cur.copy.side_effect = copy
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    with patch.object(player_ratings.player_history, "capture"):
        player_ratings._write(conn, [], None, [], [], [], [(1, 2026, 60.0, 900, None)], {}, {}, None, history)
    return copies.get("reconstructed_lineups")


class ReconstructedLineupWriteTests(unittest.TestCase):
    def test_one_row_per_team_with_players_and_roles_in_slot_order(self):
        xi = [(10, "GK"), (11, "CB"), (12, None)]
        self.assertEqual(write([(7, 1, xi)]), "7\t1\t{10,11,12}\t{GK,CB,NULL}\n")

    def test_skipped_until_the_migration_is_applied(self):
        self.assertIsNone(write([(7, 1, [(10, "GK")])], table_exists=False))


if __name__ == "__main__":
    unittest.main()

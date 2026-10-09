import unittest
from collections import Counter
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, Mock, patch

from thecornerfc.evidence import evaluation
from thecornerfc.publish import export
from thecornerfc.models import national_lineups as nl

NOW = datetime(2026, 10, 7, 12, tzinfo=timezone.utc)
ROLES = ["GK", "RB", "CB", "CB", "LB", "DM", "DM", "RW", "AM", "LW", "ST"]      # a 4-2-3-1's XI, players 1-11


def conn_with(fixtures, lineups=(), players=(), formations=(), tables=True):
    """A connection holding the national tables' rows, by the table each query reads."""
    def execute(sql, params=None):
        if "to_regclass" in sql:
            return Mock(fetchone=lambda: ("x" if tables else None,))
        rows = (lineups if "from national_fixture_lineups" in sql else players if "from national_fixture_players" in sql
                else formations if "from national_fixture_formations" in sql else fixtures)
        result = MagicMock(fetchall=lambda: list(rows))
        result.__iter__.side_effect = lambda: iter(list(rows))
        return result
    conn = MagicMock()
    conn.execute.side_effect = execute
    return conn


def played(fid, team, ids, roles=ROLES):
    return [(fid, team, p, role, f"Player {p}") for p, role in zip(ids, roles)]


class PredictTests(unittest.TestCase):
    def test_each_slot_goes_to_the_most_minutes_in_that_role(self):
        roles = {p: Counter({r: 3}) for p, r in zip(range(1, 12), ROLES)}
        roles[12] = Counter({"ST": 3})
        recent = [{**{p: 90 for p in range(1, 12)}, 12: 20}, {**{p: 90 for p in range(1, 11)}, 12: 90}]
        shape, minutes, xi = nl.predict(recent, ["4-2-3-1", "4-2-3-1"], roles, {})
        self.assertEqual(shape, "4-2-3-1")
        self.assertEqual(minutes[12], 110)
        self.assertEqual(dict(xi)[12], "ST")              # 110 minutes up front against player 11's 90
        self.assertNotIn(11, dict(xi))
        self.assertEqual(sorted(dict(xi).values()), sorted(ROLES))

    def test_without_a_formation_the_keeper_and_ten_outfielders_with_most_minutes(self):
        broad = {1: "G", 13: "G", **{p: "M" for p in range(2, 13)}}
        recent = [{1: 90, 13: 45, **{p: 90 - p for p in range(2, 13)}}]
        shape, _, xi = nl.predict(recent, [], {p: Counter() for p in broad}, broad)
        self.assertIsNone(shape)
        self.assertEqual([p for p, _ in xi], list(range(1, 12)))        # one keeper; player 12 has the fewest minutes
        self.assertEqual(xi[0][1], "GK")


class ReplayTests(unittest.TestCase):
    PAST, NEXT = NOW - timedelta(days=30), NOW + timedelta(days=2)

    def test_an_upcoming_match_is_predicted_from_the_matches_before_it(self):
        fixtures = [(1, self.PAST, 5, 10, 20, False), (2, self.NEXT, 5, 20, 10, True)]
        lineups = played(1, 10, range(1, 12))
        stat_lines = [(1, 10, p, 90, "G" if p == 1 else "M", f"Player {p}") for p in range(1, 12)] \
            + [(1, 10, 12, 30, "F", "Sub"), (1, 10, 13, 0, "F", "Unused")]
        predicted, names = nl.replay(conn_with(fixtures, lineups, stat_lines, [(1, 10, "4-2-3-1")]), NOW)
        self.assertEqual(set(predicted), {(2, 10)})                   # team 20 has no match with a line-up
        m = predicted[2, 10]
        self.assertEqual((m["kickoff"], m["league"], m["opponent"], m["home"], m["formation"]),
                         (self.NEXT, 5, 20, False, "4-2-3-1"))
        self.assertEqual(sorted(m["xi"]), sorted(zip(range(1, 12), ROLES)))
        self.assertEqual((m["minutes"][12], 13 in m["minutes"]), (30, False))
        self.assertEqual(names[12], "Sub")

    def test_a_starter_with_no_stat_line_counts_a_full_match(self):
        fixtures = [(1, self.PAST, 10, 10, 20, False), (2, self.NEXT, 10, 10, 20, True)]
        predicted, _ = nl.replay(conn_with(fixtures, played(1, 10, range(1, 12))), NOW)
        self.assertEqual(predicted[2, 10]["minutes"][5], nl.FULL_MATCH)
        self.assertEqual(len(predicted[2, 10]["xi"]), 11)


class CaptureTests(unittest.TestCase):
    def test_one_snapshot_per_team_under_its_own_lineup_version(self):
        m = {"kickoff": NOW + timedelta(days=2), "league": 5, "opponent": 20, "home": True, "formation": "4-2-3-1",
             "minutes": {p: 90 for p in range(1, 13)}, "xi": list(zip(range(1, 12), ROLES))}
        with patch.object(nl, "register_model_version", return_value="mv_national") as register, \
                patch.object(nl.lineup_snapshots, "append") as append:
            self.assertEqual(nl.capture(Mock(), {(2, 10): m}, NOW), 1)
        self.assertEqual(register.call_args.args[1:], (nl.ModelType.LINEUP, "national-recent-minutes-lineup"))
        table, row = append.call_args.args[1:]
        self.assertEqual((table, row["fixture_id"], row["team_id"], row["model_version_id"], row["source"]),
                         ("lineup_prediction_snapshots", 2, 10, "mv_national", "prospective"))
        self.assertEqual(row["seconds_to_kickoff"], 2 * 86400)
        self.assertEqual(row["players"][0], {"player": 1, "predicted_starter": True, "role": "GK", "line": "GK",
                                             "player_rating": None, "availability_state": "not_reported",
                                             "start_probability": None})
        self.assertEqual(row["selection_inputs"]["unpicked"], [12])

    def test_a_failure_is_rolled_back_and_does_not_raise(self):
        conn = MagicMock()
        with patch.object(nl, "ready", side_effect=RuntimeError("boom")), self.assertLogs(nl.log, "ERROR"):
            self.assertEqual(nl.update_safely(conn), 0)
        conn.rollback.assert_called_once()

    def test_nothing_before_the_tables_exist(self):
        with self.assertLogs(nl.log, "WARNING"):
            self.assertEqual(nl.update_safely(conn_with([], tables=False)), 0)


class RecordTests(unittest.TestCase):
    def test_club_evaluations_leave_national_line_ups_out(self):
        from types import SimpleNamespace
        args = SimpleNamespace(as_of=NOW, start=NOW, end=NOW, hours_before=0)
        for national in (False, True):
            with patch.object(evaluation, "query", return_value=[]) as query:
                evaluation.load_lineups(None, args, **({"national": True} if national else {}))
            sql, params = query.call_args.args[1:]
            self.assertIn("(%s OR EXISTS (SELECT 1 FROM fixtures f WHERE f.fixture_id=s.fixture_id))", sql)
            self.assertEqual((sql.count("%s"), params[-1]), (len(params), national))

    def test_the_match_detail_carries_each_side_s_predicted_xi(self):
        m = {"xi": [(1, "GK"), (2, "CB")]}
        with patch.object(export.national_lineups, "ready", return_value=True), \
                patch.object(export.national_lineups, "replay", return_value=({(2, 10): m}, {1: "J. Pickford"})):
            self.assertEqual(export.national_xis(Mock(), NOW), {(2, 10): [[1, "J. Pickford", "GK"], [2, "Player 2", "CB"]]})
        with patch.object(export.national_lineups, "ready", side_effect=RuntimeError("boom")), self.assertLogs(export.log, "ERROR"):
            self.assertEqual(export.national_xis(Mock(), NOW), {})


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from thecornerfc import evaluation
from thecornerfc import export
from thecornerfc.export import export_lineup_history, export_lineup_record, export_methodology

T1 = datetime(2026, 9, 26, 15, tzinfo=timezone.utc)
T2 = datetime(2026, 9, 27, 15, tzinfo=timezone.utc)


def conn_with(tables=True, names=()):
    """A connection whose to_regclass finds every table (or none) and whose model_versions lookup
    returns names; site_freshness sees an empty database."""
    def execute(sql, params=None):
        if "to_regclass(%s)" in sql:
            return Mock(fetchone=lambda: (params[0] if tables else None,))
        if "from model_versions where model_version_id" in sql:
            return Mock(fetchall=lambda: list(names))
        return Mock(fetchone=lambda: (None,))
    conn = Mock()
    conn.execute.side_effect = execute
    return conn


def match(p, outcome, when, likely="1-0", actual="1-0"):
    return {"probabilities": p, "outcome": outcome, "effective_at": when, "model_version_id": "mv_a",
            "likely_score": likely, "actual_score": actual, "market": [0.5, 0.3, 0.2]}


class MethodologyExportTests(unittest.TestCase):
    def export(self, conn, matches=(), lineups=()):
        with tempfile.TemporaryDirectory() as d, \
                patch.object(evaluation, "load_matches", return_value=(list(matches), {"missing_regulation_score": 2})) as lm, \
                patch.object(evaluation, "load_lineups", return_value=(list(lineups), {"missing_or_incomplete_official_xi": 1})), \
                patch.object(export, "export_lineup_record") as record:
            export_methodology(conn, Path(d), now=T2)
            self.load_matches = lm
            record.assert_called_once()
            return json.loads((Path(d) / "methodology.json").read_text())

    def test_scores_prospective_matches_without_the_market(self):
        out = self.export(conn_with(names=[("mv_a", "match-v1")]),
                          [match([0.6, 0.25, 0.15], 0, T1), match([0.2, 0.3, 0.5], 1, T2, actual="1-1")])
        args, kwargs = self.load_matches.call_args
        self.assertEqual(args[1].source, "prospective")
        self.assertIs(kwargs["market"], False)
        m = out["matches"]
        self.assertEqual(m["n"], 2)
        self.assertEqual(m["accuracy"], 0.5)
        self.assertEqual(m["exact_score"], {"n": 2, "accuracy": 0.5})
        self.assertEqual(m["period"], {"from": T1.isoformat(), "to": T2.isoformat()})
        self.assertEqual(m["versions"], [{"name": "match-v1", "n": 2}])
        self.assertEqual(m["excluded_no_regulation_score"], 2)
        self.assertEqual(sum(b[1] for b in m["calibration"]), 6)  # 3 outcomes per match, pooled
        # P6 (model vs market) stays blinded: no market figure is published
        self.assertNotIn("market", json.dumps(out))

    def test_lineup_record(self):
        official = [{"player": i, "starter": True, "role": "CB"} for i in range(11)]
        predicted = [{"player": i, "predicted_starter": True, "role": "CB", "line": "DEF"} for i in range(2, 13)]
        out = self.export(conn_with(), lineups=[{"players": predicted, "official": official, "effective_at": T1,
                                                  "model_version_id": "mv_l"}])
        self.assertEqual(out["lineups"]["n"], 1)
        self.assertEqual(out["lineups"]["correct_starters_mean"], 9)
        self.assertEqual(out["lineups"]["role_accuracy"], {"n": 9, "accuracy": 1.0})
        self.assertEqual(out["lineups"]["versions"], [{"name": "mv_l", "n": 1}])

    def test_no_evidence_is_null_not_zero(self):
        self.assertEqual(self.export(conn_with())["matches"], None)
        out = self.export(conn_with(tables=False), [match([0.6, 0.25, 0.15], 0, T1)])
        self.assertIsNone(out["matches"])
        self.assertIsNone(out["lineups"])
        self.load_matches.assert_not_called()


def record_conn(tables=True, history=(), starters=()):
    """A connection for the line-up exports: fixture 7 is team 1 (home) against team 2, in league
    39; history is reconstructed_lineups rows and starters fixture_players rows."""
    def execute(sql, params=None):
        rows = []
        if "to_regclass(%s)" in sql:
            return Mock(fetchone=lambda: (params[0] if tables else None,))
        if "from reconstructed_lineups r join fixtures" in sql:
            rows = list(history)
        elif "from fixture_players" in sql:
            rows = list(starters)
        elif "from fixtures" in sql:
            rows = [(7, 39, 1, 2)]
        elif "from model_versions" in sql:
            rows = [("mv_new", "recent-minutes-lineup", T2), ("mv_old", "recent-minutes-lineup", T1)]
        elif "from teams" in sql:
            rows = [(1, "Home FC"), (2, "Away FC")]
        elif "from leagues" in sql:
            rows = [(39, "Premier League", "England")]
        elif "from players" in sql:
            rows = [(p, f"Player {p}") for p in params[0]]
        result = MagicMock(fetchall=lambda: rows)
        result.__iter__.side_effect = lambda: iter(rows)
        return result
    conn = Mock()
    conn.execute.side_effect = execute
    return conn


def lineup(team, version, predicted_ids, when=T1):
    # official XI: 0 is the keeper, 1-4 defenders, 5-8 midfielders, 9-10 forwards
    roles = ["GK", "CB", "CB", "LB", "RB", "CM", "CM", "LM", "RM", "ST", "ST"]
    official = [{"player": i, "starter": True, "role": roles[i]} for i in range(11)]
    official.append({"player": 50, "starter": False, "role": None})
    players = [{"player": i, "predicted_starter": True, "role": "ST" if i == 5 else roles[i] if i < 11 else "CM"}
               for i in predicted_ids]
    return {"fixture_id": 7, "team_id": team, "players": players, "official": official, "effective_at": when,
            "seconds_to_kickoff": 5400, "model_version_id": version}


class LineupRecordExportTests(unittest.TestCase):
    def export(self, conn, lineups=()):
        with tempfile.TemporaryDirectory() as d, \
                patch.object(evaluation, "load_lineups", return_value=(list(lineups), {"missing_or_incomplete_official_xi": 3})):
            with patch.object(export, "export_lineup_history") as history:
                export_lineup_record(conn, Path(d), now=T2)
            history.assert_called_once()
            return json.loads((Path(d) / "lineups.json").read_text())

    def test_one_row_per_team_lineup(self):
        # team 1 missed starters 9 and 10 (forwards) for 11 and 12, and put 5 up front
        out = self.export(record_conn(), [lineup(1, "mv_old", list(range(9)) + [11, 12]),
                                          lineup(2, "mv_new", range(11))])
        rows = [dict(zip(out["fields"], r)) for r in out["rows"]]
        home, away = rows
        self.assertEqual((home["team"], home["opponent"], home["home"], home["league"]), (1, 2, 1, 39))
        self.assertEqual((away["team"], away["opponent"], away["home"]), (2, 1, 0))
        self.assertEqual(home["correct"], 9)
        self.assertEqual((home["roles_right"], home["roles_known"]), (8, 9))
        self.assertEqual(home["lines"], [1, 1, 4, 4, 4, 4, 2, 0])
        self.assertEqual((home["missed"], home["wrong"]), ([9, 10], [11, 12]))
        self.assertEqual(home["hours_before"], 1.5)
        self.assertEqual(away["correct"], 11)
        self.assertEqual((away["missed"], away["wrong"]), ([], []))
        # versions oldest first, so the page can tell same-named versions apart
        self.assertEqual([v["id"] for v in out["versions"]], ["mv_old", "mv_new"])
        self.assertEqual((home["version"], away["version"]), (0, 1))
        self.assertEqual(out["teams"], {"1": "Home FC", "2": "Away FC"})
        self.assertEqual(out["leagues"], {"39": {"name": "Premier League", "country": "England"}})
        self.assertEqual(set(out["players"]), {"9", "10", "11", "12"})
        self.assertEqual(out["excluded_no_official_xi"], 3)

    def test_no_tables_writes_an_empty_record(self):
        out = self.export(record_conn(tables=False))
        self.assertEqual(out["rows"], [])
        self.assertEqual(out["fields"][6], "correct")


class LineupHistoryExportTests(unittest.TestCase):
    ROLES = ["GK", "CB", "CB", "LB", "RB", "CM", "CM", "LM", "RM", "ST", "ST"]

    def export(self, conn):
        with tempfile.TemporaryDirectory() as d:
            export_lineup_history(conn, Path(d), now=T2)
            return json.loads((Path(d) / "lineups_history.json").read_text(encoding="utf-8"))

    def test_scored_like_the_live_record(self):
        starters = [(7, 2, i, self.ROLES[i], None) for i in range(11)]
        # the predicted XI: 0-8 right (8 as a striker), 11 and 12 instead of 9 and 10
        predicted = (list(range(9)) + [11, 12], self.ROLES[:8] + ["ST", "ST", "ST"])
        out = self.export(record_conn(history=[(7, 2, *predicted, T1, 39, 1, 2)], starters=starters))
        self.assertTrue(out["available"])
        row = dict(zip(out["fields"], out["rows"][0]))
        self.assertEqual((row["fixture"], row["kickoff"], row["team"], row["opponent"], row["home"]),
                         (7, "2026-09-26", 2, 1, 0))
        self.assertEqual((row["correct"], row["roles_right"], row["roles_known"]), (9, 8, 9))
        self.assertEqual(row["lines"], [1, 1, 4, 4, 4, 4, 2, 0])
        self.assertEqual((row["missed"], row["wrong"]), ([9, 10], [11, 12]))
        self.assertEqual(set(out["players"]), {"9", "10", "11", "12"})

    def test_skips_a_match_without_a_full_team_sheet(self):
        starters = [(7, 2, i, "CB", None) for i in range(10)]
        out = self.export(record_conn(history=[(7, 2, list(range(11)), ["CB"] * 11, T1, 39, 1, 2)], starters=starters))
        self.assertEqual(out["rows"], [])

    def test_before_the_migration_it_says_so(self):
        out = self.export(record_conn(tables=False))
        self.assertFalse(out["available"])
        self.assertEqual(out["rows"], [])


class LoadMatchesMarketSwitchTests(unittest.TestCase):
    def test_market_false_skips_odds_lookups(self):
        row = {"fixture_id": 1, "ft_home": 2, "ft_away": 1, "status_short": "FT", "home_goals": 2, "away_goals": 1,
               "p_home": 0.5, "p_draw": 0.3, "p_away": 0.2, "captured_at": T1, "effective_at": T2}
        args = Mock(source="prospective", start=T1, end=T2, as_of=T2, hours_before=0)
        with patch.object(evaluation, "query", return_value=[row]), \
                patch("thecornerfc.paper_evidence.latest_quotes") as quotes:
            rows, _ = evaluation.load_matches(Mock(), args, market=False)
        quotes.assert_not_called()
        self.assertEqual(rows[0]["outcome"], 0)
        self.assertIsNone(rows[0]["market"])


if __name__ == "__main__":
    unittest.main()

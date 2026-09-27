import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from thecornerfc import evaluation
from thecornerfc.export import export_methodology

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
                patch.object(evaluation, "load_lineups", return_value=(list(lineups), {"missing_or_incomplete_official_xi": 1})):
            export_methodology(conn, Path(d), now=T2)
            self.load_matches = lm
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

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from thecornerfc import predictions
from thecornerfc.export import explanation, export_explanations, export_fixture_pages
from tests import test_match_snapshots

HOME = [(1.8, 0.9), (2.1, 1.2), (1.1, 1.0)]
AWAY = [(0.9, 1.6), (1.3, 1.4)]
SIDES = (4.0, 6.0, 3.0, 2.0, 1.45, 1.15)
LINES = ([60, 62, 64, 66], [55, 57, 59, 61])


def snapshot_inputs(h_rank=1100.0, a_rank=1000.0, league_id=39, h_miss=0.4, a_miss=None,
                    sides=SIDES, lines=LINES):
    """Inputs as update_predictions stores them, after a JSON round trip (tuples become lists)."""
    inputs = {"home_current_rank": h_rank + 10, "away_current_rank": a_rank - 5,
              "home_lt_algo": h_rank - 20, "away_lt_algo": a_rank + 8,
              "home_match_rank": h_rank, "away_match_rank": a_rank,
              "league_home_goals": 1.5, "league_away_goals": 1.2, "sides": sides,
              "predicted_lines": lines, "home_missing": h_miss, "away_missing": a_miss,
              "home_records": HOME, "away_records": AWAY}
    stored = predictions.predict_match(h_rank, a_rank, HOME, AWAY, 1.5, 1.2, league_id,
                                       h_miss or 0.0, a_miss or 0.0, sides, lines)
    return json.loads(json.dumps(inputs)), stored[:3]


def explain(inputs, league_id, stored):
    return predictions.explain(inputs, league_id, predictions.record_totals(inputs["home_records"]),
                               predictions.record_totals(inputs["away_records"]), stored)


class MarginTermTests(unittest.TestCase):
    def test_predict_match_margin_is_the_sum_of_its_terms(self):
        for league, sides, lines, miss in [(39, SIDES, LINES, (0.4, 1.1)), (2, None, None, (0, 0)),
                                           (39, SIDES, (LINES[0], [None] * 4), (0, 0.3))]:
            terms = predictions.margin_terms(1100.0, 1000.0, league, *miss, sides, lines)
            got = predictions.predict_match(1100.0, 1000.0, HOME, AWAY, 1.5, 1.2, league, *miss, sides, lines)
            self.assertEqual(sum(v for _, v in terms), got[0])

    def test_optional_terms_only_when_the_model_uses_them(self):
        names = lambda *a: [k for k, _ in predictions.margin_terms(1000.0, 1000.0, *a)]
        self.assertEqual(names(39), ["ranks", "absences"])
        self.assertEqual(names(2, 0, 0, SIDES, LINES), ["ranks", "europe_home", "absences", "home_edges", "lineups"])
        self.assertNotIn("lineups", names(39, 0, 0, None, (LINES[0], [None, 1, 2, 3])))


class ExplainTests(unittest.TestCase):
    def test_parts_add_up_to_the_stored_margin(self):
        inputs, stored = snapshot_inputs()
        parts = explain(inputs, 39, stored)
        self.assertAlmostEqual(sum(parts["margin"].values()), stored[0], places=12)
        self.assertAlmostEqual(parts["margin"]["strength"], 1.0)
        self.assertEqual(parts["margin"]["home_advantage"], 0.3)
        self.assertAlmostEqual(parts["margin"]["absences"], -0.04)       # home 0.4 missing
        self.assertAlmostEqual(parts["margin"]["home_edges"], 0.05)
        self.assertAlmostEqual(parts["margin"]["lineups"], 0.075)
        self.assertNotIn("europe_home", parts["margin"])

    def test_open_sides_raise_the_expected_total(self):
        inputs, stored = snapshot_inputs()
        self.assertGreater(explain(inputs, 39, stored)["tendencies"], 0)
        inputs, stored = snapshot_inputs(sides=(-8.0, -6.0, 0.0, 0.0, 1.45, 1.15))
        self.assertLess(explain(inputs, 39, stored)["tendencies"], 0)
        inputs, stored = snapshot_inputs(sides=None)
        self.assertIsNone(explain(inputs, 39, stored)["tendencies"])

    def test_nothing_when_the_snapshot_does_not_reproduce_the_prediction(self):
        inputs, stored = snapshot_inputs()
        self.assertIsNone(explain(inputs, 39, (stored[0] + 0.01, *stored[1:])))
        self.assertIsNone(explain(inputs, 39, (stored[0], stored[1] + 0.01, stored[2])))
        with patch.object(predictions, "HOME_EDGE_WEIGHT", 0.5):      # settings changed since
            self.assertIsNone(explain(inputs, 39, stored))
        inputs.pop("home_match_rank")
        self.assertIsNone(explain(inputs, 39, stored))

    def test_reasons_are_the_largest_effects_above_the_floor(self):
        inputs, stored = snapshot_inputs(h_rank=1020.0, a_rank=1000.0, h_miss=None)
        reasons = explain(inputs, 39, stored)["reasons"]
        self.assertLessEqual(len(reasons), predictions.MAX_REASONS)
        sizes = [abs(v) for _, v in reasons]
        self.assertEqual(sizes, sorted(sizes, reverse=True))
        self.assertTrue(all(s >= predictions.REASON_MIN_GOALS for s in sizes))
        self.assertEqual(reasons[0][0], "home_advantage")                # 0.3 beats a 0.2 gap
        self.assertNotIn("absences", [k for k, _ in reasons])

    def test_explains_a_snapshot_written_by_update_predictions(self):
        case = test_match_snapshots.MatchSnapshotTests("test_stored_components_reproduce_original_prediction")
        case.setUp()
        try:
            predictions.update_predictions(case.conn)
            row = next(iter(case.conn.snapshots.values()))
        finally:
            case.doCleanups()
        inputs = json.loads(row["inputs"])
        parts = explain(inputs, row["league_id"], (row["exp_diff"], row["home_xg"], row["away_xg"]))
        self.assertIsNotNone(parts)
        self.assertAlmostEqual(sum(parts["margin"].values()), row["exp_diff"], places=12)


class ExportTests(unittest.TestCase):
    def test_entry_is_rounded_and_flags_rank_fallbacks(self):
        inputs, stored = snapshot_inputs()
        inputs["away_rank_fallback"] = True
        entry = explanation(inputs, 39, predictions.record_totals(HOME), predictions.record_totals(AWAY),
                            stored, {"source": "prospective"})
        self.assertEqual(entry["current"], [1110, 995])
        self.assertEqual(entry["missing"], [0.4, None])
        self.assertEqual(entry["margin"]["strength"], 1.0)
        self.assertEqual(entry["fallback"], [False, True])
        self.assertEqual(entry["source"], "prospective")
        for _, v in entry["reasons"]:
            self.assertEqual(v, round(v, 2))

    def test_writes_an_empty_file_without_the_snapshot_table(self):
        conn = Mock()
        conn.execute.return_value.fetchone.return_value = (None,)
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(export_explanations(conn, Path(d)), {})
            self.assertEqual(json.loads((Path(d) / "explanations.json").read_text())["matches"], {})


class FixturePageTests(unittest.TestCase):
    """One file per match: a page asks for the match it shows, not for every match."""
    def test_each_match_gets_only_its_own_parts(self):
        why = {"11": {"reasons": [["strength", 0.4]], "exp_diff": 0.4}}
        lineups = {"xi": {"11": {"1": [[5, "A. Player", "ST", 80.0]]}, "12": {"2": [[6, "B. Player", "GK", 70.0]]}},
                   "actual": {"13": {"3": [[7, "C. Player", "CB", 75.0]]}}, "prematch": {"13": {"3": [[8, "D. Player", "CB", 74.0]]}}}
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "fixtures").mkdir()
            (Path(d) / "fixtures/9.json").write_text("{}")           # a match no longer on the site
            export_fixture_pages(Path(d), why, lineups)
            pages = {p.stem: json.loads(p.read_text()) for p in (Path(d) / "fixtures").glob("*.json")}
        self.assertEqual(set(pages), {"11", "12", "13"})
        self.assertEqual(pages["11"], {"id": 11, "why": why["11"], "xi": lineups["xi"]["11"]})
        self.assertEqual(set(pages["12"]), {"id", "xi"})
        self.assertEqual(set(pages["13"]), {"id", "actual", "prematch"})

    def test_the_shared_files_no_longer_carry_every_match(self):
        import inspect
        from thecornerfc import export
        players = inspect.getsource(export.export_players)
        for gone in ('"fixture_xi": fixture_xi', '"actual_xi": actual_xi', '"prematch_xi": prematch_xi'):
            self.assertNotIn(gone, players)
        self.assertIn('{"reasons": entry["reasons"]}', inspect.getsource(export.export_explanations))
        app = (Path(export.__file__).resolve().parents[1] / "docs/assets/app.js").read_text()
        self.assertIn("data/fixtures/${id}.json", app)
        self.assertNotIn('getJson("data/player_seasons.json")', app.split("function loadPlayerSeasons")[0])


if __name__ == "__main__":
    unittest.main()

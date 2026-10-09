import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from thecornerfc.publish.export import (ExportValidationError, _ban, _club_positions, _injured, _kit_colors, _publish_export,
                                export_player_seasons)
from thecornerfc.pipeline.workflow_inputs import parse_int_list


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_valid_export(root, marker):
    write_json(root / "site.json", {"generated_at": "test", "competitions": {}, "teams": {}})
    write_json(root / "matches.json", {"generated_at": "test", "fields": ["id"], "matches": []})
    write_json(root / "rankings.json", {
        "generated_at": "test",
        "fields": ["team"],
        "rankings": [[i] for i in range(100)],
        "marker": marker,
    })
    write_json(root / "stats.json", {"generated_at": "test", "ranges": {}})
    write_json(root / "bets.json", {"summary": {}, "bets": [], "rules": {}, "marker": marker})
    write_json(root / "injuries.json", {"generated_at": "test", "fields": [], "teams": {}})
    write_json(root / "players.json", {
        "generated_at": "test",
        "fields": ["id"],
        "players": [[i] for i in range(100)],
    })
    write_json(root / "player_seasons.json", {
        "generated_at": "test",
        "fields": ["id"],
        "players": {str(i): {"2026": [[1, 90, 50, 0, 0]]} for i in range(100)},
    })
    for dirname in ("players", "clubs", "leagues"):
        write_json(root / dirname / "1.json", {"marker": marker})


class ExportSafetyTests(unittest.TestCase):
    def test_player_seasons_are_returned_for_the_page_files_and_no_file_is_written(self):
        conn = Mock()
        conn.execute.side_effect = [
            [(i,) for i in range(100)],
            Mock(fetchall=lambda: [(i, 2026, 1, 90, 50, 0, 0) for i in range(100)]),
            Mock(fetchall=lambda: []), Mock(fetchall=lambda: []),
            [], [], [], [(1, "Club")], [],
        ]
        with tempfile.TemporaryDirectory() as tmp:
            live = Path(tmp) / "data"
            returned = []

            def build(staged):
                write_valid_export(staged, "new")
                returned.append(export_player_seasons(conn, staged))

            (live / "player_seasons.json").unlink(missing_ok=True) if live.exists() else None
            _publish_export(build, live)
            players = returned[0]["players"]                      # each player's rows, for his page file
            self.assertEqual(len(players), 100)
            self.assertEqual(players["0"]["2026"], [[1, 90, 50, 0, 0]])

    def test_invalid_or_depleted_rankings_preserve_old_output(self):
        for rankings, message in (({}, "does not contain a list"),
                                  ([], "expected at least 50"),
                                  ([[i] for i in range(60)], "collapsed from 200 to 60")):
            with self.subTest(message=message), tempfile.TemporaryDirectory() as tmp:
                live = Path(tmp) / "data"
                write_valid_export(live, "old")
                write_json(live / "rankings.json", {"rankings": [[i] for i in range(200)], "marker": "old"})

                def build(staged):
                    write_valid_export(staged, "new")
                    write_json(staged / "rankings.json", {"rankings": rankings})

                with self.assertRaisesRegex(ExportValidationError, message):
                    _publish_export(build, live)
                self.assertEqual(json.loads((live / "rankings.json").read_text())["marker"], "old")

    def test_export_failure_preserves_old_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            live = Path(tmp) / "data"
            write_valid_export(live, "old")

            def build(staged):
                write_valid_export(staged, "new")
                raise RuntimeError("boom")

            with self.assertRaises(RuntimeError):
                _publish_export(build, live)

            self.assertEqual(json.loads((live / "rankings.json").read_text())["marker"], "old")

    def test_invalid_generated_json_preserves_old_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            live = Path(tmp) / "data"
            write_valid_export(live, "old")

            def build(staged):
                write_valid_export(staged, "new")
                (staged / "players" / "1.json").write_text("{", encoding="utf-8")

            with self.assertRaises(ExportValidationError):
                _publish_export(build, live)

            self.assertEqual(json.loads((live / "rankings.json").read_text())["marker"], "old")

    def test_with_no_earlier_files_the_export_is_compared_with_the_stored_one(self):
        # the data isn't kept in the repository: a run's working copy has no export from before
        stored = {"rows": {"rankings.json": 200}, "dirs": {"clubs": 40}}
        for build_players, clubs, message in ((60, 1, "rankings.json collapsed from 200 to 60"), (150, 1, "clubs/ collapsed from 40 to 1")):
            with self.subTest(message=message), tempfile.TemporaryDirectory() as tmp:
                live = Path(tmp) / "data"

                def build(staged):
                    write_valid_export(staged, "new")
                    write_json(staged / "rankings.json", {"rankings": [[i] for i in range(build_players)]})

                with patch("thecornerfc.publish.export._stored_shape", return_value=stored) as asked, \
                        self.assertRaisesRegex(ExportValidationError, message):
                    _publish_export(build, live, conn=object())
                asked.assert_called_once()
                self.assertFalse(live.exists())
        with tempfile.TemporaryDirectory() as tmp:
            live = Path(tmp) / "data"
            write_valid_export(live, "old")
            with patch("thecornerfc.publish.export._stored_shape") as asked:           # files from before: they are what it is compared with
                _publish_export(lambda staged: write_valid_export(staged, "new"), live, conn=object())
            asked.assert_not_called()

    def test_successful_export_replaces_old_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            live = Path(tmp) / "data"
            write_valid_export(live, "old")

            _publish_export(lambda staged: write_valid_export(staged, "new"), live)

            self.assertEqual(json.loads((live / "rankings.json").read_text())["marker"], "new")
            self.assertEqual(json.loads((live / "clubs" / "1.json").read_text())["marker"], "new")


class WorkflowInputTests(unittest.TestCase):
    def test_parse_int_list_accepts_space_separated_numbers(self):
        self.assertEqual(parse_int_list("233 188\t39", "leagues"), [233, 188, 39])

    def test_parse_int_list_rejects_shell_syntax(self):
        with self.assertRaises(ValueError):
            parse_int_list("233; echo hacked", "leagues")

    def test_parse_int_list_rejects_empty_input(self):
        with self.assertRaises(ValueError):
            parse_int_list("   ", "seasons")


class MarkupValueTests(unittest.TestCase):
    """API values that the site writes into style attributes and image sources."""

    def test_kit_colours_must_be_six_digit_hex(self):
        self.assertEqual(_kit_colors("FF0000", "ffffff"), ["ff0000", "ffffff"])
        self.assertEqual(_kit_colors("ffffffffff", "000000"), None)      # seen in real API data
        self.assertEqual(_kit_colors("f00;background:url(x)", "fff"), None)
        self.assertEqual(_kit_colors(None, None), None)

    def test_bad_number_colour_is_dropped_but_shirt_kept(self):
        self.assertEqual(_kit_colors("123abc", "red"), ["123abc", None])

    def test_only_ban_reasons_are_published(self):
        for ban in ("Red Card", "Yellow Cards", "Suspended"):
            self.assertEqual(_ban(ban), ban)
        for medical in ("Knee Injury", "Illness", "Heart Problems", "Surgery", "Doping", "Manual injury", "", None):
            self.assertIsNone(_ban(medical), medical)

    def test_injured_flag_carries_no_reason(self):
        self.assertEqual(_injured("Missing Fixture", "Knee Injury"), 1)
        self.assertEqual(_injured("Missing Fixture", "Illness"), 1)
        self.assertEqual(_injured("Questionable", "Knee Injury"), 0)       # doubtful, not out
        self.assertEqual(_injured("Missing Fixture", "International duty"), 0)
        self.assertEqual(_injured("Missing Fixture", "Red Card"), 0)
        self.assertEqual(_injured("Missing Fixture", None), 0)

    def test_club_positions_are_each_clubs_current_players_last_12_months(self):
        positions = {"1": {"2026": [["ST", 900]], "12m": [["ST", 1200], ["LW", 300]]},
                     "2": {"12m": [["GK", 2000]]}, "3": {"2024": [["CB", 90]]}}
        self.assertEqual(_club_positions({1: 10, 2: 10, 3: 10, 4: 11, 5: None}, positions),
                         {10: {"1": [["ST", 1200], ["LW", 300]], "2": [["GK", 2000]]}})


if __name__ == "__main__":
    unittest.main()

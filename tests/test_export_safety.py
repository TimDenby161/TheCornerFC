import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from thecornerfc.export import (ExportValidationError, _kit_colors, _media_url, _publish_export,
                                export_player_seasons)
from thecornerfc.workflow_inputs import parse_int_list


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_valid_export(root, marker):
    write_json(root / "matches.json", {
        "generated_at": "test",
        "fields": ["id"],
        "matches": [],
        "competitions": {},
        "teams": {},
    })
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
        "players": {str(i): {"2026": [[1, 90, 50, 7, 0, 0]]} for i in range(100)},
    })
    for dirname in ("players", "clubs", "leagues"):
        write_json(root / dirname / "1.json", {"marker": marker})


class ExportSafetyTests(unittest.TestCase):
    def test_real_player_seasons_writer_passes_publication_validation(self):
        conn = Mock()
        conn.execute.side_effect = [
            [(i,) for i in range(100)],
            Mock(fetchall=lambda: [(i, 2026, 1, 90, 50, 7, 0, 0) for i in range(100)]),
            Mock(fetchall=lambda: []), Mock(fetchall=lambda: []),
            [], [], [], [(1, "Club")], [],
        ]
        with tempfile.TemporaryDirectory() as tmp:
            live = Path(tmp) / "data"

            def build(staged):
                write_valid_export(staged, "new")
                export_player_seasons(conn, staged)

            _publish_export(build, live)
            players = json.loads((live / "player_seasons.json").read_text())["players"]
            self.assertEqual(len(players), 100)
            self.assertEqual(players["0"]["2026"], [[1, 90, 50, 7, 0, 0]])

    def test_invalid_or_depleted_player_seasons_preserves_old_output(self):
        for players, message in (([], "does not contain a dict"),
                                 ({}, "expected at least 50"),
                                 ({str(i): {} for i in range(60)}, "collapsed from 200 to 60")):
            with self.subTest(message=message), tempfile.TemporaryDirectory() as tmp:
                live = Path(tmp) / "data"
                write_valid_export(live, "old")
                write_json(live / "player_seasons.json",
                           {"players": {str(i): {} for i in range(200)}})

                def build(staged):
                    write_valid_export(staged, "new")
                    write_json(staged / "player_seasons.json", {"players": players})

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

    def test_media_urls_only_from_api_football_host(self):
        ok = "https://media.api-sports.io/football/coachs/1234.png"
        self.assertEqual(_media_url(ok), ok)
        for bad in ("javascript:alert(1)", "http://media.api-sports.io/football/coachs/1.png",
                    "https://media.api-sports.io.evil.test/football/coachs/1.png",
                    'https://media.api-sports.io/football/coachs/1.png" onerror="x', "", None, 5):
            self.assertIsNone(_media_url(bad), bad)


if __name__ == "__main__":
    unittest.main()

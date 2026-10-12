"""thecornerfc.publish.export is the one address the rest of the code uses for the export.

The work is in the site_*.py modules beside it; export.py runs the export and passes every name
on. These tests keep that true: nothing that could be imported from export before the split has
gone, and each name is the owning module's own object, not a second copy that could drift.
"""
import importlib
import inspect
import unittest
from pathlib import Path

from thecornerfc.publish import export

PUBLISH = Path(export.__file__).resolve().parent

# Every function, class and constant export.py defined on 2026-10-11, before it was split. A name
# may be added. Take one away only when nothing uses it, here and in the code together.
NAMES = """
    BAN_REASONS BET_BANK_GBP BET_STAKE_GBP CARRIED_FILES CLUB_ACTIVE_DAYS COLLAPSE_RATIO
    CRITICAL_DETAIL_DIRS CRITICAL_JSON_FILES ENGLISH ExportValidationError FANTASY_RESULTS
    FORM_GAMES FPL_POSITIONS FREE_DAYS FREE_LEAGUE FREE_POSITION FREE_WORLD FUTURE_DAYS
    HEX_COLOR INJURY_LOOKBACK_DAYS INJURY_REASON LEAGUE_FIXTURE_FIELDS LINEUP_RECORD_FIELDS
    LISTED MAJOR_ROW_TYPES MANIFEST MATCH_FIELDS MATCH_PAID_CHANCES MATCH_PAID_DEPTH
    MIN_MAJOR_ROWS MIN_PLAYERS MOVEMENT_FIELDS NEUTRAL_SQL ONE_MATCH_REASONS OUT_DIR PAID_PREFIX
    PAST_DAYS PENALTY_CELLS PLAYER_FIELDS PLAYER_MATCHES PLAYER_PAID_FIELDS PLAYER_SEASONS
    PLAYER_SEASON_FIELDS POSITION_SHARE PREDICTION_GWS PUBLISHED_FANTASY_PARAMS SEASON_FIELDS
    SITE_MATCH_FIELDS SITE_PLAYER_FIELDS SPELL_FIELDS STAT_MARKETS STAT_RANGES XG_FROM_SHOTS
    XG_RECENT _ENTITIES _ban _check_row_collapse _check_table_collapse _club_positions
    _club_spells _decode _export_shape _fantasy_progress _fold _fpl_state _hex_color _injured
    _kit_colors _lineup_names _market_stats _paid_rows _paywall_on _period _places
    _player_movement _publish_export _r _read_json _records_sum _replace_export _round_number
    _score_xi _stats _stored_hashes _stored_shape _table_exists _versions _write_json_file
    _write_site_data _xg_from_shots _xi_lines blanked blanked_player build_player_pages
    cut_league_fixtures cut_player_page explanation export_bets export_clubs export_efl_fantasy
    export_fantasy export_fantasy_predictions export_injuries export_leagues
    export_lineup_history export_lineup_record export_methodology export_nations
    export_player_pages export_player_seasons export_players export_site_data export_stats
    fantasy_prediction_payload headline_projection log market_consensus market_probabilities
    match_explanations mirror_site_docs national_match national_matches national_nationalities
    national_stat_rows national_xis site_freshness site_player_rows store_matches
    store_owner_doc store_players validate_export write_manifest
""".split()

# Modules and classes other code reaches through export (export.config.require_db_write, a
# test's patch of export.datetime ...)
REACHED_THROUGH = ("config", "national_lineups", "datetime", "log")


def site_modules():
    return [importlib.import_module(f"thecornerfc.publish.{path.stem}")
            for path in sorted(PUBLISH.glob("site_*.py"))]


class ExportSurfaceTests(unittest.TestCase):
    def test_every_name_is_still_importable_from_export(self):
        missing = [name for name in (*NAMES, *REACHED_THROUGH) if not hasattr(export, name)]
        self.assertFalse(missing)

    def test_each_name_has_one_home(self):
        # defined in exactly one place: export.py itself or one site_* module (the log is the one
        # name every module has, and it is the same logger in each)
        for name in NAMES:
            if name == "log":
                continue
            homes = [m.__name__ for m in (export, *site_modules()) if _defined_in(m, name)]
            self.assertEqual(len(homes), 1, (name, homes))

    def test_export_passes_on_the_owning_modules_own_object(self):
        for module in site_modules():
            for name in NAMES:
                if _defined_in(module, name):
                    self.assertIs(getattr(export, name), getattr(module, name), (module.__name__, name))

    def test_the_output_folder_is_one_object_everywhere(self):
        # functions that default to OUT_DIR took the value when they were defined: every module
        # must have taken the same one
        for module in (export, *site_modules()):
            for fn in vars(module).values():
                if inspect.isfunction(fn) and fn.__module__ == module.__name__:
                    default = inspect.signature(fn).parameters.get("out_dir")
                    if default is not None and default.default not in (inspect.Parameter.empty, None):
                        self.assertIs(default.default, export.OUT_DIR, fn.__qualname__)

    def test_the_log_keeps_its_name(self):
        # the jobs' logs and the tests' assertLogs(export.log) read this name
        self.assertEqual(export.log.name, "thecornerfc.publish.export")
        for module in site_modules():
            self.assertIs(module.log, export.log, module.__name__)


def _defined_in(module, name):
    """Whether module's own source assigns or defines name at its top level (not an import)."""
    import ast
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == name:
            return True
        if isinstance(node, ast.Assign):
            if any(isinstance(n, ast.Name) and n.id == name for target in node.targets for n in ast.walk(target)):
                return True
    return False


if __name__ == "__main__":
    unittest.main()

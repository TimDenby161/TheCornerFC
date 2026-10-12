"""Everything derived from the fantasy games (FPL and Fantasy EFL). Owner-only: what is built here
goes to the database for the owner's sign-in (store_owner_doc), never into a public file or table.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..models.predictions import UPCOMING_STATUSES
from .site_files import OUT_DIR, _r, _write_json_file, store_owner_doc

# the export's one log, whichever module writes to it
log = logging.getLogger("thecornerfc.publish.export")


FANTASY_RESULTS = Path(__file__).resolve().parent.parent.parent / "experiments" / "fantasy_v1" / "results.json"


def _fantasy_progress(conn, model="fantasy-v1.1"):
    """Accrual of a prospective fantasy test (P8: v1.1): finished fixtures with one of the model's
    snapshots before kickoff."""
    if conn.execute("select to_regclass('public.fantasy_fixture_snapshots')").fetchone()[0] is None:
        return {"state": "not_started"}
    first, rows, fixtures, rounds = conn.execute(
        """select min(s.captured_at), count(*), count(distinct s.fixture_id), count(distinct (f.season, f.round))
                  filter (where f.status_short = 'FT')
           from fantasy_fixture_snapshots s join fixtures f using (fixture_id)
           join model_versions mv using (model_version_id)
           where s.source = 'prospective' and mv.version_name = %s""", [model]).fetchone()
    done = conn.execute(
        """select count(distinct s.fixture_id) from fantasy_fixture_snapshots s join fixtures f using (fixture_id)
           join model_versions mv using (model_version_id)
           where s.source = 'prospective' and mv.version_name = %s and f.status_short = 'FT'""", [model]).fetchone()[0]
    return {"state": "capturing" if first else "waiting", "first_capture": first.isoformat() if first else None,
            "snapshots": rows, "fixtures": fixtures, "finished_fixtures": done, "finished_rounds": rounds}


def export_fantasy(conn, out_dir=OUT_DIR):
    """fpl.json: the fantasy model's validation findings (experiments/fantasy_v1/results.json) and
    the prospective test's progress. Uses no FPL data. Not critical: any problem skips the file."""
    try:
        r = json.loads(FANTASY_RESULTS.read_text(encoding="utf-8"))
        t = r["test"]
        pick = lambda m: {k: m[k] for k in ("n", "mae", "rmse", "pearson", "spearman", "mean_pred", "mean_actual", "bias_pct")}
        names = ("model", "recent5", "ppg", "flat_team_goals", "v1_1")
        seg = lambda name, keys=None: {g: {k: pick(v[k]) for k in ("model", "recent5", "ppg")}
                                       for g, v in t["segments"][name].items() if keys is None or g in keys}
        calib = lambda c: {"ece": c["ece"], "n": c["n"], "mean_p": c["mean_p"], "rate": c["rate"],
                           "bins": [[b["n"], b["mean_p"], b["rate"]] for b in c["bins"]]}
        s = r["success"]
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "test": {"rows": r["rows"]["test"], "train_rows": r["rows"]["train"],
                     "validation_rows": r["rows"]["validation"], "from": "2024-07-01",
                     "rounds": t["round_wins"]["recent5"]["rounds"]},
            "criteria": [
                {"key": "benchmarks", "pass": s["1_beats_ppg_and_recent_on_mae_and_rmse"],
                 "mae_vs_recent": t["vs"]["recent5"]["mae"], "mse_vs_recent": t["vs"]["recent5"]["mse"]},
                {"key": "bias", "pass": s["2_bias_within_limits"], **s["2_detail"]},
                {"key": "calibration", "pass": s["3_calibration"], **s["3_detail"]},
                {"key": "match_model", "pass": s["4_beats_flat_team_goals"], "mae_vs_flat": t["vs"]["flat_team_goals"]["mae"]}],
            "overall": {k: pick(t["overall"][k]) for k in names},
            "top_n": {k: t["top_n"][k] for k in names},
            "round_wins": t["round_wins"]["recent5"],
            "vs_regulars": {k: t["vs_regulars"][k]["mae"] for k in ("recent5", "ppg")},
            "segments": {"regular": seg("regular"), "position": seg("position"),
                         "round_bucket": seg("round_bucket"), "ability_band": seg("ability_band", ("80+", "70-80", "60-70")),
                         "season": seg("season")},
            "minutes": {k: t["minutes"][k] for k in ("mae", "recent5_mae", "rmse", "recent5_rmse", "mean_pred", "mean_actual")},
            "availability_minutes_mae": t["availability_variant_detail"]["minutes_mae"],
            "start_calibration": calib(t["start_calibration"]),
            "clean_sheet_calibration": calib(r["test_team_checks"]["team_clean_sheet"]),
            "validation_clean_sheet_ece": r["validation_team_checks"]["team_clean_sheet"]["ece"],
            "components": {k: {"pred": v["mean_pred"], "actual": v["mean_actual"]} for k, v in t["components"].items()},
            "saves": {"validation_terciles": r["validation_team_checks"]["saves_terciles"],
                      "posthoc_gk_bias": r["posthoc_with_saves"]["position_v1_bias_pct"]["G"]},
            "v1_1_gk_bias": t["segments"]["position"]["G"]["v1_1"]["bias_pct"],
            "coverage_outside_share": r["coverage"]["outside_share"],
            "fpl_rows_available": sum(r["fpl_audit"].values()),
            "prospective": dict(_fantasy_progress(conn), target_rounds=10, target_rows=3000),
        }

        _write_json_file(Path(out_dir) / "fpl.json", payload)
    except Exception:
        conn.rollback()         # a failed query must not leave the export's connection aborted
        log.exception("Fantasy findings export skipped")


PREDICTION_GWS = 10                     # gameweeks ahead on the FPL tab
PUBLISHED_FANTASY_PARAMS = Path(__file__).resolve().parent.parent / "fantasy_games" / "fantasy_params_v1_6.json"   # the FPL tab shows v1.6
FPL_POSITIONS = {"GKP": "G", "DEF": "D", "MID": "M", "FWD": "F"}
# v1.5's figures behind the goal / penalty / FPL assist lines of the breakdown
PENALTY_CELLS = ("exp_np_goals", "exp_pen_goals", "exp_pen_misses", "exp_fpl_pen_assists", "exp_fpl_other_assists")


def _fpl_state(conn):
    """From the latest FPL capture: ({api player: (position letter, price tenths, status, chance)},
    {(api home, api away): gameweek}, captured_at). Empty without a capture."""
    cap = conn.execute("""select capture_id, season, fixtures, captured_at from fpl_captures
                          order by captured_at desc, capture_id desc limit 1""").fetchone()
    if not cap:
        return {}, {}, None
    capture_id, season, fixtures, captured = cap
    players = {}
    for api, pos, price, status, chance in conn.execute(
            """select m.api_id, s.position, s.price_tenths, s.status, s.chance_next_round
               from fpl_player_states s join fpl_id_map_current m
                 on m.kind = 'player' and m.season = %s and m.fpl_id = s.fpl_player_id
               where s.capture_id = %s and m.api_id is not null order by s.fpl_player_id""", [season, capture_id]):
        players.setdefault(api, (FPL_POSITIONS.get(pos), price, status, chance))
    teams = dict(conn.execute("""select fpl_id, api_id from fpl_id_map_current
                                 where kind = 'team' and season = %s and api_id is not null""", [season]).fetchall())
    gws = {(teams[f["fpl_team_h"]], teams[f["fpl_team_a"]]): f["event_id"] for f in fixtures
           if f.get("event_id") and f.get("fpl_team_h") in teams and f.get("fpl_team_a") in teams}
    return players, gws, captured


def _round_number(name):
    try:
        return int(str(name).rsplit("-", 1)[-1])
    except ValueError:
        return None


def fantasy_prediction_payload(fixtures, teams_out, doc, fpl_players, names, team_info, *, source, captured=None):
    """fpl_predictions.json from fantasy_snapshots.build output. fixtures: {fixture: (gameweek,
    home, away, kickoff)}; fpl_players: fpl_state()'s players. Points are rescored with the FPL
    position where one is known, since FPL scores by its own position."""
    from ..fantasy_games import fantasy as fm
    params = doc["params"]
    gws = sorted({g for g, *_ in fixtures.values()})
    index = {g: i for i, g in enumerate(gws)}
    first = {g: min(k for gg, _, _, k in fixtures.values() if gg == g) for g in gws}
    parts = [*fm.COMPONENT_POINTS, *(fm.EXTRA_POINTS if "bonus_beta" in params else ())]   # v1.1 has no extras
    pens = "penalties" in params          # v1.5: penalties after goals, FPL-only assists after assists
    if pens:
        parts.insert(parts.index("goal_points") + 1, "penalty_points")
        parts.insert(parts.index("assist_points") + 1, "fpl_assist_points")
    players, cells = {}, {}
    for fid, team, _, preds, inputs in teams_out:
        gw, home, away, _ = fixtures[fid]
        lam = preds[0]["lambda_against"] if preds else None
        save_mean = max(params["save_intercept"] + params["save_slope"] * lam, 0.1) if doc["saves"] and lam is not None else None
        for p in preds:
            pid = p["player_id"]
            fpl = fpl_players.get(pid)
            if source == "fpl" and fpl_players and not fpl:
                continue     # not in FPL at his club: left it, though our match history still has him
            position = (fpl and fpl[0]) or p["position"]
            if position != p["position"]:
                mins = {k: p[k] for k in ("p_start", "p_play", "p60", "exp_minutes")}
                p = dict(p, **fm.expected_points(position, mins, p.get("exp_np_goals", p["exp_goals"]), p["exp_assists"],
                                                 p["lambda_against"],
                                                 p.get("save_mean", save_mean), fm.player_extras(params, stored=p)))
            if pid not in players:
                players[pid] = [pid, names.get(pid, str(pid)), team, p["position"], fpl[0] if fpl else None,
                                fpl[1] if fpl else None, fpl[2] if fpl else None, fpl[3] if fpl else None,
                                inputs["availability"].get(str(pid))]
            cells.setdefault(pid, []).append([index[gw], away if team == home else home, team == home,
                                              _r(p["expected_points"]), round(p["exp_minutes"]),
                                              _r(p["exp_goals"]), _r(p["exp_assists"]), _r(p["p_clean_sheet"]),
                                              [_r(p[k]) for k in parts],
                                              *([_r(p[k]) for k in PENALTY_CELLS] if pens else [])])
    order = sorted(players, key=lambda pid: -sum(c[3] for c in cells[pid]))
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "model": doc["version_name"], "source": source,
            "fpl_captured_at": captured.isoformat() if captured else None,
            "gameweeks": [{"id": g, "first_kickoff": first[g].isoformat()} for g in gws],
            "teams": {str(t): v for t, v in team_info.items()},
            "fields": ["player", "name", "team", "position", "fpl_position", "price", "fpl_status", "fpl_chance", "availability"],
            "cell_fields": ["gw", "opponent", "home", "xp", "minutes", "goals", "assists", "p_clean_sheet", "parts",
                            *([k.removeprefix("exp_") for k in PENALTY_CELLS] if pens else [])],
            "part_fields": [k.removesuffix("_points") for k in parts],
            "players": [players[pid] for pid in order], "cells": [sorted(cells[pid]) for pid in order]}


def export_fantasy_predictions(conn, doc=None):
    """fpl_predictions: every player's expected points for the next PREDICTION_GWS gameweeks
    (FPL's gameweeks once FPL is captured, else API-Football rounds), with FPL position and price.
    Same code as the fantasy snapshots, with v1.6's frozen parameters (the version the site shows)
    unless doc is given. Owner only (store_owner_doc). Not critical: a failure skips it."""
    try:
        from ..fantasy_games import fantasy_snapshots
        now = datetime.now(timezone.utc)
        fpl_players, fpl_gws, captured = _fpl_state(conn)
        upcoming = conn.execute(
            """select fixture_id, round, home_team_id, away_team_id, kickoff from fixtures
               where league_id = %s and status_short = any(%s) and kickoff > %s order by kickoff""",
            [fantasy_snapshots.PL, list(UPCOMING_STATUSES), now]).fetchall()
        source = "fpl" if fpl_gws else "rounds"
        fixtures = {}
        for fid, name, home, away, kickoff in upcoming:
            gw = fpl_gws.get((home, away)) if fpl_gws else _round_number(name)
            if gw is not None:          # FPL has no gameweek for it yet: a blank until rescheduled
                fixtures[fid] = (gw, home, away, kickoff)
        keep = sorted({g for g, *_ in fixtures.values()})[:PREDICTION_GWS]
        fixtures = {f: v for f, v in fixtures.items() if v[0] in keep}
        if not fixtures:
            return
        horizon = max(v[3] for v in fixtures.values()) - now + timedelta(days=1)
        doc, teams_out = fantasy_snapshots.build(conn, list(fixtures), now=now, horizon=horizon,
                                                 doc=doc or fantasy_snapshots.load_params(PUBLISHED_FANTASY_PARAMS))
        pids = sorted({p["player_id"] for *_, preds, _ in teams_out for p in preds})
        names = dict(conn.execute("select player_id, name from players where player_id = any(%s)", [pids]).fetchall())
        team_ids = sorted({t for v in fixtures.values() for t in v[1:3]})
        team_info = {t: [n, c] for t, n, c in conn.execute(
            "select team_id, name, code from teams where team_id = any(%s)", [team_ids])}
        store_owner_doc(conn, "fpl_predictions", fantasy_prediction_payload(
            fixtures, teams_out, doc, fpl_players, names, team_info, source=source, captured=captured))
    except Exception:
        conn.rollback()
        log.exception("Fantasy predictions export skipped")


def export_efl_fantasy(conn, out_dir=OUT_DIR):
    """efl_predictions: expected Fantasy EFL points for Championship, League One and League Two
    players and clubs (efl_fantasy.py). Owner only (store_owner_doc): nothing is written to out_dir.
    Not critical: a failure skips it."""
    try:
        from ..fantasy_games import efl_fantasy
        doc = efl_fantasy.payload(conn)
        if doc:
            store_owner_doc(conn, "efl_predictions", doc)
    except Exception:
        conn.rollback()
        log.exception("EFL fantasy export skipped")

"""Export compact JSON for the static website in docs/ (read by docs/index.html).

The nightly GitHub Action runs this after the sync and commits docs/data/ if it changed,
so the site never needs database credentials.
"""
import html
import json
import logging
import math
import re
import shutil
import tempfile
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .health import monitored
from . import config, positions, availability, predictions
from .cache import WEEK, cached_rows, finished_fixtures, rank_history
from .betting import BOOKMAKER, CAUTIOUS_RULE, MAX_ODDS, MIN_EDGE, is_cautious
from .predictions import GOAL_LINES, UPCOMING_STATUSES, goal_lines

log = logging.getLogger(__name__)

OUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "data"
# Written by other commands, not the export: kept across a full export
CARRIED_FILES = ()
PAST_DAYS = 21       # recent results shown on the site
FUTURE_DAYS = 60     # upcoming fixtures shown on the site
FORM_GAMES = 6       # rank change over this many recent games = "form"
CRITICAL_JSON_FILES = (
    "matches.json", "rankings.json", "stats.json", "bets.json",
    "injuries.json", "players.json", "player_seasons.json",
)
CRITICAL_DETAIL_DIRS = ("players", "clubs", "leagues")
MIN_MAJOR_ROWS = {
    "rankings.json": ("rankings", 50),
    "players.json": ("players", 50),
    "player_seasons.json": ("players", 50),
}
MAJOR_ROW_TYPES = {"player_seasons.json": dict}
COLLAPSE_RATIO = 0.5


class ExportValidationError(RuntimeError):
    """Raised when a staged website export is unsafe to publish."""


def market_probabilities(conn):
    """{fixture_id: (p_home, p_draw, p_away)} from the stored match-winner odds: each
    bookmaker's 1/odds normalised to remove its margin, then averaged across bookmakers."""
    books = {}
    for fid, bm, sel, odd in conn.execute(
            "select fixture_id, bookmaker_id, selection, odd from odds where bet_id = 1 and odd > 1"):
        books.setdefault((fid, bm), {})[sel] = 1 / float(odd)
    per_fixture = {}
    for (fid, _), p in books.items():
        if len(p) == 3:
            total = p["Home"] + p["Draw"] + p["Away"]
            per_fixture.setdefault(fid, []).append((p["Home"] / total, p["Draw"] / total, p["Away"] / total))
    return {fid: tuple(sum(x[i] for x in ps) / len(ps) for i in range(3)) for fid, ps in per_fixture.items()}


def site_freshness(conn):
    """When the site's model inputs last changed, for the small 'updated' line on the site:
    the latest stored prediction, injury and odds rows (odds = when we last fetched a price) and
    the latest registered match model version. Anything with no rows is left out, never guessed."""
    out = {}
    for key, table in (("predictions", "fixture_predictions"), ("injuries", "injuries"), ("odds", "odds")):
        (latest,) = conn.execute(f"select max(updated_at) from {table}").fetchone()
        if latest is not None:
            out[key] = latest.isoformat()
    (registry,) = conn.execute("select to_regclass('public.model_versions')").fetchone()
    if registry is not None:
        row = conn.execute(
            """select version_name, code_sha, created_at from model_versions
               where model_type = 'match' order by created_at desc limit 1""").fetchone()
        if row:
            out["model"] = {"name": row[0], "code": row[1][:7] if row[1] else None,
                            "registered": row[2].isoformat()}
    return out


def _r(x, n=2):
    return None if x is None else round(float(x), n)


# API-derived values that the site puts into markup: kit colours go into a style attribute, so
# only a plain hex colour passes
HEX_COLOR = re.compile(r"[0-9a-fA-F]{6}")


def _hex_color(v):
    """A six-digit hex colour without the '#', lower-cased, or None."""
    return v.lower() if isinstance(v, str) and HEX_COLOR.fullmatch(v) else None


def _kit_colors(shirt, number):
    """[shirt, number] when the shirt colour is valid (a bad number colour becomes None), else None."""
    shirt = _hex_color(shirt)
    return [shirt, _hex_color(number)] if shirt else None


def _xi_lines(vals):
    """[GK, DEF, MID, FWD] average ranks rounded, or None when no line has anyone."""
    vals = [_r(v, 1) for v in vals]
    return vals if any(v is not None for v in vals) else None


@monitored("exports", conn_index=0)
def export_site_data(conn, out_dir=OUT_DIR):
    """Build, validate and publish the static site export without clobbering old data."""
    _publish_export(lambda staged: _write_site_data(conn, staged), out_dir)


def _publish_export(build, out_dir=OUT_DIR):
    out_dir = Path(out_dir)
    parent = out_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    staged = Path(tempfile.mkdtemp(prefix=f".{out_dir.name}-staged-", dir=parent))
    try:
        build(staged)
        for rel in CARRIED_FILES:
            if (out_dir / rel).exists() and not (staged / rel).exists():
                shutil.copy2(out_dir / rel, staged / rel)
        validate_export(staged, previous_dir=out_dir if out_dir.exists() else None)
        _replace_export(staged, out_dir)
        staged = None
    finally:
        if staged and staged.exists():
            shutil.rmtree(staged, ignore_errors=True)


def _replace_export(staged, out_dir):
    backup = None
    if out_dir.exists():
        backup = Path(tempfile.mkdtemp(prefix=f".{out_dir.name}-old-", dir=out_dir.parent))
        backup.rmdir()
        out_dir.rename(backup)
    try:
        staged.rename(out_dir)
    except Exception:
        if backup and backup.exists() and not out_dir.exists():
            backup.rename(out_dir)
        raise
    finally:
        if backup and backup.exists():
            shutil.rmtree(backup, ignore_errors=True)


def validate_export(out_dir, previous_dir=None):
    out_dir = Path(out_dir)
    if not out_dir.is_dir():
        raise ExportValidationError(f"Export directory does not exist: {out_dir}")

    parsed = {}
    for rel in CRITICAL_JSON_FILES:
        path = out_dir / rel
        if not path.exists():
            raise ExportValidationError(f"Missing critical export file: {rel}")
        if path.stat().st_size == 0:
            raise ExportValidationError(f"Critical export file is empty: {rel}")
        parsed[rel] = _read_json(path)

    for path in out_dir.rglob("*.json"):
        _read_json(path)

    for rel, (key, minimum) in MIN_MAJOR_ROWS.items():
        value = parsed[rel].get(key)
        expected_type = MAJOR_ROW_TYPES.get(rel, list)
        if not isinstance(value, expected_type):
            raise ExportValidationError(
                f"{rel} does not contain a {expected_type.__name__} at {key!r}")
        if len(value) < minimum:
            raise ExportValidationError(
                f"{rel} has only {len(value)} {key} rows; expected at least {minimum}")

    for rel in CRITICAL_DETAIL_DIRS:
        detail_dir = out_dir / rel
        if not detail_dir.is_dir():
            raise ExportValidationError(f"Missing critical export directory: {rel}")
        if not any(detail_dir.glob("*.json")):
            raise ExportValidationError(f"Critical export directory is empty: {rel}")

    previous_dir = Path(previous_dir) if previous_dir else None
    if previous_dir and previous_dir.is_dir():
        _check_row_collapse(out_dir, previous_dir)


def _read_json(path):
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        raise ExportValidationError(f"Invalid JSON in {path}: {exc}") from exc


def store_owner_doc(conn, name, payload):
    """Owner-only FPL data (audit L3, owner's decision 2026-10-02): FPL's terms don't allow its data
    to be republished, so fpl_predictions and fpl_team go to fpl_owner_docs, never docs/data. The
    site reads them through fpl_owner_data, which checks the owner's passphrase
    (db/migrations/20261003_fpl_owner_docs.sql). Raises if the table is missing or the connection
    is read-only: callers treat that as a skipped export."""
    config.require_db_write(f"store {name}")
    conn.execute("""insert into fpl_owner_docs (name, doc, updated_at) values (%s, %s::jsonb, now())
                    on conflict (name) do update set doc = excluded.doc, updated_at = excluded.updated_at""",
                 [name, json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":"))])
    conn.commit()


def _write_json_file(path, payload, *, ensure_ascii=True):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, separators=(",", ":"), ensure_ascii=ensure_ascii)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as fh:
        fh.write(text)
        tmp = Path(fh.name)
    try:
        tmp.replace(path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def _check_row_collapse(out_dir, previous_dir):
    for rel, (key, _) in MIN_MAJOR_ROWS.items():
        old_path = previous_dir / rel
        new_path = out_dir / rel
        if not old_path.exists():
            continue
        old_value = _read_json(old_path).get(key)
        new_value = _read_json(new_path).get(key)
        expected_type = MAJOR_ROW_TYPES.get(rel, list)
        if not isinstance(old_value, expected_type) or not isinstance(new_value, expected_type) or not old_value:
            continue
        if len(new_value) < len(old_value) * COLLAPSE_RATIO:
            raise ExportValidationError(
                f"{rel} collapsed from {len(old_value)} to {len(new_value)} {key} rows")

    for rel in CRITICAL_DETAIL_DIRS:
        old_dir = previous_dir / rel
        new_dir = out_dir / rel
        if not old_dir.is_dir() or not new_dir.is_dir():
            continue
        old_count = sum(1 for _ in old_dir.glob("*.json"))
        new_count = sum(1 for _ in new_dir.glob("*.json"))
        if old_count >= 10 and new_count < old_count * COLLAPSE_RATIO:
            raise ExportValidationError(
                f"{rel}/ collapsed from {old_count} to {new_count} JSON files")


def _write_site_data(conn, out_dir=OUT_DIR):
    now = datetime.now(timezone.utc)
    out_dir.mkdir(parents=True, exist_ok=True)

    competitions = {
        lid: {"name": name, "country": country, "type": ltype}
        for lid, name, country, ltype in conn.execute(
            "select league_id, name, country, type from leagues")
    }

    market = market_probabilities(conn)
    matches = []
    team_ids = set()
    teams_extra = {}           # national team names (national teams aren't in teams)
    for row in conn.execute(
            """select f.fixture_id, f.kickoff, f.league_id, f.round, f.home_team_id, f.away_team_id,
                      f.status_short, f.home_goals, f.away_goals, f.pen_home, f.pen_away,
                      p.p_home, p.p_draw, p.p_away, p.home_xg, p.away_xg, p.likely_score,
                      p.home_rank, p.away_rank, p.source, p.rating, p.rating_winner,
                      p.rating_margin, p.rating_clean_sheets, p.rating_shape, p.rating_goals,
                      p.home_missing, p.away_missing, p.p_over25, p.p_btts,
                      coalesce(rh.actual_xi_rating, rh.predicted_xi_rating), rh.recent_xi_rating,
                      coalesce(ra.actual_xi_rating, ra.predicted_xi_rating), ra.recent_xi_rating
               from fixtures f left join fixture_predictions p using (fixture_id)
               left join fixture_team_ratings rh on rh.fixture_id = f.fixture_id and rh.team_id = f.home_team_id
               left join fixture_team_ratings ra on ra.fixture_id = f.fixture_id and ra.team_id = f.away_team_id
               where f.kickoff between %s and %s
               order by f.kickoff, f.fixture_id""",
            [now - timedelta(days=PAST_DAYS), now + timedelta(days=FUTURE_DAYS)]):
        (fid, kickoff, lid, rnd, home, away, status, hg, ag, ph, pa_, p_h, p_d, p_a,
         hxg, axg, likely, hr, ar, source, *ratings, h_miss, a_miss, p_over, p_btts,
         h_xi, h_recent, a_xi, a_recent) = row
        team_ids.update((home, away))
        matches.append([
            fid, kickoff.isoformat(), lid, rnd, home, away, status, hg, ag, ph, pa_,
            _r(p_h, 3), _r(p_d, 3), _r(p_a, 3), _r(hxg), _r(axg), likely, _r(hr, 0), _r(ar, 0),
            source, *ratings,
            *[_r(x, 3) for x in market.get(fid, (None, None))[:2]],     # the away share is the rest
            _r(h_miss), _r(a_miss), _r(p_over, 3), _r(p_btts, 3),
            _r(h_xi, 1), _r(h_recent, 1), _r(a_xi, 1), _r(a_recent, 1),
            0,
        ])

    # National team matches (national_fixtures), shown on the Matches tab only: no predictions,
    # line-ups or ranks, and flagged intl = 1 so the site links them to the nation pages
    since, until = now - timedelta(days=PAST_DAYS), now + timedelta(days=FUTURE_DAYS)
    for row in national_matches(conn, since, until):
        fid, kickoff, lid, tournament, rnd, home, away, h_name, a_name, status, hg, ag = row
        competitions.setdefault(lid, {"name": tournament or config.NATIONAL_TEAM_LEAGUES.get(lid, f"Competition {lid}"),
                                      "country": "World", "type": "International"})
        teams_extra[home], teams_extra[away] = html.unescape(h_name), html.unescape(a_name)
        matches.append([fid, kickoff.isoformat(), lid, rnd, home, away, status, hg, ag, None, None,
                        *[None] * 25, 1])
    matches.sort(key=lambda m: (m[1], m[0]))
    nation_pages = {t: nat for t, nat in national_nationalities(conn, list(teams_extra)).items()
                    if nat != teams_extra[t]}

    # Form: total rank change over each team's last FORM_GAMES games
    form = dict(conn.execute(
        """select team_id, sum(rank_change) from (
             select team_id, rank_change,
                    row_number() over (partition by team_id order by match_no desc) rn
             from team_rank_history) x
           where rn <= %s group by team_id""", [FORM_GAMES]).fetchall())

    # League each club is playing in this season (league fixtures in a current season); null for
    # clubs relegated out of every tracked league or only seen in cups
    current_league = dict(conn.execute(
        """select distinct on (team_id) team_id, league_id from (
             select f.home_team_id team_id, f.league_id, f.kickoff from fixtures f
               join leagues l using (league_id) join league_seasons ls using (league_id, season)
               where l.type = 'League' and ls.is_current
             union all
             select f.away_team_id, f.league_id, f.kickoff from fixtures f
               join leagues l using (league_id) join league_seasons ls using (league_id, season)
               where l.type = 'League' and ls.is_current) x
           order by team_id, kickoff desc""").fetchall())

    rankings = []
    for team, lid, cur, st, lt, played, att, dfn, home_r, away_r in conn.execute(
            """select team_id, league_id, current_rank, st_algo, lt_algo, played,
                      attack, defence, home_rating, away_rating
               from team_rankings order by lt_algo desc"""):
        team_ids.add(team)
        rankings.append([team, current_league.get(team, lid), _r(cur, 1), _r(st, 1), _r(lt, 1),
                         played, _r(form.get(team), 1),
                         1 if team in current_league else 0,
                         _r(att, 1), _r(dfn, 1), _r(home_r, 1), _r(away_r, 1)])

    teams = {t: n for t, n in conn.execute(
        "select team_id, name from teams where team_id = any(%s)", [list(team_ids)])}
    for team, name in teams_extra.items():
        teams.setdefault(team, name)

    generated = now.isoformat()
    (out_dir / "matches.json").write_text(json.dumps({
        "generated_at": generated,
        "freshness": site_freshness(conn),
        "fields": ["id", "kickoff", "league", "round", "home", "away", "status", "hg", "ag",
                   "pen_h", "pen_a", "p_home", "p_draw", "p_away", "home_xg", "away_xg",
                   "likely", "home_rank", "away_rank", "source", "rating", "r_winner",
                   "r_margin", "r_clean_sheets", "r_shape", "r_goals", "m_home", "m_draw",
                   "home_missing", "away_missing", "p_over25", "p_btts",
                   "home_xi", "home_recent_xi", "away_xi", "away_recent_xi", "intl"],
        "matches": matches,
        "competitions": competitions,
        "teams": teams,
        "nation_pages": nation_pages,
    }, separators=(",", ":")), encoding="utf-8")
    (out_dir / "rankings.json").write_text(json.dumps({
        "generated_at": generated,
        "fields": ["team", "league", "current", "st", "lt", "played",
                   "form", "in_league", "attack", "defence", "home", "away"],
        "rankings": rankings,
    }, separators=(",", ":")), encoding="utf-8")
    log.info("Exported %d matches and %d rankings to %s", len(matches), len(rankings), out_dir)
    export_stats(conn, out_dir)
    export_bets(conn, out_dir)
    export_explanations(conn, out_dir, now)
    export_methodology(conn, out_dir, now)
    export_injuries(conn, out_dir)
    player_team = export_players(conn, out_dir)
    detail = export_player_seasons(conn, out_dir)
    export_clubs(conn, out_dir, _club_positions(player_team, detail["positions"]))
    export_leagues(conn, out_dir)
    export_player_pages(conn, out_dir, detail)
    export_fantasy(conn, out_dir)
    export_fantasy_predictions(conn)
    export_efl_fantasy(conn, out_dir)
    export_nations(conn, out_dir)


def export_nations(conn, out_dir=OUT_DIR):
    """data/nations.json, the national team ranking, and data/nations/, the national team pages
    (nations.py). Not critical: if it fails (no copy of the public results and no download), the
    last published files are kept."""
    from . import nations
    try:
        nations.export_nations(conn, out_dir)
    except Exception:
        log.exception("Nations export failed; keeping the last published nations.json and nations/")
        conn.rollback()
        old, new = OUT_DIR / "nations.json", Path(out_dir) / "nations.json"
        if old.exists() and old.resolve() != new.resolve():
            shutil.copy2(old, new)
            if (OUT_DIR / "nations").is_dir():
                shutil.copytree(OUT_DIR / "nations", Path(out_dir) / "nations", dirs_exist_ok=True)


def _records_sum(side):
    """SQL for record_totals() of a snapshot's home_records / away_records, so the record lists
    (most of a snapshot's size) never leave the database."""
    return f"""cross join lateral (
        select coalesce(sum((r->>0)::float8), 0), coalesce(sum((r->>1)::float8), 0), count(*)
        from jsonb_array_elements(coalesce(s.inputs->'{side}_records', '[]'::jsonb)) r) {side[0]}r"""


def explanation(inputs, league_id, home_totals, away_totals, stored, meta):
    """One match's entry in explanations.json: predictions.explain() on the snapshot behind the
    stored prediction, plus the inputs it was built from, rounded for display. None if the
    snapshot doesn't reproduce the stored prediction."""
    parts = predictions.explain(inputs, league_id, home_totals, away_totals, stored)
    if parts is None:
        return None
    pair = lambda k, n=0: [_r(inputs.get(f"home_{k}"), n), _r(inputs.get(f"away_{k}"), n)]
    lines = inputs.get("predicted_lines")
    out = {
        "current": pair("current_rank"), "baseline": pair("lt_algo"), "match": pair("match_rank"),
        "margin": {k: _r(v) for k, v in parts["margin"].items()},
        "exp_diff": _r(parts["exp_diff"]),
        "tendencies": _r(parts["tendencies"]), "league_goals": _r(parts["league_goals"]),
        "missing": pair("missing", 1),
        "lines": [[_r(v, 0) for v in side] for side in lines] if lines else None,
        "reasons": [[k, _r(v)] for k, v in parts["reasons"]],
        **meta,
    }
    fallback = [bool(inputs.get("home_rank_fallback")), bool(inputs.get("away_rank_fallback"))]
    if any(fallback):
        out["fallback"] = fallback
    return out


def export_explanations(conn, out_dir=OUT_DIR, now=None):
    """docs/data/explanations.json: for every match on the site whose prediction has a snapshot,
    the parts of that prediction (see predictions.explain), when its inputs were captured and
    the model version that made it (details once each, under "models"). The site loads it after the matches, so it doesn't slow the first page."""
    now = now or datetime.now(timezone.utc)
    out, models = {}, {}
    (registry,) = conn.execute("select to_regclass('public.match_prediction_snapshots')").fetchone()
    if registry is not None:
        # The latest snapshot whose outputs are the stored prediction's: the one it came from
        rows = conn.execute(
            f"""select distinct on (f.fixture_id) f.fixture_id, f.league_id,
                       s.inputs - 'home_records' - 'away_records',
                       hr.*, ar.*, p.exp_diff, p.home_xg, p.away_xg,
                       s.source, s.captured_at, s.model_version_id, v.version_name, v.code_sha
                from fixtures f join fixture_predictions p using (fixture_id)
                join match_prediction_snapshots s on s.fixture_id = f.fixture_id
                  and s.home_xg = p.home_xg and s.away_xg = p.away_xg and s.p_home = p.p_home
                left join model_versions v on v.model_version_id = s.model_version_id
                {_records_sum("home")} {_records_sum("away")}
                where f.kickoff between %s and %s
                order by f.fixture_id, s.captured_at desc""",
            [now - timedelta(days=PAST_DAYS), now + timedelta(days=FUTURE_DAYS)]).fetchall()
        ids = [r[0] for r in rows]
        seen = {}
        for key, sql in (("odds_at", "select fixture_id, max(updated_at) from odds where bet_id = 1 and fixture_id = any(%s) group by fixture_id"),
                         ("injuries_at", "select fixture_id, max(updated_at) from injuries where fixture_id = any(%s) group by fixture_id")):
            seen[key] = dict(conn.execute(sql, [ids]).fetchall()) if ids else {}
        for (fid, lid, inputs, hs, hc, hn, as_, ac, an, exp_diff, hxg, axg,
             source, captured, version_id, version_name, code_sha) in rows:
            meta = {"source": source, "captured_at": captured.isoformat(), "model": version_id}
            meta.update((k, v[fid].isoformat()) for k, v in seen.items() if fid in v)
            entry = explanation(inputs, lid, (hs, hc, hn), (as_, ac, an), (exp_diff, hxg, axg), meta)
            if entry:
                out[str(fid)] = entry
                models[version_id] = {"name": version_name, "code": code_sha[:7] if code_sha else None}
    _write_json_file(out_dir / "explanations.json",
                     {"generated_at": now.isoformat(), "models": models, "matches": out})
    log.info("Exported explanations for %d matches", len(out))


STAT_RANGES = {"7d": 7, "30d": 30, "90d": 90, "365d": 365}
ENGLISH = [39, 40, 41, 42, 43, 50, 51, 45, 46, 47, 48, 528]


def _stats(rows):
    """Accuracy summary for (p_home, p_draw, p_away, home_xg, away_xg, likely, hg, ag, source,
    rating, r_winner, r_margin, r_clean_sheets, r_shape, r_goals)."""
    n = len(rows)
    if not n:
        return None
    correct = exact = live = home_wins = 0
    logloss = brier = goal_err = 0.0
    calib = [[0, 0.0, 0] for _ in range(10)]   # per 10% bin: count, sum of predicted, hits
    ratings = [0] * 5                               # count of 1s..5s
    factor_sums = [0.0] * 5
    rated = 0
    mk = {"n": 0, "model_ll": 0.0, "market_ll": 0.0, "model_correct": 0, "market_correct": 0}
    for ph, pd, pa, hxg, axg, likely, hg, ag, source, rating, *factors, mprobs in rows:
        if mprobs:
            r_ = 0 if hg > ag else 1 if hg == ag else 2
            mk["n"] += 1
            mk["model_ll"] += -math.log(max((ph, pd, pa)[r_], 1e-6))
            mk["market_ll"] += -math.log(max(mprobs[r_], 1e-6))
            mk["model_correct"] += (ph, pd, pa).index(max(ph, pd, pa)) == r_
            mk["market_correct"] += mprobs.index(max(mprobs)) == r_
        if rating:
            rated += 1
            ratings[rating - 1] += 1
            for i, f in enumerate(factors):
                factor_sums[i] += f
        res = 0 if hg > ag else 1 if hg == ag else 2
        probs = (ph, pd, pa)
        correct += probs.index(max(probs)) == res
        exact += likely == f"{hg}-{ag}"
        live += source == "live"
        home_wins += res == 0
        logloss += -math.log(max(probs[res], 1e-6))
        brier += sum((p - (i == res)) ** 2 for i, p in enumerate(probs))
        goal_err += (abs(hxg - hg) + abs(axg - ag)) / 2
        for i, p in enumerate(probs):
            b = calib[min(9, int(p * 10))]
            b[0] += 1; b[1] += p; b[2] += i == res
    return {
        "n": n, "live": live,
        "correct": round(correct / n, 4), "exact": round(exact / n, 4),
        "home_rate": round(home_wins / n, 4),
        "log_loss": round(logloss / n, 4), "brier": round(brier / n, 4),
        "goal_error": round(goal_err / n, 3),
        "market": {"n": mk["n"],
                   "model_ll": round(mk["model_ll"] / mk["n"], 4),
                   "market_ll": round(mk["market_ll"] / mk["n"], 4),
                   "model_correct": round(mk["model_correct"] / mk["n"], 4),
                   "market_correct": round(mk["market_correct"] / mk["n"], 4)} if mk["n"] else None,
        "rated": rated,
        "rating_avg": round(sum((i + 1) * c for i, c in enumerate(ratings)) / rated, 3) if rated else None,
        "rating_counts": ratings,
        "factor_avgs": dict(zip(["winner", "margin", "clean_sheets", "shape", "goals"],
                                [round(x / rated, 2) for x in factor_sums])) if rated else None,
        "calibration": [[c, round(s / c, 3), round(h / c, 3)] if c else [0, None, None]
                        for c, s, h in calib],
    }


# Stats tab, model vs bookmakers per market: market -> (bet id, API line or "", selections)
STAT_MARKETS = {
    "1X2": (1, "", ("Home", "Draw", "Away")),
    "BTTS": (8, "", ("Yes", "No")),
    **{f"OU{int(l * 10)}": (5, str(l), ("Over", "Under")) for l in GOAL_LINES},
}


def market_consensus(conn, since):
    """{(fixture, market): {"close": [probs], "open": [probs] or None}} for finished fixtures
    since `since`, in STAT_MARKETS' selection order.

    Each bookmaker's complete set of prices with its margin removed, averaged, worked out in the
    database so only a dozen numbers per fixture come back. Closing = the last price before
    kickoff (odds.odd); opening = odds.first_odd, only where the bookmaker's whole set was
    first seen before kickoff (odds loaded after a match was played have no real opening)."""
    lines = [f"{side} {l}" for l in GOAL_LINES for side in ("Over", "Under")]
    out = defaultdict(lambda: {"close": {}, "open": {}})
    for fid, bet, line, sel, close, open_ in conn.execute(
            """with o as (
                 select o.fixture_id, o.bookmaker_id, o.bet_id,
                        case when o.bet_id = 5 then split_part(o.selection, ' ', 2) else '' end as line,
                        case when o.bet_id = 5 then split_part(o.selection, ' ', 1) else o.selection end as sel,
                        o.odd::float8 as odd, o.first_odd::float8 as first_odd,
                        o.first_seen_at < f.kickoff and o.first_odd > 1 as has_open
                 from odds o join fixtures f using (fixture_id)
                 where f.status_short = any(%s) and f.kickoff >= %s and o.odd > 1
                   and (o.bet_id in (1, 8) or (o.bet_id = 5 and o.selection = any(%s)))),
               s as (
                 select *, sum(1 / odd) over w as tot, count(*) over w as n,
                        bool_and(has_open) over w as all_open,
                        sum(case when has_open then 1 / first_odd end) over w as tot_open
                 from o window w as (partition by fixture_id, bookmaker_id, bet_id, line))
               select fixture_id, bet_id, line, sel, avg(1 / odd / tot),
                      avg(1 / first_odd / tot_open) filter (where all_open)
               from s where n = case when bet_id = 1 then 3 else 2 end
               group by 1, 2, 3, 4""",
            [["FT", "AET", "PEN"], since, lines]):
        market = next((m for m, (b, l, _) in STAT_MARKETS.items() if b == bet and l == line), None)
        if market:
            out[(fid, market)]["close"][sel] = close
            if open_ is not None:
                out[(fid, market)]["open"][sel] = open_
    result = {}
    for (fid, market), d in out.items():
        sels = STAT_MARKETS[market][2]
        if all(x in d["close"] for x in sels):
            result[(fid, market)] = {"close": [d["close"][x] for x in sels],
                                     "open": [d["open"][x] for x in sels] if all(x in d["open"] for x in sels) else None}
    return result


def _market_stats(rows):
    """Model vs bookmakers per market for rows of (model {market: probs}, index of what
    happened per market, consensus {market: {close, open}}): log losses on the same matches."""
    out = {}
    for market in STAT_MARKETS:
        n = no = 0
        m_ll = c_ll = mo_ll = o_ll = 0.0
        for model, happened, cons in rows:
            c = cons.get(market)
            if not c or market not in model:
                continue
            i = happened[market]
            ll = lambda p: -math.log(max(p[i], 1e-6))
            n += 1; m_ll += ll(model[market]); c_ll += ll(c["close"])
            if c["open"]:
                no += 1; mo_ll += ll(model[market]); o_ll += ll(c["open"])
        if n:
            out[market] = {"n": n, "model_ll": round(m_ll / n, 4), "close_ll": round(c_ll / n, 4),
                           "open_n": no, "model_open_ll": round(mo_ll / no, 4) if no else None,
                           "open_ll": round(o_ll / no, 4) if no else None}
    return out or None


def export_stats(conn, out_dir=OUT_DIR):
    """Prediction accuracy by date range and competition, for the site's Stats tab."""
    now = datetime.now(timezone.utc)
    rows = conn.execute(
        """select f.kickoff, f.league_id, p.p_home, p.p_draw, p.p_away, p.home_xg, p.away_xg,
                  p.likely_score, f.home_goals, f.away_goals, p.source, p.rating, p.rating_winner,
                  p.rating_margin, p.rating_clean_sheets, p.rating_shape, p.rating_goals,
                  f.fixture_id
           from fixture_predictions p join fixtures f using (fixture_id)
           where f.status_short = any(%s) and f.home_goals is not null and f.kickoff >= %s""",
        [["FT", "AET", "PEN"], now - timedelta(days=max(STAT_RANGES.values()))]).fetchall()
    market = market_probabilities(conn)
    rows = [(*r, market.get(r[-1])) for r in rows]

    # every market with odds: the model's chances (goal lines from its projected goals) and
    # what happened over 90 minutes, per fixture
    since = now - timedelta(days=max(STAT_RANGES.values()))
    cons = market_consensus(conn, since)
    with_odds = {fid for fid, _ in cons}
    per_fixture = {}
    for fid, ph, pd, pa, pb, hx, ax, hg, ag in conn.execute(
            """select f.fixture_id, p.p_home, p.p_draw, p.p_away, p.p_btts, p.home_xg, p.away_xg,
                      f.ft_home, f.ft_away
               from fixture_predictions p join fixtures f using (fixture_id)
               where f.fixture_id = any(%s) and f.ft_home is not null and p.home_xg is not null""",
            [list(with_odds)]):
        model = {"1X2": [float(ph), float(pd), float(pa)]}
        if pb is not None:
            model["BTTS"] = [float(pb), 1 - float(pb)]
        for line, po in goal_lines(float(hx), float(ax)).items():
            model[f"OU{int(line * 10)}"] = [po, 1 - po]
        happened = {"1X2": 0 if hg > ag else 1 if hg == ag else 2, "BTTS": 0 if hg > 0 and ag > 0 else 1,
                    **{f"OU{int(l * 10)}": 0 if hg + ag > l else 1 for l in GOAL_LINES}}
        per_fixture[fid] = (model, happened, {m: cons[(fid, m)] for m in STAT_MARKETS if (fid, m) in cons})
    stats = {}
    for key, days in STAT_RANGES.items():
        recent = [r for r in rows if r[0] >= now - timedelta(days=days)]
        by_group = {"all": recent, "eng": [r for r in recent if r[1] in ENGLISH]}
        for r in recent:
            by_group.setdefault(str(r[1]), []).append(r)
        # drop the fixture_id column (second to last) before summarising
        stats[key] = {g: _stats([(*r[2:-2], r[-1]) for r in rs]) for g, rs in by_group.items() if rs}
        for g, rs in by_group.items():
            if g in stats[key]:
                stats[key][g]["markets"] = _market_stats([per_fixture[r[-2]] for r in rs if r[-2] in per_fixture])
    (out_dir / "stats.json").write_text(json.dumps(
        {"generated_at": now.isoformat(), "ranges": stats}, separators=(",", ":")), encoding="utf-8")
    log.info("Exported prediction stats for %d finished fixtures", len(rows))


def _table_exists(conn, name):
    (found,) = conn.execute("select to_regclass(%s)", [f"public.{name}"]).fetchone()
    return found is not None


def national_matches(conn, since, until):
    """Senior national team matches (national_fixtures) kicking off between since and until, for
    the Matches tab. Friendlies also has youth sides ("England U19") and clubs touring against
    national teams (teams.national false); both are left out. Empty until that table exists."""
    if not _table_exists(conn, "national_fixtures"):
        return []
    return conn.execute(
        r"""select fixture_id, kickoff, league_id, tournament, round, home_team_id, away_team_id,
                   home_name, away_name, status_short, home_goals, away_goals
            from national_fixtures nf
            where kickoff between %s and %s
              and home_name !~ ' U\d{2}$' and away_name !~ ' U\d{2}$'
              and not exists (select 1 from teams t where t.team_id in (nf.home_team_id, nf.away_team_id)
                                                     and t.national is false)
            order by kickoff, fixture_id""", [since, until]).fetchall()


def national_nationalities(conn, team_ids):
    """{national team id: its players' most common nationality}: the site's nation pages go by
    nationality, which isn't always the team's name ("Bosnia & Herzegovina" plays as "Bosnia and
    Herzegovina"). A nationality that is another national team's name is dropped: small nations
    have many dual nationals (Madagascar's players are mostly listed as French). Teams with no
    stat lines yet are left out."""
    if not team_ids or not _table_exists(conn, "national_fixture_players"):
        return {}
    return dict(conn.execute(
        """select x.team_id, x.nationality from (
             select distinct on (nfp.team_id) nfp.team_id, p.nationality
             from national_fixture_players nfp join players p using (player_id)
             where nfp.team_id = any(%s) and p.nationality is not null
             group by nfp.team_id, p.nationality
             order by nfp.team_id, count(*) desc, p.nationality) x
           where not exists (select 1 from national_fixtures nf
                             where (nf.home_name = x.nationality and nf.home_team_id <> x.team_id)
                                or (nf.away_name = x.nationality and nf.away_team_id <> x.team_id))""",
        [team_ids]).fetchall())


def _period(rows):
    kickoffs = [r["effective_at"] for r in rows]
    return {"from": min(kickoffs).isoformat(), "to": max(kickoffs).isoformat()} if kickoffs else None


def _versions(conn, rows):
    """[{name, n}] for the model versions behind rows, most used first; unregistered ids by id."""
    counts = defaultdict(int)
    for r in rows:
        counts[r["model_version_id"]] += 1
    names = dict(conn.execute("select model_version_id, version_name from model_versions where model_version_id = any(%s)",
                              [list(counts)]).fetchall()) if counts else {}
    return [{"name": names.get(v, v), "n": n} for v, n in sorted(counts.items(), key=lambda x: -x[1])]


def export_methodology(conn, out_dir=OUT_DIR, now=None):
    """docs/data/methodology.json: the live record for the Methodology page. Only prospective
    snapshots (captured and stored before kickoff) are scored, through evaluation.py's selection
    and metrics; reconstructed predictions never enter it. Model vs market is left out on purpose:
    that comparison is protocol P6, blinded until its registered sample is reached."""
    from . import evaluation
    from types import SimpleNamespace
    now = now or datetime.now(timezone.utc)
    args = SimpleNamespace(source="prospective", start=datetime(2000, 1, 1, tzinfo=timezone.utc),
                           end=now, as_of=now, hours_before=0)
    out = {"generated_at": now.isoformat(), "freshness": site_freshness(conn), "matches": None, "lineups": None}
    if _table_exists(conn, "match_prediction_snapshots"):
        rows, coverage = evaluation.load_matches(conn, args, market=False)
        if rows:
            m = evaluation.match_metrics(rows)
            probs = [p for r in rows for p in r["probabilities"]]
            hits = [int(k == r["outcome"]) for r in rows for k in range(3)]
            out["matches"] = {
                "n": m["n"], "period": _period(rows), "versions": _versions(conn, rows),
                "accuracy": _r(m["accuracy"], 4), "log_loss": _r(m["log_loss"], 4), "brier": _r(m["brier"], 4),
                "exact_score": {"n": m["exact_score"]["n"], "accuracy": _r(m["exact_score"]["accuracy"], 4)},
                # every home/draw/away probability pooled into tenths: [bin, n, mean predicted, observed rate]
                "calibration": [[b, v["n"], _r(v["mean_probability"], 3), _r(v["observed_rate"], 3)]
                                for b, v in evaluation.calibration(probs, hits).items()],
                "excluded_no_regulation_score": coverage["missing_regulation_score"]}
    if _table_exists(conn, "lineup_prediction_snapshots") and _table_exists(conn, "official_lineup_snapshots"):
        rows, coverage = evaluation.load_lineups(conn, args)
        if rows:
            m = evaluation.lineup_metrics(rows)
            out["lineups"] = {
                "n": m["n"], "period": _period(rows), "versions": _versions(conn, rows),
                "correct_starters_mean": _r(m["correct_starters_mean"], 2),
                "role_accuracy": {"n": m["role_accuracy"]["n"], "accuracy": _r(m["role_accuracy"]["accuracy"], 4)},
                "excluded_no_official_xi": coverage["missing_or_incomplete_official_xi"]}
    _write_json_file(out_dir / "methodology.json", out)
    log.info("Exported the methodology live record (%s matches, %s lineups)",
             (out["matches"] or {}).get("n", 0), (out["lineups"] or {}).get("n", 0))
    export_lineup_record(conn, out_dir, now)


LINEUP_RECORD_FIELDS = ["fixture", "kickoff", "league", "team", "opponent", "home", "correct",
                        "roles_right", "roles_known", "lines", "hours_before", "version", "missed", "wrong"]
LINEUP_HISTORY_FIELDS = ["fixture", "kickoff", "league", "team", "opponent", "home", "correct",
                         "roles_right", "roles_known", "lines", "missed", "wrong"]


def _score_xi(predicted, actual):
    """A predicted XI {player: role} against the XI that started {player: (role, broad position)}:
    (starters named, of them in the right role, of them with both roles known, [starters, of them
    named] for GK, DEF, MID and FWD by the starting role, starters missed, players picked instead)."""
    from .player_ratings import LINES, line_of
    shared = predicted.keys() & actual.keys()
    roles = [predicted[p] == actual[p][0] for p in shared if predicted[p] and actual[p][0]]
    lines = []
    for line in LINES:
        starters = [p for p, (role, broad) in actual.items() if line_of(role, broad) == line]
        lines += [len(starters), sum(p in shared for p in starters)]
    return len(shared), sum(roles), len(roles), lines, sorted(actual.keys() - shared), sorted(predicted.keys() - shared)


def _lineup_names(conn, out, rows, team_i, league_i, missed_i):
    """Fills out's teams, leagues and players (the missed and wrongly picked) for the rows."""
    team_ids = list({x for row in rows for x in (row[team_i], row[team_i + 1]) if x})
    league_ids = list({row[league_i] for row in rows if row[league_i]})
    people = list({p for row in rows for p in row[missed_i] + row[missed_i + 1]})
    if team_ids:
        out["teams"] = {str(t): n for t, n in conn.execute(
            "select team_id, name from teams where team_id = any(%s)", [team_ids]).fetchall()}
    if league_ids:
        out["leagues"] = {str(lid): {"name": n, "country": c} for lid, n, c in conn.execute(
            "select league_id, name, country from leagues where league_id = any(%s)", [league_ids]).fetchall()}
    if people:
        out["players"] = {str(p): n for p, n in conn.execute(
            "select player_id, name from players where player_id = any(%s)", [people]).fetchall()}


def export_lineup_record(conn, out_dir=OUT_DIR, now=None):
    """docs/data/lineups.json: every scored pre-match line-up for the Line-up record tab, one row
    per team, picked by the same rule as the methodology record (evaluation.load_lineups). The tab
    adds them up itself, so it can filter by competition. lines is [starters, of them predicted]
    for GK, DEF, MID and FWD, by the official XI's roles; missed are starters the model left out,
    wrong are the players it picked instead."""
    from . import evaluation
    from types import SimpleNamespace
    now = now or datetime.now(timezone.utc)
    out = {"generated_at": now.isoformat(), "fields": LINEUP_RECORD_FIELDS, "rows": [], "versions": [],
           "leagues": {}, "teams": {}, "players": {}, "excluded_no_official_xi": 0}
    if _table_exists(conn, "lineup_prediction_snapshots") and _table_exists(conn, "official_lineup_snapshots"):
        args = SimpleNamespace(source="prospective", start=datetime(2000, 1, 1, tzinfo=timezone.utc),
                               end=now, as_of=now, hours_before=0)
        rows, coverage = evaluation.load_lineups(conn, args)
        out["excluded_no_official_xi"] = coverage["missing_or_incomplete_official_xi"]
        fixtures = {f: (league, home, away) for f, league, home, away in conn.execute(
            "select fixture_id, league_id, home_team_id, away_team_id from fixtures where fixture_id = any(%s)",
            [list({r["fixture_id"] for r in rows})]).fetchall()} if rows else {}
        version_ids = sorted({r["model_version_id"] for r in rows})
        registered = {v: (name, created) for v, name, created in conn.execute(
            "select model_version_id, version_name, created_at from model_versions where model_version_id = any(%s)",
            [version_ids]).fetchall()} if version_ids else {}
        # oldest first, so the tab can number them v1, v2, ... even when the names repeat
        version_ids.sort(key=lambda v: (registered.get(v, (None, None))[1] or now, v))
        out["versions"] = [{"id": v, "name": registered.get(v, (v,))[0],
                            "registered": registered[v][1].isoformat() if registered.get(v, (None, None))[1] else None}
                           for v in version_ids]
        index = {v: i for i, v in enumerate(version_ids)}
        for r in sorted(rows, key=lambda r: (r["effective_at"], r["fixture_id"], r["team_id"])):
            league, home, away = fixtures.get(r["fixture_id"], (None, None, None))
            correct, right, known, lines, missed, wrong = _score_xi(
                {p["player"]: p.get("role") for p in r["players"] if p.get("predicted_starter")},
                {p["player"]: (p.get("role"), p.get("position")) for p in r["official"] if p.get("starter")})
            out["rows"].append([
                r["fixture_id"], r["effective_at"].isoformat(), league, r["team_id"],
                away if r["team_id"] == home else home, int(r["team_id"] == home), correct, right, known, lines,
                _r(r["seconds_to_kickoff"] / 3600, 1), index[r["model_version_id"]], missed, wrong])
        _lineup_names(conn, out, out["rows"], 3, 2, 12)
    _write_json_file(out_dir / "lineups.json", out)
    log.info("Exported the line-up record (%s team line-ups)", len(out["rows"]))
    export_lineup_history(conn, out_dir, now)


def export_lineup_history(conn, out_dir=OUT_DIR, now=None):
    """docs/data/lineups_history.json: the reconstructed history for the Line-up record tab. The
    predicted XI the nightly player-ratings replay worked out for every finished match
    (reconstructed_lineups), from what it knew before kick-off, scored against the XI that
    started exactly as the live record is. Rebuilt with today's code, so it's kept apart from the
    live record; loaded only when the tab switches to it. kickoff is the match date."""
    now = now or datetime.now(timezone.utc)
    out = {"generated_at": now.isoformat(), "fields": LINEUP_HISTORY_FIELDS, "available": False, "rows": [],
           "leagues": {}, "teams": {}, "players": {}}
    if _table_exists(conn, "reconstructed_lineups"):
        out["available"] = True
        starters = defaultdict(dict)
        for fid, team, player, role, broad in conn.execute(
                """select fp.fixture_id, fp.team_id, fp.player_id, fp.role, fp.position
                   from fixture_players fp join reconstructed_lineups r using (fixture_id, team_id)
                   where fp.started"""):
            starters[(fid, team)][player] = (role, broad)
        for fid, team, players, roles, kickoff, league, home, away in conn.execute(
                """select r.fixture_id, r.team_id, r.players, r.roles, f.kickoff, f.league_id,
                          f.home_team_id, f.away_team_id
                   from reconstructed_lineups r join fixtures f using (fixture_id)
                   where f.status_short = any(%s)
                   order by f.kickoff, r.fixture_id, r.team_id""", [list(config.FINISHED_STATUSES)]):
            actual = starters.get((fid, team), {})
            if len(actual) != 11 or len(players) != 11:
                continue     # no complete team sheet to check against
            correct, right, known, lines, missed, wrong = _score_xi(dict(zip(players, roles)), actual)
            out["rows"].append([fid, kickoff.date().isoformat(), league, team, away if team == home else home,
                                int(team == home), correct, right, known, lines, missed, wrong])
        _lineup_names(conn, out, out["rows"], 3, 2, 10)
    _write_json_file(out_dir / "lineups_history.json", out, ensure_ascii=False)
    log.info("Exported the reconstructed line-up history (%s team line-ups)", len(out["rows"]))


# Paper money shown on the Bets tab: a flat stake per bet out of a starting bank
BET_BANK_GBP = 1000
BET_STAKE_GBP = 10


def _summary(bets):
    settled = [b for b in bets if b["result"] in ("win", "loss")]
    clvs = [b["clv"] for b in settled if b["clv"] is not None]
    staked = len(settled)
    profit = sum(b["profit"] for b in settled)
    return {
        "bets": len(bets), "settled": staked, "pending": sum(1 for b in bets if b["result"] is None),
        "wins": sum(1 for b in settled if b["result"] == "win"),
        "profit": round(profit, 2), "roi": round(profit / staked, 4) if staked else None,
        "avg_odds": round(sum(b["odds"] for b in settled) / staked, 3) if staked else None,
        "avg_clv": round(sum(clvs) / len(clvs), 4) if clvs else None,
        "beat_close": round(sum(1 for c in clvs if c > 0) / len(clvs), 4) if clvs else None,
    }


INJURY_LOOKBACK_DAYS = 21
# reasons that only cover the match they were listed for: left out of a past match's list
ONE_MATCH_REASONS = {"Red Card", "Yellow Cards", "Suspended", "Coach's decision", "Rest", "International duty",
                     "Transfer negotiations", "Personal Reasons"}
# The only reasons published. Anything else is a medical reason (or "Doping") from a third-party
# feed: health data, which stays in the database for availability.py and never reaches the site
BAN_REASONS = {"Red Card", "Yellow Cards", "Suspended"}
# reasons that mean he is out injured or ill (published as a yes/no, for the national teams' XI)
INJURY_REASON = re.compile(r"injur|illness|knock|surgery|fracture|virus|muscle", re.I)


def _ban(reason):
    """The reason if it is a ban, else None."""
    return reason if reason in BAN_REASONS else None


def _injured(kind, reason):
    """1 when he is listed out (not doubtful) with an injury or illness, else 0."""
    return 1 if kind == "Missing Fixture" and INJURY_REASON.search(reason or "") else 0


def export_injuries(conn, out_dir=OUT_DIR):
    """Each club's injury list for the club page (docs/data/injuries.json): out and doubtful
    players for its next match that has a list, else its latest list from the last
    INJURY_LOOKBACK_DAYS (API-Football publishes a match's list only shortly before it), less
    the one-match reasons (a ban already served). Upcoming fixtures use the backend
    availability merge; past red cards alone are not treated as confirmed current bans.

    ban: the reason when it is a ban (BAN_REASONS), else null: medical reasons aren't published.
    missed: how many of the club's played matches in a row he has been on its list, back from its
    latest (matches with no list for the club, e.g. cups, are skipped). season_rank: his latest
    season rank, for players off the current players list. injured: 1 when he is out injured or ill.
    """
    teams = {}
    for team, fid, kickoff, upcoming, player, name, kind, reason in conn.execute(
            """with pick as (
                   select distinct on (i.team_id) i.team_id, i.fixture_id, f.kickoff,
                          f.status_short in ('NS', 'TBD') and f.kickoff > now() as upcoming
                   from injuries i join fixtures f using (fixture_id)
                   where f.kickoff > now() - %s * interval '1 day'
                   order by i.team_id, (f.status_short in ('NS', 'TBD') and f.kickoff > now()) desc,
                            case when f.kickoff > now() then f.kickoff end, f.kickoff desc)
               select i.team_id, i.fixture_id, pick.kickoff, pick.upcoming, i.player_id, p.name, i.type, i.reason
               from injuries i join pick using (team_id, fixture_id) left join players p using (player_id)
               order by i.team_id, i.type, p.name""", [INJURY_LOOKBACK_DAYS]):
        if not upcoming and reason in ONE_MATCH_REASONS:
            continue
        entry = teams.setdefault(str(team), {"fixture": fid, "kickoff": kickoff.isoformat(), "upcoming": upcoming,
                                             "players": []})
        entry["players"].append([player, html.unescape(name or ""), kind, reason])   # reason: replaced below
    # Upcoming display uses the exact same fixture-scoped merge as lineup selection.
    upcoming_fixtures = availability.next_fixtures(conn)
    merged = availability.load(conn, upcoming_fixtures)
    ids = sorted({p for states in merged.values() for p in states})
    names = dict(conn.execute('SELECT player_id,name FROM players WHERE player_id=any(%s)', [ids]))
    for fid,kickoff,home,away,upcoming in upcoming_fixtures:
        for team in (home,away):
            existing = teams.get(str(team))
            if existing and existing.get('_merged') and existing['kickoff'] <= kickoff.isoformat():
                continue
            states = merged[(fid,team)]
            rows = []
            for player,state in states.items():
                evidence = state['evidence'][-1]  # manual explanation, retaining API evidence in snapshots
                rows.append([player,html.unescape(names.get(player) or evidence.get('name','')),
                             'Suspended' if state['state']=='suspended' else evidence.get('type'),
                             evidence.get('reason')])
            teams[str(team)] = {'fixture':fid,'kickoff':kickoff.isoformat(),'upcoming':True,
                                'players':rows,'_merged':True}
    for entry in teams.values():
        entry.pop('_merged',None)
    listed = defaultdict(dict)          # team -> {fixture: (kickoff, {players on its list})}
    for team, fid, kickoff, player in conn.execute(
            """select i.team_id, i.fixture_id, f.kickoff, i.player_id from injuries i join fixtures f using (fixture_id)
               where i.team_id = any(%s) and f.status_short = any(%s) and f.kickoff > now() - interval '365 days'""",
            [[int(t) for t in teams], list(config.FINISHED_STATUSES)]):
        listed[team].setdefault(fid, (kickoff, set()))[1].add(player)
    for team, entry in teams.items():
        lists = [ps for _, ps in sorted(listed[int(team)].values(), key=lambda x: x[0], reverse=True)]
        for row in entry["players"]:
            row.append(next((k for k, ps in enumerate(lists) if row[0] not in ps), len(lists)))
    # a rank for players off the current list (no recent minutes): his latest season rank, an
    # estimate for a season he hasn't played (player_ratings: unrated players get one too)
    ids = [row[0] for entry in teams.values() for row in entry["players"]]
    season_rank = {p: float(r) for p, r in conn.execute(
        """select distinct on (player_id) player_id, season_rank from player_season_ranks
           where player_id = any(%s) and season_rank is not null
           order by player_id, season desc""", [ids])}
    for entry in teams.values():
        for row in entry["players"]:
            row.append(season_rank.get(row[0]))
            kind, reason = row[2], row[3]
            row[3] = _ban(reason)
            row.append(_injured(kind, reason))
    _write_json_file(out_dir / "injuries.json", {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fields": ["player", "name", "type", "ban", "missed", "season_rank", "injured"], "teams": teams,
    }, ensure_ascii=False)
    log.info("Exported injury lists for %d clubs", len(teams))


def export_bets(conn, out_dir=OUT_DIR):
    """Every paper bet and its result for the site's Bets tab (docs/data/bets.json), all of them
    so the bank there runs from the first bet."""
    rows = conn.execute(
        """select b.bet_id, b.strategy, b.fixture_id, b.kickoff, b.league_id, b.market, b.selection,
                  b.model_prob, b.fair_prob, b.odds_taken, bk.name, b.edge, b.closing_odds, b.clv,
                  b.result, b.profit, b.placed_at, b.settled_at, h.name, a.name,
                  coalesce(f.ft_home, f.home_goals), coalesce(f.ft_away, f.away_goals), b.tags,
                  f.home_team_id, f.away_team_id
           from paper_bets b join fixtures f using (fixture_id)
           join teams h on h.team_id = f.home_team_id join teams a on a.team_id = f.away_team_id
           left join bookmakers bk on bk.bookmaker_id = b.bookmaker_id
           where b.bookmaker_id = %s       -- bets taken elsewhere before Bet365-only stay in the table
           order by b.kickoff desc, b.bet_id""", [BOOKMAKER]).fetchall()
    bets = [{
        "id": r[0], "strategy": r[1], "fixture": r[2], "kickoff": r[3].isoformat(), "league": r[4],
        "market": r[5], "selection": r[6], "model_prob": _r(r[7], 3), "fair_prob": _r(r[8], 3),
        "odds": float(r[9]), "bookmaker": r[10], "edge": _r(r[11], 3),
        "closing_odds": float(r[12]) if r[12] is not None else None, "clv": _r(r[13], 4),
        "result": r[14], "profit": float(r[15]) if r[15] is not None else None,
        "home": r[18], "away": r[19], "home_id": r[23], "away_id": r[24], "score": f"{r[20]}-{r[21]}" if r[20] is not None else None,
        "tags": r[22] or [], "cautious": is_cautious(r[5], r[22]),
    } for r in rows]
    by = lambda key: {k: _summary([b for b in bets if key(b) == k]) for k in sorted({key(b) for b in bets})}
    summary = {
        "all": _summary(bets),
        "strategy": by(lambda b: b["strategy"]),
        "market": by(lambda b: b["market"]),
        "strategy_market": by(lambda b: f"{b['strategy']}|{b['market']}"),
        "league": by(lambda b: str(b["league"])),
        "cautious": _summary([b for b in bets if b["cautious"]]),
        "tag": {t: _summary([b for b in bets if t in b["tags"]]) for t in sorted({t for b in bets for t in b["tags"]})},
    }
    last = max([r[16] for r in rows] + [r[17] for r in rows if r[17]], default=None)
    # No generation timestamp, so the file only changes (and gets committed) when bets do
    _write_json_file(out_dir / "bets.json", {
        "last_change": last.isoformat() if last else None,
        "rules": {"min_edge": MIN_EDGE, "max_odds": MAX_ODDS, "bookmaker": "Bet365", "stake": 1, "stake_gbp": BET_STAKE_GBP, "bank": BET_BANK_GBP, "cautious_rule": CAUTIOUS_RULE},
        "summary": summary, "bets": bets,
    })
    log.info("Exported %d paper bets", len(bets))


PLAYER_SEASONS = list(range(2026, 2020, -1))     # season ranks shown, newest first


POSITION_SHARE = 0.25      # a position counts for the filter at this share of his starting minutes

LISTED = """p.current_rank is not null and (p.rank_minutes >= 450 or exists (
    select 1 from player_season_ranks r where r.player_id = p.player_id and r.season = any(%s)
      and r.minutes >= 1500) or exists (select 1 from team_squads s where s.player_id = p.player_id))"""


def export_players(conn, out_dir=OUT_DIR):
    """Current player ranks, season ranks and each team's predicted XI for its next match
    (players.json). A season rank is the player's average rank across that season (after each
    match, weighted by minutes; player_season_ranks), blank if he didn't play in these leagues."""
    # Listed: 450+ minutes in his last 20 appearances, a 1,500+ minute season in the seasons
    # shown (an established player back from injury, e.g. John Stones), or in a current squad
    # (a new signing). His club: the squad he's in now (team_squads), else the club the weekly
    # current-club check found this season (player_career_checks), else his last appearance.
    # Nationality can be corrected by hand in player_overrides
    players = conn.execute(
        f"""with club_league as (           -- each club's league: its latest league fixture
                select distinct on (team_id) team_id, league_id from (
                    select f.home_team_id team_id, f.league_id, f.kickoff from fixtures f join leagues l using (league_id)
                    where l.type = 'League'
                    union all
                    select f.away_team_id, f.league_id, f.kickoff from fixtures f join leagues l using (league_id)
                    where l.type = 'League') x
                order by team_id, kickoff desc),
            this_season as (select max(season) s from fixtures where league_id = any(%s))
           select p.player_id, p.name, p.rank_position, p.current_rank, p.rank_minutes, c.team_id,
                  coalesce(cl.league_id, f.league_id), extract(year from age(p.birth_date))::int,
                  coalesce(o.nationality, p.nationality)
           from players p
           left join player_overrides o using (player_id)
           join lateral (select fp.team_id, fp.fixture_id from fixture_players fp
                         where fp.player_id = p.player_id order by fp.fixture_id desc limit 1) x on true
           join fixtures f on f.fixture_id = x.fixture_id
           left join lateral (select s.team_id from team_squads s where s.player_id = p.player_id
                              order by (s.team_id = x.team_id) desc, s.fetched_at desc limit 1) sq on true
           left join player_career_checks cc on cc.player_id = p.player_id
                and cc.season = (select s from this_season) and cc.team_id is not null
           -- his last club, unless we have its current squad and he isn't in it (he has left and his
           -- new club isn't known yet: no club rather than the wrong one)
           cross join lateral (select coalesce(sq.team_id, cc.team_id,
                case when exists (select 1 from team_squads s2 where s2.team_id = x.team_id) then null
                     else x.team_id end) team_id) c
           left join club_league cl on cl.team_id = c.team_id
           where {LISTED}
           order by p.current_rank desc""", [config.MATCH_PLAYER_LEAGUES, PLAYER_SEASONS]).fetchall()
    season_ranks, estimated = defaultdict(dict), defaultdict(set)
    for player, season, rank, minutes in conn.execute(
            "select player_id, season, season_rank, minutes from player_season_ranks where season = any(%s)",
            [PLAYER_SEASONS]):
        season_ranks[player][season] = float(rank)
        if minutes == 0:                 # a gap season filled from the age curve
            estimated[player].add(season)
    # Positions he started in for POSITION_SHARE+ of his starting minutes over the last 12 months
    # (the position filter includes him there too); minutes off the bench have no position
    role_mins = defaultdict(dict)
    for player, role, mins in conn.execute(
            """select fp.player_id, fp.role, sum(fp.minutes) from fixture_players fp join fixtures f using (fixture_id)
               where fp.player_id = any(%s) and fp.role is not null and fp.minutes > 0
                 and f.status_short = any(%s) and f.kickoff > now() - interval '365 days'
               group by 1, 2""", [[r[0] for r in players], list(config.FINISHED_STATUSES)]):
        role_mins[player][role] = mins
    pos_12m = {p: sorted((r for r, m in rm.items() if m >= POSITION_SHARE * sum(rm.values())), key=lambda r: -rm[r])
               for p, rm in role_mins.items()}
    # his position on the site: where he's started most minutes over the last 12 months (his
    # latest rating window's most common start if he hasn't started in that time)
    main_pos = {p: max(rm, key=rm.get) for p, rm in role_mins.items()}
    pos_ranks = defaultdict(dict)        # {player: {role group: rank as that position}}
    for player, g, r in conn.execute("select player_id, role_group, position_rank from player_position_ranks"):
        pos_ranks[player][g] = float(r)
    # anchored on the position shown for him, so "As <his position>" equals his rank, and no
    # position above his rank (De Cuyper, shown as LW, isn't better as a full-back than overall)
    for r in players:
        ranks = pos_ranks.get(r[0])
        if not ranks:
            continue
        g = positions.group(main_pos.get(r[0], r[2]))
        shift = float(r[3]) - ranks[g] if g in ranks else 0.0
        pos_ranks[r[0]] = {k: round(min(max(v + shift, 0), float(r[3])), 1) for k, v in ranks.items()}
    lineups = conn.execute(
        """select distinct on (pl.team_id, pl.player_id) pl.team_id, pl.fixture_id, pl.player_id,
                  p.name, pl.position, pl.player_rank
           from predicted_lineups pl join players p using (player_id) join fixtures f using (fixture_id)
           where (pl.team_id, f.kickoff) in (select pl2.team_id, min(f2.kickoff) from predicted_lineups pl2
                                             join fixtures f2 using (fixture_id) group by pl2.team_id)
           order by pl.team_id, pl.player_id""").fetchall()
    next_xi = {}
    for team, fid, player, name, pos, rank in lineups:
        entry = next_xi.setdefault(str(team), {"fixture": fid, "players": []})
        entry["players"].append([player, name, pos, float(rank) if rank is not None else None])
    all_lineups = conn.execute(
        """select pl.fixture_id, pl.team_id, pl.player_id, p.name, pl.position, pl.player_rank
           from predicted_lineups pl join players p using (player_id)
           order by pl.fixture_id, pl.team_id, pl.player_id""").fetchall()
    fixture_xi = {}
    for fid, team, player, name, pos, rank in all_lineups:
        fixture_xi.setdefault(str(fid), {}).setdefault(str(team), []).append(
            [player, name, pos, float(rank) if rank is not None else None])
    actual_lineups = conn.execute(
        f"""with starters as (
                select fixture_id, team_id, player_id,
                       coalesce(role, case position when 'G' then 'GK' when 'D' then 'CB'
                                      when 'M' then 'CM' when 'F' then 'ST' end) role,
                       1 src
                from fixture_players where started
                union all
                select fixture_id, team_id, player_id, role, 2 src from fixture_lineups),
            x as (select distinct on (fixture_id, team_id, player_id) fixture_id, team_id, player_id, role
                  from starters order by fixture_id, team_id, player_id, src)
            select x.fixture_id, x.team_id, x.player_id, p.name, x.role,
                  coalesce(fpr.player_rank, p.current_rank)
            from x join fixtures f using (fixture_id)
            join players p using (player_id)
            left join fixture_player_ranks fpr on fpr.fixture_id = x.fixture_id and fpr.player_id = x.player_id
            where f.status_short = any(%s) and f.kickoff > now() - interval '{PAST_DAYS} days'
            order by x.fixture_id, x.team_id, x.player_id""", [list(config.FINISHED_STATUSES)]).fetchall()
    actual_xi = {}
    for fid, team, player, name, pos, rank in actual_lineups:
        actual_xi.setdefault(str(fid), {}).setdefault(str(team), []).append(
            [player, name, pos, float(rank) if rank is not None else None])
    # the XI the model predicted for those matches: its last genuine pre-match capture, taken before
    # the official XI was first seen (evaluation.load_lineups' rule), so the site can mark each
    # starter as predicted or not. [id, name, role, rank going into the match]
    prematch_xi = {}
    if actual_xi and _table_exists(conn, "lineup_prediction_snapshots") and _table_exists(conn, "official_lineup_snapshots"):
        snapshots = conn.execute(
            """select distinct on (s.fixture_id, s.team_id) s.fixture_id, s.team_id, s.players
               from lineup_prediction_snapshots s
               where s.source = 'prospective' and s.fixture_id = any(%s)
                 and s.captured_at < coalesce((select min(o.captured_at) from official_lineup_snapshots o
                     where o.fixture_id = s.fixture_id and o.team_id = s.team_id
                       and o.effective_at = s.effective_at), 'infinity'::timestamptz)
               order by s.fixture_id, s.team_id, s.captured_at desc, s.snapshot_id desc""",
            [[int(f) for f in actual_xi]]).fetchall()
        ids = list({p["player"] for *_, ps in snapshots for p in ps if p.get("predicted_starter")})
        names = dict(conn.execute("select player_id, name from players where player_id = any(%s)", [ids]).fetchall())
        for fid, team, ps in snapshots:
            prematch_xi.setdefault(str(fid), {})[str(team)] = [
                [p["player"], names.get(p["player"], ""), p.get("role"), p.get("player_rating")]
                for p in ps if p.get("predicted_starter")]
    # team-sheet order: keeper, defence right to left, midfield, attack
    order = {r: i for i, r in enumerate(["GK", "RB", "RWB", "CB", "LB", "LWB", "DM", "CM", "RM", "LM",
                                          "AM", "RW", "LW", "ST"])}
    for entry in next_xi.values():
        entry["players"].sort(key=lambda x: (order.get(x[2], 99), -(x[3] or 0)))
    for teams in fixture_xi.values():
        for xi_players in teams.values():
            xi_players.sort(key=lambda x: (order.get(x[2], 99), -(x[3] or 0)))
    for teams in actual_xi.values():
        for xi_players in teams.values():
            xi_players.sort(key=lambda x: (order.get(x[2], 99), -(x[3] or 0)))
    # this season so far, all his clubs: [minutes, match rating (minutes-weighted), goals, assists,
    # his clubs' minutes]; the per-match leagues first, else the season totals where his league has
    # them (player_seasons, no club minutes)
    season_stats = {}
    rating_avg = """(sum(x.rating * x.minutes) filter (where x.rating is not null)
                     / nullif(sum(x.minutes) filter (where x.rating is not null), 0))::float8"""
    for _, player, mins, rating, goals, assists in conn.execute(
            f"""select 1 src, x.player_id, sum(x.minutes), {rating_avg}, sum(x.goals), sum(x.assists)
                from player_seasons x where x.season = %s and x.player_id = any(%s) and x.minutes > 0
                group by 2
                union all
                select 2, x.player_id, sum(x.minutes), {rating_avg}, sum(x.goals), sum(x.assists)
                from fixture_players x join fixtures f using (fixture_id)
                where f.season = %s and x.player_id = any(%s) and f.status_short = any(%s) and x.minutes > 0
                group by 2
                order by src""",
            [PLAYER_SEASONS[0], [r[0] for r in players]] * 2 + [list(config.FINISHED_STATUSES)]):
        season_stats[player] = [int(mins), round(rating, 2) if rating is not None else None,
                                int(goals or 0), int(assists or 0), None]   # per-match rows come last and win
    # his clubs' minutes: 90 a match for each club he's played for this season, from his first
    # appearance for it (a new signing isn't marked down for matches before he joined), in the
    # matches with player data (the ones his own minutes come from). The site greys his rating when
    # he's played under a third of them (a squad player, or back from injury)
    for player, club_mins in conn.execute(
            """with joined as (
                   select x.player_id, x.team_id, min(f.kickoff) since
                   from fixture_players x join fixtures f using (fixture_id)
                   where f.season = %s and x.player_id = any(%s) and f.status_short = any(%s) and x.minutes > 0
                   group by 1, 2)
               select j.player_id, 90 * count(*)
               from joined j join fixtures f on f.season = %s and j.team_id in (f.home_team_id, f.away_team_id)
                    and f.kickoff >= j.since and f.status_short = any(%s)
                    and (f.league_id = any(%s) or f.players_fetched_at is not null)
               group by 1""",
            [PLAYER_SEASONS[0], [r[0] for r in players], list(config.FINISHED_STATUSES),
             PLAYER_SEASONS[0], list(config.FINISHED_STATUSES), config.MATCH_PLAYER_LEAGUES]):
        if player in season_stats:
            season_stats[player][4] = int(club_mins)
    # his next seasons, projected along his age curve (player_ratings.py)
    future = defaultdict(dict)
    for player, season, rank in conn.execute("select player_id, season, projected_rank from player_projected_ranks"):
        future[player][season] = float(rank)
    future_seasons = sorted({y for ys in future.values() for y in ys})
    (out_dir / "players.json").write_text(json.dumps({
        "fields": ["id", "name", "position", "rank", "minutes", "team", "league", "seasons", "age", "estimated",
                   "nationality", "positions_12m", "position_ranks", "future", "season"],
        "seasons": PLAYER_SEASONS,
        "future_seasons": future_seasons,    # oldest first
        "players": [[r[0], r[1], main_pos.get(r[0], r[2]), float(r[3]), r[4], r[5], r[6],
                     [season_ranks[r[0]].get(y) for y in PLAYER_SEASONS], r[7],
                     [i for i, y in enumerate(PLAYER_SEASONS) if y in estimated[r[0]]], r[8],
                     pos_12m.get(r[0], []), pos_ranks.get(r[0], {}),
                     [future[r[0]].get(y) for y in future_seasons], season_stats.get(r[0])] for r in players],
        "next_xi": next_xi,
        "fixture_xi": fixture_xi,
        "actual_xi": actual_xi,
        "prematch_xi": prematch_xi,
        # names of players' clubs outside the club rankings (a move out of our leagues)
        "teams": {str(t): n for t, n in conn.execute(
            "select team_id, name from teams where team_id = any(%s)", [list({r[5] for r in players if r[5]})])},
    }, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    log.info("Exported %d player ranks and %d predicted XIs", len(players), len(next_xi))
    return {r[0]: r[5] for r in players}       # {player: his club}, for the club files' positions


def _club_spells(rows):
    """[(player, key, team, minutes, club rank, rating, goals, assists)]
    -> {player: {key: [[team, mins, rank, rating, goals, assists], ...]}}, clubs by minutes, most first."""
    out = defaultdict(dict)
    for player, key, team, mins, rank, rating, goals, assists in rows:
        out[player].setdefault(key, []).append(
            [team, int(mins), round(float(rank)) if rank is not None else None,
             round(float(rating), 2) if rating is not None else None, int(goals or 0), int(assists or 0)])
    for seasons in out.values():
        for spells in seasons.values():
            spells.sort(key=lambda x: -x[1])
    return out


SPELL_FIELDS = ["team", "minutes", "club_rank", "rating", "goals", "assists"]


def export_player_seasons(conn, out_dir=OUT_DIR):
    """Hover detail for the Players table (player_seasons.json, loaded on the first hover there).
    Returns what it wrote: each player's own rows also go in his page file and his club's file.

    For each exported player and each season in PLAYER_SEASONS, and for "now" (his last 20
    appearances, the ones the current rank is built from): the clubs he played for, his minutes
    for each, the club's average rank over those matches and his average match rating.
    """
    ids = [r[0] for r in conn.execute(f"select player_id from players p where {LISTED}", [PLAYER_SEASONS])]
    per_club = """sum(fp.minutes),
                  sum(h.lt_before * fp.minutes) / nullif(sum(fp.minutes) filter (where h.lt_before is not null), 0),
                  sum(fp.rating * fp.minutes) filter (where fp.rating is not null)
                    / nullif(sum(fp.minutes) filter (where fp.rating is not null), 0),
                  sum(fp.goals), sum(fp.assists)"""
    seasons = conn.execute(
        f"""select fp.player_id, f.season, fp.team_id, {per_club}
            from fixture_players fp join fixtures f using (fixture_id)
            left join team_rank_history h on h.fixture_id = fp.fixture_id and h.team_id = fp.team_id
            where fp.player_id = any(%s) and f.season = any(%s) and f.status_short = any(%s) and fp.minutes > 0
            group by 1, 2, 3""", [ids, PLAYER_SEASONS, list(config.FINISHED_STATUSES)]).fetchall()
    recent = conn.execute(
        f"""with apps as (
                select fp.*, row_number() over (partition by fp.player_id order by f.kickoff desc) as n
                from fixture_players fp join fixtures f using (fixture_id)
                where fp.player_id = any(%s) and f.status_short = any(%s) and fp.minutes > 0
                  and f.kickoff > now() - interval '540 days')
            select fp.player_id, 'now', fp.team_id, {per_club}
            from apps fp left join team_rank_history h on h.fixture_id = fp.fixture_id and h.team_id = fp.team_id
            where fp.n <= 20 group by 1, 3""", [ids, list(config.FINISHED_STATUSES)]).fetchall()
    # seasons away from the per-match leagues: the club he was at and its level that season, with
    # his season totals where the league has them (player_seasons; minutes 0: an estimate)
    gaps = conn.execute(
        """select r.player_id, r.season, r.team_id, r.minutes, avg(h.lt_before),
                  (select sum(ps.rating * ps.minutes) / nullif(sum(ps.minutes) filter (where ps.rating is not null), 0)
                   from player_seasons ps where ps.player_id = r.player_id and ps.season = r.season
                     and ps.team_id = r.team_id)::float8,
                  coalesce((select sum(ps.goals) from player_seasons ps where ps.player_id = r.player_id
                            and ps.season = r.season and ps.team_id = r.team_id), 0),
                  coalesce((select sum(ps.assists) from player_seasons ps where ps.player_id = r.player_id
                            and ps.season = r.season and ps.team_id = r.team_id), 0)
           from player_season_ranks r
           left join fixtures f on f.season = r.season and r.team_id in (f.home_team_id, f.away_team_id)
           left join team_rank_history h on h.fixture_id = f.fixture_id and h.team_id = r.team_id
           where r.team_id is not null and r.player_id = any(%s)
           group by 1, 2, 3, 4""", [ids]).fetchall()
    spells = _club_spells(seasons + recent + gaps)
    # Starting minutes by position per season: the role he started in (from the line-up grid and
    # formation), or his broad position (G/D/M/F) if a start has no grid. Minutes off the bench
    # have no position and aren't counted. Seasons in leagues without per-match data have none
    positions = defaultdict(dict)
    for player, season, role, mins in conn.execute(
            """select fp.player_id, f.season,
                      coalesce(fp.role, fp.position), sum(fp.minutes)
               from fixture_players fp join fixtures f using (fixture_id)
               where fp.player_id = any(%s) and f.season = any(%s) and f.status_short = any(%s) and fp.minutes > 0
                 and fp.started
               group by 1, 2, 3 order by 4 desc""", [ids, PLAYER_SEASONS, list(config.FINISHED_STATUSES)]):
        positions[player].setdefault(str(season), []).append([role, int(mins)])
    # ... and over the last 12 months ("12m") and all our data from 2020/21 ("all")
    for key, since in (("12m", "now() - interval '365 days'"), ("all", "'-infinity'::timestamptz")):
        for player, role, mins in conn.execute(
                f"""select fp.player_id, coalesce(fp.role, fp.position),
                           sum(fp.minutes)
                    from fixture_players fp join fixtures f using (fixture_id)
                    where fp.player_id = any(%s) and f.status_short = any(%s) and fp.minutes > 0
                      and fp.started and f.kickoff > {since}
                    group by 1, 2 order by 3 desc""", [ids, list(config.FINISHED_STATUSES)]):
            positions[player].setdefault(key, []).append([role, int(mins)])
    team_ids = {x[0] for p in spells.values() for v in p.values() for x in v}
    names = dict(conn.execute("select team_id, name from teams where team_id = any(%s)", [list(team_ids)]))
    detail = {
        "fields": SPELL_FIELDS,
        "teams": {str(t): names.get(t) for t in team_ids},
        "born": {str(p): b.isoformat() for p, b in conn.execute(
            "select player_id, birth_date from players where player_id = any(%s) and birth_date is not null", [ids])},
        "players": {str(p): {str(k): v for k, v in d.items()} for p, d in spells.items()},
        "positions": {str(p): d for p, d in positions.items()},   # {player: {season: [[role, minutes], ...]}}
    }
    (out_dir / "player_seasons.json").write_text(
        json.dumps(detail, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    log.info("Exported season detail for %d players", len(spells))
    return detail


def _club_positions(player_team, positions):
    """{team: {player: [[role, minutes], ...]}}: each club's current players' starting minutes by
    position over the last 12 months (the "12m" rows of the season detail), for its club file."""
    out = defaultdict(dict)
    for player, team in player_team.items():
        rows = positions.get(str(player), {}).get("12m")
        if team is not None and rows:
            out[team][str(player)] = rows
    return out


PLAYER_MATCHES = 20      # match log on a player's page: his last this-many appearances
SEASON_FIELDS = ["season", "team", "league", "apps", "starts", "minutes", "rating", "goals", "assists",
                 "shots_on", "key_passes", "passes", "pass_acc", "tackles", "interceptions", "blocks",
                 "duels_won", "duels", "dribbles_won", "fouls", "yellow", "red", "saves", "conceded"]
MATCH_FIELDS = ["fixture", "date", "league", "team", "opponent", "home", "gf", "ga", "started", "minutes",
                "role", "rating", "rank", "goals", "assists", "shots_on", "key_passes", "tackles_int",
                "duels_won", "duels", "yellow", "red", "saves", "conceded"]


def build_player_pages(ids, apps, fixtures, other_seasons):
    """{player: page payload} for docs/data/players/<id>.json, from cached rows (runs offline).

    apps: player_ratings._appearances rows; fixtures: cache.finished_fixtures rows;
    other_seasons: player_ratings._other_seasons rows. Season lines are per club and league: from
    his appearances in the per-match leagues, and the season totals (player_seasons) elsewhere,
    where starts and pass accuracy aren't known. A match's rank (going into it) is filled in later.
    """
    ids = set(ids)
    fx = {r[0]: r for r in fixtures}
    # per (season, team, league): apps, starts, minutes, rated minutes, rating x minutes, goals,
    # assists, shots_on, key_passes, passes, accurate passes, tackles, interceptions, blocks,
    # duels_won, duels, dribbles_won, fouls, yellow, red, saves, conceded
    lines = defaultdict(lambda: defaultdict(lambda: [0] * 22))
    recent = defaultdict(list)
    for r in apps:
        if r[2] not in ids or r[3] <= 0 or r[10] not in config.FINISHED_STATUSES or r[0] not in fx:
            continue
        (goals, assists, shots_on, key_passes, passes, passes_acc, tackles, interceptions, blocks, duels,
         duels_won, dribbles_won, fouls, yellow, red, saves, conceded, _, _) = (x or 0 for x in r[11:30])
        s = lines[r[2]][(r[8], r[1], r[9])]
        for i, v in enumerate((1, 1 if r[4] else 0, r[3], r[3] if r[7] else 0, (r[7] or 0) * r[3],
                               goals, assists, shots_on, key_passes, passes, passes_acc, tackles, interceptions,
                               blocks, duels_won, duels, dribbles_won, fouls, yellow, red, saves, conceded)):
            s[i] += v
        recent[r[2]].append(r)
    out = {}
    for player in ids:
        seasons = [[season, team, league, *s[:3], round(s[4] / s[3], 2) if s[3] else None, *s[5:10],
                    round(100 * s[10] / s[9]) if s[9] else None, *s[11:]]
                   for (season, team, league), s in lines.get(player, {}).items()]
        matches = []
        for r in sorted(recent.get(player, []), key=lambda r: fx[r[0]][1], reverse=True)[:PLAYER_MATCHES]:
            f = fx[r[0]]
            home = r[1] == f[4]
            st = [x or 0 for x in r[11:30]]
            matches.append([r[0], f[1].date().isoformat(), r[9], r[1], f[5] if home else f[4], 1 if home else 0,
                            f[6] if home else f[7], f[7] if home else f[6], 1 if r[4] else 0, r[3],
                            r[6] or r[5], _r(r[7], 1), None, st[0], st[1], st[2], st[3], st[6] + st[7],
                            st[10], st[9], st[13], st[14], st[15], st[16]])
        out[player] = {"seasons": seasons, "matches": matches, "injury": None}
    for (player, team, league, season, _, minutes, n, rating, goals, assists, shots_on, key_passes, passes, _,
         tackles, interceptions, blocks, duels, duels_won, dribbles_won, fouls, yellow, yellow_red, red,
         saves, conceded, _, _) in other_seasons:
        if player in out:
            out[player]["seasons"].append(
                [season, team, league, n or 0, None, minutes, _r(rating), goals or 0, assists or 0, shots_on,
                 key_passes, passes, None, tackles, interceptions, blocks, duels_won, duels, dribbles_won,
                 fouls, yellow, (red or 0) + (yellow_red or 0), saves, conceded])
    for page in out.values():
        page["seasons"].sort(key=lambda x: (-x[0], -x[5]))     # newest season first, then most minutes
    return out


MOVEMENT_FIELDS = ["horizon", "rating_change", "rank_movement", "baseline_at"]


def _player_movement(conn, ids):
    """Each player's stored rating movement (player_rating_movement: his latest daily rating
    capture against an earlier one), for his page's genuine movement. Only horizons with a stored
    baseline from the same player model version: a change across model versions is the model
    changing, not the player. Empty until the captures exist (or before the migration)."""
    (view,) = conn.execute("select to_regclass('public.player_rating_movement')").fetchone()
    if view is None or not ids:
        return {}
    out = {}
    for pid, captured, horizon, change, move, base_at in conn.execute(
            """select player_id, captured_at, horizon, rating_change, rank_movement, baseline_at
               from player_rating_movement
               where player_id = any(%s) and baseline_at is not null and not model_changed
               order by player_id, horizon""", [ids]):
        entry = out.setdefault(pid, {"captured_at": captured.isoformat(), "fields": MOVEMENT_FIELDS, "rows": []})
        entry["rows"].append([horizon, _r(change, 1), move, base_at.isoformat()])
    return out


def export_player_pages(conn, out_dir=OUT_DIR, detail=None):
    """One small file per listed player for his page: docs/data/players/<player_id>.json, with his
    stats per season and club, his last PLAYER_MATCHES appearances (with his rank going into each)
    and his injury status for his next fixture ([fixture, type, ban]: no medical reason), plus his
    own rows of the season detail (born, spells, positions) so his page needn't load
    player_seasons.json. Built from the query cache (cache.py), so the
    only database reads are the per-match ranks and injuries for those few rows."""
    from .cache import finished_fixtures
    from .player_ratings import _appearances, _other_seasons
    ids = [r[0] for r in conn.execute(f"select player_id from players p where {LISTED}", [PLAYER_SEASONS])]
    apps, fixtures, other = _appearances(conn), finished_fixtures(conn), _other_seasons(conn)
    pages = build_player_pages(ids, apps, fixtures, other)
    fids = sorted({m[0] for p in pages.values() for m in p["matches"]})
    ranks = {(fid, player): float(rank) for fid, player, rank in conn.execute(
        """select fixture_id, player_id, player_rank from fixture_player_ranks
           where fixture_id = any(%s) and player_id = any(%s)""", [fids, ids])}
    injuries = {}
    next_fixtures = availability.next_fixtures(conn)
    resolved = availability.load(conn, next_fixtures)
    for fid,kickoff,home,away,upcoming in next_fixtures:
        for team in (home,away):
            for player,state in resolved[(fid,team)].items():
                item = state['evidence'][-1]
                injuries.setdefault(player,[fid,'Suspended' if state['state']=='suspended' else item.get('type'),_ban(item.get('reason'))])
    movement = _player_movement(conn, ids)
    for pid, page in pages.items():
        for m in page["matches"]:
            m[12] = _r(ranks.get((m[0], pid)), 1)
        page["injury"] = injuries.get(pid)
        if pid in movement:
            page["movement"] = movement[pid]
    # his own rows of the season detail (export_player_seasons), so his page needs only this file
    detail = detail or {}
    for pid, page in pages.items():
        page["born"] = detail.get("born", {}).get(str(pid))
        page["spell_fields"] = SPELL_FIELDS
        page["spells"] = detail.get("players", {}).get(str(pid), {})
        page["positions"] = detail.get("positions", {}).get(str(pid), {})
    team_ids = {x for p in pages.values() for x in [s[1] for s in p["seasons"]] + [m[4] for m in p["matches"]]
                + [sp[0] for v in p["spells"].values() for sp in v]}
    names = dict(conn.execute("select team_id, name from teams where team_id = any(%s)", [list(team_ids)]))
    player_dir = out_dir / "players"
    player_dir.mkdir(parents=True, exist_ok=True)
    for old in player_dir.glob("*.json"):
        if int(old.stem) not in pages:
            old.unlink()
    for pid, page in pages.items():
        teams = ({s[1] for s in page["seasons"]} | {m[4] for m in page["matches"]}
                 | {sp[0] for v in page["spells"].values() for sp in v})
        payload = json.dumps({"id": pid, "season_fields": SEASON_FIELDS, "match_fields": MATCH_FIELDS, **page,
                              "teams": {str(t): names.get(t) for t in sorted(teams)}},
                             separators=(",", ":"), ensure_ascii=False)
        path = player_dir / f"{pid}.json"
        if not path.exists() or path.read_text(encoding="utf-8") != payload:
            path.write_text(payload, encoding="utf-8")
    log.info("Exported %d player pages", len(pages))


CLUB_ACTIVE_DAYS = 400
# xG estimated from shots where API-Football gives none (most cup and European matches): a
# least-squares fit over two years of team matches with both (35,664 of them, September 2026),
# xG = 0.12 per shot inside the box + 0.002 per shot outside it + 0.101 per shot on target
# - 0.022 per blocked shot + 0.026. R^2 0.62, typical error 0.4 goals a team a match.
XG_FROM_SHOTS = (0.12, 0.002, 0.101, -0.022, 0.026)


def _xg_from_shots(inside, outside, on_target, blocked):
    a, b, c, d, e = XG_FROM_SHOTS
    return max(0.0, a * inside + b * outside + c * on_target + d * (blocked or 0) + e)

# Finished matches at a neutral ground: in a city where neither club played its league home games
# that season (2+ of them) and not at either's league ground by name (the API's venue names and
# cities vary: Bayern's league games are at "Fußball Arena München", its cup games at "Allianz
# Arena"; BayArena's city is sometimes "Bayer Leverkusen"). Wembley, the Stade de France and La
# Cartuja host finals in their clubs' own cities, so they're neutral unless they're the home
# club's league ground (Betis at La Cartuja while their stadium is rebuilt).
NEUTRAL_SQL = """
    with hv as (
        select f.home_team_id t, f.season, lower(trim(split_part(f.venue_city, ',', 1))) c, f.venue_name n
        from fixtures f join leagues l using (league_id) where l.type = 'League'),
    hc as (select t, season, c from hv where c is not null group by 1, 2, 3 having count(*) >= 2),
    hn as (select t, season, n from hv where n is not null group by 1, 2, 3 having count(*) >= 2)
    select f.fixture_id from fixtures f
    where f.venue_city is not null and f.status_short = any(%s)
      and exists (select 1 from hc where hc.t = f.home_team_id and hc.season = f.season)
      and not exists (select 1 from hn where hn.t = f.home_team_id and hn.season = f.season and hn.n = f.venue_name)
      and (f.venue_name ~* '^(wembley|stade de france|estadio de la cartuja)'
           or (not exists (select 1 from hn where hn.t = f.away_team_id and hn.season = f.season and hn.n = f.venue_name)
               and not exists (select 1 from hc where hc.t in (f.home_team_id, f.away_team_id) and hc.season = f.season
                               and hc.c = lower(trim(split_part(f.venue_city, ',', 1))))))"""


def export_clubs(conn, out_dir=OUT_DIR, positions=None):
    """One small file per active club for its club page: docs/data/clubs/<team_id>.json.

    history: every match since 2020 as [date, rank after, opponent, home (1, 0 away, 2 neutral), goals for, against,
    competition, formation (null where the line-up isn't known), attack and defence after,
    starting XI average rank by line [GK, DEF, MID, FWD] (null outside the line-up leagues)]; plus 12-month home/away goal
    averages, the current manager and the home kit colours. starts: this season's matches with a
    line-up (games), each player's starts by position in them, each match's starters (xi) and
    competition (xi_league) and formation (xi_formation), and per player his starts, substitute appearances and minutes in
    them over the last 12 months (mins, out of mins_matches). positions: its current players'
    starting minutes by position over the last 12 months, wherever they played
    ({player: [[role, minutes], ...]}, from export_player_seasons).
    Loaded only when the page opens.
    """
    now = datetime.now(timezone.utc)
    active = {r[0] for r in conn.execute(
        """select team_id from team_rankings where last_match >= %s
           union select home_team_id from fixtures where status_short in ('NS','TBD') and kickoff > now()
           union select away_team_id from fixtures where status_short in ('NS','TBD') and kickoff > now()""",
        [now - timedelta(days=CLUB_ACTIVE_DAYS)])}
    formations = {(f, t): fm for f, t, fm in cached_rows(conn, "formations", f"""
            select {WEEK.format('f.kickoff')} as part, ff.fixture_id, ff.team_id, ff.formation
            from fixture_formations ff join fixtures f using (fixture_id) where ff.formation is not null""",
            order_by="fixture_id, team_id")}
    coaches = {t: {"id": c, "name": n, "since": s.isoformat() if s else None}
               for t, c, n, s in conn.execute("select team_id, coach_id, name, since from team_coaches")}
    colors = {t: _kit_colors(s, n) for t, s, n in conn.execute("select team_id, shirt, number from team_colors")}
    xi_lines = {(f, t): _xi_lines(rest) for f, t, *rest in cached_rows(conn, "xi_lines", f"""
            select {WEEK.format('f.kickoff')} as part, r.fixture_id, r.team_id,
                   r.actual_gk::float8, r.actual_def::float8, r.actual_mid::float8, r.actual_fwd::float8
            from fixture_team_ratings r join fixtures f using (fixture_id) where r.actual_xi_rating is not null""",
            order_by="fixture_id, team_id")}
    neutral = {f for (f,) in conn.execute(NEUTRAL_SQL, [list(config.FINISHED_STATUSES)])}
    # this season (the club's latest season with a line-up): matches with a line-up, and starts by
    # position per player, league (fixture_players.role) and cup (fixture_lineups) alike
    current = """with cur as (
            select ff.team_id, max(f.season) s from fixture_formations ff join fixtures f using (fixture_id)
            where f.status_short = any(%(fin)s) and ff.formation is not null and ff.team_id = any(%(teams)s) group by 1)"""
    args = {"fin": list(config.FINISHED_STATUSES), "teams": list(active)}
    starts = {t: {"games": n, "players": {}} for t, n in conn.execute(current + """
            select ff.team_id, count(*) from fixture_formations ff join fixtures f using (fixture_id)
            join cur on cur.team_id = ff.team_id and cur.s = f.season
            where f.status_short = any(%(fin)s) and ff.formation is not null group by 1""", args)}
    for team, player, role, n in conn.execute(current + """
            select fp.team_id, fp.player_id, fp.role, count(*) from (select fixture_id, team_id, player_id, role from fixture_players where started and role is not null
                  union all select fixture_id, team_id, player_id, role from fixture_lineups where role is not null) fp join fixtures f using (fixture_id)
            join cur on cur.team_id = fp.team_id and cur.s = f.season
            join fixture_formations ff on ff.fixture_id = fp.fixture_id and ff.team_id = fp.team_id
            where ff.formation is not null and f.status_short = any(%(fin)s)
            group by 1, 2, 3""", args):
        if team in starts:
            starts[team]["players"].setdefault(str(player), {})[role] = n
    # the same starts match by match (oldest first): [[player, role, player, role, ...], ...], so the
    # club page can see who has started in a position since an injured player last did
    xis, xi_league, xi_formation = defaultdict(dict), defaultdict(dict), defaultdict(dict)
    for team, fid, league, formation, player, role in conn.execute(current + """
            select fp.team_id, fp.fixture_id, f.league_id, ff.formation, fp.player_id, fp.role from (select fixture_id, team_id, player_id, role from fixture_players where started and role is not null
                  union all select fixture_id, team_id, player_id, role from fixture_lineups where role is not null) fp join fixtures f using (fixture_id)
            join cur on cur.team_id = fp.team_id and cur.s = f.season
            join fixture_formations ff on ff.fixture_id = fp.fixture_id and ff.team_id = fp.team_id
            where ff.formation is not null and f.status_short = any(%(fin)s)
            order by f.kickoff, fp.fixture_id, fp.player_id""", args):
        xis[team].setdefault(fid, []).extend([player, role])
        xi_league[team][fid] = league
        xi_formation[team][fid] = formation
    for team, by_fixture in xis.items():
        if team in starts:
            starts[team]["xi"] = list(by_fixture.values())
            starts[team]["xi_league"] = list(xi_league[team].values())   # each match's competition
            starts[team]["xi_formation"] = list(xi_formation[team].values())   # and formation
    # minutes over the last 12 months (league matches with player data): the club's matches, and
    # per player [starts, minutes in them, substitute appearances, minutes in those], for the
    # club page's expected minutes (how long a starter usually lasts, who comes off the bench)
    for team, matches in conn.execute(
            """select fp.team_id, count(distinct fp.fixture_id) from fixture_players fp join fixtures f using (fixture_id)
               where fp.team_id = any(%s) and f.kickoff > now() - interval '365 days' group by 1""", [list(active)]):
        if team in starts:
            starts[team]["mins_matches"] = matches
    for team, player, n_start, m_start, n_sub, m_sub in conn.execute(
            """select fp.team_id, fp.player_id, count(*) filter (where fp.started),
                      coalesce(sum(fp.minutes) filter (where fp.started), 0),
                      count(*) filter (where not fp.started), coalesce(sum(fp.minutes) filter (where not fp.started), 0)
               from fixture_players fp join fixtures f using (fixture_id)
               where fp.team_id = any(%s) and f.kickoff > now() - interval '365 days' group by 1, 2""", [list(active)]):
        if team in starts:
            starts[team].setdefault("mins", {})[str(player)] = [n_start, m_start, n_sub, m_sub]
    match_xg = {r[0]: (r[9], r[10]) for r in finished_fixtures(conn)}   # fixture -> (home xG, away xG)
    # estimates from shots for matches without xG: {(fixture, team): xG}
    shot_xg = {(f, t): _xg_from_shots(i, o, on, bl) for f, t, i, o, on, bl in cached_rows(conn, "shots_without_xg", f"""
            select {WEEK.format('f.kickoff')} as part, s.fixture_id, s.team_id, s.shots_inside_box,
                   s.shots_outside_box, s.shots_on_goal, s.blocked_shots
            from fixture_team_stats s join fixtures f using (fixture_id)
            where s.expected_goals is null and s.shots_inside_box is not null
              and s.shots_outside_box is not null and s.shots_on_goal is not null""",
            order_by="fixture_id, team_id")}

    def xg_pair(fid, team, opp, is_home):
        """(xG for, xG against, estimated?) for the club in this match."""
        h, a = match_xg.get(fid, (None, None))
        f_, a_ = (h, a) if is_home else (a, h)
        if f_ is not None and a_ is not None:
            return _r(f_, 2), _r(a_, 2), 0
        ef, ea = shot_xg.get((fid, team)), shot_xg.get((fid, opp))
        return (_r(ef, 2), _r(ea, 2), 1) if ef is not None and ea is not None else (None, None, 0)
    history = {}
    club_rows = sorted((r for r in rank_history(conn) if r[1] in active), key=lambda r: (r[1], r[2]))
    for fid, team, _, kickoff, is_home, opp, rank_before, rank_after, _, hg, ag, league, att, dfn, *_ in club_rows:
        rows = history.setdefault(team, {"start": round(rank_before), "matches": []})["matches"]
        gf, ga = (hg, ag) if is_home else (ag, hg)
        rows.append([kickoff.date().isoformat(), round(rank_after, 1), opp, 2 if fid in neutral else 1 if is_home else 0,
                     gf, ga, league,
                     formations.get((fid, team)), _r(att, 1), _r(dfn, 1), xi_lines.get((fid, team)),
                     *xg_pair(fid, team, opp, is_home)])
    stats = {t: [_r(x) for x in rest] for t, *rest in conn.execute(
        "select team_id, hg, ha, ag, aa from team_rankings where team_id = any(%s)", [list(active)])}
    club_dir = out_dir / "clubs"
    club_dir.mkdir(parents=True, exist_ok=True)
    for old in club_dir.glob("*.json"):
        if int(old.stem) not in active:
            old.unlink()
    names = dict(conn.execute("select team_id, name from teams"))
    for team in active:
        h = history.get(team, {"start": None, "matches": []})
        opponents = {m[2] for m in h["matches"]}
        payload = {"id": team, "start": h["start"],
                   "fields": ["date", "rank", "opponent", "home", "gf", "ga", "league", "formation",
                              "attack", "defence", "xi_lines", "xgf", "xga", "xg_est"],
                   "matches": h["matches"], "goal_averages": stats.get(team), "coach": coaches.get(team),
                   "colors": colors.get(team), "starts": starts.get(team),
                   "positions": (positions or {}).get(team, {}),
                   "teams": {o: names.get(o) for o in opponents}}
        (club_dir / f"{team}.json").write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    log.info("Exported %d club pages", len(active))


XG_RECENT = 5   # league games behind the tables' xG and xG conceded per 90


def export_leagues(conn, out_dir=OUT_DIR):
    """One file per competition for its league page: docs/data/leagues/<league_id>.json.

    The current season's table (every group, as API-Football sends it) and all its fixtures, the
    upcoming ones with the model's projected goals and home / draw / away chances (for the page's
    projected table), and each club's recent xG for and against (for the table). Loaded only when
    the page opens.
    """
    seasons = {lid: (season, start) for lid, season, start in conn.execute(
        """select distinct on (league_id) league_id, season, start_date from league_seasons
           where is_current order by league_id, season desc""")}
    tables = defaultdict(list)
    for (lid, season, group, team, rank, pts, gd, form, desc, pl, w, d, l, gf, ga) in conn.execute(
            """select league_id, season, group_name, team_id, rank, points, goal_diff, form, description,
                      played, win, draw, lose, goals_for, goals_against
               from standings where (league_id, season) in (select league_id, max(season) from league_seasons
                                                             where is_current group by league_id)
               order by league_id, group_name, rank"""):
        tables[lid].append([group, rank, team, pl, w, d, l, gf, ga, gd, pts, form, desc])
    fixtures = defaultdict(list)
    for fid, lid, kickoff, rnd, home, away, status, hg, ag, ph, pa_, xh, xa, p1, px, p2 in conn.execute(
            """select f.fixture_id, f.league_id, f.kickoff, f.round, f.home_team_id, f.away_team_id, f.status_short,
                      f.home_goals, f.away_goals, f.pen_home, f.pen_away,
                      p.home_xg::float8, p.away_xg::float8, p.p_home::float8, p.p_draw::float8, p.p_away::float8
               from fixtures f
               left join fixture_predictions p on p.fixture_id = f.fixture_id and f.status_short = any(%s)
               where (f.league_id, f.season) in (select league_id, max(season) from league_seasons
                                                 where is_current group by league_id)
               order by f.kickoff, f.fixture_id""", [list(UPCOMING_STATUSES)]):
        fixtures[lid].append([fid, kickoff.isoformat(), rnd, home, away, status, hg, ag, ph, pa_,
                              _r(xh), _r(xa), _r(p1, 3), _r(px, 3), _r(p2, 3)])
    # each club's xG and xG conceded per 90 over its last XG_RECENT league games with xG for both sides
    # (a match that went to extra time counts as 120 minutes)
    recent_xg = defaultdict(dict)
    for lid, team, xg, xga, n in conn.execute(
            """with games as (
                 select f.league_id, s.team_id, f.kickoff,
                        s.expected_goals * 90 / case when f.status_short in ('AET', 'PEN') then 120 else 90 end as xg,
                        o.expected_goals * 90 / case when f.status_short in ('AET', 'PEN') then 120 else 90 end as xga
                 from fixtures f
                 join fixture_team_stats s on s.fixture_id = f.fixture_id
                 join fixture_team_stats o on o.fixture_id = f.fixture_id and o.team_id <> s.team_id
                 where f.status_short = any(%s) and s.expected_goals is not null and o.expected_goals is not null
                   and (f.league_id, f.season) in (select league_id, max(season) from league_seasons
                                                   where is_current group by league_id)),
               ranked as (select *, row_number() over (partition by league_id, team_id order by kickoff desc) as n
                          from games)
               select league_id, team_id, avg(xg)::float8, avg(xga)::float8, count(*)
               from ranked where n <= %s group by 1, 2""",
            [list(config.FINISHED_STATUSES), XG_RECENT]):
        recent_xg[lid][team] = [_r(xg), _r(xga), n]
    names = dict(conn.execute("select team_id, name from teams"))
    league_dir = out_dir / "leagues"
    league_dir.mkdir(parents=True, exist_ok=True)
    for old in league_dir.glob("*.json"):
        if int(old.stem) not in seasons:
            old.unlink()
    for lid, (season, start) in seasons.items():
        teams = {r[2] for r in tables[lid]} | {t for f in fixtures[lid] for t in (f[3], f[4])}
        payload = {"id": lid, "season": season, "start": start.isoformat() if start else None,
                   "table_fields": ["group", "rank", "team", "played", "win", "draw", "lose", "gf", "ga", "gd",
                                    "points", "form", "description"],
                   "table": tables[lid],
                   "fixture_fields": ["id", "kickoff", "round", "home", "away", "status", "hg", "ag", "pen_h", "pen_a",
                                      "home_xg", "away_xg", "p_home", "p_draw", "p_away"],
                   "fixtures": fixtures[lid],
                   "recent_xg_fields": ["xg90", "xga90", "games"],
                   "recent_xg": recent_xg[lid],
                   "teams": {t: names.get(t) for t in teams}}
        (league_dir / f"{lid}.json").write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    log.info("Exported %d league pages", len(seasons))


FANTASY_RESULTS = Path(__file__).resolve().parent.parent / "experiments" / "fantasy_v1" / "results.json"


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
PUBLISHED_FANTASY_PARAMS = Path(__file__).with_name("fantasy_params_v1_6.json")   # the FPL tab shows v1.6
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
    from . import fantasy as fm
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
        from . import fantasy_snapshots
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
    """efl_predictions.json: expected Fantasy EFL points for Championship, League One and League Two
    players and clubs (efl_fantasy.py). Not critical: a failure skips it."""
    try:
        from . import efl_fantasy
        doc = efl_fantasy.payload(conn)
        if doc:
            _write_json_file(Path(out_dir) / "efl_predictions.json", doc)
    except Exception:
        conn.rollback()
        log.exception("EFL fantasy export skipped")

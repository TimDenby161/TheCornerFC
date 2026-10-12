"""The pages that show how the models have done: Stats, Model vs Market, the methodology page's
numbers, the line-up record and its reconstructed history, and the paper bets.
"""
import html
import json
import logging
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from .. import config
from ..models import national_predictions
from ..models.betting import BOOKMAKER, CAUTIOUS_RULE, MAX_ODDS, MIN_EDGE, is_cautious
from ..models.predictions import GOAL_LINES, goal_lines
from .site_files import OUT_DIR, _r, _table_exists, _write_json_file
from .site_matches import market_probabilities, site_freshness

# the export's one log, whichever module writes to it
log = logging.getLogger("thecornerfc.publish.export")


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
    # club matches and, once their table exists, national team matches
    matches = "select fixture_id, status_short, kickoff from fixtures" + (
        " union all select fixture_id, status_short, kickoff from national_fixtures"
        if _table_exists(conn, "national_fixtures") else "")
    for fid, bet, line, sel, close, open_ in conn.execute(
            f"""with o as (
                 select o.fixture_id, o.bookmaker_id, o.bet_id,
                        case when o.bet_id = 5 then split_part(o.selection, ' ', 2) else '' end as line,
                        case when o.bet_id = 5 then split_part(o.selection, ' ', 1) else o.selection end as sel,
                        o.odd::float8 as odd, o.first_odd::float8 as first_odd,
                        o.first_seen_at < f.kickoff and o.first_odd > 1 as has_open
                 from odds o join ({matches}) f using (fixture_id)
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
    rows += national_stat_rows(conn, now - timedelta(days=max(STAT_RANGES.values())))
    market = market_probabilities(conn)
    rows = [(*r, market.get(r[-1])) for r in rows]

    # every market with odds: the model's chances (goal lines from its projected goals) and
    # what happened over 90 minutes, per fixture
    since = now - timedelta(days=max(STAT_RANGES.values()))
    cons = market_consensus(conn, since)
    with_odds = {fid for fid, _ in cons}
    per_fixture = {}
    scored = conn.execute(
            """select f.fixture_id, p.p_home, p.p_draw, p.p_away, p.p_btts, p.home_xg, p.away_xg,
                      f.ft_home, f.ft_away
               from fixture_predictions p join fixtures f using (fixture_id)
               where f.fixture_id = any(%s) and f.ft_home is not null and p.home_xg is not null""",
            [list(with_odds)]).fetchall()
    # national team matches: only the score after extra time is stored, so the ones that went to
    # extra time are left out rather than marked against a 90-minute price
    if _table_exists(conn, "national_fixtures") and _table_exists(conn, national_predictions.TABLE):
        scored += conn.execute(
            f"""select f.fixture_id, p.p_home, p.p_draw, p.p_away, p.p_btts, p.home_xg, p.away_xg,
                       f.home_goals, f.away_goals
                from {national_predictions.TABLE} p join national_fixtures f using (fixture_id)
                where f.fixture_id = any(%s) and f.status_short = 'FT' and f.home_goals is not null
                  and p.p_home is not null and p.home_xg is not null""", [list(with_odds)]).fetchall()
    for fid, ph, pd, pa, pb, hx, ax, hg, ag in scored:
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


def national_stat_rows(conn, since):
    """Finished national team matches since `since` that had a projection, in export_stats' row
    shape, so the Stats tab counts them with the club matches (under their own competitions).
    source is 'live' for a projection made before kickoff, else 'backfill', as national_match
    has it. Empty until national_fixture_predictions exists."""
    if not _table_exists(conn, "national_fixtures") or not _table_exists(conn, national_predictions.TABLE):
        return []
    return conn.execute(
        f"""select f.kickoff, f.league_id, p.p_home, p.p_draw, p.p_away, p.home_xg, p.away_xg,
                   p.likely_score, f.home_goals, f.away_goals,
                   case when p.updated_at > f.kickoff then 'backfill' else 'live' end, p.rating,
                   p.rating_winner, p.rating_margin, p.rating_clean_sheets, p.rating_shape,
                   p.rating_goals, f.fixture_id
            from {national_predictions.TABLE} p join national_fixtures f using (fixture_id)
            where f.status_short = any(%s) and f.home_goals is not null and f.kickoff >= %s
              and p.p_home is not null and p.home_xg is not null""",
        [["FT", "AET", "PEN"], since]).fetchall()


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
    """.export/methodology.json: the live record for the Methodology page. Only prospective
    snapshots (captured and stored before kickoff) are scored, through evaluation.py's selection
    and metrics; reconstructed predictions never enter it. Model vs market is left out on purpose:
    that comparison is protocol P6, blinded until its registered sample is reached."""
    from ..evidence import evaluation
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


def _score_xi(predicted, actual):
    """A predicted XI {player: role} against the XI that started {player: (role, broad position)}:
    (starters named, of them in the right role, of them with both roles known, [starters, of them
    named] for GK, DEF, MID and FWD by the starting role, starters missed, players picked instead)."""
    from ..models.player_ratings import LINES, line_of
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
    """.export/lineups.json: every scored pre-match line-up for the Line-up record tab, one row
    per team, picked by the same rule as the methodology record (evaluation.load_lineups). The tab
    adds them up itself, so it can filter by competition. lines is [starters, of them predicted]
    for GK, DEF, MID and FWD, by the official XI's roles; missed are starters the model left out,
    wrong are the players it picked instead."""
    from ..evidence import evaluation
    from types import SimpleNamespace
    now = now or datetime.now(timezone.utc)
    out = {"generated_at": now.isoformat(), "fields": LINEUP_RECORD_FIELDS, "rows": [], "versions": [],
           "leagues": {}, "teams": {}, "players": {}, "excluded_no_official_xi": 0}
    if _table_exists(conn, "lineup_prediction_snapshots") and _table_exists(conn, "official_lineup_snapshots"):
        args = SimpleNamespace(source="prospective", start=datetime(2000, 1, 1, tzinfo=timezone.utc),
                               end=now, as_of=now, hours_before=0)
        # national team XIs too (national_lineups.py): the methodology record keeps to clubs
        rows, coverage = evaluation.load_lineups(conn, args, national=True)
        out["excluded_no_official_xi"] = coverage["missing_or_incomplete_official_xi"]
        fixtures = {f: (league, home, away) for f, league, home, away in conn.execute(
            "select fixture_id, league_id, home_team_id, away_team_id from fixtures where fixture_id = any(%s)",
            [list({r["fixture_id"] for r in rows})]).fetchall()} if rows else {}
        national = {"teams": {}, "leagues": {}}     # names the club tables don't have
        if rows and _table_exists(conn, "national_fixtures"):
            for f, league, tournament, home, away, h_name, a_name in conn.execute(
                    """select fixture_id, league_id, tournament, home_team_id, away_team_id, home_name, away_name
                       from national_fixtures where fixture_id = any(%s)""",
                    [list({r["fixture_id"] for r in rows} - fixtures.keys())]).fetchall():
                fixtures[f] = (league, home, away)
                national["teams"].update({str(home): html.unescape(h_name), str(away): html.unescape(a_name)})
                national["leagues"][str(league)] = {
                    "name": tournament or config.NATIONAL_TEAM_LEAGUES.get(league, f"Competition {league}"), "country": "World"}
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
        for key in national:
            out[key] = {**national[key], **out[key]}
        unnamed = [p for row in out["rows"] for p in row[12] + row[13] if str(p) not in out["players"]]
        if unnamed and _table_exists(conn, "national_fixture_players"):
            out["players"].update({str(p): html.unescape(n) for p, n in conn.execute(
                """select distinct on (player_id) player_id, player_name from (
                       select player_id, player_name from national_fixture_players where player_id = any(%(p)s)
                       union all select player_id, player_name from national_fixture_lineups where player_id = any(%(p)s)) x
                   where player_name is not null order by player_id""", {"p": unnamed}).fetchall()})
    _write_json_file(out_dir / "lineups.json", out)
    log.info("Exported the line-up record (%s team line-ups)", len(out["rows"]))
    export_lineup_history(conn, out_dir, now)


def export_lineup_history(conn, out_dir=OUT_DIR, now=None):
    """site.lineup_history: the reconstructed history for the Line-up record tab. The predicted XI
    the nightly player-ratings replay worked out for every finished match (reconstructed_lineups),
    from what it knew before kick-off, scored against the XI that started exactly as the live
    record is. Rebuilt with today's code, so it's kept apart from the live record.

    Stored in the database, not in a file (it was lineups_history.json, 6.5 MB): the tab asks
    site_lineup_history() for the totals and the rows it shows
    (db/migrations/20261005_site_lineup_history.sql). The table is rewritten whole and the
    whole-history counts the function reads are counted again from it
    (site.lineup_history_refresh, 20261005_site_lineup_history_fast.sql), in one transaction. A
    read-only run stores nothing, and neither does a database from before the migration
    (logged); any other failure stops the run. Returns the rows:
    (fixture, team, kickoff, match date, league, opponent, home, starters named, in the right
    role, with both roles known, lines, missed, wrong)."""
    rows = []
    if _table_exists(conn, "reconstructed_lineups"):
        starters = defaultdict(dict)
        for fid, team, player, role, broad in conn.execute(
                """select fp.fixture_id, fp.team_id, fp.player_id, fp.role, fp.position
                   from fixture_players fp join reconstructed_lineups r using (fixture_id, team_id)
                   where fp.started"""):
            starters[(fid, team)][player] = (role, broad)
        # cup and European matches: the XI alone is stored (fixture_lineups), with each starter's
        # role but no broad position, so a starter whose role isn't known counts in no line
        for fid, team, player, role in conn.execute(
                """select fl.fixture_id, fl.team_id, fl.player_id, fl.role
                   from fixture_lineups fl join reconstructed_lineups r using (fixture_id, team_id)
                   where not exists (select 1 from fixture_players fp
                                     where fp.fixture_id = fl.fixture_id and fp.team_id = fl.team_id)"""):
            starters[(fid, team)][player] = (role, None)
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
            rows.append((fid, team, kickoff, kickoff.date(), league, away if team == home else home, team == home,
                         correct, right, known, lines, missed, wrong))
    try:
        config.require_db_write("store the line-up history")
    except config.SafetyError as exc:
        log.info("Line-up history not stored: %s", exc)
        return rows
    (table,) = conn.execute("select to_regclass(%s)", ["site.lineup_history"]).fetchone()
    if table is None:
        log.warning("site.lineup_history isn't there yet (db/migrations/20261005_site_lineup_history.sql): "
                    "the reconstructed line-up history wasn't stored")
        return rows
    with conn.cursor() as cur:
        cur.execute("delete from site.lineup_history")
        with cur.copy("""copy site.lineup_history (fixture_id, team_id, kickoff, day, league_id, opponent_id, home,
                              correct, roles_right, roles_known, lines, missed, wrong) from stdin""") as copy:
            for row in rows:
                copy.write_row(row)
        (refresh,) = cur.execute("select to_regprocedure('site.lineup_history_refresh()')").fetchone()
        if refresh is not None:
            cur.execute("select site.lineup_history_refresh()")
        else:
            log.warning("site.lineup_history_refresh() isn't there yet (db/migrations/20261005_site_lineup_history_fast.sql)")
    conn.commit()
    log.info("Stored the reconstructed line-up history (%s team line-ups)", len(rows))
    return rows


# Paper money shown on the Bets tab: a flat stake per bet out of a starting bank
BET_BANK_GBP = 1000
BET_STAKE_GBP = 10


def export_bets(conn, out_dir=OUT_DIR):
    """Every paper bet and its result for the site's Bets tab (.export/bets.json), all of them
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
    # bets on national team matches: the sides' names are the fixture's (national teams aren't in
    # teams) and the score is the 90-minute one the bet was settled on
    national = set()
    if _table_exists(conn, "national_fixtures"):
        from ..models.betting import _national_scores
        home, away = _national_scores(conn)
        more = conn.execute(
            f"""select b.bet_id, b.strategy, b.fixture_id, b.kickoff, b.league_id, b.market, b.selection,
                       b.model_prob, b.fair_prob, b.odds_taken, bk.name, b.edge, b.closing_odds, b.clv,
                       b.result, b.profit, b.placed_at, b.settled_at, f.home_name, f.away_name,
                       {home}, {away}, b.tags, f.home_team_id, f.away_team_id
                from paper_bets b join national_fixtures f using (fixture_id)
                left join bookmakers bk on bk.bookmaker_id = b.bookmaker_id
                where b.bookmaker_id = %s""", [BOOKMAKER]).fetchall()
        national = {r[0] for r in more}
        rows = sorted(rows + [(*r[:18], html.unescape(r[18]), html.unescape(r[19]), *r[20:]) for r in more],
                      key=lambda r: (-r[3].timestamp(), r[0]))
    bets = [{
        "id": r[0], "strategy": r[1], "fixture": r[2], "kickoff": r[3].isoformat(), "league": r[4],
        "market": r[5], "selection": r[6], "model_prob": _r(r[7], 3), "fair_prob": _r(r[8], 3),
        "odds": float(r[9]), "edge": _r(r[11], 3),
        "closing_odds": float(r[12]) if r[12] is not None else None, "clv": _r(r[13], 4),
        "result": r[14], "profit": float(r[15]) if r[15] is not None else None,
        "home": r[18], "away": r[19], "home_id": r[23], "away_id": r[24], "score": f"{r[20]}-{r[21]}" if r[20] is not None else None,
        "cautious": is_cautious(r[5], r[22]),       # the tags themselves stay in the database
        **({"intl": 1} if r[0] in national else {}),
    } for r in rows]
    # Only what the Bets tab reads: it adds up its own totals from the bets (app.js, summarise).
    # No generation timestamp, so the file only changes when bets do
    _write_json_file(out_dir / "bets.json", {
        "rules": {"min_edge": MIN_EDGE, "max_odds": MAX_ODDS, "stake": 1, "stake_gbp": BET_STAKE_GBP, "bank": BET_BANK_GBP, "cautious_rule": CAUTIOUS_RULE},
        "bets": bets,
    })
    log.info("Exported %d paper bets", len(bets))

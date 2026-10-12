"""The match rows the site shows, club and national: the market's chances, how fresh the data is,
the words that explain a prediction, and the rows of site.matches.
"""
import html
import json
import logging
from datetime import datetime, timedelta, timezone

from .. import config
from ..models import national_lineups, national_predictions, predictions
from .site_files import _check_table_collapse, _r, _table_exists

# the export's one log, whichever module writes to it
log = logging.getLogger("thecornerfc.publish.export")


PAST_DAYS = 21       # recent results shown on the site
FUTURE_DAYS = 60     # upcoming fixtures shown on the site


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


def _records_sum(side):
    """SQL for record_totals() of a snapshot's home_records / away_records, so the record lists
    (most of a snapshot's size) never leave the database."""
    return f"""cross join lateral (
        select coalesce(sum((r->>0)::float8), 0), coalesce(sum((r->>1)::float8), 0), count(*)
        from jsonb_array_elements(coalesce(s.inputs->'{side}_records', '[]'::jsonb)) r) {side[0]}r"""


def explanation(inputs, league_id, home_totals, away_totals, stored, meta):
    """One match's explanation (match_explanations): predictions.explain() on the snapshot behind the
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


def match_explanations(conn, now=None):
    """{fixture id: its explanation} for every match on the site whose prediction has a snapshot:
    the parts of the prediction (predictions.explain), the key reasons its card shows, when its
    inputs were captured and the model version that made it. Each goes in the match's row of
    site.matches (store_matches): the reasons come with the match, the rest is fetched when its
    card's model detail is opened."""
    now = now or datetime.now(timezone.utc)
    out = {}
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
    log.info("Explained %d matches", len(out))
    return out


# A match as the site draws it: the order of its row in site.matches.data
SITE_MATCH_FIELDS = ["id", "kickoff", "league", "round", "home", "away", "status", "hg", "ag",
                     "pen_h", "pen_a", "p_home", "p_draw", "p_away", "home_xg", "away_xg",
                     "likely", "home_rank", "away_rank", "source", "rating", "r_winner",
                     "r_margin", "r_clean_sheets", "r_shape", "r_goals", "m_home", "m_draw",
                     "home_missing", "away_missing", "p_over25", "p_btts",
                     "home_xi", "home_recent_xi", "away_xi", "away_recent_xi", "intl"]


# What a visitor without a subscription doesn't get of a match that hasn't kicked off, once
# the paywall is on (db/migrations/20261006_paid_tier.sql; the line is the owner's of
# 2026-10-04): the depth always, and the chances themselves more than 7 days ahead.
MATCH_PAID_DEPTH = ("home_xg", "away_xg", "likely", "home_missing", "away_missing", "p_over25", "p_btts",
                    "home_xi", "home_recent_xi", "away_xi", "away_recent_xi")
MATCH_PAID_CHANCES = ("p_home", "p_draw", "p_away")


def blanked(row, fields):
    """A match's row (SITE_MATCH_FIELDS order) with these fields null."""
    hide = {SITE_MATCH_FIELDS.index(f) for f in fields}
    return [None if i in hide else v for i, v in enumerate(row)]


def store_matches(conn, matches, explained=None):
    """site.matches: every match on the site as a row, with the key reasons its card shows and
    its full model detail (match_explanations), for the database functions the site asks
    (db/migrations/20261005_site_matches.sql and 20261005_site_matches_queries.sql: site_matches,
    site_match_days, site_match_detail). matches: the rows, in SITE_MATCH_FIELDS order. The table
    is rewritten whole, in one transaction, unless it would lose most of its rows
    (_check_table_collapse).

    True once stored. False, with nothing written, on a read-only run or a database from before
    the migration (logged). Any other failure stops the run."""
    explained = explained or {}
    try:
        config.require_db_write("store the matches")
    except config.SafetyError as exc:
        log.info("Matches not stored: %s", exc)
        return False
    (table,) = conn.execute("select to_regclass(%s)", ["site.matches"]).fetchone()
    has = lambda column: conn.execute(
        "select 1 from pg_attribute where attrelid = 'site.matches'::regclass and attname = %s and not attisdropped",
        [column]).fetchone() is not None
    ready = table is not None and has("intl")
    if not ready:
        log.warning("site.matches isn't ready (db/migrations/20261005_site_matches.sql and "
                    "20261005_site_matches_queries.sql): the matches weren't stored")
        return False
    text = lambda value: None if value is None else json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    at = {name: i for i, name in enumerate(SITE_MATCH_FIELDS)}
    # the blanked copies the paid tier's migration added (20261006_paid_tier.sql), once it is applied
    paid = has("data_locked")
    with conn.cursor() as cur:
        _check_table_collapse(cur, "site.matches", len(matches))
        cur.execute("delete from site.matches")
        with cur.copy(f"""copy site.matches (fixture_id, kickoff, league_id, home_id, away_id, status, intl, data, reasons, why
                          {', data_free, data_locked' if paid else ''}) from stdin""") as copy:
            for row in matches:
                why = explained.get(str(row[at["id"]]))
                copy.write_row((row[at["id"]], row[at["kickoff"]], row[at["league"]], row[at["home"]], row[at["away"]],
                                row[at["status"]], bool(row[at["intl"]]), text(row), text(why and why["reasons"]), text(why),
                                *((text(blanked(row, MATCH_PAID_DEPTH)),
                                   text(blanked(row, MATCH_PAID_DEPTH + MATCH_PAID_CHANCES))) if paid else ())))
        cur.execute("analyze site.matches")
    conn.commit()
    log.info("Stored %d matches (%d with model detail)", len(matches), sum(str(m[0]) in explained for m in matches))
    return True


def national_matches(conn, since, until):
    """Senior national team matches (national_fixtures) kicking off between since and until, for
    the Matches tab, each with its projection (national_fixture_predictions; nulls where it has
    none, or before that table exists) and the projection's rating. Friendlies also has youth
    sides ("England U19") and clubs touring against national teams (teams.national false); both
    are left out. Empty until national_fixtures exists."""
    if not _table_exists(conn, "national_fixtures"):
        return []
    projected = _table_exists(conn, national_predictions.TABLE)
    columns = ("p_home", "p_draw", "p_away", "home_xg", "away_xg", "likely_score", "home_rank", "away_rank",
               "neutral", "exp_diff", "p_over25", "p_btts", "updated_at", "rating", "rating_winner",
               "rating_margin", "rating_clean_sheets", "rating_shape", "rating_goals")
    return conn.execute(
        rf"""select nf.fixture_id, nf.kickoff, nf.league_id, nf.tournament, nf.round, nf.home_team_id,
                   nf.away_team_id, nf.home_name, nf.away_name, nf.status_short, nf.home_goals, nf.away_goals,
                   {", ".join(f"p.{c}" if projected else f"null as {c}" for c in columns)}
            from national_fixtures nf
            {f"left join {national_predictions.TABLE} p using (fixture_id)" if projected else ""}
            where nf.kickoff between %s and %s
              and nf.home_name !~ ' U\d{{2}}$' and nf.away_name !~ ' U\d{{2}}$'
              and not exists (select 1 from teams t where t.team_id in (nf.home_team_id, nf.away_team_id)
                                                     and t.national is false)
            order by nf.kickoff, nf.fixture_id""", [since, until]).fetchall()


def national_xis(conn, now=None):
    """{(fixture, team): [[player, name, role], ...]}: the predicted XI of each national team with
    a match coming (national_lineups.replay). Not critical: empty if it can't be worked out."""
    try:
        if not national_lineups.ready(conn):
            return {}
        predicted, names = national_lineups.replay(conn, now)
    except Exception:
        log.exception("National line-ups not exported")
        return {}
    return {key: [[p, html.unescape(names.get(p) or f"Player {p}"), role] for p, role in m["xi"]]
            for key, m in predicted.items()}


def national_match(row, market=None):
    """(a national_matches row as the site draws it, in SITE_MATCH_FIELDS order; its model detail,
    or None where it has no projection). market: the bookmakers' (home, draw, away) chances with
    their margin removed, where odds were collected for it."""
    (fid, kickoff, lid, _, rnd, home, away, _, _, status, hg, ag,
     p_h, p_d, p_a, hxg, axg, likely, hr, ar, neutral, exp_diff, p_over, p_btts, projected_at, *ratings) = row
    # a projection written after kickoff was reconstructed (national_predictions.backfill_predictions)
    source = None if p_h is None else "backfill" if projected_at > kickoff else "live"
    match = [fid, kickoff.isoformat(), lid, rnd, home, away, status, hg, ag, None, None,
             _r(p_h, 3), _r(p_d, 3), _r(p_a, 3), _r(hxg), _r(axg), likely, _r(hr, 0), _r(ar, 0),
             source, *ratings,
             *[_r(x, 3) for x in (market or (None, None))[:2]], None, None, _r(p_over, 3), _r(p_btts, 3),
             None, None, None, None, 1]
    why = (national_predictions.explanation(hr, ar, neutral, exp_diff, projected_at, source == "backfill")
           if p_h is not None else None)
    return match, why


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

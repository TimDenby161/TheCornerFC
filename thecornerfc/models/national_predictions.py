"""Projected scores and win/draw/loss chances for upcoming national team matches.

The club projections (predictions.py) with the national team ranking (nations.py) in place of
the club one, and only the parts national teams have data for:

    exp_diff   = (home rank - away rank + nations.HOME_ADVANTAGE_POINTS) / 100
                 no home advantage at a neutral ground (national_fixtures.neutral; where that
                 isn't known, the finals of a tournament count as neutral)
    home_xg, away_xg = predictions.project(LEVEL_GOALS, LEVEL_GOALS, exp_diff): the same
                 proportional shift as for clubs, from what each of two level sides scores
    chances, likely score, over 2.5, both to score: predictions.outcome_probabilities and
                 goal_markets, unchanged

Left out, because there is no data behind them for national teams: Baseline Strength (the rank
is the current one), attack/defence tendencies and each side's own home edge, injury lists and
predicted line-up ratings. Bookmakers' odds are collected for them (ingest.sync_national_odds)
and shown beside the projection; nothing here reads them.

Backtest (experiments/nations_proj, see REPORT.md): LEVEL_GOALS tuned on 2000-13, checked on
2014-26 (11,071 matches). Log loss, with guessing the base rates in brackets: W/D/L 0.8703
(1.0522), over 2.5 0.6724 (0.6922), both to score 0.6752 (0.6816).

Rows go in national_fixture_predictions, never fixture_predictions: the stats, the paper bets and
the prediction ratings read every row of that, and each reads this table beside it (export.py's
national_stat_rows, betting.py's place_bets and rate_fixtures below). As for clubs, a match's row is left alone once it
has kicked off, so it keeps the last projection made before it. Projections are made by the
nightly run only: nothing they use changes on the day.

A finished match of the last year with no row (played before its projection could be made) gets one afterwards
from the ranks both sides had going into it (backfill_predictions), as predictions.py does for
clubs. Such a row was written after kickoff (updated_at > kickoff): the export calls it
'backfill' and the site says it was reconstructed.
"""
import logging
from datetime import datetime, timedelta, timezone

from .. import config
from ..evidence import match_snapshots
from . import nations, rating
from ..evidence.model_versions import ModelType, current_code_sha, register_model_version, source_digests
from .predictions import UPCOMING_STATUSES, goal_markets, outcome_probabilities, project

log = logging.getLogger(__name__)

# A year: the Stats tab's longest range (export.STAT_RANGES), so it can mark the projections
# against a past tournament (the 2026 World Cup). It was 21, the finished matches the site shows
BACKFILL_DAYS = 365
LEVEL_GOALS = 1.1            # goals each of two level sides is expected to score (1.1-1.15 scored best)
# API-Football's ids of the tournaments whose finals are played at neutral grounds (the hosts'
# own matches aside): World Cup, Euros, Africa Cup of Nations, Asian Cup, Copa America, Gold Cup
FINALS_LEAGUES = {1, 4, 6, 7, 9, 22}
TABLE = "national_fixture_predictions"


def is_neutral(neutral, league_id):
    return bool(neutral) if neutral is not None else league_id in FINALS_LEAGUES


def margin(h_rank, a_rank, neutral):
    """The expected home margin's parts, in goals: {"strength", "home_advantage"}."""
    return {"strength": (h_rank - a_rank) / 100,
            "home_advantage": 0.0 if neutral else nations.HOME_ADVANTAGE_POINTS / 100}


def predict_match(h_rank, a_rank, neutral=False):
    """(exp_diff, home_xg, away_xg, p_home, p_draw, p_away, likely_score, p_over25, p_btts)."""
    exp_diff = sum(margin(h_rank, a_rank, neutral).values())
    home_xg, away_xg = project(LEVEL_GOALS, LEVEL_GOALS, exp_diff)
    return (exp_diff, home_xg, away_xg, *outcome_probabilities(home_xg, away_xg),
            *goal_markets(home_xg, away_xg))


def current_ranks(matches):
    """{nation (the dataset's name): its rank now}."""
    return {team: history[-1] for team, history in nations.replay(matches).items()}


def ready(conn):
    return conn.execute("select to_regclass(%s)", [f"public.{TABLE}"]).fetchone()[0] is not None


def update_predictions(conn, matches=None):
    """Project every national team match that hasn't kicked off, between two nations the ranking
    knows (so not youth sides, or clubs playing a national team). matches: every result
    (nations.load), loaded if not given. Returns the number projected."""
    if not ready(conn):
        log.warning("National predictions skipped: %s doesn't exist yet "
                    "(db/migrations/20261007_national_predictions.sql)", TABLE)
        return 0
    now = datetime.now(timezone.utc)
    upcoming = conn.execute(
        """select fixture_id, kickoff, league_id, home_team_id, away_team_id, home_name, away_name, neutral
           from national_fixtures
           where status_short = any(%s) and kickoff > %s order by kickoff""",
        [list(UPCOMING_STATUSES), now]).fetchall()
    if not upcoming:
        log.info("National predictions: no upcoming matches")
        return 0
    ranks = current_ranks(matches if matches is not None else nations.load(conn))
    rows, unranked = [], set()
    for fid, kickoff, league_id, home, away, h_name, a_name, neutral in upcoming:
        h_rank, a_rank = ranks.get(nations.api_name(h_name)), ranks.get(nations.api_name(a_name))
        if h_rank is None or a_rank is None:
            unranked.update(n for n, r in ((h_name, h_rank), (a_name, a_rank)) if r is None)
            continue
        neutral = is_neutral(neutral, league_id)
        rows.append((fid, kickoff, league_id, home, away, h_rank, a_rank, neutral,
                     *predict_match(h_rank, a_rank, neutral)))
    capture_snapshots(conn, rows, now)
    _store(conn, rows)
    conn.commit()
    log.info("National predictions: %d upcoming matches (%d left out: no rank for %s)",
             len(rows), len(upcoming) - len(rows), sorted(unranked)[:20] or "-")
    return len(rows)


def register_version(conn):
    """The national projection's entry in model_versions: a match model of its own, so its
    snapshots are never read as the club model's."""
    settings = {"LEVEL_GOALS": LEVEL_GOALS, "FINALS_LEAGUES": sorted(FINALS_LEAGUES),
                "HOME_ADVANTAGE_POINTS": nations.HOME_ADVANTAGE_POINTS,
                "source_digests": source_digests(("national_predictions.py", "nations.py", "predictions.py"))}
    return register_model_version(conn, ModelType.MATCH, "national-match-prediction",
                                  code_sha=current_code_sha(), configuration=settings,
                                  notes="National team ranking projection; no injuries, line-ups or odds.")


def capture_snapshots(conn, rows, now):
    """Each upcoming projection as an append-only match_prediction_snapshots row, as the club
    projections are (match_snapshots.py): the paper bets record the snapshot they were decided
    on (paper_evidence.record_decision). Everything that scores the club model reads that table
    joined to fixtures, where a national match never is. Skipped before that table exists."""
    if not rows or conn.execute("select to_regclass('public.match_prediction_snapshots')").fetchone()[0] is None:
        return
    version = register_version(conn)
    match_snapshots.append_snapshots(conn, [
        match_snapshots.make_snapshot((*r[:7], *r[8:]), {"home_rank": r[5], "away_rank": r[6], "neutral": r[7]},
                                      version_id=version, captured_at=now, reference_at=now, source="prospective")
        for r in rows])


def _store(conn, rows, overwrite=True):
    """Insert projection rows; overwrite=False leaves a match that already has one alone."""
    config.require_db_write("store national predictions")
    update = """do update set
                 kickoff = excluded.kickoff, league_id = excluded.league_id,
                 home_team_id = excluded.home_team_id, away_team_id = excluded.away_team_id,
                 home_rank = excluded.home_rank, away_rank = excluded.away_rank,
                 neutral = excluded.neutral, exp_diff = excluded.exp_diff,
                 home_xg = excluded.home_xg, away_xg = excluded.away_xg,
                 p_home = excluded.p_home, p_draw = excluded.p_draw, p_away = excluded.p_away,
                 likely_score = excluded.likely_score, p_over25 = excluded.p_over25,
                 p_btts = excluded.p_btts, updated_at = now()"""
    with conn.cursor() as cur:
        cur.executemany(
            f"""insert into {TABLE} (fixture_id, kickoff, league_id, home_team_id, away_team_id,
                   home_rank, away_rank, neutral, exp_diff, home_xg, away_xg, p_home, p_draw, p_away,
                   likely_score, p_over25, p_btts)
               values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               on conflict (fixture_id) {update if overwrite else "do nothing"}""", rows)


def ranks_before(matches):
    """{(day, {home, away}): ({nation: its rank going into that match}, neutral)} for every rated
    match, by the dataset's names and day."""
    out = {}
    nations.replay(matches, on_match=lambda m, h, a, _: out.__setitem__(
        (m.day, frozenset((m.home, m.away))), ({m.home: h, m.away: a}, m.neutral)))
    return out


def backfill_predictions(conn, matches=None):
    """Project the finished matches of the last BACKFILL_DAYS that have no projection, from the
    ranks both sides had going into them. A match the ranking didn't rate (a side it doesn't
    know, or a tournament it leaves out) gets none. Returns the number added."""
    if not ready(conn):
        return 0
    now = datetime.now(timezone.utc)
    finished = conn.execute(
        f"""select nf.fixture_id, nf.kickoff, nf.league_id, nf.home_team_id, nf.away_team_id,
                   nf.home_name, nf.away_name
            from national_fixtures nf
            where nf.status_short in ('FT', 'AET', 'PEN') and nf.home_goals is not null
              and nf.kickoff between %s and %s
              and not exists (select 1 from {TABLE} p where p.fixture_id = nf.fixture_id)
            order by nf.kickoff""", [now - timedelta(days=BACKFILL_DAYS), now]).fetchall()
    if not finished:
        return 0
    before = ranks_before(matches if matches is not None else nations.load(conn))
    rows = []
    for fid, kickoff, league_id, home, away, h_name, a_name in finished:
        h_name, a_name = nations.api_name(h_name), nations.api_name(a_name)
        day = kickoff.date()
        # the dataset's day is the local one, so it can be a day either side of the UTC kickoff
        found = next((before[key] for off in (0, -1, 1)
                      if (key := (str(day + timedelta(days=off)), frozenset((h_name, a_name)))) in before), None)
        if found is None:
            continue
        ranks, neutral = found
        rows.append((fid, kickoff, league_id, home, away, ranks[h_name], ranks[a_name], neutral,
                     *predict_match(ranks[h_name], ranks[a_name], neutral)))
    _store(conn, rows, overwrite=False)
    conn.commit()
    log.info("National predictions: %d finished matches projected afterwards (%d had no rated match)",
             len(rows), len(finished) - len(rows))
    return len(rows)


def update_safely(conn):
    """update_predictions and rate_fixtures, but a failure is logged and rolled back instead of
    failing the run: the ranking needs the public results file (downloaded, or the cached copy),
    and the club pipeline and the export mustn't wait on it. The matches then keep the
    projections they had."""
    try:
        matches = nations.load(conn)
        update_predictions(conn, matches)
        backfill_predictions(conn, matches)
        rate_fixtures(conn)
    except Exception:
        conn.rollback()
        log.exception("National predictions failed (the run continues)")


def rate_fixtures(conn):
    """Rate finished national team matches that had a projection, as rating.rate_fixtures does for
    clubs: new ones, plus the last 14 days again in case a score was corrected."""
    if not ready(conn):
        return 0
    rows = conn.execute(
        f"""select p.fixture_id, p.home_xg, p.away_xg, f.home_goals, f.away_goals
            from {TABLE} p join national_fixtures f using (fixture_id)
            where (p.rating is null or f.kickoff >= now() - interval '14 days')
              and f.status_short in ('FT', 'AET', 'PEN')
              and f.home_goals is not null and p.home_xg is not null""").fetchall()
    updates = []
    for fid, ph, pa, hg, ag in rows:
        s = rating.factor_scores(ph, pa, hg, ag)
        updates.append((rating.overall(s), s["winner"], s["margin"], s["clean_sheets"], s["shape"],
                        s["goals"], fid))
    with conn.cursor() as cur:
        cur.executemany(
            f"""update {TABLE} set rating = %s, rating_winner = %s, rating_margin = %s,
                rating_clean_sheets = %s, rating_shape = %s, rating_goals = %s
                where fixture_id = %s""", updates)
    conn.commit()
    log.info("Rated %d finished national team matches", len(updates))
    return len(updates)


REASON_MIN_GOALS = 0.05       # as predictions.REASON_MIN_GOALS


def explanation(h_rank, a_rank, neutral, exp_diff, updated_at, backfill=False):
    """One match's model detail for the site, in the shape export.explanation gives a club match
    (what a national projection has no part for is left out or null). backfill: the projection
    was made after the match, from the ranks going into it."""
    parts = margin(h_rank, a_rank, neutral)
    if neutral:
        del parts["home_advantage"]
    reasons = sorted((kv for kv in parts.items() if abs(kv[1]) >= REASON_MIN_GOALS), key=lambda kv: -abs(kv[1]))
    return {
        "current": [round(h_rank), round(a_rank)], "baseline": [None, None], "match": [None, None],
        "margin": {k: round(v, 2) for k, v in parts.items()},
        "exp_diff": round(exp_diff, 2), "tendencies": None, "league_goals": round(2 * LEVEL_GOALS, 2),
        "missing": [None, None], "lines": None,
        "reasons": [[k, round(v, 2)] for k, v in reasons],
        "neutral": bool(neutral), "source": "reconstruction" if backfill else "prospective", "captured_at": updated_at.isoformat(),
    }

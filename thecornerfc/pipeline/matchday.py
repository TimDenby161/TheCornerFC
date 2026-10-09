"""Match-day run (GitHub Actions every 30 minutes).

For matches kicking off in the next WINDOW_HOURS: refresh odds (so the last price before
kickoff is kept as the closing price) and injury lists, re-project, place 'late' paper bets,
refresh results of matches that kicked off recently, and settle finished bets. Official XIs
published shortly before kickoff are recorded as evidence only; projections do not use them.
National team matches (national_fixtures) get their results refreshed the same way; their
projections are the nightly run's (national_predictions.py: nothing they use changes on the day).
"""
import logging
from datetime import datetime, timedelta, timezone

from ..models import betting, predictions
from .. import config
from ..fantasy_games import fantasy_snapshots
from .db import upsert
from .ingest import _national_rows, _store_fixtures, sync_injuries_fixtures, sync_odds_fixtures
from ..evidence.lineup_snapshots import capture_official

log = logging.getLogger(__name__)

WINDOW_HOURS = 3
MAX_ODDS_CALLS = 250
LINEUP_WINDOW_MINUTES = 70   # XIs are published about an hour before kickoff; runs are 30 minutes apart
MAX_LINEUP_CALLS = 10        # 20 fixtures per call


def run_matchday(api, conn):
    now = datetime.now(timezone.utc)

    # Results for matches that kicked off in the last few hours
    recent = [r[0] for r in conn.execute(
        """select fixture_id from fixtures
           where kickoff between %s and %s and status_short not in ('FT', 'AET', 'PEN', 'CANC')""",
        [now - timedelta(hours=5), now])]
    for i in range(0, len(recent), 20):
        _store_fixtures(conn, api.get("fixtures", ids="-".join(map(str, recent[i:i + 20]))))
        conn.commit()
    refresh_national_results(api, conn, now)

    # Leagues where bookmaker odds are actually available (seen in the last 30 days)
    odds_leagues = [r[0] for r in conn.execute(
        """select distinct f.league_id from odds o join fixtures f using (fixture_id)
           where f.kickoff > %s""", [now - timedelta(days=30)])]
    upcoming = conn.execute(
        """select fixture_id, league_id from fixtures
           where status_short in ('NS', 'TBD') and kickoff > %s and kickoff <= %s
           order by kickoff""", [now, now + timedelta(hours=WINDOW_HOURS)]).fetchall()
    national = national_with_odds(conn, now)
    with_odds = ([f for f, l in upcoming if l in odds_leagues] + national)[:MAX_ODDS_CALLS]
    injury_fixtures = [f for f, l in upcoming if l in config.INJURY_MODEL_LEAGUES]
    log.info("Match day: %d upcoming in %dh (%d with odds, %d with injury lists), %d recent results",
             len(upcoming), WINDOW_HOURS, len(with_odds), len(injury_fixtures), len(recent))

    capture_prekickoff_lineups(api, conn, now)
    if with_odds:
        sync_odds_fixtures(api, conn, with_odds)
    if injury_fixtures:
        sync_injuries_fixtures(api, conn, injury_fixtures)
    if upcoming:
        predictions.update_predictions(conn, [f for f, _ in upcoming])
        fantasy_snapshots.capture_safely(conn, [f for f, _ in upcoming])   # evidence only
    if upcoming or national:      # a national match keeps the nightly run's projection
        betting.place_late(conn)
    betting.settle_bets(conn)


def capture_prekickoff_lineups(api, conn, now):
    """Official XIs for player-data fixtures kicking off within LINEUP_WINDOW_MINUTES that don't yet
    have both teams' XI recorded before kickoff (experiments/prospective P3). Evidence only."""
    due = [f for (f,) in conn.execute(
        """select f.fixture_id from fixtures f
           where f.status_short in ('NS', 'TBD') and f.kickoff > %s and f.kickoff <= %s
             and f.league_id = any(%s)
             and (select count(distinct o.team_id) from official_lineup_snapshots o
                  where o.fixture_id = f.fixture_id and o.captured_at < f.kickoff) < 2
           order by f.kickoff""",
        [now, now + timedelta(minutes=LINEUP_WINDOW_MINUTES), config.MATCH_PLAYER_LEAGUES])]
    due = due[:20 * MAX_LINEUP_CALLS]
    for i in range(0, len(due), 20):
        for f in api.get("fixtures", ids="-".join(map(str, due[i:i + 20]))):
            capture_official(conn, f)
        conn.commit()
    if due:
        log.info("Pre-kickoff line-ups checked for %d fixtures", len(due))


def national_with_odds(conn, now):
    """Projected national team matches kicking off within WINDOW_HOURS that the nightly run found
    odds for (ingest.sync_national_odds), so their last price before kickoff is refreshed like a
    club's. One call each, so not the youth and unranked sides' matches, which nothing compares."""
    if not conn.execute("select to_regclass('public.national_fixture_predictions')").fetchone()[0]:
        return []
    return [r[0] for r in conn.execute(
        """select nf.fixture_id from national_fixtures nf
           where nf.status_short in ('NS', 'TBD') and nf.kickoff > %s and nf.kickoff <= %s
             and exists (select 1 from national_fixture_predictions p where p.fixture_id = nf.fixture_id)
             and exists (select 1 from odds o where o.fixture_id = nf.fixture_id)
           order by nf.kickoff""", [now, now + timedelta(hours=WINDOW_HOURS)])]


def refresh_national_results(api, conn, now):
    """Scores and statuses of national team matches that kicked off in the last few hours, as
    run_matchday does for club matches (20 per call). Nothing before the national_fixtures
    migration. Returns the number of matches asked for."""
    if not conn.execute("select to_regclass('public.national_fixtures')").fetchone()[0]:
        return 0
    recent = [r[0] for r in conn.execute(
        """select fixture_id from national_fixtures
           where kickoff between %s and %s and status_short not in ('FT', 'AET', 'PEN', 'CANC')""",
        [now - timedelta(hours=5), now])]
    for i in range(0, len(recent), 20):
        items = api.get("fixtures", ids="-".join(map(str, recent[i:i + 20])))
        upsert(conn, "national_fixtures", _national_rows(conn, items), ["fixture_id"])
        conn.commit()
    if recent:
        log.info("Match day: %d recent national team results", len(recent))
    return len(recent)

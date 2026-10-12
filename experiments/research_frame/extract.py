"""The research inputs: one read-only read of production, frozen in inputs.json.gz (gitignored).

Every experiment that says it uses the research frame reads this file and nothing else, so they
all see the same matches and the database is read once. Nothing is written to the database.

    python scripts/environment.py production            # read-only
    python experiments/research_frame/extract.py
    python scripts/environment.py staging

What is read, all for fixtures kicked off before CUT:
    fixtures     every finished fixture with a score, its regulation score, and both sides' match
                 statistics (xG, shots, possession, cards) where they exist
    predictions  the stored projection of each (fixture_predictions), which is the baseline
    leagues      name, country, type, starting rank
    formations   the formation and the manager on each line-up (for manager changes)
    odds         the stored 1X2 prices, one row per bookmaker and selection: first and last price
                 seen, with their times. Kickoffs before CUT only, which is the window the
                 12 October audit already read, so protocol P6 loses nothing by it.
    coverage     counts by competition and season of what else exists (injury lists, line-ups,
                 player rows), for the data assessment
"""
import gzip
import json
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

OUT = Path(__file__).parent / "inputs.json.gz"
CUT = "2026-10-12"

QUERIES = {
    "fixtures": """
        select f.fixture_id, f.kickoff, f.league_id, f.season, f.round, f.home_team_id, f.away_team_id,
               f.status_short, f.home_goals, f.away_goals, f.ft_home, f.ft_away, f.venue_id,
               hx.expected_goals::float8, ax.expected_goals::float8,
               hx.total_shots, ax.total_shots, hx.shots_on_goal, ax.shots_on_goal,
               hx.shots_inside_box, ax.shots_inside_box, hx.possession_pct::float8,
               hx.red_cards, ax.red_cards, hx.corners, ax.corners
        from fixtures f
        left join fixture_team_stats hx on hx.fixture_id = f.fixture_id and hx.is_home
        left join fixture_team_stats ax on ax.fixture_id = f.fixture_id and not ax.is_home
        where f.status_short in ('FT', 'AET', 'PEN') and f.home_goals is not null
          and f.away_goals is not null and f.kickoff < %(cut)s
        order by f.kickoff, f.fixture_id""",
    "predictions": """
        select p.fixture_id, p.home_rank, p.away_rank, p.exp_diff, p.home_xg, p.away_xg, p.p_home,
               p.p_draw, p.p_away, p.p_over25, p.p_btts, p.source, p.home_missing, p.away_missing
        from fixture_predictions p join fixtures f using (fixture_id)
        where f.status_short in ('FT', 'AET', 'PEN') and f.kickoff < %(cut)s""",
    "leagues": "select league_id, name, country, type, starting_rank::float8 from leagues",
    "formations": """
        select m.fixture_id, m.team_id, m.formation, m.coach_id
        from fixture_formations m join fixtures f using (fixture_id) where f.kickoff < %(cut)s""",
    "odds": """
        select o.fixture_id, o.bookmaker_id, o.selection, o.odd::float8, o.first_odd::float8,
               o.first_seen_at, o.updated_at, o.api_updated_at
        from odds o join fixtures f using (fixture_id)
        where o.bet_id = 1 and f.status_short = 'FT' and f.kickoff < %(cut)s""",
    "bookmakers": "select bookmaker_id, name from bookmakers",
    "coverage_injuries": """
        select f.league_id, f.season, count(distinct i.fixture_id), count(*),
               min(i.updated_at), max(i.updated_at)
        from injuries i join fixtures f using (fixture_id) group by 1, 2""",
    "coverage_lineups": """
        select f.league_id, f.season, count(distinct r.fixture_id),
               count(distinct r.fixture_id) filter (where r.actual_xi_rating is not null),
               count(distinct r.fixture_id) filter (where r.predicted_xi_rating is not null)
        from fixture_team_ratings r join fixtures f using (fixture_id) group by 1, 2""",
    "table_sizes": """
        select relname, n_live_tup from pg_stat_user_tables order by 2 desc""",
    "stats_timing": """
        select f.season, count(*), count(f.stats_fetched_at),
               percentile_cont(0.5) within group (order by extract(epoch from f.stats_fetched_at - f.kickoff) / 3600)
        from fixtures f where f.status_short in ('FT', 'AET', 'PEN') and f.kickoff < %(cut)s group by 1""",
}


def plain(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def main():
    from thecornerfc.pipeline import db
    doc = {"cut": CUT}
    with db.connect() as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        conn.execute("set local statement_timeout = '120s'")
        doc["database_role"] = conn.execute("select current_user").fetchone()[0]
        doc["read_only"] = conn.execute("select current_setting('transaction_read_only')").fetchone()[0]
        doc["database"] = conn.execute("select current_database()").fetchone()[0]
        for name, sql in QUERIES.items():
            cur = conn.execute(sql, {"cut": CUT})
            doc[name] = {"columns": [d.name for d in cur.description],
                         "rows": [[plain(v) for v in row] for row in cur.fetchall()]}
            print(name, len(doc[name]["rows"]), flush=True)
    doc["extracted_at"] = datetime.now(timezone.utc).isoformat()
    with gzip.open(OUT, "wt", encoding="utf-8") as fh:
        json.dump(doc, fh)
    print("wrote", OUT, OUT.stat().st_size, "bytes; role", doc["database_role"], "read only", doc["read_only"])


if __name__ == "__main__":
    main()

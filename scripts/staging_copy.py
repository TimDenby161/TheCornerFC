"""Fill staging with a few leagues' football data, copied once from production.

    python scripts/staging_copy.py            # staging's tables must be empty
    python scripts/staging_copy.py --replace  # empties the copied tables first

It reads production through the read-only role and writes staging, and nothing else: only the
tables in COPIED, only the rows of the competitions in LEAGUES. Never copied: accounts and
subscriptions, anything from FPL or Fantasy EFL, the append-only evidence (snapshots, model
versions, odds observations) and what the models and the export build (staging builds its own:
run rank, player-ratings, predict and export afterwards). guide/environments.md.

Both addresses come from the profiles scripts/environment.py uses. Before anything is copied:
production's role is shown to be unable to write, staging's address must be staging's project,
and the staging database must say it is staging. It asks for `staging` to be typed, so it runs
only at a terminal. It is gentle on production: one connection, one table at a time.
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "db"))
sys.path.insert(0, str(ROOT / "scripts"))

# England's four divisions and their cups (config.LEAGUES)
LEAGUES = (39, 40, 41, 42, 45, 48, 46, 528)

IN_LEAGUES = "league_id in ({leagues})"
FIXTURES = "fixture_id in (select fixture_id from fixtures where league_id in ({leagues}))"
TEAMS = ("team_id in (select home_team_id from fixtures where league_id in ({leagues}) "
         "union select away_team_id from fixtures where league_id in ({leagues}) "
         "union select team_id from team_seasons where league_id in ({leagues}) "
         "union select team_id from standings where league_id in ({leagues}))")
PLAYERS = ("player_id in (select player_id from player_seasons where league_id in ({leagues}) "
           "union select player_id from fixture_players where " + FIXTURES + " "
           "union select player_id from fixture_lineups where " + FIXTURES + " "
           "union select player_id from injuries where " + FIXTURES + " "
           "union select player_id from team_squads where " + TEAMS + ")")

# table: which of its rows. In an order that satisfies the foreign keys.
COPIED = {
    "leagues": IN_LEAGUES,
    "league_seasons": IN_LEAGUES,
    "venues": "venue_id in (select venue_id from teams where " + TEAMS + ")",
    "teams": TEAMS,
    "team_seasons": IN_LEAGUES,
    "fixtures": IN_LEAGUES,
    "fixture_team_stats": FIXTURES,
    "standings": IN_LEAGUES,
    "bookmakers": "true",
    "bet_types": "true",
    "odds": FIXTURES,
    "players": PLAYERS,
    "player_seasons": IN_LEAGUES,
    "injuries": FIXTURES,
    "fixture_players": FIXTURES,
    "fixture_formations": FIXTURES,
    "fixture_lineups": FIXTURES,
    "team_colors": TEAMS,
    "team_coaches": TEAMS,
    "team_squads": TEAMS,
    "player_career_teams": PLAYERS,
    "player_overrides": PLAYERS,
    "player_career_checks": PLAYERS,
    # the record that can't be rebuilt: projections made before kick-off, and the paper bets
    "fixture_predictions": FIXTURES,
    "paper_bets": FIXTURES,
    # internationals are few: all of them
    "national_fixtures": "true",
    "national_fixture_formations": "true",
    "national_fixture_lineups": "true",
    "national_fixture_players": "true",
}
# Never, whatever is added above: accounts, payment, fantasy game data (owner-only), evidence
NEVER = ("auth.", "subscriptions", "fpl_", "fantasy_", "snapshot", "model_versions", "observations",
         "paper_decisions", "paper_outcomes", "settings", "site.")


def query(table, leagues=LEAGUES):
    where = COPIED[table].format(leagues=", ".join(str(int(n)) for n in leagues))
    return f"select {{columns}} from public.{table} where {where}"


def columns(conn, table):
    return [r[0] for r in conn.execute(
        "select column_name from information_schema.columns where table_schema = 'public' and table_name = %s "
        "order by ordinal_position", (table,))]


def addresses():
    """Production's read-only address and staging's, from the profiles, each checked."""
    from dotenv import dotenv_values
    import environment
    from check_local_access import ask
    from thecornerfc import config
    folder = environment.profile_dir()
    source = environment.read_profile("production", folder)["READ_ONLY_DATABASE_URL"]
    target = environment.read_profile("staging", folder)["DATABASE_URL"]
    environment.prove("production", {"READ_ONLY_DATABASE_URL": source}, ask)     # raises unless it cannot write
    if config.database_project(target) != config.PROJECTS["staging"] or not config.PROJECTS["staging"] \
            or config.database_project(source) != config.PROJECTS["production"]:
        raise environment.Refused("The addresses are not production's and staging's.")
    return source, target


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if [a for a in argv if a != "--replace"]:
        print(__doc__)
        return 2
    import psycopg
    import environment
    try:
        source, target = addresses()
    except environment.Refused as why:
        print(f"Nothing copied. {why}")
        return 1
    with psycopg.connect(source, prepare_threshold=None, connect_timeout=15,
                         options="-c default_transaction_read_only=on") as src, \
         psycopg.connect(target, prepare_threshold=None, connect_timeout=15) as dst:
        src.read_only = True
        said = dst.execute("select site.environment()").fetchone()[0]
        if said != "staging":
            print(f"Nothing copied. The target database says it is {said}, not staging.")
            return 1
        full = [t for t in COPIED if dst.execute(f"select exists (select 1 from public.{t})").fetchone()[0]]
        if full and "--replace" not in argv:
            print("Nothing copied. These staging tables already hold rows: " + ", ".join(full)
                  + ".\nRun it again with --replace to empty them first.")
            return 1
        print(f"From PRODUCTION (read-only) to STAGING: {len(COPIED)} tables, competitions {', '.join(map(str, LEAGUES))}.")
        if not sys.stdin.isatty() or input("Type staging to go on: ").strip() != "staging":
            print("Nothing copied.")
            return 1
        if full:
            dst.execute("truncate " + ", ".join(f"public.{t}" for t in COPIED))
        total = 0
        for table in COPIED:
            shared = [c for c in columns(dst, table) if c in set(columns(src, table))]
            names = ", ".join(f'"{c}"' for c in shared)
            started = time.monotonic()
            with src.cursor() as out, dst.cursor() as into:
                with out.copy(f"copy ({query(table).format(columns=names)}) to stdout") as reading, \
                     into.copy(f"copy public.{table} ({names}) from stdin") as writing:
                    for block in reading:
                        writing.write(block)
                rows = into.rowcount
            total += rows
            print(f"  {rows:>9,} rows  {table}  ({time.monotonic() - started:.0f}s)")
            time.sleep(1)                       # a breath between tables, for production's sake
        # the copied bets keep their numbers, so the next one staging places must follow them
        dst.execute("select setval(pg_get_serial_sequence('public.paper_bets', 'bet_id'), "
                    "greatest((select max(bet_id) from public.paper_bets), 1))")
        dst.commit()
        dst.autocommit = True
        dst.execute("analyze")
        size = dst.execute("select pg_size_pretty(pg_database_size(current_database()))").fetchone()[0]
    print(f"Copied {total:,} rows. Staging is now {size} (the free limit is 500 MB).")
    print("Next: python -m thecornerfc rank, player-ratings, predict, export (in staging mode).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

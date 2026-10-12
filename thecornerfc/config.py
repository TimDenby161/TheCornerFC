import os

from dotenv import load_dotenv

load_dotenv()


def _bool_env(name, default):
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class SafetyError(RuntimeError):
    """Raised when a local safety guard blocks a dangerous action."""


MODE = os.getenv("THECORNERFC_MODE", "local").strip().lower()
GITHUB_ACTIONS = _bool_env("GITHUB_ACTIONS", False)
READ_ONLY = _bool_env("THECORNERFC_READ_ONLY", MODE != "production")
NO_API = _bool_env("THECORNERFC_NO_API", MODE != "production")
LOCAL_OVERRIDE = os.getenv("THECORNERFC_LOCAL_OVERRIDE", "")
LOCAL_OVERRIDE_TOKEN = "I_UNDERSTAND_THIS_CAN_WRITE_PRODUCTION_DATA_AND_USE_API_QUOTA"

API_BASE_URL = "https://v3.football.api-sports.io"
API_KEY = os.getenv("API_FOOTBALL_KEY")
READ_ONLY_DATABASE_URL = os.getenv("READ_ONLY_DATABASE_URL")
API_DAILY_RESERVE = int(os.getenv("API_DAILY_RESERVE", "200"))


# Which copy of the system this run belongs to: "production", "staging", or not said. Each has its
# own Supabase project, named here by its public id (the site's address for each is in web/). A
# run that names none writes nothing. The name alone is never trusted: before a session that may
# write is used, the address must belong to that project and the database must say the same of
# itself (require_write_address, verify_database; guide/environments.md).
ENV = os.getenv("THECORNERFC_ENV", "").strip().lower()
if ENV not in ("", "production", "staging"):
    raise ValueError("THECORNERFC_ENV must be production or staging")
PROJECTS = {
    "production": "bookkurhdabdeccckjbn",
    "staging": "sjvzmlbdowebylnzvisa",
}


def _local_override_allowed():
    """The override token, which now lifts only the API block, and only for staging: nothing on
    this machine writes to production or spends its quota, whatever it carries."""
    return LOCAL_OVERRIDE == LOCAL_OVERRIDE_TOKEN and ENV == "staging"


def writes_allowed():
    """Whether this run may write to the database at all: read-only mode is off, and it is either
    a GitHub Actions job or a local run against staging. A local run never writes to production.
    The same test as require_db_write, for choosing the connection; connect() then checks that
    the database is the one this run names."""
    return not READ_ONLY and (GITHUB_ACTIONS or ENV == "staging")


# The write address is only ever picked up where a write is meant. Turning THECORNERFC_READ_ONLY
# off on its own (no Actions run, not staging) still connects with the read-only address, and
# connect() still opens a read-only session (guide/local-safety.md).
DATABASE_URL = os.getenv("DATABASE_URL") if writes_allowed() else READ_ONLY_DATABASE_URL


def require_db_write(action):
    if READ_ONLY:
        raise SafetyError(
            f"{action} requires database writes, but THECORNERFC_READ_ONLY is enabled. "
            "Locally only staging can be written to: python scripts/environment.py staging."
        )
    if not writes_allowed():
        raise SafetyError(
            f"{action} writes to the database, and a local run writes only to staging "
            "(python scripts/environment.py staging). Production is written by the GitHub jobs."
        )


def database_project(url):
    """The Supabase project a database address belongs to, or None when it names none or more
    than one. The shared pooler has one host for every project and carries the project in the
    user name (role.project); the direct address carries it in the host (db.project.supabase.co);
    either may also carry it as options=reference=project."""
    import re
    from psycopg.conninfo import conninfo_to_dict
    try:
        params = conninfo_to_dict((url or "").strip())
    except Exception:
        return None
    found = set()
    user, host, options = (str(params.get(k) or "") for k in ("user", "host", "options"))
    if "." in user:
        found.add(user.rsplit(".", 1)[1])
    at_host = re.fullmatch(r"db\.([a-z0-9]+)\.supabase\.(?:co|com)", host.lower())
    if at_host:
        found.add(at_host.group(1))
    in_options = re.search(r"reference[=:]([a-z0-9]+)", options)
    if in_options:
        found.add(in_options.group(1))
    return found.pop() if len(found) == 1 else None


def require_write_address(url):
    """Before a session that may write is opened: the address must belong to the project this
    run's environment names. An address whose project can't be read is not known to be the right
    one, so it is refused too. The address is never shown."""
    expected = PROJECTS.get(ENV)
    if not ENV:
        raise SafetyError("This run may write but names no environment (THECORNERFC_ENV).")
    if not expected:
        raise SafetyError(f"No Supabase project is recorded for {ENV} yet (config.PROJECTS).")
    project = database_project(url)
    if project != expected:
        raise SafetyError(
            f"This run is for {ENV}, but its database address "
            + ("names no project that can be read." if project is None else "belongs to another project.")
        )


def verify_database(conn):
    """Before a session that may write is used: the database must say it is this run's
    environment (site.environment(), a row that is set once in each database and can't then be
    changed: db/migrations/20261012_database_environment.sql). One of three checks, with the
    address and the credentials themselves; not on its own a boundary."""
    try:
        said = conn.execute("select site.environment()").fetchone()[0]
    except Exception:
        said = None
    finally:
        conn.rollback()             # leave the session as connect() found it: no open transaction
    if said != ENV or not ENV:
        raise SafetyError(
            f"This run is for {ENV or 'no named environment'}, but the database "
            + (f"says it is {said}." if isinstance(said, str) else "does not say which it is.")
        )


def confirm_destructive(action):
    """A local command that replaces or deletes what staging holds asks for the environment's name
    to be typed at the terminal first. There is no flag to skip it, so it can't be run unattended.
    The GitHub jobs' commands are fixed in their workflow files and are not asked."""
    import sys
    if GITHUB_ACTIONS:
        return
    if not sys.stdin.isatty():
        raise SafetyError(f"{action} needs its confirmation typed at a terminal.")
    print(f"\n{action} will replace or delete data in the {ENV.upper()} database.")
    if input(f"Type {ENV} to go on: ").strip() != ENV:
        raise SafetyError(f"{action} was not confirmed.")


def require_api_access(action):
    if NO_API:
        raise SafetyError(
            f"{action} requires API-Football access, but THECORNERFC_NO_API is enabled. "
            "This prevents accidental quota use during local development."
        )
    if not GITHUB_ACTIONS and not _local_override_allowed():
        raise SafetyError(
            f"{action} can consume API-Football quota. Local API access is for staging only and requires "
            f"THECORNERFC_LOCAL_OVERRIDE={LOCAL_OVERRIDE_TOKEN!r}."
        )

# Fantasy Premier League endpoints are undocumented browser endpoints with no published licence,
# and the Premier League's terms restrict building databases from its sites. Off until the owner
# decides the use is acceptable (guide/fpl-evidence.md).
FPL_CAPTURE_ENABLED = _bool_env("FPL_CAPTURE_ENABLED", False)
# The owner's FPL entry, read by `fpl team` for the My FPL team page (owner's decision, 2026-09-30)
FPL_TEAM_ENTRY = int(os.getenv("FPL_TEAM_ENTRY", "3996593"))


def require_fpl_access(action):
    if not FPL_CAPTURE_ENABLED:
        raise SafetyError(
            f"{action} reads Fantasy Premier League endpoints, which have no published licence. "
            "Set FPL_CAPTURE_ENABLED=true only after deciding that use is acceptable "
            "(guide/fpl-evidence.md)."
        )
    if NO_API:
        raise SafetyError(f"{action} is an external data request, but THECORNERFC_NO_API is enabled.")
    if not GITHUB_ACTIONS and not _local_override_allowed():
        raise SafetyError(
            f"{action} writes evidence. Local runs are for staging only and require "
            f"THECORNERFC_LOCAL_OVERRIDE={LOCAL_OVERRIDE_TOKEN!r}."
        )


# API-Football league ids. Play-offs are included in each league's fixtures.
LEAGUES = {
    # England
    39: "Premier League",
    40: "Championship",
    41: "League One",
    42: "League Two",
    43: "National League",
    50: "National League North",
    51: "National League South",
    # UK cups
    45: "FA Cup",
    48: "EFL Cup",
    46: "EFL Trophy",
    47: "FA Trophy",
    528: "Community Shield",
    181: "Scottish Cup",
    185: "Scottish League Cup",
    # European / world club competitions
    2: "UEFA Champions League",
    3: "UEFA Europa League",
    848: "UEFA Conference League",
    531: "UEFA Super Cup",
    15: "FIFA Club World Cup",
    # Big 5 (rest)
    140: "La Liga",
    135: "Serie A",
    136: "Serie B",
    78: "Bundesliga",
    79: "2. Bundesliga",
    61: "Ligue 1",
    62: "Ligue 2",
    # Other European leagues
    141: "Spain Segunda Division",
    179: "Scotland Premiership",
    180: "Scotland Championship",
    88: "Netherlands Eredivisie",
    94: "Portugal Primeira Liga",
    144: "Belgium Pro League",
    203: "Turkey Super Lig",
    197: "Greece Super League 1",
    207: "Switzerland Super League",
    218: "Austria Bundesliga",
    119: "Denmark Superliga",
    103: "Norway Eliteserien",
    113: "Sweden Allsvenskan",
    106: "Poland Ekstraklasa",
    235: "Russia Premier League",
    333: "Ukraine Premier League",
    286: "Serbia Super Liga",
    345: "Czech Liga",
    419: "Azerbaijan Premyer Liqa",
    332: "Slovakia Super Liga",
    271: "Hungary NB I",
    318: "Cyprus 1. Division",
    383: "Israel Ligat Ha'al",
    172: "Bulgaria First League",
    373: "Slovenia 1. SNL",
    342: "Armenia Premier League",
    315: "Bosnia Premijer Liga",
    310: "Albania Superliga",
    362: "Lithuania A Lyga",
    327: "Georgia Erovnuli Liga",
    312: "Andorra 1a Divisio",
    389: "Kazakhstan Premier League",
    244: "Finland Veikkausliiga",
    758: "Gibraltar Premier Division",
    365: "Latvia Virsliga",
    283: "Romania Liga I",
    210: "Croatia HNL",
    # Rest of world
    71: "Brazil Serie A",
    128: "Argentina Liga Profesional",
    262: "Mexico Liga MX",
    307: "Saudi Pro League",
    253: "MLS",
    233: "Egypt Premier League",
    188: "Australia A-League",
}

# API-Football's national team competitions, for the Nations tab (nations.py). They go in their
# own table, national_fixtures, never in fixtures: the club ranking, predictions and site export
# all read every row of fixtures. Ids are API-Football's; `sync national` logs each one's name, so
# check them on a first run. The public results dataset covers history, so these are only needed
# from the current season on.
NATIONAL_TEAM_LEAGUES = {
    1: "World Cup",
    4: "Euro Championship",
    5: "UEFA Nations League",
    6: "Africa Cup of Nations",
    7: "Asian Cup",
    9: "Copa America",
    10: "Friendlies",
    22: "CONCACAF Gold Cup",
    29: "World Cup - Qualification Africa",
    30: "World Cup - Qualification Asia",
    31: "World Cup - Qualification CONCACAF",
    32: "World Cup - Qualification Europe",
    33: "World Cup - Qualification Oceania",
    34: "World Cup - Qualification South America",
    35: "Asian Cup - Qualification",
    36: "Africa Cup of Nations - Qualification",
    536: "CONCACAF Nations League",
    960: "Euro Championship - Qualification",
}
# Off until switched on: the nightly run then refreshes national_fixtures for the current seasons
# (about 20-40 calls a night)
NATIONAL_SYNC = _bool_env("THECORNERFC_NATIONAL_SYNC", False)

# API-Football seasons are keyed by the year the season starts (2025 = 2025/26).
DEFAULT_SEASONS = list(range(2020, 2027))

# Leagues with player data and injury lists
PLAYER_LEAGUES = [
    39, 40, 41, 42, 43,            # England top five
    140, 135, 78, 61,              # La Liga, Serie A, Bundesliga, Ligue 1
    203, 307, 253, 94, 88, 144,    # Turkey, Saudi Arabia, MLS, Portugal, Netherlands, Belgium
    197, 333, 345, 218, 103, 419,  # Greece, Ukraine, Czechia, Austria, Norway, Azerbaijan
    332,                           # Slovakia
]

# Leagues with enough injury history (2021+) for the injury adjustment; per-match player
# minutes are fetched for these
INJURY_MODEL_LEAGUES = [39, 40, 140, 135, 78, 61, 203, 88, 253, 103]

# Leagues with per-match player data (fixture_players: minutes, stats, line-up roles), used for
# player ranks and the players list: the injury-model leagues plus League One, League Two and
# the Saudi Pro League
MATCH_PLAYER_LEAGUES = INJURY_MODEL_LEAGUES + [41, 42, 307]

# Player ranks compare every player with the players in these leagues (stat norms, percentiles,
# the "regulars" sample), so adding a league doesn't move everyone else's rank
RATING_REFERENCE_LEAGUES = INJURY_MODEL_LEAGUES

# Cup and European matches of those leagues' clubs have their starting XIs stored from this day
# (ingest.sync_cup_lineups) and a predicted XI worked out (player_ratings.py)
CUP_LINEUPS_FROM = "2020-07-01"

FINISHED_STATUSES = ("FT", "AET", "PEN")

# Odds markets to keep (API-Football bet ids). Everything else is discarded.
ODDS_BET_IDS = {
    1: "Match Winner",
    5: "Goals Over/Under",
    8: "Both Teams Score",
    12: "Double Chance",
}

# Observed daily headers are distinct from any unconfirmed subscription allowance.
API_LEDGER_PATH = os.getenv("API_LEDGER_PATH", ".api-usage/ledger.sqlite3")
API_QUOTA_WARN_THRESHOLDS = sorted({int(n) for n in os.getenv(
    "API_QUOTA_WARN_THRESHOLDS", "2000,1000,500").split(',') if n.strip()}, reverse=True)
API_RUN_BUDGET = int(os.getenv("API_RUN_BUDGET", "0"))  # 0 = no additional cap

if API_RUN_BUDGET < 0:
    raise ValueError("API_RUN_BUDGET must be non-negative")

HEALTH_COLLAPSE_RATIO = float(os.getenv("HEALTH_COLLAPSE_RATIO", "0.2"))
HEALTH_MIN_BASELINE = int(os.getenv("HEALTH_MIN_BASELINE", "100"))
HEALTH_STALE_HOURS = int(os.getenv("HEALTH_STALE_HOURS", "72"))

if not 0 < HEALTH_COLLAPSE_RATIO < 1 or HEALTH_MIN_BASELINE < 1 or HEALTH_STALE_HOURS < 1:
    raise ValueError("Health ratio must be between 0 and 1; baseline and stale hours must be positive")

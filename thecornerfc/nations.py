"""National team ranking: the club ranking's Elo (ranking.py) run over men's full internationals.

Per match, as for clubs:
    exp_diff    = (home_rank - away_rank + home advantage) / 100     (100 points = one goal)
    act_diff    = home_goals - away_goals, capped at +/- MAX_GOAL_DIFF
    rank_change = (act_diff - exp_diff) * K_FACTOR * TIER_WEIGHT[tier]
    home_rank  += rank_change;  away_rank -= rank_change
Differences from clubs:
  * Home advantage only when the match isn't at a neutral venue (most tournament games are), and
    a bigger one: half a goal.
  * A goal difference cap of 8, not 3: mismatches like 8-0 against San Marino are real.
  * TIER_WEIGHT can weight finals, other competitive games and friendlies differently. The backtest
    found no gain from it (see below), so all three are 1 for now.
  * No xG: the public results have none.
  * Every nation starts at START_RANK. The replay begins in 1872, so starting ranks have washed
    out long before the years that matter.
Values come from experiments/nations_elo (backtest, see REPORT.md): tuned on 2000-13, checked on
2014-26. Against the club values unchanged (K 6, home 30, cap 3, friendlies 1/3), goal difference
RMSE on 2014-26 fell from 1.708 to 1.651 and W/D/L log loss from 0.8756 to 0.8702.

The Nations tab shows each nation's rank now (Current Strength) and its change over the last
12 months. No Baseline Strength: that's for clubs.

Data:
  * The public "international_results" dataset (github.com/martj42/international_results): every
    men's full international since 1872, with a neutral-venue flag and the tournament name. It's
    downloaded to the query cache folder and refreshed when older than MAX_AGE_HOURS.
  * national_fixtures (API-Football, when synced: `sync national`): matches the dataset doesn't
    have yet. Where both have a match (same two nations within a day), the dataset's row wins,
    because its neutral flag is reliable.
Only FIFA members are listed: nations that have played a World Cup qualifier since 2010. Other
sides (Jersey, Greenland, CONIFA teams) still count as opponents, but matches in tournaments for
non-FIFA sides, and multi-sport games (mostly under-23 teams), are left out.
"""
import csv
import io
import logging
import math
import os
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

from .cache import CACHE_DIR

log = logging.getLogger(__name__)

DATA_URL = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
CSV_PATH = CACHE_DIR / "international_results.csv"
MAX_AGE_HOURS = 20

K_FACTOR = 6                 # as clubs; 5-6 scored best, 3-4 and 8+ worse
HOME_ADVANTAGE_POINTS = 50   # half a goal (clubs: 0.3); 50-60 scored about the same
MAX_GOAL_DIFF = 8            # internationals have real mismatches (San Marino); 3 was clearly worse
START_RANK = 1000
# Rank change multiplier by tier. Down-weighting friendlies (0.33-0.75) or up-weighting finals
# (1.25-1.5) both scored slightly worse in the backtest, so every tier counts the same for now.
TIER_WEIGHT = {"finals": 1.0, "competitive": 1.0, "friendly": 1.0}

ACTIVE_YEARS = 4          # listed if they've played within this many years
MEMBER_SINCE = "2010"     # FIFA members: played a World Cup qualifier since then

FINALS = {"FIFA World Cup", "Confederations Cup", "UEFA Euro", "Copa América", "African Cup of Nations",
          "AFC Asian Cup", "Gold Cup", "Oceania Nations Cup"}
# One-off invitational tournaments: played like friendlies
INVITATIONAL = {"Friendly", "King's Cup", "Kirin Cup", "Kirin Challenge Cup", "FIFA Series",
                "Cyprus International Tournament", "Malta International Tournament", "Merdeka Tournament",
                "Nehru Cup", "Prime Minister's Cup", "MSG Prime Minister's Cup", "Korea Cup", "Lunar New Year Cup",
                "Jordan International Tournament", "King Hassan II Tournament", "Dunhill Cup", "USA Cup",
                "Tournoi de France", "Superclásico de las Américas", "CONCACAF Series", "Four Nations Tournament",
                "Tri Nation Tournament", "Tri-Nations Series", "Three Nations Cup", "Miami Cup", "Millennium Cup",
                "United Arab Emirates Friendship Tournament", "Philippine Peace Cup", "Navruz Cup", "Al Ain International Cup"}
# Tournaments for non-FIFA sides, and multi-sport games (under-23 sides since the 2000s)
EXCLUDED = re.compile(r"CONIFA|ConIFA|Games|Viva World Cup|Muratti Vase|ELF Cup|FIFI Wild Cup|Tynwald|Niamh|"
                      r"Peoples|World Unity|Benedikt|Corsica|Heritage Cup|KTFF|Outre-Mer")

# Confederation from the confederation-only competitions a nation played in its last 15 years
CONFED_OF = {
    "UEFA": ("UEFA Euro", "UEFA Euro qualification", "UEFA Nations League"),
    "CAF": ("African Cup of Nations", "African Cup of Nations qualification", "COSAFA Cup", "CECAFA Cup"),
    "AFC": ("AFC Asian Cup", "AFC Asian Cup qualification", "AFF Championship", "ASEAN Championship",
            "Gulf Cup", "SAFF Cup", "EAFF Championship", "WAFF Championship", "AFC Challenge Cup"),
    "CONCACAF": ("Gold Cup", "Gold Cup qualification", "CONCACAF Nations League",
                 "CONCACAF Nations League qualification", "CFU Caribbean Cup", "CFU Caribbean Cup qualification",
                 "UNCAF Cup"),
    "CONMEBOL": ("Copa América",),
    "OFC": ("Oceania Nations Cup", "Oceania Nations Cup qualification"),
}
CONFED = {t: c for c, ts in CONFED_OF.items() for t in ts}
CONFED_FIXED = {"American Samoa": "OFC"}   # only plays World Cup qualifiers and Pacific Games

# The dataset's name -> flagcdn code (ISO 3166, with gb-eng etc. for the home nations)
FLAGS = {
    "Afghanistan": "af", "Albania": "al", "Algeria": "dz", "American Samoa": "as", "Andorra": "ad", "Angola": "ao",
    "Anguilla": "ai", "Antigua and Barbuda": "ag", "Argentina": "ar", "Armenia": "am", "Aruba": "aw",
    "Australia": "au", "Austria": "at", "Azerbaijan": "az", "Bahamas": "bs", "Bahrain": "bh", "Bangladesh": "bd",
    "Barbados": "bb", "Belarus": "by", "Belgium": "be", "Belize": "bz", "Benin": "bj", "Bermuda": "bm",
    "Bhutan": "bt", "Bolivia": "bo", "Bosnia and Herzegovina": "ba", "Botswana": "bw", "Brazil": "br",
    "British Virgin Islands": "vg", "Brunei": "bn", "Bulgaria": "bg", "Burkina Faso": "bf", "Burundi": "bi",
    "Cambodia": "kh", "Cameroon": "cm", "Canada": "ca", "Cape Verde": "cv", "Cayman Islands": "ky",
    "Central African Republic": "cf", "Chad": "td", "Chile": "cl", "China": "cn", "Colombia": "co",
    "Comoros": "km", "Congo": "cg", "Cook Islands": "ck", "Costa Rica": "cr", "Croatia": "hr", "Cuba": "cu",
    "Curaçao": "cw", "Cyprus": "cy", "Czech Republic": "cz", "DR Congo": "cd", "Denmark": "dk", "Djibouti": "dj",
    "Dominica": "dm", "Dominican Republic": "do", "Ecuador": "ec", "Egypt": "eg", "El Salvador": "sv",
    "England": "gb-eng", "Equatorial Guinea": "gq", "Eritrea": "er", "Estonia": "ee", "Eswatini": "sz",
    "Ethiopia": "et", "Faroe Islands": "fo", "Fiji": "fj", "Finland": "fi", "France": "fr", "Gabon": "ga",
    "Gambia": "gm", "Georgia": "ge", "Germany": "de", "Ghana": "gh", "Gibraltar": "gi", "Greece": "gr",
    "Grenada": "gd", "Guam": "gu", "Guatemala": "gt", "Guinea": "gn", "Guinea-Bissau": "gw", "Guyana": "gy",
    "Haiti": "ht", "Honduras": "hn", "Hong Kong": "hk", "Hungary": "hu", "Iceland": "is", "India": "in",
    "Indonesia": "id", "Iran": "ir", "Iraq": "iq", "Israel": "il", "Italy": "it", "Ivory Coast": "ci",
    "Jamaica": "jm", "Japan": "jp", "Jordan": "jo", "Kazakhstan": "kz", "Kenya": "ke", "Kosovo": "xk",
    "Kuwait": "kw", "Kyrgyzstan": "kg", "Laos": "la", "Latvia": "lv", "Lebanon": "lb", "Lesotho": "ls",
    "Liberia": "lr", "Libya": "ly", "Liechtenstein": "li", "Lithuania": "lt", "Luxembourg": "lu", "Macau": "mo",
    "Madagascar": "mg", "Malawi": "mw", "Malaysia": "my", "Maldives": "mv", "Mali": "ml", "Malta": "mt",
    "Mauritania": "mr", "Mauritius": "mu", "Mexico": "mx", "Moldova": "md", "Mongolia": "mn", "Montenegro": "me",
    "Montserrat": "ms", "Morocco": "ma", "Mozambique": "mz", "Myanmar": "mm", "Namibia": "na", "Nepal": "np",
    "Netherlands": "nl", "New Caledonia": "nc", "New Zealand": "nz", "Nicaragua": "ni", "Niger": "ne",
    "Nigeria": "ng", "North Korea": "kp", "North Macedonia": "mk", "Northern Ireland": "gb-nir", "Norway": "no",
    "Oman": "om", "Pakistan": "pk", "Palestine": "ps", "Panama": "pa", "Papua New Guinea": "pg", "Paraguay": "py",
    "Peru": "pe", "Philippines": "ph", "Poland": "pl", "Portugal": "pt", "Puerto Rico": "pr", "Qatar": "qa",
    "Republic of Ireland": "ie", "Romania": "ro", "Russia": "ru", "Rwanda": "rw", "Saint Kitts and Nevis": "kn",
    "Saint Lucia": "lc", "Saint Vincent and the Grenadines": "vc", "Samoa": "ws", "San Marino": "sm",
    "Saudi Arabia": "sa", "Scotland": "gb-sct", "Senegal": "sn", "Serbia": "rs", "Seychelles": "sc",
    "Sierra Leone": "sl", "Singapore": "sg", "Slovakia": "sk", "Slovenia": "si", "Solomon Islands": "sb",
    "Somalia": "so", "South Africa": "za", "South Korea": "kr", "South Sudan": "ss", "Spain": "es",
    "Sri Lanka": "lk", "Sudan": "sd", "Suriname": "sr", "Sweden": "se", "Switzerland": "ch", "Syria": "sy",
    "São Tomé and Príncipe": "st", "Tahiti": "pf", "Taiwan": "tw", "Tajikistan": "tj", "Tanzania": "tz",
    "Thailand": "th", "Timor-Leste": "tl", "Togo": "tg", "Tonga": "to", "Trinidad and Tobago": "tt",
    "Tunisia": "tn", "Turkey": "tr", "Turkmenistan": "tm", "Turks and Caicos Islands": "tc", "Uganda": "ug",
    "Ukraine": "ua", "United Arab Emirates": "ae", "United States": "us", "United States Virgin Islands": "vi",
    "Uruguay": "uy", "Uzbekistan": "uz", "Vanuatu": "vu", "Venezuela": "ve", "Vietnam": "vn", "Wales": "gb-wls",
    "Yemen": "ye", "Zambia": "zm", "Zimbabwe": "zw",
}
# API-Football's national team names -> the dataset's (names that already match aren't listed).
# Used for its fixtures (national_fixtures) and for the site's nationality pages.
API_NAMES = {
    "USA": "United States", "Korea Republic": "South Korea", "Korea DPR": "North Korea", "Congo DR": "DR Congo",
    "Côte d'Ivoire": "Ivory Coast", "Czechia": "Czech Republic", "Türkiye": "Turkey", "Ireland": "Republic of Ireland",
    "Bosnia": "Bosnia and Herzegovina", "China PR": "China", "Chinese Taipei": "Taiwan", "Cabo Verde": "Cape Verde",
    "St. Kitts and Nevis": "Saint Kitts and Nevis", "St. Lucia": "Saint Lucia",
    "St. Vincent / Grenadines": "Saint Vincent and the Grenadines", "Macedonia": "North Macedonia",
    "FYR Macedonia": "North Macedonia", "Swaziland": "Eswatini", "Sao Tome and Principe": "São Tomé and Príncipe",
    "Curacao": "Curaçao", "East Timor": "Timor-Leste", "Brunei Darussalam": "Brunei", "Kyrgyz Republic": "Kyrgyzstan",
    "UAE": "United Arab Emirates", "US Virgin Islands": "United States Virgin Islands",
    "Bosnia & Herzegovina": "Bosnia and Herzegovina", "Rep. Of Ireland": "Republic of Ireland",
    "Cape Verde Islands": "Cape Verde", "French Guyana": "French Guiana",
}


@dataclass
class Result:
    day: str             # YYYY-MM-DD
    home: str
    away: str
    home_goals: int
    away_goals: int
    tournament: str
    neutral: bool
    source: str = "dataset"


def tier(tournament):
    """'finals', 'competitive', 'friendly', or None for a tournament left out."""
    if EXCLUDED.search(tournament):
        return None
    if tournament in FINALS:
        return "finals"
    if tournament in INVITATIONAL:
        return "friendly"
    return "competitive"


# --------------------------------------------------------------------------- data

def download(path=CSV_PATH, max_age_hours=MAX_AGE_HOURS):
    """The results CSV, from the cache folder; downloaded again when it's older than max_age_hours.
    A failed download keeps the old copy (only raises if there's none)."""
    path = Path(path)
    if path.exists() and time.time() - path.stat().st_mtime < max_age_hours * 3600:
        return path.read_text(encoding="utf-8")
    try:
        resp = requests.get(DATA_URL, timeout=60)
        resp.raise_for_status()
        text = resp.text
        if not text.startswith("date,home_team,away_team"):
            raise ValueError("unexpected header")
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
        return text
    except (requests.RequestException, ValueError) as exc:
        if path.exists():
            log.warning("International results download failed (%s); using the cached copy", exc)
            return path.read_text(encoding="utf-8")
        raise


def parse_csv(text):
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        if not r["home_score"].isdigit() or not r["away_score"].isdigit():
            continue   # not played yet
        out.append(Result(r["date"], r["home_team"], r["away_team"], int(r["home_score"]), int(r["away_score"]),
                          r["tournament"], r["neutral"].upper() == "TRUE"))
    return out


def api_name(name):
    return API_NAMES.get(name, name)


def api_matches(conn):
    """Finished matches from national_fixtures (API-Football), in the dataset's form. Empty until
    that table exists and has rows. Tournament finals are taken as neutral (API-Football has no
    flag); the dataset replaces these rows, with the right flag, once it has the match."""
    if conn is None:
        return []
    if not conn.execute("select to_regclass('national_fixtures')").fetchone()[0]:
        return []
    rows = conn.execute("""
        select kickoff, home_name, away_name, home_goals, away_goals, tournament, neutral
        from national_fixtures
        where status_short in ('FT', 'AET', 'PEN') and home_goals is not null and away_goals is not null
        order by kickoff""").fetchall()
    return [Result(k.date().isoformat(), api_name(h), api_name(a), hg, ag, t,
                   bool(n) if n is not None else t in FINALS, "api-football")
            for k, h, a, hg, ag, t, n in rows]


def merge(dataset, extra):
    """The dataset's matches plus those in extra it doesn't have (same pair of nations within a day)."""
    seen = set()
    for m in dataset:
        d = date.fromisoformat(m.day)
        for off in (-1, 0, 1):
            seen.add((str(d + timedelta(days=off)), frozenset((m.home, m.away))))
    added = [m for m in extra if (m.day, frozenset((m.home, m.away))) not in seen]
    return sorted(dataset + added, key=lambda m: m.day)   # stable: same-day order kept


# --------------------------------------------------------------------------- the model

def replay(matches, k=K_FACTOR, home_adv=HOME_ADVANTAGE_POINTS, cap=MAX_GOAL_DIFF, weights=None,
           start=START_RANK, on_match=None):
    """Replay results in order. Returns {nation: history}, history = [start, rank after each match].
    on_match(m, home_rank, away_rank, exp_diff) is called before each rated match (backtests)."""
    weights = weights or TIER_WEIGHT
    current, history = {}, {}
    for m in matches:
        t = tier(m.tournament)
        if t is None:
            continue
        for team in (m.home, m.away):
            if team not in current:
                current[team] = start
                history[team] = [start]
        h, a = current[m.home], current[m.away]
        exp_diff = (h - a + (0 if m.neutral else home_adv)) / 100
        if on_match:
            on_match(m, h, a, exp_diff)
        act = max(-cap, min(cap, m.home_goals - m.away_goals))
        change = (act - exp_diff) * k * weights[t]
        current[m.home], current[m.away] = h + change, a - change
        history[m.home].append(current[m.home])
        history[m.away].append(current[m.away])
    return history


def members(matches):
    return {t for m in matches if m.tournament == "FIFA World Cup qualification" and m.day >= MEMBER_SINCE
            for t in (m.home, m.away)}


def confederations(matches, since):
    counts = defaultdict(Counter)
    for m in matches:
        c = CONFED.get(m.tournament)
        if c and m.day >= since:
            counts[m.home][c] += 1
            counts[m.away][c] += 1
    return {**{t: c.most_common(1)[0][0] for t, c in counts.items()}, **CONFED_FIXED}


def build(matches, today=None):
    """The Nations tab's data."""
    today = today or datetime.now(timezone.utc).date()
    history = replay(matches)
    fifa = members(matches)
    confed = confederations(matches, str(today.replace(year=today.year - 15)))
    active_since = str(today.replace(year=today.year - ACTIVE_YEARS))
    year_ago = str(today - timedelta(days=365))

    # Each nation's rated matches, newest last, for the last-match and form columns
    rated = defaultdict(list)
    idx = defaultdict(int)
    for m in matches:
        if tier(m.tournament) is None:
            continue
        for side, opp, gf, ga in ((m.home, m.away, m.home_goals, m.away_goals),
                                  (m.away, m.home, m.away_goals, m.home_goals)):
            idx[side] += 1
            rated[side].append((m.day, opp, gf, ga, m.tournament, history[side][idx[side]]))

    rows = []
    for team in fifa:
        games = rated.get(team, [])
        if not games or games[-1][0] < active_since:
            continue
        last = games[-1]
        recent = [g for g in games if g[0] >= year_ago]
        past = [g for g in games if g[0] < year_ago]
        rows.append({
            "name": team, "flag": FLAGS.get(team), "confed": confed.get(team),
            "current": round(history[team][-1], 1),
            "year_ago": round(past[-1][5], 1) if past else None,
            "played": len(games), "played_4y": sum(g[0] >= active_since for g in games),
            "w": sum(g[2] > g[3] for g in recent), "d": sum(g[2] == g[3] for g in recent),
            "l": sum(g[2] < g[3] for g in recent),
            "last": {"date": last[0], "opp": last[1], "gf": last[2], "ga": last[3], "comp": last[4]},
        })
    rows.sort(key=lambda r: -r["current"])
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "latest_match": max(m.day for m in matches),
        "matches": sum(tier(m.tournament) is not None for m in matches),
        "from_api": sum(m.source == "api-football" for m in matches),
        "params": {"k": K_FACTOR, "home_advantage": HOME_ADVANTAGE_POINTS, "cap": MAX_GOAL_DIFF,
                   "weights": TIER_WEIGHT},
        "aliases": _aliases(),
        "nations": rows,
    }


def _aliases():
    """{dataset name: [API-Football names]}, so the site can link a nation to its players' page."""
    out = defaultdict(list)
    for api, name in API_NAMES.items():
        out[name].append(api)
    return dict(out)


def load(conn=None):
    """Every result: the dataset, plus API-Football's between nations the dataset knows (an unknown
    name would start a new nation from START_RANK; add it to API_NAMES instead)."""
    dataset = parse_csv(download())
    known = {t for m in dataset for t in (m.home, m.away)}
    extra = api_matches(conn)
    unknown = sorted({t for m in extra for t in (m.home, m.away) if t not in known})
    if unknown:
        log.warning("National fixtures with names not in the dataset (add to API_NAMES): %s", unknown)
    return merge(dataset, [m for m in extra if m.home in known and m.away in known])


# --------------------------------------------------------------------------- team pages

TEAM_YEARS = ACTIVE_YEARS   # matches on a nation page's Formations and Players tabs
APP_FIELDS = ["match", "player", "minutes", "started", "role", "goals", "assists", "yellow", "red"]
MATCH_FIELDS = ["date", "opp", "venue", "gf", "ga", "tournament", "formation", "coach", "coach_id"]


def team_pages(conn, today=None):
    """{team_id: page} for each national team with a finished match in national_fixtures in the last
    TEAM_YEARS: its head coach (team_coaches: since when), its matches (oldest first) with the
    formation and coach, and every appearance.
    Appearances come from national_fixture_players, plus starters from national_fixture_lineups
    with no stat line (minutes unknown). Empty until the national_players migration has run."""
    if conn is None or not conn.execute("select to_regclass('national_fixture_players')").fetchone()[0]:
        return {}
    today = today or datetime.now(timezone.utc).date()
    since = today.replace(year=today.year - TEAM_YEARS)
    fixtures = conn.execute("""
        select fixture_id, kickoff, home_team_id, away_team_id, home_name, away_name, home_goals, away_goals,
               tournament, neutral
        from national_fixtures
        where status_short in ('FT', 'AET', 'PEN') and home_goals is not null and away_goals is not null
          and kickoff >= %s
        order by kickoff, fixture_id""", [since]).fetchall()
    ids = [f[0] for f in fixtures]
    formations = {(fid, t): (fm, coach, coach_id) for fid, t, fm, coach, coach_id in conn.execute(
        "select fixture_id, team_id, formation, coach_name, coach_id from national_fixture_formations"
        " where fixture_id = any(%s)", [ids])}
    apps = {}                                  # (fixture, player) -> [team, minutes, started, role, g, a, y, r]
    names = {}
    for fid, team, pid, grid_role, name in conn.execute(
            "select fixture_id, team_id, player_id, role, player_name from national_fixture_lineups where fixture_id = any(%s)",
            [ids]):
        apps[fid, pid] = [team, None, True, grid_role, None, None, None, None]
        if name:
            names[pid] = name
    for fid, team, pid, mins, started, g, a, y, r, name in conn.execute("""
            select fixture_id, team_id, player_id, minutes, started, goals, assists, yellow_cards, red_cards,
                   player_name
            from national_fixture_players where fixture_id = any(%s)""", [ids]):
        role = apps.get((fid, pid), [None] * 4)[3]
        apps[fid, pid] = [team, mins, bool(started), role, g, a, y, r]
        if name:
            names[pid] = name
    coaches = {t: {"id": c, "name": n, "since": since.isoformat() if since else None}
               for t, c, n, since in conn.execute(
                   "select team_id, coach_id, name, since from team_coaches where team_id = any(%s)",
                   [list({t for f in fixtures for t in f[2:4]})])}
    # the site's name for a player where we have him (as on his player page)
    pids = list({pid for _, pid in apps})
    names.update(conn.execute("select player_id, name from players where player_id = any(%s)", [pids]).fetchall())

    by_match = defaultdict(list)               # (fixture, team) -> [[player, *line]]
    for (fid, pid), (team, *line) in apps.items():
        by_match[fid, team].append([pid, *[int(v) if isinstance(v, bool) else v for v in line]])

    pages = {}
    for fid, kickoff, h_id, a_id, h_name, a_name, hg, ag, tournament, neutral in fixtures:
        for team, name, opp, gf, ga, venue in ((h_id, h_name, a_name, hg, ag, "H"), (a_id, a_name, h_name, ag, hg, "A")):
            page = pages.setdefault(team, {"id": team, "name": name, "coach": coaches.get(team), "matches": [],
                                           "apps": [], "players": {}})
            page["name"] = name                # the latest name API-Football sent
            fm, coach, coach_id = formations.get((fid, team), (None, None, None))
            page["matches"].append([kickoff.date().isoformat(), opp, "N" if neutral else venue, gf, ga, tournament,
                                    fm, coach, coach_id])
            idx = len(page["matches"]) - 1
            for pid, *line in by_match.get((fid, team), []):
                page["apps"].append([idx, pid, *line])
                page["players"][pid] = names.get(pid)
    for page in pages.values():
        page["apps"].sort(key=lambda a: (a[0], not a[3], a[1]))     # by match, starters first
        page["match_fields"], page["app_fields"] = MATCH_FIELDS, APP_FIELDS
    return pages


def export_team_pages(conn, out_dir):
    """Write data/nations/<team_id>.json for each national team page (team_pages); remove the
    rest. Returns {dataset name: team_id}, for nations.json."""
    from .export import _write_json_file
    pages = team_pages(conn)
    team_dir = Path(out_dir) / "nations"
    team_dir.mkdir(parents=True, exist_ok=True)
    for old in team_dir.glob("*.json"):
        if not old.stem.isdigit() or int(old.stem) not in pages:
            old.unlink()
    for team, page in pages.items():
        _write_json_file(team_dir / f"{team}.json", page)
    log.info("Nation pages: %d teams, %d appearances", len(pages), sum(len(p["apps"]) for p in pages.values()))
    return {api_name(p["name"]): team for team, p in pages.items()}


def export_nations(conn=None, out_dir=None):
    """Write data/nations.json and the team pages (data/nations/). Returns the payload."""
    from .export import OUT_DIR, _write_json_file
    out_dir = Path(out_dir or OUT_DIR)
    payload = build(load(conn))
    team_ids = export_team_pages(conn, out_dir)
    for row in payload["nations"]:
        row["team_id"] = team_ids.get(row["name"])
    _write_json_file(out_dir / "nations.json", payload)
    log.info("Nations: %d ranked, latest match %s", len(payload["nations"]), payload["latest_match"])
    return payload

"""People: the injuries and bans list, the players table's rows (site.players) with the free slice
and the paid order, each player's seasons and his page. Where a removal request and the paywall's
rules bite.
"""
import html
import json
import logging
import math
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone

from .. import config
from ..models import availability
from ..pipeline.cache import finished_fixtures
from .site_files import (
    ExportValidationError,
    OUT_DIR,
    PAID_PREFIX,
    _check_table_collapse,
    _paid_rows,
    _paywall_on,
    _r,
    _sync_table,
    _write_json_file,
)

# the export's one log, whichever module writes to it
log = logging.getLogger("thecornerfc.publish.export")


# The matches and the players are rows of site.matches and site.players, not files: each table is
# checked the same way before it is rewritten (_check_table_collapse)
MIN_PLAYERS = 50


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


def export_injuries(conn, out_dir=OUT_DIR, free=None):
    """Each club's injury list for the club page (.export/injuries.json): out and doubtful
    players for its next match that has a list, else its latest list from the last
    INJURY_LOOKBACK_DAYS (API-Football publishes a match's list only shortly before it), less
    the one-match reasons (a ban already served). Upcoming fixtures use the backend
    availability merge; past red cards alone are not treated as confirmed current bans.

    ban: the reason when it is a ban (BAN_REASONS), else null: medical reasons aren't published.
    missed: how many of the club's played matches in a row he has been on its list, back from its
    latest (matches with no list for the club, e.g. cups, are skipped). season_rank: his latest
    season rank, for players off the current players list. injured: 1 when he is out injured or ill.
    free: the players in the paid tier's free slice (export_players). Once the paywall is on, a
    season rank is published only for them: the file is one anyone can ask for.
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
    if free is not None and _paywall_on(conn):
        season_rank = {p: r for p, r in season_rank.items() if p in free}
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


PLAYER_SEASONS = list(range(2026, 2020, -1))     # season ranks shown, newest first
PLAYER_SEASON_FIELDS = ["minutes", "goals", "assists"]     # a player's "season" in his row


POSITION_SHARE = 0.25      # a position counts for the filter at this share of his starting minutes

LISTED = """p.current_rank is not null and (p.rank_minutes >= 450 or exists (
    select 1 from player_season_ranks r where r.player_id = p.player_id and r.season = any(%s)
      and r.minutes >= 1500) or exists (select 1 from team_squads s where s.player_id = p.player_id))"""


def export_players(conn, out_dir=OUT_DIR, rankings=()):
    """Current player ranks and season ranks, as rows of the site.players table (store_players).
    A season rank is the player's average rank across that season (after each match, weighted by
    minutes; player_season_ranks), blank if he didn't play in these leagues. Line-ups aren't
    here: the site asks the database for the match it opens (site_lineups) and for a club's next
    predicted XI (site_next_xi). rankings: the rows of rankings.json, for each club's world
    rank. Returns ({player: his club}, {"stored": whether the table was written,
    "future_seasons", "teams": the names of the players' clubs, "free": the players in the paid
    tier's free slice})."""
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
    # published as the model has them: how good he is in that position (player_ratings step 6),
    # which needn't equal his overall rank, even in the position shown for him
    # (line-ups aren't exported: the site asks the database for a match's, site_lineups, and for
    # a club's next predicted XI, site_next_xi)
    # this season so far, all his clubs (PLAYER_SEASON_FIELDS): the per-match leagues first, else
    # the season totals where his league has them (player_seasons). No match rating: API-Football's
    # rating isn't published anywhere on the site
    season_stats = {}
    for _, player, mins, goals, assists in conn.execute(
            """select 1 src, x.player_id, sum(x.minutes), sum(x.goals), sum(x.assists)
               from player_seasons x where x.season = %s and x.player_id = any(%s) and x.minutes > 0
               group by 2
               union all
               select 2, x.player_id, sum(x.minutes), sum(x.goals), sum(x.assists)
               from fixture_players x join fixtures f using (fixture_id)
               where f.season = %s and x.player_id = any(%s) and f.status_short = any(%s) and x.minutes > 0
               group by 2
               order by src""",
            [PLAYER_SEASONS[0], [r[0] for r in players]] * 2 + [list(config.FINISHED_STATUSES)]):
        season_stats[player] = [int(mins), int(goals or 0), int(assists or 0)]   # per-match rows come last and win
    # his next seasons, projected along his age curve (player_ratings.py)
    future = defaultdict(dict)
    for player, season, rank in conn.execute("select player_id, season, projected_rank from player_projected_ranks"):
        future[player][season] = float(rank)
    future_seasons = sorted({y for ys in future.values() for y in ys})
    # his skill scores, 0-100 (player_ratings.skill_scores, MC-0030), once the column is there
    # (db/migrations/20261021_player_skills.sql)
    skills = {}
    if _has_column(conn, "public.players", "skills"):
        skills = dict(conn.execute("select player_id, skills from players where skills is not null and player_id = any(%s)",
                                   [[r[0] for r in players]]).fetchall())
    rows = [[r[0], r[1], main_pos.get(r[0], r[2]), float(r[3]), r[4], r[5], r[6],
             [season_ranks[r[0]].get(y) for y in PLAYER_SEASONS], r[7],
             [i for i, y in enumerate(PLAYER_SEASONS) if y in estimated[r[0]]], r[8],
             pos_12m.get(r[0], []),
             shown_position_ranks(main_pos.get(r[0], r[2]), season_ranks[r[0]].get(PLAYER_SEASONS[0]), pos_ranks.get(r[0], {})),
             [future[r[0]].get(y) for y in future_seasons], season_stats.get(r[0])] for r in players]
    # names of players' clubs outside the club rankings (a move out of our leagues)
    teams = {t: n for t, n in conn.execute(
        "select team_id, name from teams where team_id = any(%s)", [list({r[5] for r in players if r[5]})])}
    log.info("Exported %d player ranks", len(players))
    site_rows = site_player_rows(rows, rankings, skills)
    stored = store_players(conn, site_rows)
    # {player: his club}, for the club files' positions
    return {r[0]: r[5] for r in players}, {"stored": stored, "future_seasons": future_seasons, "teams": teams,
                                           "free": {p["player_id"] for p in site_rows if p["free"]}}


def shown_position_ranks(position, ability, ranks):
    """His position ranks as the site shows them: in the position it lists him in (where he has
    started most over the last 12 months), his rank is his Ability, the number the Players tab
    is ordered by (owner, 2026-10-12). The model's own rank for him there can differ, most for a
    player filling in away from the position his seasons were played in; it stays in
    player_position_ranks. Keepers have none there, so a keeper's only one is GK, his Ability: it
    puts him in his position's free top ten and fills the Players tab's As GK column."""
    from ..models.positions import GROUPS
    group = GROUPS.get(position)
    if ability is None or group is None:
        return ranks
    return {**ranks, group: ability}


# A player as the site draws him: the order of his row in site.players.data (SITE_PLAYER_FIELDS):
# the fields the export builds for each player (PLAYER_FIELDS), then what is counted across all
# of them: his place by Ability among every listed player (world) and in his league (lg of
# lg_of), his place by current rank among his league's players with a club (lg_rank of lg_n, on
# his page), and his place in the export's order (ord).
PLAYER_FIELDS = ["id", "name", "position", "rank", "minutes", "team", "league", "seasons", "age", "estimated",
                 "nationality", "positions_12m", "position_ranks", "future", "season"]
# (skills last, added 2026-10-21: the database functions read the earlier fields by their place)
SITE_PLAYER_FIELDS = PLAYER_FIELDS + ["world", "lg", "lg_of", "lg_rank", "lg_n", "ord", "skills"]
# The paid tier (db/migrations/20261006_paid_players.sql, 20261007_paid_players_order.sql): the
# top FREE_WORLD players by Ability, the top FREE_LEAGUE of each league and the top FREE_POSITION
# of each position on the Players tab's pitch are free (a position's: of the players listed under
# it, the best by their rank as that position, the order the tab puts them in when it is picked).
# For everyone else a visitor without a subscription gets the row with PLAYER_PAID_FIELDS null
# (who he is, his club, age, minutes, goals and assists stay), once the paywall is on. He keeps
# his place in the export's order (ord): the owner's line of 2026-10-07 is that every list is in
# the order a subscriber sees, with the ranks hidden. The owner's line on the slice: every
# league's top 10 (2026-10-04), the five big leagues' only (2026-10-06, when the hidden players
# were put after the ranked ones and a nation's page misled), every league's again and each
# position's (2026-10-07, with the order kept).
FREE_WORLD, FREE_LEAGUE, FREE_POSITION = 50, 10, 10
PLAYER_PAID_FIELDS = ("rank", "seasons", "estimated", "position_ranks", "future", "world", "lg", "lg_rank", "skills")


def blanked_player(data):
    """A player's row (SITE_PLAYER_FIELDS order) with the paid fields null."""
    hide = {SITE_PLAYER_FIELDS.index(f) for f in PLAYER_PAID_FIELDS}
    return [None if i in hide else v for i, v in enumerate(data)]


def _fold(text):
    """Text as the site's search folds it (foldText in app.js): no accents, lower case, anything
    but letters and digits a space."""
    plain = "".join(ch for ch in unicodedata.normalize("NFD", str(text or "")) if not "\u0300" <= ch <= "\u036f")
    return re.sub(r"[^a-z0-9]+", " ", plain.lower()).strip()


def _places(values):
    """{value: its place among values, highest first}; a tie shares the higher place."""
    places = {}
    for i, v in enumerate(sorted(values, reverse=True)):
        places.setdefault(v, i + 1)
    return places


_ENTITIES = {"apos": "'", "#39": "'", "quot": '"', "amp": "&", "lt": "<", "gt": ">"}


def _decode(text):
    """A name as the site shows it (decodeEntities in app.js): API-Football sends some
    HTML-encoded ("O&apos;Reilly")."""
    return re.sub(r"&(apos|#39|quot|amp|lt|gt);", lambda m: _ENTITIES[m.group(1)], text or "")


def site_player_rows(rows, rankings=(), skills=None):
    """The rows of site.players, one dict per player in rows (PLAYER_FIELDS order, the export's
    order): the columns site_players() filters and sorts on, and "data", his row in
    SITE_PLAYER_FIELDS order. rankings: the rows of rankings.json (club, ..., Baseline Strength
    fifth), for his club's world rank. skills: {player: {skill: 0-100}}. Places are counted as the site counted them from the
    whole list: by Ability (this season's rank) among every listed player and within his
    league; a tie shares the higher place."""
    from ..models.positions import GROUPS
    at = {name: i for i, name in enumerate(PLAYER_FIELDS)}
    ability = lambda r: r[at["seasons"]][0] if r[at["seasons"]] else None
    world = _places([ability(r) for r in rows if ability(r) is not None])
    by_league, club_league = defaultdict(list), defaultdict(list)
    for r in rows:
        if ability(r) is not None and r[at["league"]] is not None:
            by_league[r[at["league"]]].append(ability(r))
        if r[at["team"]] and r[at["league"]]:
            club_league[r[at["league"]]].append(r[at["rank"]])
    league_place = {lg: _places(v) for lg, v in by_league.items()}
    club_place = {lg: _places(v) for lg, v in club_league.items()}
    # each position's players (his main one, and those of positions_12m) by their rank as it
    plays_of = lambda r: [x for x in dict.fromkeys([r[at["position"]], *r[at["positions_12m"]]]) if x]
    as_position = lambda r, role: (r[at["position_ranks"]] or {}).get(GROUPS.get(role))
    by_position = defaultdict(list)
    for r in rows:
        for role in plays_of(r):
            if as_position(r, role) is not None:
                by_position[role].append(as_position(r, role))
    position_place = {role: _places(v) for role, v in by_position.items()}
    strengths = [r[4] for r in rankings if r[4] is not None]
    club_places = _places(strengths)
    club_world = {r[0]: club_places[r[4]] for r in rankings if r[4] is not None}
    out = []
    for i, r in enumerate(rows):
        a, league, team = ability(r), r[at["league"]], r[at["team"]]
        placed = a is not None
        in_league = placed and league is not None
        with_club = bool(team and league)
        season = r[at["season"]]
        goals, assists = (season[PLAYER_SEASON_FIELDS.index("goals")], season[PLAYER_SEASON_FIELDS.index("assists")]) if season else (None, None)
        name = _decode(r[at["name"]])
        plays = plays_of(r)
        top_of_position = any(as_position(r, role) is not None and position_place[role][as_position(r, role)] <= FREE_POSITION
                              for role in plays)
        data = [*r, world[a] if placed else None,
                league_place[league][a] if in_league else None, len(by_league[league]) if in_league else None,
                club_place[league][r[at["rank"]]] if with_club else None, len(club_league[league]) if with_club else None, i,
                (skills or {}).get(r[at["id"]])]
        out.append({
            "free": bool((placed and world[a] <= FREE_WORLD)
                         or (in_league and league_place[league][a] <= FREE_LEAGUE)
                         or top_of_position),
            "data_free": blanked_player(data),
            "player_id": r[at["id"]], "ord": i, "name_lc": name.lower(), "name_fold": _fold(name),
            "team_id": team, "league_id": league, "age": r[at["age"]], "nationality": r[at["nationality"]],
            "plays": plays, "ability": None if a is None else math.floor(a + 0.5),
            "club_world": club_world.get(team), "minutes": r[at["minutes"]],
            "seasons": r[at["seasons"]], "future": r[at["future"]], "pos_ranks": r[at["position_ranks"]],
            "ga": None if season is None else goals + assists + goals / 1000,
            "skills": (skills or {}).get(r[at["id"]]),
            "data": data,
        })
    return out


def _has_column(conn, table, column):
    """Whether table (schema.name) has column: a column a migration adds is used once it is there."""
    return conn.execute("""select 1 from pg_attribute where attrelid = to_regclass(%s) and attname = %s
                           and not attisdropped""", [table, column]).fetchone() is not None


def store_players(conn, players):
    """site.players: every listed player as a row (site_player_rows), for the database functions
    the site asks (db/migrations/20261005_site_players.sql: site_players, site_player_facets).
    The table is rewritten whole, in one transaction, unless there are too few players or it
    would lose most of its rows (_check_table_collapse).

    True once stored. False, with nothing written, on a read-only run or a database from before
    the migration (logged). Any other failure stops the run."""
    try:
        config.require_db_write("store the players")
    except config.SafetyError as exc:
        log.info("Players not stored: %s", exc)
        return False
    (table,) = conn.execute("select to_regclass(%s)", ["site.players"]).fetchone()
    if table is None:
        log.warning("site.players isn't there yet (db/migrations/20261005_site_players.sql): the players weren't stored")
        return False
    text = lambda value: json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    columns = ["player_id", "ord", "name_lc", "name_fold", "team_id", "league_id", "age", "nationality", "plays",
               "ability", "club_world", "minutes", "seasons", "future", "pos_ranks", "ga", "data"]
    # the free slice and the blanked rows, once the paid tier's migration has added their columns
    if _has_column(conn, "site.players", "data_free"):
        columns += ["free", "data_free"]
    # the skill scores, for sorting by a skill, once 20261021_player_skills.sql has added the column
    if _has_column(conn, "site.players", "skills"):
        columns += ["skills"]
    if len(players) < MIN_PLAYERS:
        raise ExportValidationError(f"only {len(players)} players to store; expected at least {MIN_PLAYERS}")
    with conn.cursor() as cur:
        _check_table_collapse(cur, "site.players", len(players))
        gone, written = _sync_table(cur, "site.players", ["player_id"], columns,
                                    ([text(p[c]) if c in ("pos_ranks", "data", "data_free") or (c == "skills" and p[c] is not None)
                                      else p[c] for c in columns]
                                     for p in players))
        cur.execute("analyze site.players")
    conn.commit()
    log.info("Stored %d players (%d new or changed, %d removed)", len(players), written, gone)
    return True


def _club_spells(rows):
    """[(player, key, team, minutes, club rank, goals, assists)]
    -> {player: {key: [[team, mins, rank, goals, assists], ...]}}, clubs by minutes, most first."""
    out = defaultdict(dict)
    for player, key, team, mins, rank, goals, assists in rows:
        out[player].setdefault(key, []).append(
            [team, int(mins), round(float(rank)) if rank is not None else None, int(goals or 0), int(assists or 0)])
    for seasons in out.values():
        for spells in seasons.values():
            spells.sort(key=lambda x: -x[1])
    return out


SPELL_FIELDS = ["team", "minutes", "club_rank", "goals", "assists"]


def export_player_seasons(conn, out_dir=OUT_DIR):
    """Each player's season detail, returned for the files that carry it: his own rows go in his
    page file (the hover on his season cells and his page read it) and his club's file.

    For each exported player and each season in PLAYER_SEASONS, and for "now" (his last 20
    appearances, the ones the current rank is built from): the clubs he played for, his minutes
    for each, the club's average rank over those matches, and his goals and assists.
    """
    ids = [r[0] for r in conn.execute(f"select player_id from players p where {LISTED}", [PLAYER_SEASONS])]
    per_club = """sum(fp.minutes),
                  sum(h.lt_before * fp.minutes) / nullif(sum(fp.minutes) filter (where h.lt_before is not null), 0),
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
    log.info("Season detail for %d players", len(spells))
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
# What a player's page publishes of his matches: what a match report states (appearances, minutes,
# goals, assists, cards) and the site's own rank. API-Football's other counts (shots, passes,
# tackles, duels, dribbles, saves) feed the ranks but aren't published.
SEASON_FIELDS = ["season", "team", "league", "apps", "starts", "minutes", "goals", "assists", "yellow", "red"]
MATCH_FIELDS = ["fixture", "date", "league", "team", "opponent", "home", "gf", "ga", "started", "minutes",
                "role", "rank", "goals", "assists", "yellow", "red"]


def build_player_pages(ids, apps, fixtures, other_seasons):
    """{player: page payload} for .export/players/<id>.json, from cached rows (runs offline).

    apps: player_ratings._appearances rows; fixtures: cache.finished_fixtures rows;
    other_seasons: player_ratings._other_seasons rows. Season lines are per club and league: from
    his appearances in the per-match leagues, and the season totals (player_seasons) elsewhere,
    where starts aren't known. A match's rank (going into it) is filled in later.
    """
    ids = set(ids)
    fx = {r[0]: r for r in fixtures}
    # per (season, team, league): apps, starts, minutes, goals, assists, yellow, red
    lines = defaultdict(lambda: defaultdict(lambda: [0] * 7))
    recent = defaultdict(list)
    for r in apps:
        if r[2] not in ids or r[3] <= 0 or r[10] not in config.FINISHED_STATUSES or r[0] not in fx:
            continue
        goals, assists = r[11] or 0, r[12] or 0
        yellow, red = r[24] or 0, r[25] or 0
        s = lines[r[2]][(r[8], r[1], r[9])]
        for i, v in enumerate((1, 1 if r[4] else 0, r[3], goals, assists, yellow, red)):
            s[i] += v
        recent[r[2]].append(r)
    out = {}
    for player in ids:
        seasons = [[season, team, league, *s] for (season, team, league), s in lines.get(player, {}).items()]
        matches = []
        for r in sorted(recent.get(player, []), key=lambda r: fx[r[0]][1], reverse=True)[:PLAYER_MATCHES]:
            f = fx[r[0]]
            home = r[1] == f[4]
            matches.append([r[0], f[1].date().isoformat(), r[9], r[1], f[5] if home else f[4], 1 if home else 0,
                            f[6] if home else f[7], f[7] if home else f[6], 1 if r[4] else 0, r[3],
                            r[6] or r[5], None, r[11] or 0, r[12] or 0, r[24] or 0, r[25] or 0])
        out[player] = {"seasons": seasons, "matches": matches, "injury": None}
    for (player, team, league, season, _, minutes, n, _, goals, assists, _, _, _, _,
         _, _, _, _, _, _, _, yellow, yellow_red, red, *_) in other_seasons:
        if player in out:
            out[player]["seasons"].append(
                [season, team, league, n or 0, None, minutes, goals or 0, assists or 0,
                 yellow, (red or 0) + (yellow_red or 0)])
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


def cut_player_page(page):
    """A player's page file as anyone can ask for it when he is outside the free slice: no rank
    going into each match and no rating movement, and "cut": true."""
    at = MATCH_FIELDS.index("rank")
    return {**{k: v for k, v in page.items() if k != "movement"},
            "matches": [[None if i == at else v for i, v in enumerate(m)] for m in page["matches"]], "cut": True}


def export_player_pages(conn, out_dir=OUT_DIR, detail=None, free=None):
    """One small file per listed player for his page: .export/players/<player_id>.json, with his
    stats per season and club, his last PLAYER_MATCHES appearances (with his rank going into each)
    and his injury status for his next fixture ([fixture, type, ban]: no medical reason), plus his
    own rows of the season detail (born, spells, positions) so his page needn't load
    player_seasons.json. Built from the query cache (cache.py), so the
    only database reads are the per-match ranks and injuries for those few rows."""
    from ..pipeline.cache import finished_fixtures
    from ..models.player_ratings import _appearances, _other_seasons
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
            m[11] = _r(ranks.get((m[0], pid)), 1)
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
    # the paid tier: a player outside the free slice (free: export_players) has a whole file stored
    # as a paid row and a cut-down one anyone can ask for, once site_player_page() is there to choose
    paid = free is not None and _paid_rows(conn, "site_player_page")
    paid_dir = out_dir / f"{PAID_PREFIX}players"
    if paid:
        paid_dir.mkdir(parents=True, exist_ok=True)
    for old in paid_dir.glob("*.json") if paid_dir.is_dir() else ():
        if not paid or int(old.stem) not in pages or int(old.stem) in free:
            old.unlink()

    def write(path, page):
        payload = json.dumps(page, separators=(",", ":"), ensure_ascii=False)
        if not path.exists() or path.read_text(encoding="utf-8") != payload:
            path.write_text(payload, encoding="utf-8")
    for pid, page in pages.items():
        teams = ({s[1] for s in page["seasons"]} | {m[4] for m in page["matches"]}
                 | {sp[0] for v in page["spells"].values() for sp in v})
        whole = {"id": pid, "season_fields": SEASON_FIELDS, "match_fields": MATCH_FIELDS, **page,
                 "teams": {str(t): names.get(t) for t in sorted(teams)}}
        if paid and pid not in free:
            write(paid_dir / f"{pid}.json", whole)
            write(player_dir / f"{pid}.json", cut_player_page(whole))
        else:
            write(player_dir / f"{pid}.json", whole)
    log.info("Exported %d player pages", len(pages))

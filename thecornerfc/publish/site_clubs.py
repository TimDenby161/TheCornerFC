"""The club pages, the league pages (tables, fixtures, projections) and the national teams' pages.
"""
import json
import logging
import re
import shutil
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .. import config
from ..models.predictions import UPCOMING_STATUSES
from ..pipeline.cache import WEEK, cached_rows, rank_history
from . import tables as league_tables
from .site_files import OUT_DIR, PAID_PREFIX, _paid_rows, _r

# the export's one log, whichever module writes to it
log = logging.getLogger("thecornerfc.publish.export")


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


def export_nations(conn, out_dir=OUT_DIR):
    """data/nations.json, the national team ranking, and data/nations/, the national team pages
    (nations.py). Not critical: if it fails (no copy of the public results and no download), the
    last published files are kept."""
    from ..models import nations
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


CLUB_ACTIVE_DAYS = 400
# The xG the club pages and league tables show: the site's own estimate from shot counts, for
# every match with them (API-Football's xG goes into the model but isn't published). A
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
    """One small file per active club for its club page: .export/clubs/<team_id>.json.

    history: every match since 2020 as [date, rank after, opponent, home (1, 0 away, 2 neutral), goals for, against,
    competition, formation (null where the line-up isn't known), attack and defence after,
    starting XI average rank by line [GK, DEF, MID, FWD] (null outside the line-up leagues)]; plus
    the current manager and the home kit colours. starts: this season's matches with a
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
    # the site's estimate from shots, for every match with shot counts: {(fixture, team): xG}
    shot_xg = {(f, t): _xg_from_shots(i, o, on, bl) for f, t, i, o, on, bl in cached_rows(conn, "shot_counts", f"""
            select {WEEK.format('f.kickoff')} as part, s.fixture_id, s.team_id, s.shots_inside_box,
                   s.shots_outside_box, s.shots_on_goal, s.blocked_shots
            from fixture_team_stats s join fixtures f using (fixture_id)
            where s.shots_inside_box is not null
              and s.shots_outside_box is not null and s.shots_on_goal is not null""",
            order_by="fixture_id, team_id")}

    def xg_pair(fid, team, opp):
        """(xG for, xG against, estimated: always 1) for the club in this match, from shots."""
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
                     *xg_pair(fid, team, opp)])
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
                   "matches": h["matches"], "coach": coaches.get(team),
                   "colors": colors.get(team), "starts": starts.get(team),
                   "positions": (positions or {}).get(team, {}),
                   "teams": {o: names.get(o) for o in opponents}}
        (club_dir / f"{team}.json").write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    log.info("Exported %d club pages", len(active))


XG_RECENT = 5   # league games behind the tables' xG and xG conceded per 90
FREE_DAYS = 7                # how far ahead the model's chances are free (the owner's line, 2026-10-04)
LEAGUE_FIXTURE_FIELDS = ["id", "kickoff", "round", "home", "away", "status", "hg", "ag", "pen_h", "pen_a",
                         "home_xg", "away_xg", "p_home", "p_draw", "p_away"]


def cut_league_fixtures(fixtures, now):
    """A league's fixtures (LEAGUE_FIXTURE_FIELDS rows) as its free file carries them: no
    projected goals, and the chances only for kick-offs within FREE_DAYS of now."""
    at = LEAGUE_FIXTURE_FIELDS.index
    goals, chances = (at("home_xg"), at("away_xg")), (at("p_home"), at("p_draw"), at("p_away"))
    limit = (now + timedelta(days=FREE_DAYS)).isoformat()
    out = []
    for f in fixtures:
        hide = set(goals) | (set(chances) if f[at("kickoff")] > limit else set())
        out.append([None if i in hide else v for i, v in enumerate(f)])
    return out


def headline_projection(table, fixtures):
    """A league's projected final table as its free file carries it: [[group, place, club,
    matches left, points]], each club's points so far plus the points the model expects from its
    remaining fixtures (3 x its chance of winning + its chance of a draw), level clubs by goal
    difference so far plus projected goals. The full version (wins, draws, losses, and each
    club's chance of finishing in every place) is played out by the page from the paid file.
    table: tables.FIELDS rows; fixtures: LEAGUE_FIXTURE_FIELDS rows, whole."""
    at = LEAGUE_FIXTURE_FIELDS.index
    extra = defaultdict(lambda: [0, 0.0, 0.0])            # club: matches left, expected points, expected goal difference
    for f in fixtures:
        ph, pd, pa, hx, ax = (f[at(k)] for k in ("p_home", "p_draw", "p_away", "home_xg", "away_xg"))
        if ph is None or pd is None or pa is None or hx is None or ax is None:
            continue
        for team, win, diff in ((f[at("home")], ph, hx - ax), (f[at("away")], pa, ax - hx)):
            e = extra[team]
            e[0] += 1
            e[1] += 3 * win + pd
            e[2] += diff
    if not extra:
        return []
    groups = defaultdict(list)
    for row in table:
        r = dict(zip(league_tables.FIELDS, row))
        left, pts, gd = extra.get(r["team"], (0, 0.0, 0.0))
        groups[r["group"]].append((-(r["points"] + pts), -(r["gd"] + gd), r["rank"], r["team"], left))
    return [[group, i + 1, team, left, round(-pts)]
            for group, rows in groups.items() for i, (pts, _, _, team, left) in enumerate(sorted(rows))]


def export_leagues(conn, out_dir=OUT_DIR):
    """One file per competition for its league page: .export/leagues/<league_id>.json.

    The current season's table (every group, worked out from the results: tables.py) and all its fixtures, the
    upcoming ones with the model's projected goals and home / draw / away chances (for the page's
    projected table), and each club's recent xG for and against (for the table): the site's
    estimate from shots (XG_FROM_SHOTS), not API-Football's xG. Loaded only when
    the page opens.
    """
    seasons = {lid: (season, start) for lid, season, start in conn.execute(
        """select distinct on (league_id) league_id, season, start_date from league_seasons
           where is_current order by league_id, season desc""")}
    # API-Football's standings give the groups and what each place leads to; the figures and
    # the order are worked out from the results (tables.py)
    standing, feed = defaultdict(list), defaultdict(list)
    for (lid, group, team, rank, pts, desc, pl, w, d, l, gf, ga) in conn.execute(
            """select league_id, group_name, team_id, rank, points, description,
                      played, win, draw, lose, goals_for, goals_against
               from standings where (league_id, season) in (select league_id, max(season) from league_seasons
                                                             where is_current group by league_id)
               order by league_id, group_name, rank"""):
        standing[lid].append((group, team, rank, desc))
        feed[lid].append((group, team, pl, w, d, l, gf, ga, pts))
    results = defaultdict(list)
    for lid, kickoff, rnd, home, away, hg, ag in conn.execute(
            """select f.league_id, f.kickoff, f.round, f.home_team_id, f.away_team_id,
                      coalesce(f.ft_home, f.home_goals), coalesce(f.ft_away, f.away_goals)
               from fixtures f
               where f.status_short = any(%s) and f.home_goals is not null and f.away_goals is not null
                 and (f.league_id, f.season) in (select league_id, max(season) from league_seasons
                                                 where is_current group by league_id)""",
            [list(config.FINISHED_STATUSES)]):
        results[lid].append((kickoff, rnd, home, away, hg, ag))
    cups = {lid for lid, in conn.execute("select league_id from leagues where type <> 'League'")}
    names = dict(conn.execute("select team_id, name from teams"))
    tables = {}
    for lid, rows in standing.items():
        season = seasons[lid][0] if lid in seasons else None
        tables[lid] = league_tables.league_table(rows, results[lid], league_tables.adjustments(lid, season), names,
                                                 league_tables.ORDER.get(lid), lid in cups)
        differ = league_tables.differences(tables[lid], feed[lid])
        if differ:
            log.warning("League %s: the table from results differs from API-Football's for %d club(s), e.g. %s "
                        "(a deduction or an annulled club goes in table_adjustments.json)", lid, len(differ), differ[0])
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
    # each club's estimated xG and xG conceded per 90 over its last XG_RECENT league games with
    # shot counts for both sides (a match that went to extra time counts as 120 minutes)
    xg_sql = ("greatest(0, %s::float8 * {0}.shots_inside_box + %s::float8 * {0}.shots_outside_box + %s::float8 * {0}.shots_on_goal"
              " + %s::float8 * coalesce({0}.blocked_shots, 0) + %s::float8)")
    counted = "{0}.shots_inside_box is not null and {0}.shots_outside_box is not null and {0}.shots_on_goal is not null"
    recent_xg = defaultdict(dict)
    for lid, team, xg, xga, n in conn.execute(
            f"""with games as (
                 select f.league_id, s.team_id, f.kickoff,
                        {xg_sql.format('s')} * 90 / case when f.status_short in ('AET', 'PEN') then 120 else 90 end as xg,
                        {xg_sql.format('o')} * 90 / case when f.status_short in ('AET', 'PEN') then 120 else 90 end as xga
                 from fixtures f
                 join fixture_team_stats s on s.fixture_id = f.fixture_id
                 join fixture_team_stats o on o.fixture_id = f.fixture_id and o.team_id <> s.team_id
                 where f.status_short = any(%s) and {counted.format('s')} and {counted.format('o')}
                   and (f.league_id, f.season) in (select league_id, max(season) from league_seasons
                                                   where is_current group by league_id)),
               ranked as (select *, row_number() over (partition by league_id, team_id order by kickoff desc) as n
                          from games)
               select league_id, team_id, avg(xg)::float8, avg(xga)::float8, count(*)
               from ranked where n <= %s group by 1, 2""",
            [*XG_FROM_SHOTS, *XG_FROM_SHOTS, list(config.FINISHED_STATUSES), XG_RECENT]):
        recent_xg[lid][team] = [_r(xg), _r(xga), n]
    league_dir = out_dir / "leagues"
    league_dir.mkdir(parents=True, exist_ok=True)
    for old in league_dir.glob("*.json"):
        if int(old.stem) not in seasons:
            old.unlink()
    paid = _paid_rows(conn, "site_league")
    now = datetime.now(timezone.utc)
    paid_dir = out_dir / f"{PAID_PREFIX}leagues"
    if paid:
        paid_dir.mkdir(parents=True, exist_ok=True)
    for old in paid_dir.glob("*.json") if paid_dir.is_dir() else ():
        if not paid or int(old.stem) not in seasons:
            old.unlink()
    for lid, (season, start) in seasons.items():
        table = tables.get(lid, [])
        teams = {r[2] for r in table} | {t for f in fixtures[lid] for t in (f[3], f[4])}
        payload = {"id": lid, "season": season, "start": start.isoformat() if start else None,
                   "table_fields": league_tables.FIELDS,
                   "table": table,
                   "fixture_fields": LEAGUE_FIXTURE_FIELDS,
                   "fixtures": fixtures[lid],
                   "recent_xg_fields": ["xg90", "xga90", "games"],
                   "recent_xg": recent_xg[lid],
                   "teams": {t: names.get(t) for t in teams}}
        if paid:
            # the whole file is the paid row; the one anyone can ask for is cut down
            (paid_dir / f"{lid}.json").write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
            payload = {**payload, "fixtures": cut_league_fixtures(fixtures[lid], now), "cut": True,
                       "projected_fields": ["group", "place", "team", "left", "points"],
                       "projected": headline_projection(table, fixtures[lid])}
        (league_dir / f"{lid}.json").write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    log.info("Exported %d league pages%s", len(seasons), " (cut down, with a paid row each)" if paid else "")

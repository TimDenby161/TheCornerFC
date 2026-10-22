"""Export compact JSON for the website: written to .export/ and sent from there to the database
(site.docs and the site.* tables), which is what the site reads. Nothing is committed.

This module runs the export (export_site_data, _write_site_data) and is the one address the
rest of the code imports from: every name of the site_* modules beside it is passed on below.
The work is in those modules, one per job (guide/architecture.md):

    site_files     nothing unsafe reaches the site: staging, checks, publishing, the paid cut
    site_matches   the match rows, club and national
    site_record    how the models have done: stats, model vs market, line-up record, bets
    site_players   players, their pages and seasons, injuries and bans
    site_clubs     club, league and nation pages
    site_fantasy   the owner-only fantasy data

A site_* module never imports this one, and a test patches a function on the module that owns
it (tests/test_publish_imports.py, tests/test_export_surface.py).
"""
import html
import json
import logging
from datetime import datetime, timedelta, timezone

from ..pipeline.health import monitored
from .. import config
from ..models import national_lineups, national_predictions      # (national_lineups: reached as export.national_lineups)
from ..models.player_ratings import SKILL_MIX
from .site_files import (
    CARRIED_FILES,
    COLLAPSE_RATIO,
    CRITICAL_DETAIL_DIRS,
    CRITICAL_JSON_FILES,
    ExportValidationError,
    MAJOR_ROW_TYPES,
    MANIFEST,
    MIN_MAJOR_ROWS,
    OUT_DIR,
    PAID_PREFIX,
    _check_row_collapse,
    _check_table_collapse,
    _export_shape,
    _paid_rows,
    _paywall_on,
    _publish_export,
    _r,
    _read_json,
    _replace_export,
    _stored_hashes,
    _stored_shape,
    _table_exists,
    _write_json_file,
    mirror_site_docs,
    store_admin_doc,
    store_owner_doc,
    validate_export,
    write_manifest,
)
from .site_matches import (
    FUTURE_DAYS,
    MATCH_PAID_CHANCES,
    MATCH_PAID_DEPTH,
    PAST_DAYS,
    SITE_MATCH_FIELDS,
    _records_sum,
    blanked,
    explanation,
    market_probabilities,
    match_explanations,
    national_match,
    national_matches,
    national_nationalities,
    national_xis,
    site_freshness,
    store_matches,
    worked_example,
)
from .site_record import (
    BET_BANK_GBP,
    BET_STAKE_GBP,
    ENGLISH,
    LINEUP_RECORD_FIELDS,
    STAT_MARKETS,
    STAT_RANGES,
    _lineup_names,
    _market_stats,
    _period,
    _score_xi,
    _stats,
    _versions,
    export_bets,
    export_lineup_history,
    export_lineup_record,
    export_methodology,
    export_model_changes,
    export_stats,
    market_consensus,
    national_stat_rows,
)
from .site_players import (
    BAN_REASONS,
    FREE_LEAGUE,
    FREE_POSITION,
    FREE_WORLD,
    INJURY_LOOKBACK_DAYS,
    INJURY_REASON,
    LISTED,
    MATCH_FIELDS,
    MIN_PLAYERS,
    MOVEMENT_FIELDS,
    ONE_MATCH_REASONS,
    PLAYER_FIELDS,
    PLAYER_MATCHES,
    PLAYER_PAID_FIELDS,
    PLAYER_SEASONS,
    PLAYER_SEASON_FIELDS,
    POSITION_SHARE,
    SEASON_FIELDS,
    SITE_PLAYER_FIELDS,
    SPELL_FIELDS,
    _ENTITIES,
    _ban,
    _club_positions,
    _club_spells,
    _decode,
    _fold,
    _injured,
    _places,
    _player_movement,
    blanked_player,
    build_player_pages,
    cut_player_page,
    export_injuries,
    export_player_pages,
    export_player_seasons,
    export_players,
    site_player_rows,
    store_players,
)
from .site_clubs import (
    CLUB_ACTIVE_DAYS,
    FREE_DAYS,
    HEX_COLOR,
    LEAGUE_FIXTURE_FIELDS,
    NEUTRAL_SQL,
    XG_FROM_SHOTS,
    XG_RECENT,
    _hex_color,
    _kit_colors,
    _xg_from_shots,
    _xi_lines,
    cut_league_fixtures,
    export_clubs,
    export_leagues,
    export_nations,
    headline_projection,
)
from .site_fantasy import (
    FANTASY_RESULTS,
    FPL_POSITIONS,
    PENALTY_CELLS,
    PREDICTION_GWS,
    PUBLISHED_FANTASY_PARAMS,
    _fantasy_progress,
    _fpl_state,
    _round_number,
    export_efl_fantasy,
    export_fantasy,
    export_fantasy_predictions,
    fantasy_prediction_payload,
)

log = logging.getLogger(__name__)
FORM_GAMES = 6       # rank change over this many recent games = "form"


@monitored("exports", conn_index=0)
def export_site_data(conn, out_dir=OUT_DIR):
    """Build, validate and publish the static site export without clobbering old data."""
    _publish_export(lambda staged: _write_site_data(conn, staged), out_dir, conn)
    mirror_site_docs(conn, out_dir)


def _write_site_data(conn, out_dir=OUT_DIR):
    now = datetime.now(timezone.utc)
    out_dir.mkdir(parents=True, exist_ok=True)

    competitions = {
        lid: {"name": name, "country": country, "type": ltype}
        for lid, name, country, ltype in conn.execute(
            "select league_id, name, country, type from leagues")
    }

    market = market_probabilities(conn)
    matches = []
    team_ids = set()
    teams_extra = {}           # national team names (national teams aren't in teams)
    for row in conn.execute(
            """select f.fixture_id, f.kickoff, f.league_id, f.round, f.home_team_id, f.away_team_id,
                      f.status_short, f.home_goals, f.away_goals, f.pen_home, f.pen_away,
                      p.p_home, p.p_draw, p.p_away, p.home_xg, p.away_xg, p.likely_score,
                      p.home_rank, p.away_rank, p.source, p.rating, p.rating_winner,
                      p.rating_margin, p.rating_clean_sheets, p.rating_shape, p.rating_goals,
                      p.home_missing, p.away_missing, p.p_over25, p.p_btts,
                      coalesce(rh.actual_xi_rating, rh.predicted_xi_rating), rh.recent_xi_rating,
                      coalesce(ra.actual_xi_rating, ra.predicted_xi_rating), ra.recent_xi_rating
               from fixtures f left join fixture_predictions p using (fixture_id)
               left join fixture_team_ratings rh on rh.fixture_id = f.fixture_id and rh.team_id = f.home_team_id
               left join fixture_team_ratings ra on ra.fixture_id = f.fixture_id and ra.team_id = f.away_team_id
               where f.kickoff between %s and %s
               order by f.kickoff, f.fixture_id""",
            [now - timedelta(days=PAST_DAYS), now + timedelta(days=FUTURE_DAYS)]):
        (fid, kickoff, lid, rnd, home, away, status, hg, ag, ph, pa_, p_h, p_d, p_a,
         hxg, axg, likely, hr, ar, source, *ratings, h_miss, a_miss, p_over, p_btts,
         h_xi, h_recent, a_xi, a_recent) = row
        team_ids.update((home, away))
        matches.append([
            fid, kickoff.isoformat(), lid, rnd, home, away, status, hg, ag, ph, pa_,
            _r(p_h, 3), _r(p_d, 3), _r(p_a, 3), _r(hxg), _r(axg), likely, _r(hr, 0), _r(ar, 0),
            source, *ratings,
            *[_r(x, 3) for x in market.get(fid, (None, None))[:2]],     # the away share is the rest
            _r(h_miss), _r(a_miss), _r(p_over, 3), _r(p_btts, 3),
            _r(h_xi, 1), _r(h_recent, 1), _r(a_xi, 1), _r(a_recent, 1),
            0,
        ])

    # National team matches (national_fixtures), on the Matches tab only and flagged intl = 1 so
    # the site links them to the nation pages. Their projections are national_predictions.py's:
    # the same fields as a club match's, without the parts national teams have no data for
    # (absences, line-up ratings)
    since, until = now - timedelta(days=PAST_DAYS), now + timedelta(days=FUTURE_DAYS)
    national_why = {}
    national_xi = national_xis(conn, now)
    for row in national_matches(conn, since, until):
        fid, lid, tournament, home, away, h_name, a_name = row[0], row[2], row[3], *row[5:9]
        competitions.setdefault(lid, {"name": tournament or config.NATIONAL_TEAM_LEAGUES.get(lid, f"Competition {lid}"),
                                      "country": "World", "type": "International"})
        teams_extra[home], teams_extra[away] = html.unescape(h_name), html.unescape(a_name)
        match, why = national_match(row, market.get(fid))
        matches.append(match)
        if why:
            # each side's predicted XI, for the card's line-ups (national_lineups.py)
            xi = {str(t): national_xi[fid, t] for t in (home, away) if (fid, t) in national_xi}
            national_why[str(fid)] = {**why, "xi": xi} if xi else why
    # and the national team competitions with a projected match in the Stats tab's longest range,
    # so its menu can name the ones no longer on the Matches tab
    if _table_exists(conn, "national_fixtures") and _table_exists(conn, national_predictions.TABLE):
        for lid, tournament in conn.execute(
                f"""select distinct on (f.league_id) f.league_id, f.tournament
                    from national_fixtures f join {national_predictions.TABLE} p using (fixture_id)
                    where f.kickoff >= %s order by f.league_id, f.kickoff desc""",
                [now - timedelta(days=max(STAT_RANGES.values()))]):
            competitions.setdefault(lid, {"name": tournament or config.NATIONAL_TEAM_LEAGUES.get(lid, f"Competition {lid}"),
                                          "country": "World", "type": "International"})
    matches.sort(key=lambda m: (m[1], m[0]))
    nation_pages = {t: nat for t, nat in national_nationalities(conn, list(teams_extra)).items()
                    if nat != teams_extra[t]}

    # Form: total rank change over each team's last FORM_GAMES games
    form = dict(conn.execute(
        """select team_id, sum(rank_change) from (
             select team_id, rank_change,
                    row_number() over (partition by team_id order by match_no desc) rn
             from team_rank_history) x
           where rn <= %s group by team_id""", [FORM_GAMES]).fetchall())

    # League each club is playing in this season (league fixtures in a current season); null for
    # clubs relegated out of every tracked league or only seen in cups
    current_league = dict(conn.execute(
        """select distinct on (team_id) team_id, league_id from (
             select f.home_team_id team_id, f.league_id, f.kickoff from fixtures f
               join leagues l using (league_id) join league_seasons ls using (league_id, season)
               where l.type = 'League' and ls.is_current
             union all
             select f.away_team_id, f.league_id, f.kickoff from fixtures f
               join leagues l using (league_id) join league_seasons ls using (league_id, season)
               where l.type = 'League' and ls.is_current) x
           order by team_id, kickoff desc""").fetchall())

    rankings = []
    for team, lid, cur, st, lt, played, att, dfn, home_r, away_r in conn.execute(
            """select team_id, league_id, current_rank, st_algo, lt_algo, played,
                      attack, defence, home_rating, away_rating
               from team_rankings order by lt_algo desc"""):
        team_ids.add(team)
        rankings.append([team, current_league.get(team, lid), _r(cur, 1), _r(st, 1), _r(lt, 1),
                         played, _r(form.get(team), 1),
                         1 if team in current_league else 0,
                         _r(att, 1), _r(dfn, 1), _r(home_r, 1), _r(away_r, 1)])

    teams = {t: n for t, n in conn.execute(
        "select team_id, name from teams where team_id = any(%s)", [list(team_ids)])}
    for team, name in teams_extra.items():
        teams.setdefault(team, name)

    generated = now.isoformat()
    # site.json: what every page needs whatever it shows (the competitions, the clubs' names, when
    # the data was made). It is one of the two files loaded on every visit (rankings.json is the
    # other); the matches are rows of site.matches, asked for by the views that show them.
    site = {
        "generated_at": generated,
        "freshness": site_freshness(conn),
        "competitions": competitions,
        "teams": teams,
        "nation_pages": nation_pages,
        "match_fields": SITE_MATCH_FIELDS,      # the order of a match's row, as site_matches() returns them
        # each outfield position's mix of skills (player_ratings.SKILL_MIX, MC-0030), for the Skills
        # part of a player's page: the model's own table, so the page can't drift from it
        "skill_mix": SKILL_MIX,
    }
    (out_dir / "rankings.json").write_text(json.dumps({
        "generated_at": generated,
        "fields": ["team", "league", "current", "st", "lt", "played",
                   "form", "in_league", "attack", "defence", "home", "away"],
        "rankings": rankings,
    }, separators=(",", ":")), encoding="utf-8")
    log.info("Exported %d matches and %d rankings to %s", len(matches), len(rankings), out_dir)
    export_stats(conn, out_dir)
    export_bets(conn, out_dir)
    explained = {**match_explanations(conn, now), **national_why}
    store_matches(conn, matches, explained)
    export_methodology(conn, out_dir, now)
    export_model_changes(conn, out_dir, now, example=worked_example(matches, explained, teams, competitions))
    player_team, listed = export_players(conn, out_dir, rankings)
    export_injuries(conn, out_dir, listed["free"])
    # the players are rows of site.players: the site asks for the ones a view shows, and needs the
    # order of a row, the seasons and the names of their clubs outside the rankings
    site.update(player_fields=SITE_PLAYER_FIELDS, player_season_fields=PLAYER_SEASON_FIELDS,
                player_seasons=PLAYER_SEASONS, player_future_seasons=listed["future_seasons"])
    for team, name in listed["teams"].items():
        site["teams"].setdefault(team, name)
    (out_dir / "site.json").write_text(json.dumps(site, separators=(",", ":")), encoding="utf-8")
    detail = export_player_seasons(conn, out_dir)
    export_clubs(conn, out_dir, _club_positions(player_team, detail["positions"]))
    export_leagues(conn, out_dir)
    export_player_pages(conn, out_dir, detail, listed["free"])
    export_fantasy(conn, out_dir)
    export_fantasy_predictions(conn)
    export_efl_fantasy(conn, out_dir)
    export_nations(conn, out_dir)

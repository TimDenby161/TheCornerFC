"""Predicted starting XIs for national team matches (owner, 2026-10-07).

The club predictor's selection (player_ratings._select_lineup) on a national team's own matches:
each slot of the team's most used formation over its last PREDICT_MATCHES matches goes to the
player with the most minutes in them x his fit to that role, from the roles he has started in
for the national team. Without a usable formation, the keeper and the ten outfielders with the
most minutes.

Left out, because nothing is known of them before the team sheet: who has been called up, and
who is injured or suspended. No player ranks either (not every international is in players).
So expect it to name fewer starters than a club's predicted XI does.

Replayed in kickoff order over national_fixtures (senior sides) from the stored line-ups and
stat lines (national_fixture_lineups, national_fixture_players, national_fixture_formations),
so each XI is from what was known before that match. The XI for a match that hasn't kicked off
is captured in lineup_prediction_snapshots under a line-up model version of its own, as a
club's is (lineup_snapshots.py), and scored on the Line-up record tab against the official XI
(ingest.sync_national_lineups records it). The site's match detail carries it too
(export.national_match). Nothing is stored for finished matches.
"""
import logging
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone

from ..evidence import lineup_snapshots
from ..evidence.model_versions import ModelType, current_code_sha, register_model_version, source_digests, snapshot_times
from .player_ratings import PREDICT_MATCHES, _select_lineup, likely_formation, line_of
from .positions import FALLBACK

log = logging.getLogger(__name__)

FULL_MATCH = 90      # minutes counted for a starter with no stat line
TABLES = ("national_fixtures", "national_fixture_lineups", "national_fixture_players", "national_fixture_formations")


def ready(conn):
    return all(conn.execute("select to_regclass(%s)", [f"public.{t}"]).fetchone()[0] is not None for t in TABLES)


def predict(recent, shapes, roles, broad):
    """(formation, {player: recent minutes}, [(player, role)]) for a team going into a match.
    recent: its last matches' {player: minutes}; shapes: their formations; roles: {player:
    Counter of the roles he has started in}; broad: {player: his API position, G/D/M/F}."""
    minutes = Counter()
    for played in recent:
        minutes.update(played)
    shape = likely_formation(list(shapes))

    def usual(p):
        """His most common starting role, else the one his API position stands for."""
        started = +roles[p]
        return started.most_common(1)[0][0] if started else FALLBACK.get(broad.get(p)) or "CM"
    # no stat score for an international: every candidate is scored alike, so minutes x fit decides
    _, _, xi = _select_lineup(minutes, set(), lambda p, _: (0.0, usual(p), minutes[p]), None, shape,
                              lambda p: roles[p])
    return shape, minutes, [(p, slot or usual(p)) for p, _, _, _, slot in xi]


def replay(conn, now=None):
    """({(fixture, team): match}, {player: name}) for each senior national team match that hasn't
    kicked off and whose team has a recent match with a line-up. match: kickoff, league, opponent,
    home, formation, minutes ({player: recent minutes}) and xi ([(player, role)])."""
    now = now or datetime.now(timezone.utc)
    fixtures = conn.execute(
        r"""select nf.fixture_id, nf.kickoff, nf.league_id, nf.home_team_id, nf.away_team_id,
                   nf.status_short in ('NS', 'TBD')
            from national_fixtures nf
            where (nf.status_short in ('FT', 'AET', 'PEN') or (nf.status_short in ('NS', 'TBD') and nf.kickoff > %s))
              and nf.kickoff is not null
              and nf.home_name !~ ' U\d{2}$' and nf.away_name !~ ' U\d{2}$'
              and not exists (select 1 from teams t where t.team_id in (nf.home_team_id, nf.away_team_id)
                                                     and t.national is false)
            order by nf.kickoff, nf.fixture_id""", [now]).fetchall()
    played = defaultdict(dict)       # (fixture, team) -> {player: minutes}
    started = defaultdict(dict)      # (fixture, team) -> {player: role}
    broad, names = {}, {}
    for fid, team, player, role, name in conn.execute(
            "select fixture_id, team_id, player_id, role, player_name from national_fixture_lineups"):
        started[fid, team][player] = role
        played[fid, team][player] = FULL_MATCH
        if name:
            names[player] = name
    for fid, team, player, minutes, position, name in conn.execute(
            "select fixture_id, team_id, player_id, minutes, position, player_name from national_fixture_players"):
        if minutes:
            played[fid, team][player] = minutes
        elif player not in started[fid, team]:
            played[fid, team].pop(player, None)
        if position:
            broad[player] = position
        if name:
            names[player] = name
    formations = {(fid, team): shape for fid, team, shape in conn.execute(
        "select fixture_id, team_id, formation from national_fixture_formations where formation is not null")}

    recent = defaultdict(lambda: deque(maxlen=PREDICT_MATCHES))
    shapes = defaultdict(lambda: deque(maxlen=PREDICT_MATCHES))
    roles = defaultdict(Counter)
    out = {}
    for fid, kickoff, league, home, away, upcoming in fixtures:
        for team, opponent in ((home, away), (away, home)):
            if upcoming:
                if recent[team]:
                    shape, minutes, xi = predict(recent[team], shapes[team], roles, broad)
                    out[fid, team] = {"kickoff": kickoff, "league": league, "opponent": opponent, "home": team == home,
                                      "formation": shape, "minutes": dict(minutes), "xi": xi}
                continue
            if played.get((fid, team)):
                recent[team].append(played[fid, team])
            if (fid, team) in formations:
                shapes[team].append(formations[fid, team])
            for player, role in started.get((fid, team), {}).items():
                if role:
                    roles[player][role] += 1
    return out, names


def register_version(conn):
    return register_model_version(conn, ModelType.LINEUP, "national-recent-minutes-lineup",
        code_sha=current_code_sha(), configuration={
            "recent_matches": PREDICT_MATCHES, "keepers": 1, "outfield": 10, "full_match_minutes": FULL_MATCH,
            "slot_rule": "most-used-recent-formation, greedy minutes x role fit; minutes-only fallback",
            "availability_rule": "none: squad and absences unknown before the team sheet",
            "source_digests": source_digests(("national_lineups.py", "player_ratings.py", "positions.py", "lineup_snapshots.py"))},
        notes="National team XI by recent national-team minutes x role fit. No squad list, absences or start probability.")


def capture(conn, predicted, now=None):
    """One lineup_prediction_snapshots row per team with an XI, in the shape a club's has
    (lineup_snapshots.capture_predictions): an unchanged XI isn't stored twice."""
    if not predicted:
        return 0
    version = register_version(conn)
    captured = now or datetime.now(timezone.utc)
    for (fid, team), m in sorted(predicted.items()):
        picked = {p for p, _ in m["xi"]}
        lineup_snapshots.append(conn, "lineup_prediction_snapshots", dict(
            fixture_id=fid, team_id=team, model_version_id=version,
            source="prospective" if captured < m["kickoff"] else "late_observation",
            **snapshot_times(captured_at=captured, effective_at=m["kickoff"]),
            seconds_to_kickoff=(m["kickoff"] - captured).total_seconds(),
            players=[{"player": p, "predicted_starter": True, "role": role, "line": line_of(role),
                      "player_rating": None, "availability_state": "not_reported", "start_probability": None}
                     for p, role in m["xi"]],
            selection_inputs={"formation": m["formation"], "recent_minutes": sorted(m["minutes"].items()),
                              "slots": [{"player": p, "role": role} for p, role in m["xi"]],
                              "unpicked": sorted(set(m["minutes"]) - picked)},
            availability={}))
    return len(predicted)


def update_safely(conn):
    """Predict and capture the upcoming matches' XIs; a failure is logged and rolled back instead
    of failing the run, as national_predictions.update_safely does. Returns the number captured."""
    try:
        if not ready(conn):
            log.warning("National line-ups skipped: the national line-up tables don't exist yet")
            return 0
        predicted, _ = replay(conn)
        n = capture(conn, predicted)
        conn.commit()
        log.info("National line-ups: %d predicted XIs captured", n)
        return n
    except Exception:
        conn.rollback()
        log.exception("National line-ups failed (the run continues)")
        return 0

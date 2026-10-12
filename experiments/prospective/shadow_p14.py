"""P14: the formula candidates for the match predictions, tracked on prospective snapshots against
production, against the bookmakers' prices, and as shadow bets (PROTOCOLS.md).

    combined     movers, then the shot formula, then the calibration (the primary)
    formula      P13's shot formula alone
    calibration  the goal total following recent scoring (development chose no margin curve)
    movers       a club changing division moved towards it, a new club moving faster
    gb           P13's boosted-tree correction: the ceiling the formulas are judged against

Each is applied to the projected goals of a fixture's latest prospective snapshot before
kickoff. Three questions are asked of each, on the same fixtures as production:

    accuracy   its probabilities against the snapshot's own stored ones
    market     both against the bookmakers' margin-free prices as they stood when the snapshot
               was made
    bets       the bets the paper rule would have placed from its chances at Bet365's price at
               that moment, settled on the 90-minute score, with their closing-line value

Nothing here is read by production and no bet is recorded anywhere: the candidates and their
bets are worked out afterwards, offline, from the database as it stands.

Blinded by default. With no option it asks the database how many fixtures have accrued and
prints that. --unblind refuses until the registered target is reached and P6 has been read;
--interim overrides that and labels the output a protocol deviation that cannot support a
decision.

    python experiments/prospective/shadow_p14.py                # accrual only; runs in .venv
    python experiments/prospective/shadow_p14.py --reestimate   # once, at 500: SD only
    python experiments/prospective/shadow_p14.py --unblind      # once, at the target

Read-only: one READ ONLY / REPEATABLE READ transaction, no API calls. --reestimate and --unblind
read every finished fixture once and need numpy, scipy and scikit-learn at the versions in
requirements-p13.txt; run them against production (read-only), not staging.
"""
import argparse
import importlib.util
import json
import math
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
EXPERIMENTS = ROOT / "experiments"
FRAME, ARCH = EXPERIMENTS / "research_frame", EXPERIMENTS / "architectures"
RATING, GOALS, CALIBRATION = (EXPERIMENTS / n for n in ("rating_dynamics", "goals_home_scores", "relearned_calibration"))

# Registered in PROTOCOLS.md; change only by a dated amendment there.
START = "2026-10-14"                 # first kickoff day (UTC) that counts
TARGET = 6200
REESTIMATE_AT = 500
THRESHOLD = 0.002                    # the improvement in accuracy a proposal needs
PLANNING_EFFECT = 0.0028             # four fifths of combined's selection-window gain
PRIMARY = "combined"
CANDIDATES = ("combined", "formula", "calibration", "movers", "gb")
TOLERANCE = 1e-8
SEED, DRAWS, MIN_WEEKS = 20260927, 2000, 8
EUROPE = (2, 3, 848)
STATUSES = ("FT", "AET", "PEN")      # a tie level at 90 minutes is a draw, as a bet on it settles

# The paper rule as thecornerfc/models/betting.py stood at registration, copied so that a later
# change to the live rule does not change what is tracked here.
MIN_EDGE, MAX_ODDS, BOOKMAKER = 0.10, 10.0, 8
MARKETS = {      # market -> (market id, selections, index of the "over" / "yes" chance)
    "1X2": (1, ("Home", "Draw", "Away"), None),
    "OU15": (5, ("Over 1.5", "Under 1.5"), 0), "OU25": (5, ("Over 2.5", "Under 2.5"), 1),
    "OU35": (5, ("Over 3.5", "Under 3.5"), 2), "OU45": (5, ("Over 4.5", "Under 4.5"), 3),
    "BTTS": (8, ("Yes", "No"), 4),
}
GROUP = {"1X2": "1X2", "OU15": "OU", "OU25": "OU", "OU35": "OU", "OU45": "OU", "BTTS": "BTTS"}
SELECTIONS = sorted({s for _, sels, _ in MARKETS.values() for s in sels})

# The candidates are these files as they were at registration. A changed file is a different
# candidate, so the evaluator stops.
PINNED = {
    HERE / "shadow_p13.py": "0d54e221ca3fd922bc1357fbef104eca4e65a01b8a334acf0218aab3ef37fff8",
    FRAME / "frame.py": "dd5a3e1e2973f0574234e8d120b1a9c99187bb1b999a11eaca250fd698671fba",
    FRAME / "features.py": "3d850304212cd88146df88b3497e8d491e8c9bb507bdc4af1e90354904bb6ab6",
    FRAME / "extract.py": "b35e7ac5513def5cf8f3bd3da085cd899064243df952332a4fb42164bbd96169",
    ARCH / "run.py": "6d971182346bcace45b0d3504daf35fac089e26f60bef5da54255c192b9342da",
    ARCH / "chosen.json": "7b6a4b0fc51b78c3cbddc4aa620b417fb88e278170b65b29236dfe9dbd259502",
    RATING / "run.py": "b06d25bf6f32a54aa1ab09cb3fa3021d189973f9bb84f033b94366db0671c8b7",
    RATING / "chosen.json": "83bac50319f1289218105488296c45f75380d646938ca7009c90e6d59d6d0112",
    GOALS / "run.py": "002490ff967636765db2fda0982d47911cfdab43583d82414d62c571d05d5e68",
    GOALS / "chosen.json": "7845718dd6d1deb1a3dde24d404477f7f3368565b34d9907069d3d49ebc18b98",
    CALIBRATION / "run.py": "987c8208f41f67c3d01793337c39e0913a0db8813424a1031e61568d1d1255f9",
    CALIBRATION / "chosen.json": "f3598cc1a343ace9881f14a6b1f607339b00654f886a5032f9b8557a1183a1ee",
}

_spec = importlib.util.spec_from_file_location("shadow_p13", HERE / "shadow_p13.py")
p13 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p13)

_FINISHED = "f.status_short in ('FT', 'AET', 'PEN') and f.ft_home is not null and f.ft_away is not null"
ACCRUAL_SQL = f"""
    select count(*), count(distinct to_char(f.kickoff at time zone 'UTC', 'IYYY-IW')),
           count(*) filter (where exists (select 1 from odds_observations o
                                          where o.fixture_id = f.fixture_id and o.market_id = 1
                                            and o.captured_at < f.kickoff))
    from fixtures f
    where {_FINISHED} and f.kickoff >= %(start)s
      and exists (select 1 from match_prediction_snapshots s
                  where s.fixture_id = f.fixture_id and s.source = 'prospective'
                    and s.captured_at < f.kickoff and s.created_at < f.kickoff)"""
SNAPSHOT_SQL = f"""
    select s.fixture_id, s.captured_at, s.created_at, s.home_xg, s.away_xg, s.exp_diff, s.p_home,
           s.p_draw, s.p_away, s.p_over25, s.p_btts, s.model_version_id,
           (s.inputs->>'home_match_rank')::float8, (s.inputs->>'away_match_rank')::float8,
           (s.inputs->>'home_missing')::float8, (s.inputs->>'away_missing')::float8
    from match_prediction_snapshots s join fixtures f using (fixture_id)
    where s.source = 'prospective' and {_FINISHED} and f.kickoff >= %(start)s
      and s.captured_at < f.kickoff and s.created_at < f.kickoff"""
# Every bookmaker's latest price for each selection at a cutoff, reduced in the database to one
# row per fixture and selection: the margin-free chance averaged over the bookmakers with a
# complete market, and Bet365's price. {cutoff} is one of the two fixed expressions in CUTOFFS.
PRICES_SQL = f"""
    with snap as (
        select distinct on (s.fixture_id) s.fixture_id, greatest(s.captured_at, s.created_at) as made, f.kickoff
        from match_prediction_snapshots s join fixtures f using (fixture_id)
        where s.source = 'prospective' and {_FINISHED} and f.kickoff >= %(start)s
          and s.captured_at < f.kickoff and s.created_at < f.kickoff
        order by s.fixture_id, greatest(s.captured_at, s.created_at) desc, s.snapshot_id desc),
    quote as (
        select distinct on (o.fixture_id, o.bookmaker_id, o.market_id, o.selection)
               o.fixture_id, o.bookmaker_id, o.market_id, o.selection, o.odds::float8 as odd,
               case when o.market_id = 5 then split_part(o.selection, ' ', 2) else '' end as line
        from odds_observations o join snap using (fixture_id)
        where o.market_id in (1, 5, 8) and o.selection = any(%(selections)s) and {{cutoff}}
        order by o.fixture_id, o.bookmaker_id, o.market_id, o.selection, o.captured_at desc, o.observation_id desc),
    book as (
        select fixture_id, bookmaker_id, market_id, line, sum(1 / odd) as total,
               count(*) = case when market_id = 1 then 3 else 2 end as complete
        from quote group by 1, 2, 3, 4)
    select q.fixture_id, q.market_id, q.selection,
           avg((1 / q.odd) / b.total) filter (where b.complete) as fair,
           count(*) filter (where b.complete) as books,
           max(q.odd) filter (where q.bookmaker_id = %(bookmaker)s) as taken,
           max(snap.made) as made
    from quote q join book b using (fixture_id, bookmaker_id, market_id, line) join snap using (fixture_id)
    group by 1, 2, 3"""
CUTOFFS = {"decision": "greatest(o.captured_at, o.created_at) <= snap.made",
           "closing": "greatest(o.captured_at, o.created_at) < snap.kickoff"}
FETCHED_SQL = p13.FETCHED_SQL
SKIP_QUERIES = p13.SKIP_QUERIES


def check_pins():
    wrong = [str(p.relative_to(ROOT)) for p, want in PINNED.items() if p13.digest(p) != want]
    if wrong:
        raise SystemExit("P14's candidate files have changed since registration: " + ", ".join(wrong))


def fixtures_required(sd, effect=PLANNING_EFFECT):
    return max(REESTIMATE_AT, math.ceil(((1.959964 + 0.841621) * sd / effect) ** 2))


# ---- the shadow bets (plain Python: no database, no numpy) ------------------------------------

def pick_score(model_prob, fair_prob, odd):
    """betting.pick_score: the return if the truth is halfway between the model and the market."""
    p = model_prob if fair_prob is None else (model_prob + fair_prob) / 2
    return p * odd - 1


def won(market, selection, home_goals, away_goals):
    if market == "1X2":
        return {"Home": home_goals > away_goals, "Draw": home_goals == away_goals, "Away": home_goals < away_goals}[selection]
    if market.startswith("OU"):
        return (home_goals + away_goals > int(market[2:]) / 10) == selection.startswith("Over")
    return (home_goals > 0 and away_goals > 0) == (selection == "Yes")


def chances(result, goal):
    """{market: chance of each selection} from (home, draw, away) and the five goal-market
    chances in frame.GOAL_MARKETS order (over 1.5, 2.5, 3.5, 4.5, both to score)."""
    out = {"1X2": tuple(result)}
    for market, (_, _, column) in MARKETS.items():
        if column is not None:
            out[market] = (goal[column], 1 - goal[column])
    return out


def shadow_bets(model, prices, closing, home_goals, away_goals):
    """The paper rule on one fixture: every selection whose chance times Bet365's price is at
    least 1 + MIN_EDGE (prices above MAX_ODDS left out), then one bet of each kind, the best by
    pick_score. prices / closing are {(market id, selection): {"fair", "taken"}}."""
    best = {}
    for market, (market_id, selections, _) in MARKETS.items():
        for selection, chance in zip(selections, model[market]):
            quote = prices.get((market_id, selection))
            if not quote or quote.get("taken") is None:
                continue
            odd, fair = quote["taken"], quote.get("fair")
            if chance * odd - 1 < MIN_EDGE or odd > MAX_ODDS:
                continue
            score = pick_score(chance, fair, odd)
            if GROUP[market] not in best or score > best[GROUP[market]][0]:
                best[GROUP[market]] = (score, market, market_id, selection, chance, fair, odd)
    bets = []
    for _, market, market_id, selection, chance, fair, odd in best.values():
        hit = won(market, selection, home_goals, away_goals)
        close = (closing.get((market_id, selection)) or {}).get("fair")
        fairs = [prices[(market_id, s)]["fair"] for s in MARKETS[market][1]
                 if (market_id, s) in prices and prices[(market_id, s)].get("fair") is not None]
        bets.append({"market": market, "group": GROUP[market], "selection": selection, "chance": chance,
                     "fair": fair, "odds": odd, "won": hit, "profit": odd - 1 if hit else -1.0,
                     "clv": odd * close - 1 if close is not None else None,
                     "outsider": bool(fair is not None and fairs and fair < max(fairs))})
    return bets


def price_table(rows):
    """{fixture: {(market id, selection): {"fair", "books", "taken", "made"}}} from PRICES_SQL rows."""
    out = defaultdict(dict)
    for fixture, market_id, selection, fair, books, taken, made in rows:
        out[fixture][(market_id, selection)] = {"fair": fair, "books": books, "taken": taken, "made": made}
    return out


# ---- the database ----------------------------------------------------------------------------

def accrual():
    with p13.connect() as conn:
        said = p13.environment(conn)
        n, weeks, priced = conn.execute(ACCRUAL_SQL, {"start": START}).fetchone()
    return {"database_says": said, "accrued_upper_bound": n, "weeks": weeks, "with_a_result_price_before_kickoff": priced,
            "target": TARGET, "p6_has_been_read": (HERE / "results_P6.json").exists(),
            "note": "finished fixtures (90-minute score) from the start day with a prospective snapshot before "
                    "kickoff; the few whose snapshot today's probability step does not reproduce are taken out at analysis"}


def extract():
    """Everything the candidates need, read once: the research frame's own queries with the cut
    moved to tomorrow, the prospective snapshots, the prices at each snapshot and at the close,
    and when each recent fixture's statistics were last fetched."""
    frame_extract = p13.load("p14_frame_extract", FRAME / "extract.py")
    cut = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
    doc = {"cut": cut}
    with p13.connect() as conn:
        doc["database_says"] = p13.environment(conn)
        doc["database_role"] = conn.execute("select current_user").fetchone()[0]
        for name, sql in frame_extract.QUERIES.items():
            if name in SKIP_QUERIES:
                continue
            cur = conn.execute(sql, {"cut": cut})
            doc[name] = {"columns": [d.name for d in cur.description],
                         "rows": [[frame_extract.plain(v) for v in row] for row in cur.fetchall()]}
        keys = ("fixture_id", "captured_at", "created_at", "home_xg", "away_xg", "exp_diff", "p_home", "p_draw",
                "p_away", "p_over25", "p_btts", "model_version_id", "home_match_rank", "away_match_rank",
                "home_missing", "away_missing")
        doc["snapshots"] = [dict(zip(keys, (frame_extract.plain(v) for v in row)))
                            for row in conn.execute(SNAPSHOT_SQL, {"start": START})]
        for name, cutoff in CUTOFFS.items():
            doc[f"prices_{name}"] = [[frame_extract.plain(v) for v in row] for row in conn.execute(
                PRICES_SQL.format(cutoff=cutoff), {"start": START, "selections": SELECTIONS, "bookmaker": BOOKMAKER})]
        doc["fetched"] = {str(f): frame_extract.plain(t) for f, t in conn.execute(FETCHED_SQL, {"from": "2026-07-01"})}
    doc["extracted_at"] = datetime.now(timezone.utc).isoformat()
    return doc


# ---- the candidates --------------------------------------------------------------------------

def build(doc, start=START):
    """Per accrued fixture: production's stored probabilities and each candidate's, the prices,
    and what the analysis needs beside them. Returns (rows, exclusions)."""
    import numpy as np
    frame = p13.load("frame", FRAME / "frame.py")
    sys.modules["frame"] = frame
    features = p13.load("features", FRAME / "features.py")
    sys.modules["features"] = features
    arch = p13.load("p14_architectures", ARCH / "run.py")
    rating = p13.load("p14_rating_dynamics", RATING / "run.py")
    goals = p13.load("p14_goals_home_scores", GOALS / "run.py")
    calibration = p13.load("p14_relearned_calibration", CALIBRATION / "run.py")
    frame.FINAL_END = "9999-12-31"            # the frame stops scoring at its own cut; P14 goes on
    chosen = json.loads((ARCH / "chosen.json").read_text())
    registered = json.loads((CALIBRATION / "chosen.json").read_text())
    movers, level = registered["registered_settings"]["movers"], registered["registered_settings"]["goal_level"]
    curve = registered["curve"]["setting"]

    kick = {r[0]: r[1] for r in doc["fixtures"]["rows"]}
    picked = p13.latest_before_kickoff(doc["snapshots"], {f: k for f, k in kick.items() if k[:10] >= start})
    # the stored projection of an accrued fixture is its chosen snapshot, nothing later
    columns = doc["predictions"]["columns"]
    rows = [r for r in doc["predictions"]["rows"] if r[0] not in picked and kick.get(r[0], "")[:10] < start]
    for fid, s in picked.items():
        value = {"fixture_id": fid, "home_rank": s["home_match_rank"], "away_rank": s["away_match_rank"],
                 "source": "live", **{k: s[k] for k in ("exp_diff", "home_xg", "away_xg", "p_home", "p_draw", "p_away",
                                                        "p_over25", "p_btts", "home_missing", "away_missing")}}
        rows.append([value[c] for c in columns])
    data = frame.Data({**doc, "predictions": {"columns": columns, "rows": rows}})

    rep, hx, ax, _ = arch.baseline(data)
    regulation = np.isin(data.status, STATUSES) & ~np.isnan(data.ft_home) & ~np.isnan(data.ft_away)
    index = np.array([data.index[f] for f in picked if f in data.index and regulation[data.index[f]]], dtype=int)
    index.sort()
    for i in index:                            # the snapshot's own goals, not a re-projection
        s = picked[int(data.fixture_id[i])]
        hx[i], ax[i] = s["home_xg"], s["away_xg"]
    stored = np.array([[picked[int(f)][k] for k in ("p_home", "p_draw", "p_away")] for f in data.fixture_id[index]])
    stored = stored.reshape(len(index), 3)
    again = frame.outcome_probabilities(hx[index], ax[index]) if len(index) else stored
    same = np.abs(again - stored).max(axis=1) <= TOLERANCE if len(index) else np.zeros(0, dtype=bool)
    excluded = {"not_reproduced_by_the_registered_probability_step": int((~same).sum()),
                "no_snapshot_before_kickoff_or_no_90_minute_score": int(
                    sum(1 for f, k in kick.items() if k[:10] >= start) - len(index))}
    index, stored = index[same], stored[same]
    if not len(index):
        return None, excluded

    latest = max(str(v) for v in data.day[index])
    last_day = (date.fromisoformat(latest) + timedelta(days=1)).isoformat()
    usable = data.scored & ~np.isnan(hx)
    blocks = p13.blocks_until(latest)
    feats = features.build(data, rep, hx, ax)
    rank_shift = calibration.movers_shift(data, rep, rating, movers)
    projected, detail = calibration.candidates(data, feats, hx, ax, rank_shift, usable, blocks, last_day,
                                               curve, level, goals)
    lam, mu = arch.DC(data, **chosen["dc"]["setting"]).run(frame.BURN_IN_END, last_day, verbose=False)
    feats["dc_margin"], feats["dc_total"] = lam - mu - (hx - ax), lam + mu - (hx + ax)
    dm, dt = arch.gb_fit_predict(data, feats, chosen["gb"]["features"], hx, ax, blocks, last_day,
                                 chosen["gb"]["params"], usable)
    projected["gb"] = arch.gb_apply(hx, ax, dm, dt, chosen["gb"]["shrink"])
    projected["production"] = (hx, ax)

    # operational subset: both sides' latest earlier match had its statistics in before the snapshot
    last_match, before = {}, {}
    for i in range(data.n):
        for t in (data.home[i], data.away[i]):
            before[(i, t)] = last_match.get(t)
            last_match[t] = i
    fetched = doc.get("fetched", {})

    def in_time(i):
        made = p13.created(picked[int(data.fixture_id[i])])
        for t in (data.home[i], data.away[i]):
            j = before.get((i, t))
            if j is None or np.isnan(data.home_shots[j]):
                continue                        # no earlier match, or one with no statistics to wait for
            at = fetched.get(str(int(data.fixture_id[j])))
            if at is None and data.day[j] < "2026-07-01":
                continue                        # fetched long before; not in the recent list
            if at is None or p13.stamp(at) > made:
                return False
        return True

    # prices count only when the database's choice of snapshot is the one scored here
    decision, closing = price_table(doc.get("prices_decision", [])), price_table(doc.get("prices_closing", []))
    prices, mismatched = [], 0
    for i in index:
        fid = int(data.fixture_id[i])
        table = decision.get(fid, {})
        made = {p13.stamp(q["made"]) for q in table.values()}
        if made and made != {p13.created(picked[fid])}:
            mismatched += 1
            table = {}
        prices.append(table)
    excluded["prices_left_out_for_a_different_snapshot"] = mismatched

    names = ("production",) + CANDIDATES
    out = {
        "frame": frame, "fixture": data.fixture_id[index], "y": data.result[index], "week": data.week[index],
        "day": data.day[index], "league": data.league[index], "is_league": data.is_league[index],
        "ft_only": data.status[index] == "FT", "home_goals": data.ft_home[index], "away_goals": data.ft_away[index],
        "models": {"production": stored, **{n: frame.outcome_probabilities(projected[n][0][index], projected[n][1][index])
                                           for n in CANDIDATES}},
        "goal_chances": {n: frame.goal_markets(projected[n][0][index], projected[n][1][index]) for n in names},
        "goal_events": frame.goal_events(data, index),
        "operational": np.array([in_time(i) for i in index]),
        "prices": prices, "closing": [closing.get(int(f), {}) for f in data.fixture_id[index]],
        "retrained_on": blocks,
        "formula_coefficients": {k: dict(zip([n for n, _, _ in calibration.FORMULA_PAIRS] + ["constant"], v))
                                 for k, v in detail["formula"].items()},
        "margin_moved_sd": {n: float(((projected[n][0] - projected[n][1]) - (hx - ax))[index].std()) for n in CANDIDATES},
    }
    return out, excluded


# ---- the analysis (only ever reached through --unblind or --reestimate) -----------------------

def accuracy(rows):
    import numpy as np
    frame, y, weeks = rows["frame"], rows["y"], rows["week"]
    base = rows["models"]["production"]
    europe, ft = np.isin(rows["league"], EUROPE), rows["ft_only"]
    base_goal = frame.binary_log_loss(rows["goal_chances"]["production"], rows["goal_events"])
    out = {"production": {**frame.summary(base, y), "ends_gap": p13.ends_gap(base, y)}, "candidates": {}}
    for name in CANDIDATES:
        p = rows["models"][name]
        d = frame.log_loss(p, y) - frame.log_loss(base, y)
        b = frame.brier(p, y) - frame.brier(base, y)
        goal = frame.binary_log_loss(rows["goal_chances"][name], rows["goal_events"]) - base_goal
        part = lambda m: {"n": int(m.sum()), **p13.interval(frame, d[m], weeks[m])}
        c = {"measures": {**frame.summary(p, y), "ends_gap": p13.ends_gap(p, y)},
             "log_loss": p13.interval(frame, d, weeks), "brier": p13.interval(frame, b, weeks),
             "leagues": part(rows["is_league"]), "cups": part(~rows["is_league"]),
             "european_ties": part(europe), "finished_in_90_minutes_only": part(ft),
             "operational_subset": part(rows["operational"]),
             "goal_markets": {m: p13.interval(frame, goal[:, i], weeks) for i, m in enumerate(frame.GOAL_MARKETS)},
             "goal_markets_mean": p13.interval(frame, goal.mean(axis=1), weeks),
             "by_month": {m: {"n": int(k.sum()), "log_loss": float(d[k].mean())}
                          for m in sorted({str(v)[:7] for v in rows["day"]})
                          for k in [np.char.find(rows["day"].astype(str), m) == 0]}}
        ci = c["log_loss"]["ci95"]
        rule = {"better_by_the_threshold": c["log_loss"]["delta"] <= -THRESHOLD,
                "interval_excludes_zero": bool(ci and ci[1] < 0),
                "brier_agrees": c["brier"]["delta"] < 0,
                "goal_markets_no_worse": c["goal_markets_mean"]["delta"] <= 0.0005,
                "european_ties_no_worse": c["european_ties"]["delta"] is None or c["european_ties"]["delta"] <= 0}
        c["decision_rule"] = rule
        c["may_be_proposed"] = all(rule[k] for k in ("better_by_the_threshold", "interval_excludes_zero",
                                                     "brier_agrees", "goal_markets_no_worse"))
        out["candidates"][name] = c
    return out


def market(rows):
    """Each model against the bookmakers' margin-free chances at the snapshot, on the fixtures
    that have them: the result market, over 2.5 and both teams to score."""
    import numpy as np
    frame, weeks = rows["frame"], rows["week"]
    names = ("production",) + CANDIDATES
    fair = lambda table, market_id, selection: (table.get((market_id, selection)) or {}).get("fair")
    out = {}
    # the result market
    q = np.array([[fair(t, 1, s) for s in MARKETS["1X2"][1]] for t in rows["prices"]], dtype=float).reshape(-1, 3)
    has = ~np.isnan(q).any(axis=1)
    y, w = rows["y"][has], weeks[has]
    section = {"n": int(has.sum()), "market": frame.summary(q[has], y) if has.any() else None, "models": {}}
    losses = {n: frame.log_loss(rows["models"][n][has], y) for n in names} if has.any() else {}
    for n in names if has.any() else ():
        m = {"measures": frame.summary(rows["models"][n][has], y),
             "minus_market_log_loss": p13.interval(frame, losses[n] - frame.log_loss(q[has], y), w),
             "minus_market_brier": p13.interval(frame, frame.brier(rows["models"][n][has], y) - frame.brier(q[has], y), w)}
        if n != "production":
            m["minus_production_log_loss"] = p13.interval(frame, losses[n] - losses["production"], w)
            behind = float((losses["production"] - frame.log_loss(q[has], y)).mean())
            m["share_of_production's_gap_closed"] = float((losses["production"] - losses[n]).mean() / behind) if behind > 0 else None
        section["models"][n] = m
    out["result"] = section
    # over 2.5 and both teams to score
    for label, market_id, selection, column in (("over_2.5", 5, "Over 2.5", 1), ("both_teams_to_score", 8, "Yes", 4)):
        q = np.array([np.nan if fair(t, market_id, selection) is None else fair(t, market_id, selection)
                      for t in rows["prices"]], dtype=float)
        has = ~np.isnan(q)
        event, w = rows["goal_events"][has, column], weeks[has]
        section = {"n": int(has.sum()), "models": {}}
        if has.any():
            against = frame.binary_log_loss(q[has], event)
            section["market_log_loss"] = float(against.mean())
            for n in names:
                mine = frame.binary_log_loss(rows["goal_chances"][n][has, column], event)
                section["models"][n] = {"log_loss": float(mine.mean()),
                                        "minus_market_log_loss": p13.interval(frame, mine - against, w)}
        out[label] = section
    return out


def bets(rows):
    """The shadow bets of each model, and each candidate's against production's on the same
    priced fixtures."""
    import numpy as np
    frame, weeks = rows["frame"], rows["week"]
    names = ("production",) + CANDIDATES
    priced = np.array([any(q.get("taken") is not None for q in t.values()) for t in rows["prices"]], dtype=bool)
    placed = {n: [] for n in names}                     # (row, bet)
    profit = {n: np.zeros(len(weeks)) for n in names}
    for i in np.where(priced)[0]:
        for n in names:
            model = chances(rows["models"][n][i], rows["goal_chances"][n][i])
            for bet in shadow_bets(model, rows["prices"][i], rows["closing"][i],
                                   rows["home_goals"][i], rows["away_goals"][i]):
                placed[n].append((i, bet))
                profit[n][i] += bet["profit"]

    def record(items):
        if not items:
            return {"bets": 0}
        w = np.array([weeks[i] for i, _ in items])
        pnl = np.array([b["profit"] for _, b in items])
        with_fair = [b for _, b in items if b["fair"] is not None]
        clv = [(weeks[i], b["clv"]) for i, b in items if b["clv"] is not None]
        out = {"bets": len(items), "fixtures": len({i for i, _ in items}), "won": int(sum(b["won"] for _, b in items)),
               "profit_units": float(pnl.sum()), "average_odds": float(np.mean([b["odds"] for _, b in items])),
               "return": p13.interval(frame, pnl, w),
               "claimed_return": float(np.mean([b["chance"] * b["odds"] - 1 for _, b in items])),
               "wins_expected_if_the_model_is_right": float(sum(b["chance"] for _, b in items)),
               "wins_expected_if_the_market_is_right": float(sum(b["fair"] for b in with_fair)) if with_fair else None,
               "bets_with_a_market_chance": len(with_fair)}
        if clv:
            out["closing_line_value"] = {"n": len(clv), **p13.interval(frame, np.array([c for _, c in clv]),
                                                                         np.array([k for k, _ in clv]))}
        return out

    out = {"priced_fixtures": int(priced.sum()), "rule": {"min_edge": MIN_EDGE, "max_odds": MAX_ODDS, "bookmaker": BOOKMAKER},
           "models": {}}
    for n in names:
        items = placed[n]
        m = {"all": record(items),
             "by_kind": {g: record([x for x in items if x[1]["group"] == g]) for g in ("1X2", "OU", "BTTS")},
             "odds_under_4": record([x for x in items if x[1]["odds"] < 4]),
             "no_result_bets_on_outsiders": record([x for x in items if not (x[1]["market"] == "1X2" and x[1]["outsider"])])}
        if n != "production":
            d = (profit[n] - profit["production"])[priced]
            m["profit_per_priced_fixture_minus_production"] = p13.interval(frame, d, weeks[priced])
            mine = {(i, b["market"], b["selection"]) for i, b in items}
            theirs = {(i, b["market"], b["selection"]) for i, b in placed["production"]}
            m["bets_shared_with_production"] = len(mine & theirs)
        ret, value = m["all"].get("return", {}), m["all"].get("closing_line_value", {})
        m["edge_shown"] = {"return_interval_above_zero": bool(ret.get("ci95") and ret["ci95"][0] > 0),
                           "closing_line_value_interval_above_zero": bool(value.get("ci95") and value["ci95"][0] > 0)}
        out["models"][n] = m
    return out


def analyse(rows):
    import numpy as np
    out = {"n": int(len(rows["y"])), "weeks": int(len(np.unique(rows["week"]))), "threshold": THRESHOLD,
           "primary": PRIMARY, "retrained_on": rows["retrained_on"], "formula_coefficients": rows["formula_coefficients"],
           "margin_moved_sd": rows["margin_moved_sd"], "operational_share": float(rows["operational"].mean()),
           "decided_in_extra_time_or_on_penalties": int((~rows["ft_only"]).sum()),
           "accuracy": accuracy(rows), "market": market(rows), "bets": bets(rows)}
    # an edge needs all three: no worse than the market's prices, and both bet measures above zero
    for n, m in out["bets"]["models"].items():
        gap = out["market"]["result"]["models"].get(n, {}).get("minus_market_log_loss", {})
        m["edge_shown"]["not_behind_the_market"] = gap.get("delta") is not None and gap["delta"] <= 0
        m["edge_shown"]["all_three"] = all(m["edge_shown"].values())
    return out


def reestimate(rows):
    """SD of the primary candidate's paired differences only, never their mean."""
    import numpy as np
    frame, y = rows["frame"], rows["y"]
    d = frame.log_loss(rows["models"][PRIMARY], y) - frame.log_loss(rows["models"]["production"], y)
    sd = float(np.std(d, ddof=1))
    return {"n": int(len(d)), "sd": sd, "planning_effect": PLANNING_EFFECT, "fixtures_required": fixtures_required(sd)}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--unblind", action="store_true", help="outcome metrics, once the target is reached and P6 is read")
    parser.add_argument("--interim", action="store_true", help="allow --unblind early; labelled a protocol deviation")
    parser.add_argument("--reestimate", action="store_true", help=f"one-time blinded sample-size re-estimate at {REESTIMATE_AT}")
    args = parser.parse_args()
    check_pins()
    status = {"protocol": "P14", "generated_at": datetime.now(timezone.utc).isoformat(),
              "evaluator_sha256": p13.digest(__file__), "start": START, "target": TARGET, "blinded": not args.unblind}
    if not (args.unblind or args.reestimate):
        status["accrual"] = accrual()
        (HERE / "status_P14.json").write_text(json.dumps(status, indent=2) + "\n")
        print(json.dumps(status["accrual"], indent=2))
        return
    if args.unblind and not args.interim and not (HERE / "results_P6.json").exists():
        raise SystemExit("P14 reads production against the bookmakers, which is P6's question: read P6 first")
    doc = extract()
    if doc["database_says"] != "production":
        raise SystemExit(f"P14 is analysed on production (read-only); this database says it is {doc['database_says']}")
    rows, excluded = build(doc)
    n = 0 if rows is None else len(rows["y"])
    status.update(extracted_at=doc["extracted_at"], database_role=doc["database_role"], accrued=n, exclusions=excluded)
    if args.reestimate:
        if n < REESTIMATE_AT:
            raise SystemExit(f"P14: {n} fixtures accrued; re-estimation needs {REESTIMATE_AT}")
        status["reestimate"] = reestimate(rows)
        print(json.dumps(status, indent=2))
        return
    if n < TARGET and not args.interim:
        raise SystemExit(f"P14: {n} of {TARGET} fixtures; refusing to unblind before the registered target")
    status["results"] = analyse(rows)
    if n < TARGET or not (HERE / "results_P6.json").exists():
        status["results"]["label"] = "INTERIM - protocol deviation; not decision-grade"
    (HERE / "results_P14.json").write_text(json.dumps(status, indent=2) + "\n")
    print(json.dumps(status, indent=2))


if __name__ == "__main__":
    main()

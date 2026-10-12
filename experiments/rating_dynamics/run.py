"""Rating dynamics: four structural changes to the club rank replay, and their combination
(DESIGN.md).

    levels       a level for each league, learned from matches between clubs of different leagues
                 and shared by every club in it
    movers       a club that changes division is moved towards its new division on arrival
    uncertainty  a club with little history moves faster, and its opponent slower
    reaction     different step sizes (K) for matches with and without xG
    combined     the four together

Two stages, so that nothing in the final period is seen while a number is being chosen:

    python experiments/rating_dynamics/run.py develop    # chooses every setting on development
    python experiments/rating_dynamics/run.py final      # scores the final period once

`develop` writes chosen.json. `final` reads it, refuses to run without it, and writes
results.json. Offline: reads experiments/research_frame/inputs.json.gz only. Needs numpy.
"""
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research_frame"))
import frame  # noqa: E402

HERE = Path(__file__).parent
CHOSEN, OUT = HERE / "chosen.json", HERE / "results.json"

SELECTION_START = "2022-07-01"          # settings are chosen on 2022-07-01 to 2024-06-30
LEAGUE_WINDOW = 400                     # days a club's last league match stays its league
FAMILY = 13                             # registered comparisons on the final period this round
LEVEL = 1 - 0.05 / FAMILY
MIN_GAIN = 0.0002                       # a setting must beat production by this on selection to be chosen

OFF = dict(league_k=0.0, pull=0.0, shift_down=0.0, shift_up=0.0, boost=0.0, tau=20.0, damp=0,
           reset=None, k=frame.PRODUCTION["k"], k_xg=frame.PRODUCTION["k_xg"])

GRIDS = {
    "levels": [dict(league_k=v) for v in (0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0)],
    "movers": [dict(pull=v) for v in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6)]
    + [dict(shift_down=dn, shift_up=up) for dn in (0, 15, 30, 45, 60) for up in (0, 15, 30) if dn or up],
    "uncertainty": [dict(boost=b, tau=t, damp=dm, reset=r) for b in (0.5, 1.0, 2.0, 3.0) for t in (10.0, 20.0, 40.0)
                    for dm in (0, 1) for r in (None, 10)],
    "reaction": [dict(k=k, k_xg=kx) for k in (5.0, 6.0, 7.0, 8.0, 9.0, 10.0) for kx in (8.0, 10.0, 12.0, 14.0)
                 if (k, kx) != (6.0, 10.0)],
}


def replay(data, p):
    """frame.replay with the four changes. With p == OFF it is production's replay."""
    start, _, _ = frame.starting_ranks(data)
    s = frame.PRODUCTION
    cur, hist, sums, played = {}, {}, {}, {}
    league_of, seen_on, offset = {}, {}, {}
    members = {}
    out = frame.Replay(data.n)
    hfa, cap, gw = s["home_advantage"], s["max_goal_diff"], s["goals_weight"]
    home, away, hg, ag, hx, ax, lg = (data.home, data.away, data.home_goals, data.away_goals,
                                      data.home_xg, data.away_xg, data.league)
    is_league, ordinal, leagues = data.is_league, data.ordinal, data.leagues
    league_k, pull, down, up = p["league_k"], p["pull"], p["shift_down"], p["shift_up"]
    boost, tau, damp, reset = p["boost"], p["tau"], p["damp"], p["reset"]

    def shift(team, by):
        cur[team] += by
        hist[team] = [v + by for v in hist[team]]
        total, run = 0.0, [0.0]
        for v in hist[team]:
            total += v
            run.append(total)
        sums[team] = run

    def known(team, day):
        got = league_of.get(team)
        return got if got is not None and day - seen_on[team] <= LEAGUE_WINDOW else None

    for i in range(data.n):
        th, ta, day = home[i], away[i], ordinal[i]
        for t in (th, ta):
            if t not in cur:
                cur[t] = start[t]
                hist[t] = [cur[t]]
                sums[t] = [0.0, cur[t]]
                played[t] = 0
        if is_league[i]:
            here = lg[i]
            for t in (th, ta):
                was = league_of.get(t)
                if was == here:
                    continue
                if was is not None:
                    members[was].discard(t)
                    # keep the club's effective rank continuous across the two leagues' levels
                    by = offset.get(was, 0.0) - offset.get(here, 0.0)
                    same_country = leagues[was]["country"] == leagues[here]["country"]
                    if same_country and day - seen_on[t] <= LEAGUE_WINDOW:
                        if pull and members.get(here):
                            mean = sum(cur[m] for m in members[here]) / len(members[here]) + offset.get(here, 0.0)
                            by += pull * (mean - (cur[t] + offset.get(was, 0.0)))
                        a, b = leagues[here]["starting_rank"], leagues[was]["starting_rank"]
                        if a is not None and b is not None and a != b:
                            by += up if a > b else -down
                        if reset is not None:
                            played[t] = min(played[t], reset)
                    if by:
                        shift(t, by)
                members.setdefault(here, set()).add(t)
                league_of[t] = here
        if is_league[i]:
            seen_on[th] = seen_on[ta] = day
        lh, la = known(th, day), known(ta, day)
        oh, oa = offset.get(lh, 0.0) if lh is not None else 0.0, offset.get(la, 0.0) if la is not None else 0.0
        h, a = cur[th], cur[ta]
        out.h_now[i], out.a_now[i] = h + oh, a + oa
        out.h_lt[i] = frame._lt(hist[th], sums[th]) + oh
        out.a_lt[i] = frame._lt(hist[ta], sums[ta]) + oa
        out.h_played[i], out.a_played[i] = len(hist[th]) - 1, len(hist[ta]) - 1
        exp_diff = (h + oh - a - oa + hfa) / 100
        capped = max(-cap, min(cap, hg[i] - ag[i]))
        if math.isnan(hx[i]) or math.isnan(ax[i]):
            result, k = capped, p["k"]
        else:
            result, k = gw * capped + (1 - gw) * (hx[i] - ax[i]), p["k_xg"]
        weight = frame.COMPETITION_WEIGHT.get(lg[i], 1.0)
        surprise = (result - exp_diff) * weight
        kh = ka = k
        if boost:
            gh, ga = 1 + boost * math.exp(-played[th] / tau), 1 + boost * math.exp(-played[ta] / tau)
            kh, ka = (k * gh / ga, k * ga / gh) if damp else (k * gh, k * ga)
        cur[th], cur[ta] = h + surprise * kh, a - surprise * ka
        if league_k and lh is not None and la is not None and lh != la:
            offset[lh] = offset.get(lh, 0.0) + league_k * surprise
            offset[la] = offset.get(la, 0.0) - league_k * surprise
        for t in (th, ta):
            hist[t].append(cur[t])
            sums[t].append(sums[t][-1] + cur[t])
            played[t] += 1
    out.offsets = offset
    return out


def predict(data, p):
    """(home goals, away goals, result probabilities) of every fixture under settings p."""
    hx, ax = frame.reprojected(data, replay(data, p))
    ok = ~np.isnan(hx)
    probs = np.full((data.n, 3), np.nan)
    probs[ok] = frame.outcome_probabilities(hx[ok], ax[ok])
    return hx, ax, probs


def loss(data, probs, rows):
    return float(frame.log_loss(probs[rows], data.result[rows]).mean())


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ---- develop: choose every setting on the selection window -----------------------------------

def develop():
    data = frame.Data()
    select = data.development & (data.day >= SELECTION_START)
    seasons = {data.season_label(s): data.development & (data.season == s) for s in (2021, 2022, 2023)}
    _, _, base = predict(data, OFF)
    stored = frame.baseline_probabilities(data, data.scored)
    base_loss = loss(data, base, select)
    report = {"selection_window": [SELECTION_START, frame.DEVELOPMENT_END], "selection_matches": int(select.sum()),
              "production_selection_log_loss": base_loss,
              "replayed_against_stored_baseline": {
                  "stored_log_loss_all_scored": float(frame.log_loss(stored, data.result[data.scored]).mean()),
                  "replayed_log_loss_all_scored": loss(data, base, data.scored)},
              "production_by_season": {k: loss(data, base, m) for k, m in seasons.items()},
              "grids": {}, "chosen": {}}

    def run_grid(name, settings, around=OFF):
        rows = []
        for change in settings:
            p = {**around, **change}
            _, _, probs = predict(data, p)
            rows.append({"change": change, "selection_log_loss": loss(data, probs, select),
                         "by_season": {k: loss(data, probs, m) for k, m in seasons.items()}})
            print(name, change, f"{rows[-1]['selection_log_loss'] - base_loss:+.5f}", flush=True)
        return rows

    for name, settings in GRIDS.items():
        rows = run_grid(name, settings)
        report["grids"][name] = rows
        best = min(rows, key=lambda r: r["selection_log_loss"])
        gain = base_loss - best["selection_log_loss"]
        report["chosen"][name] = {"change": best["change"] if gain >= MIN_GAIN else {},
                                  "selection_gain": gain, "chosen": gain >= MIN_GAIN}

    # combined: the chosen changes together, then one sweep that re-chooses each part's setting
    # with the other three in place (the grids above, nothing new)
    stacked = dict(OFF)
    for name in GRIDS:
        stacked.update(report["chosen"][name]["change"])
    current = dict(stacked)
    _, _, probs = predict(data, current)
    current_loss = loss(data, probs, select)
    report["stacked_selection_log_loss"] = current_loss
    sweep = {}
    for name, settings in GRIDS.items():
        keys = {k for change in settings for k in change}
        without = {**current, **{k: OFF[k] for k in keys}}
        rows = run_grid(f"combined/{name}", [{k: OFF[k] for k in keys}] + settings, around=without)
        best = min(rows, key=lambda r: r["selection_log_loss"])
        if best["selection_log_loss"] < current_loss - 1e-9:
            current, current_loss = {**without, **best["change"]}, best["selection_log_loss"]
        sweep[name] = {"best": best["change"], "selection_log_loss": best["selection_log_loss"]}
    report["combined_sweep"] = sweep
    report["chosen"]["combined"] = {"change": {k: v for k, v in current.items() if v != OFF[k]},
                                    "selection_gain": base_loss - current_loss, "chosen": True}
    report["evaluator_sha256"] = digest(__file__)
    report["frame_sha256"] = digest(frame.__file__)
    CHOSEN.write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps(report["chosen"], indent=1))


# ---- final: score the final period once ------------------------------------------------------

def verdict(c, goal_markets):
    mean, lo, hi = c["log_loss"]
    seasons = [c["by_season"].get(s, {}).get("log_loss") for s in ("2024/25", "2025/26")]
    no_worse, listed = c["competitions_no_worse"]
    bar = {"log_loss_better_by_0.002": mean <= -0.002, "adjusted_interval_excludes_zero": hi < 0,
           "brier_agrees": c["brier"][0] < 0,
           "better_in_2024/25_and_2025/26": all(s is not None and s < 0 for s in seasons),
           "no_goal_market_worse_by_0.0005": all(v <= 0.0005 for v in goal_markets.values()),
           "60_percent_of_competitions_no_worse": listed > 0 and no_worse / listed >= 0.6}
    label = "meets the bar" if all(bar.values()) else \
        "a real gain below the bar" if hi < 0 and mean < 0 else "no gain shown"
    return {"conditions": bar, "label": label}


def final():
    if not CHOSEN.exists():
        raise SystemExit("run `develop` first: chosen.json is missing")
    chosen = json.loads(CHOSEN.read_text())
    data = frame.Data()
    rows = data.final
    bx, ba, base = predict(data, OFF)
    events = frame.goal_events(data, rows)
    base_goal = frame.binary_log_loss(frame.goal_markets(bx[rows], ba[rows]), events).mean(axis=0)
    report = {"level": LEVEL, "family": FAMILY, "final_matches": int(rows.sum()),
              "chosen_sha256": digest(CHOSEN), "evaluator_sha256": digest(__file__),
              "frame_sha256": digest(frame.__file__), "inputs_extracted_at": data.doc["extracted_at"],
              "candidates": {}}
    for name, entry in chosen["chosen"].items():
        if not entry["change"]:
            report["candidates"][name] = {"setting": {}, "label": "nothing chosen on development; not scored"}
            continue
        p = {**OFF, **entry["change"]}
        hx, ax, probs = predict(data, p)
        c = frame.compare(data, rows, base[rows], probs[rows], LEVEL)
        c["interval_95"] = frame.paired_interval(
            frame.log_loss(probs[rows], data.result[rows]) - frame.log_loss(base[rows], data.result[rows]),
            data.week[rows], 0.95)
        goal = frame.binary_log_loss(frame.goal_markets(hx[rows], ax[rows]), events).mean(axis=0) - base_goal
        c["goal_markets"] = dict(zip(frame.GOAL_MARKETS, map(float, goal)))
        c["setting"] = entry["change"]
        c["verdict"] = verdict(c, c["goal_markets"])
        # the development seasons for the same setting, for the table by season
        dev = data.development
        d = frame.log_loss(probs[dev], data.result[dev]) - frame.log_loss(base[dev], data.result[dev])
        c["development_by_season"] = {data.season_label(s): float(d[data.season[dev] == s].mean()) for s in (2021, 2022, 2023)}
        report["candidates"][name] = c
        m = c["log_loss"]
        print(f"{name:12s} {entry['change']}\n   final log loss {c['baseline']['log_loss']:.5f} -> {c['candidate']['log_loss']:.5f}"
              f" ({m[0]:+.5f}, {m[1]:+.5f} to {m[2]:+.5f} at {LEVEL:.4f}) | Brier {c['brier'][0]:+.5f} | "
              f"leagues {c['leagues']['log_loss']:+.5f} cups {c['cups']['log_loss']:+.5f} | "
              f"competitions no worse {c['competitions_no_worse']} | {c['verdict']['label']}")
        print("   by season", {k: round(v["log_loss"], 5) for k, v in c["by_season"].items()},
              "| goal markets", {k: round(v, 5) for k, v in c["goal_markets"].items()})
    OUT.write_text(json.dumps(report, indent=1) + "\n")


if __name__ == "__main__":
    {"develop": develop, "final": final}[sys.argv[1] if len(sys.argv) > 1 else ""]()

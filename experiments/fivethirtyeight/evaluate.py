"""Our match model against FiveThirtyEight's club forecasts, on the matches both forecast.

Written 2026-11-06 before it was run; its SHA-256 is recorded in DESIGN.md. Reads pairs.json
(pair.py) and the research frame's inputs; writes results.json. Reads no database, calls no API.

    python experiments/fivethirtyeight/evaluate.py      # needs numpy

Ours: production's stored projection for each fixture, turned into home / draw / away by the
production probability step (frame.baseline_probabilities), as every research-round baseline is.
Theirs: prob1, probtie, prob2 from their final file, rescaled to sum to one.
Rows: the frame's scored matches (finished in 90 minutes, a regulation score, a stored projection)
from 2021-07-01 (the end of our burn-in) that pair.py paired, up to their last scored match.
Scored on the regulation result, as ours are. Their figure minus ours: below zero, theirs is better.
"""
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "research_frame"))
import frame  # noqa: E402

PAIRS = HERE / "pairs.json"
OUT = HERE / "results.json"


def main():
    data = frame.Data()
    pairs = json.loads(PAIRS.read_text())["pairs"]
    theirs = {p["fixture_id"]: p for p in pairs}

    rows = data.scored & (data.day >= frame.BURN_IN_END) & np.isin(data.fixture_id, list(theirs))
    ids = data.fixture_id[rows]
    p_ours = frame.baseline_probabilities(data, rows)
    p_theirs = np.array([[theirs[f]["prob1"], theirs[f]["probtie"], theirs[f]["prob2"]] for f in ids])
    p_theirs = p_theirs / p_theirs.sum(axis=1, keepdims=True)

    out = frame.compare(data, rows, p_ours, p_theirs)
    out["baseline_is"] = "The Corner FC (production's stored projections)"
    out["candidate_is"] = "FiveThirtyEight SPI (final archived file)"
    out["window"] = [min(data.day[rows].tolist()), max(data.day[rows].tolist())]
    out["base_rates"] = frame.summary(
        np.tile(np.bincount(data.result[rows], minlength=3) / rows.sum(), (rows.sum(), 1)),
        data.result[rows])

    their_league = np.array([theirs[f]["league"] for f in ids])
    d = frame.log_loss(p_theirs, data.result[rows]) - frame.log_loss(p_ours, data.result[rows])
    out["by_their_league"] = {lg: {"n": int((their_league == lg).sum()),
                                   "log_loss": float(d[their_league == lg].mean())}
                              for lg in sorted(set(their_league))}
    OUT.write_text(json.dumps(out, indent=1))

    b, c = out["baseline"], out["candidate"]
    print(f"{rows.sum()} matches, {out['window'][0]} to {out['window'][1]}")
    print(f"log loss   ours {b['log_loss']:.4f}   theirs {c['log_loss']:.4f}   base rates {out['base_rates']['log_loss']:.4f}")
    print("theirs minus ours, 95%: log loss {:+.4f} ({:+.4f} to {:+.4f})".format(*out["log_loss"]))
    print("                          brier {:+.4f} ({:+.4f} to {:+.4f})".format(*out["brier"]))
    print(f"accuracy   ours {b['accuracy']:.3f}   theirs {c['accuracy']:.3f}")
    print(f"sharpness power   ours {b['sharpness_power']}   theirs {c['sharpness_power']}")
    for s, v in out["by_season"].items():
        print(f"  {s}  n={v['n']:5d}  {v['log_loss']:+.4f}")
    for lg, v in sorted(out["by_their_league"].items(), key=lambda kv: kv[1]["log_loss"]):
        print(f"  {v['n']:5d}  {v['log_loss']:+.4f}  {lg}")


if __name__ == "__main__":
    main()

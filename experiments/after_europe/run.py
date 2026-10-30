"""After Europe: a side back in its league after a European match with five or more days' rest
(DESIGN.md). Fixes, from the frozen history, the one number the live test (P19) uses: DELTA, the
mean goal-difference error of such sides against the stored projection, July 2021 to 11 October
2026. Writes chosen.json. Nothing is scored here: this lead was found by looking (2026-10-29) and
only live matches can test it.

    python experiments/after_europe/run.py        # needs numpy and the research frame's inputs
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments" / "research_frame"))
import frame  # noqa: E402

HERE = Path(__file__).parent
EUROPE = (2, 3, 848)
MIN_REST = 5                    # days since the side's European match
FROM = "2021-07-01"


def flags(data):
    """(n, 2) booleans: the home side, the away side, back in a league match after a European
    match at least MIN_REST days before, that match being its previous one in the data."""
    out = np.zeros((data.n, 2), dtype=bool)
    last = {}
    for i in range(data.n):
        for side, team in enumerate((data.home[i], data.away[i])):
            j = last.get(team)
            if j is not None and data.is_league[i] and data.league[j] in EUROPE \
                    and data.ordinal[i] - data.ordinal[j] >= MIN_REST:
                out[i, side] = True
            last[team] = i
    return out


def scored(data):
    return (np.isin(data.status, ("FT", "AET", "PEN")) & ~np.isnan(data.ft_home) & ~np.isnan(data.ft_away)
            & ~np.isnan(data.pred["home_xg"]) & ~np.isnan(data.pred["away_xg"])
            & (data.day >= FROM) & (data.day < frame.FINAL_END))


def main():
    data = frame.Data()
    f = flags(data)
    rows = scored(data)
    error = (data.ft_home - data.ft_away) - (data.pred["home_xg"] - data.pred["away_xg"])
    errs, weeks = [], []
    for side, sign in ((0, 1), (1, -1)):
        m = rows & f[:, side]
        errs.append(sign * error[m])
        weeks.append(data.week[m])
    errs, weeks = np.concatenate(errs), np.concatenate(weeks)
    mean, lo, hi = frame.paired_interval(errs, weeks, 0.95)
    out = {"delta": round(float(mean), 2), "estimate": [mean, lo, hi], "side_matches": int(len(errs)),
           "period": [FROM, frame.FINAL_END], "europe": EUROPE, "min_rest_days": MIN_REST}
    (HERE / "chosen.json").write_text(json.dumps(out, indent=1) + "\n")
    print(out)


if __name__ == "__main__":
    main()

"""Pairs FiveThirtyEight's matches with our fixtures, using dates and scores only.

The research frame's inputs hold team ids, not names, so a FiveThirtyEight team is given the
API-Football id it lines up with most often: for every match of theirs since our first fixture,
our fixtures within a day with the same score vote for their two sides. A team keeps an id only
when that id turns up in at least 80% of its matches, at least 10 of them, and no other team of
theirs took the same id. A match
is paired when both its teams have an id and exactly one of our fixtures within a day has those
two sides at home and away.

Reads spi_matches.csv (fetch.sh) and the research frame's inputs.json.gz; writes pairs.json
(gitignored). Reads no forecast column of theirs and no prediction of ours, so it can be run and
checked before the evaluator scores anything.

    .venv/bin/python experiments/fivethirtyeight/pair.py
"""
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "research_frame"))
import frame  # noqa: E402

SPI = HERE / "spi_matches.csv"
OUT = HERE / "pairs.json"
MIN_VOTES, MIN_SHARE = 10, 0.8
WOMEN = ("Women", "NWSL")


def near(day):
    d = date.fromisoformat(day)
    return [(d + timedelta(days=k)).isoformat() for k in (-1, 0, 1)]


def main():
    data = frame.Data()
    # we hold no women's football, and their women's sides share the men's names (Aston Villa, Reading)
    theirs = [r for r in csv.DictReader(open(SPI, newline=""))
              if r["score1"] != "" and not any(w in r["league"] for w in WOMEN)]

    by_day_score = defaultdict(list)
    by_day_sides = defaultdict(list)
    for i in range(data.n):
        h, a = data.home_goals[i], data.away_goals[i]
        by_day_score[(data.day[i], int(h), int(a))].append(i)
        by_day_sides[(data.day[i], int(data.home[i]), int(data.away[i]))].append(i)

    first_day = min(data.day)
    theirs_overlap = [r for r in theirs if r["date"] >= first_day]
    votes, played = defaultdict(Counter), Counter()
    for r in theirs_overlap:
        played[r["team1"]] += 1
        played[r["team2"]] += 1
        s1, s2 = int(float(r["score1"])), int(float(r["score2"]))
        for day in near(r["date"]):
            for i in by_day_score.get((day, s1, s2), []):
                votes[r["team1"]][int(data.home[i])] += 1
                votes[r["team2"]][int(data.away[i])] += 1

    ids = {}
    for name, c in votes.items():
        team_id, n = c.most_common(1)[0]
        if n >= MIN_VOTES and n / played[name] >= MIN_SHARE:
            ids[name] = team_id
    taken = Counter(ids.values())
    for name, t in sorted(ids.items()):
        if taken[t] > 1:
            print(f"  shared id {t}: {name} ({votes[name][t]} of {played[name]} matches)")
    ids = {name: t for name, t in ids.items() if taken[t] == 1}

    pairs, unpaired = [], Counter()
    for r in theirs:
        h, a = ids.get(r["team1"]), ids.get(r["team2"])
        if h is None or a is None:
            unpaired[(r["league"], "team without an id")] += 1
            continue
        found = [i for day in near(r["date"]) for i in by_day_sides.get((day, h, a), [])]
        if len(found) != 1:
            unpaired[(r["league"], "no single fixture" if not found else "several fixtures")] += 1
            continue
        pairs.append({"fixture_id": int(data.fixture_id[found[0]]), "date": r["date"],
                      "league": r["league"], "team1": r["team1"], "team2": r["team2"],
                      "prob1": float(r["prob1"]), "probtie": float(r["probtie"]),
                      "prob2": float(r["prob2"]), "score1": int(float(r["score1"])),
                      "score2": int(float(r["score2"]))})

    seen = Counter(p["fixture_id"] for p in pairs)
    pairs = [p for p in pairs if seen[p["fixture_id"]] == 1]
    OUT.write_text(json.dumps({"team_ids": ids, "pairs": pairs}, indent=0))

    # checks that need no forecast: how many paired, and whether the scores agree
    i_of = data.index
    score_agrees = sum(1 for p in pairs
                       if (data.home_goals[i_of[p["fixture_id"]]], data.away_goals[i_of[p["fixture_id"]]])
                       == (p["score1"], p["score2"]))
    window = [p for p in pairs if frame.BURN_IN_END <= p["date"]]
    print(f"their scored matches {len(theirs)}; teams given an id {len(ids)} of {len(played)}")
    print(f"paired {len(pairs)} ({len(window)} from {frame.BURN_IN_END}); final score agrees on {score_agrees}")
    by_league = Counter(p["league"] for p in window)
    their_window = Counter(r["league"] for r in theirs if r["date"] >= frame.BURN_IN_END)
    for lg, n in their_window.most_common():
        print(f"  {by_league[lg]:5d} of {n:5d}  {lg}")


if __name__ == "__main__":
    main()

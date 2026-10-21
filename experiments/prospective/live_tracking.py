"""The Live tracking workflow's one job: P16 (the club-rank release), P17 (every runnable idea on
the live model) and P18 (the stored challenger against the live model) from one read, stored
as the one administrator's document `live_tracking` that the Model Change Tracker reads.

    python experiments/prospective/live_tracking.py            # prints the record; stores nothing
    python experiments/prospective/live_tracking.py --store    # and stores it

Each protocol's evaluator is its own file, pinned and registered in PROTOCOLS.md; this only runs
them and puts their records together. It adds `scores`, descriptive and outside every verdict:
each tracked change's mean log loss and share of right results on the live matches, beside the
model it is compared with, so the tracker can show both in plain figures.
"""
import argparse
import importlib.util
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[1]))


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


p17, p18 = load("live_p17"), load("live_p18")
p16 = p17.p16
LATER = "Registered after P17, so not one of its candidates: judged by its own evaluator (see its page)"


def together(release_and_ideas, challenger):
    """P16 and P17's document with P18's record added."""
    out = dict(release_and_ideas)
    out["protocol"] = "P16, P17 and P18"
    out["changes"] = {**out["changes"], **challenger["changes"]}
    out["not_run"] = {cid: why for cid, why in out["not_run"].items() if cid not in out["changes"]}
    # a change registered after P17 is none of its candidates: it is judged by its own evaluator
    out["not_run"].update({cid: LATER for cid in p16.changes_in_register() if cid not in out["changes"] and cid not in out["not_run"]})
    out["comparisons"] = {**out["comparisons"], "P18": challenger["comparisons"]}
    out["exclusions"] = {**out["exclusions"], "P18": challenger["exclusions"]}
    out["settings"] = {**out["settings"], **challenger["settings"]}
    out["p18"] = {"start": challenger["start"], "alpha": challenger["alpha"], "live_counts": challenger["live_counts"]}
    return out


def scores(pairs):
    """{change: its log loss and right results on the live matches, and the same for the model it is
    compared with}, from {change: (its probabilities, the other's, outcomes)}, each a list of
    (home, draw, away) rows. Right: the outcome given the highest chance happened (the first of a tie)."""
    def measure(probs, ys):
        loss = sum(-math.log(max(float(p[y]), 1e-15)) for p, y in zip(probs, ys)) / len(ys)
        right = sum(max(range(3), key=lambda k: float(p[k])) == y for p, y in zip(probs, ys)) / len(ys)
        return loss, right

    out = {}
    for cid, (mine, theirs, ys) in pairs.items():
        ys = [int(y) for y in ys]
        if not ys:
            continue
        (loss, right), (against, against_right) = measure(mine, ys), measure(theirs, ys)
        out[cid] = {"n": len(ys), "log_loss": loss, "right": right, "against_log_loss": against, "against_right": against_right}
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", action="store_true", help="store the record for the Admin area (needs a run that may write)")
    args = parser.parse_args()
    p17.check_pins()
    doc = p16.extract()
    rows, excluded, checks = p16.build(doc)
    release = p16.record(rows, excluded, checks, environment=doc["database_says"], generated_at=doc["extracted_at"])
    idea_rows, idea_excluded = p17.build(doc)
    ideas = p17.record(idea_rows, idea_excluded)
    with p16.p13.connect() as conn:
        challenged = p18.extract(conn)
    challenger = p18.record(challenged)
    out = together(p17.combined(release, ideas), challenger)
    compared = {}
    if rows is not None:
        compared[p16.CHANGE] = (rows["released"], rows["before"], rows["y"])
    if idea_rows is not None:
        compared.update({cid: (p, idea_rows["production"], idea_rows["y"]) for cid, p in idea_rows["candidates"].items()})
    pairs = p18.pairs(challenged)[0]
    compared[p18.CHANGE] = ([probs["a18"] for _, _, probs, _ in pairs], [probs["base"] for _, _, probs, _ in pairs], [y for _, y, _, _ in pairs])
    out["scores"] = scores(compared)
    print(json.dumps({"n": out["n"], "weeks": out["weeks"], "to": out["to"], "exclusions": out["exclusions"], "checks": checks,
                      "called": {cid: c["called"] for cid, c in out["changes"].items() if c["called"]}}, indent=2, default=str))
    if args.store:
        from thecornerfc.pipeline import db
        from thecornerfc.publish import site_files
        with db.connect() as conn:          # a run that may write, to its own environment's database only
            site_files.store_admin_doc(conn, "live_tracking", out)
        print("stored")


if __name__ == "__main__":
    main()

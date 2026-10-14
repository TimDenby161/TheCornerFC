"""The Live tracking workflow's one job: P16 (the club-rank release), P17 (every runnable idea on
the live model) and P18 (the stored challenger against the live model) from one read, stored
as the one administrator's document `live_tracking` that the Model Change Tracker reads.

    python experiments/prospective/live_tracking.py            # prints the record; stores nothing
    python experiments/prospective/live_tracking.py --store    # and stores it

Each protocol's evaluator is its own file, pinned and registered in PROTOCOLS.md; this only runs
them and puts their records together.
"""
import argparse
import importlib.util
import json
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


def together(release_and_ideas, challenger):
    """P16 and P17's document with P18's record added."""
    out = dict(release_and_ideas)
    out["protocol"] = "P16, P17 and P18"
    out["changes"] = {**out["changes"], **challenger["changes"]}
    out["not_run"] = {cid: why for cid, why in out["not_run"].items() if cid not in out["changes"]}
    out["comparisons"] = {**out["comparisons"], "P18": challenger["comparisons"]}
    out["exclusions"] = {**out["exclusions"], "P18": challenger["exclusions"]}
    out["settings"] = {**out["settings"], **challenger["settings"]}
    out["p18"] = {"start": challenger["start"], "alpha": challenger["alpha"], "live_counts": challenger["live_counts"]}
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", action="store_true", help="store the record for the Admin area (needs a run that may write)")
    args = parser.parse_args()
    p17.check_pins()
    doc = p16.extract()
    rows, excluded, checks = p16.build(doc)
    release = p16.record(rows, excluded, checks, environment=doc["database_says"], generated_at=doc["extracted_at"])
    ideas = p17.record(*p17.build(doc))
    with p16.p13.connect() as conn:
        challenger = p18.record(p18.extract(conn))
    out = together(p17.combined(release, ideas), challenger)
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

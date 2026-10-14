"""A18 on the released club rank (DESIGN.md): the boosted trees' recipe retrained on the live
model's errors, against the live model, on the final period.

    python experiments/a18_on_release/run.py

Offline: reads experiments/research_frame/inputs.json.gz only, writes results.json. Needs numpy,
scipy and scikit-learn at the versions in experiments/prospective/requirements-p13.txt.
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
EXPERIMENTS = HERE.parent
sys.path.insert(0, str(EXPERIMENTS / "research_frame"))
import frame  # noqa: E402
import features  # noqa: E402

OUT = HERE / "results.json"
ARCH, SHOTS, RATING = EXPERIMENTS / "architectures", EXPERIMENTS / "shots_proxy", EXPERIMENTS / "rating_dynamics"
SHOTS_SETTING = {"goals_weight": 0.5, "k": 10.0}
MOVEMENT = {"pull": 0.5, "boost": 0.5, "tau": 40.0}
STATUSES = ("FT", "AET", "PEN")
LEVEL = 0.95


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    arch = load("architectures", ARCH / "run.py")
    shots = load("shots_proxy", SHOTS / "run.py")
    chosen = json.loads((ARCH / "chosen.json").read_text())
    assert json.loads((RATING / "chosen.json").read_text())["chosen"]["combined"]["change"] == MOVEMENT
    beta = np.array(json.loads((SHOTS / "chosen.json").read_text())["beta"])
    data = frame.Data()

    # the live model
    rep = shots.replay(data, beta, SHOTS_SETTING, MOVEMENT)
    hx, ax = frame.reprojected(data, rep)
    ok = ~np.isnan(hx)
    base = np.full((data.n, 3), np.nan)
    base[ok] = frame.outcome_probabilities(hx[ok], ax[ok])

    # A18's recipe on it
    lam, mu = arch.DC(data, **chosen["dc"]["setting"]).run(frame.BURN_IN_END, frame.FINAL_END, verbose=False)
    feats = features.build(data, rep, hx, ax)
    feats["dc_margin"], feats["dc_total"] = lam - mu - (hx - ax), lam + mu - (hx + ax)
    usable = data.scored & ok
    dm, dt = arch.gb_fit_predict(data, feats, chosen["gb"]["features"], hx, ax, arch.GB_BLOCKS_FINAL, frame.FINAL_END,
                                 chosen["gb"]["params"], usable)
    gh, ga = arch.gb_apply(hx, ax, dm, dt, chosen["gb"]["shrink"])
    cand = np.full((data.n, 3), np.nan)
    cand[ok] = frame.outcome_probabilities(gh[ok], ga[ok])

    period = (data.day >= frame.DEVELOPMENT_END) & (data.day < frame.FINAL_END) & ok & ~np.isnan(cand[:, 0])
    populations = {
        "every_90_minute_score": period & np.isin(data.status, STATUSES) & ~np.isnan(data.ft_home) & ~np.isnan(data.ft_away),
        "finished_in_90_minutes": period & data.scored,
    }
    report = {"level": LEVEL, "setting": chosen["gb"], "baseline": "the released club rank (MC-0028), reprojected",
              "evaluator_sha256": digest(__file__), "frame_sha256": digest(frame.__file__),
              "features_sha256": digest(features.__file__), "architectures_sha256": digest(ARCH / "run.py"),
              "chosen_sha256": digest(ARCH / "chosen.json"), "inputs_extracted_at": data.doc["extracted_at"], "populations": {}}
    for name, rows in populations.items():
        c = frame.compare(data, rows, base[rows], cand[rows], LEVEL)
        events = frame.goal_events(data, rows)
        goal = frame.binary_log_loss(frame.goal_markets(gh[rows], ga[rows]), events).mean(axis=0) \
            - frame.binary_log_loss(frame.goal_markets(hx[rows], ax[rows]), events).mean(axis=0)
        c["goal_markets"] = dict(zip(frame.GOAL_MARKETS, map(float, goal)))
        report["populations"][name] = c
        m = c["log_loss"]
        print(f"{name}: {int(rows.sum())} matches | log loss {c['baseline']['log_loss']:.5f} -> {c['candidate']['log_loss']:.5f}"
              f" ({m[0]:+.5f}, {m[1]:+.5f} to {m[2]:+.5f}) | Brier {c['brier'][0]:+.5f} | leagues {c['leagues']['log_loss']:+.5f}"
              f" cups {c['cups']['log_loss']:+.5f} | no worse {c['competitions_no_worse']}")
        print("   by season", {k: round(v["log_loss"], 5) for k, v in c["by_season"].items()},
              "| goal markets", {k: round(v, 5) for k, v in c["goal_markets"].items()}, flush=True)
    OUT.write_text(json.dumps(report, indent=1) + "\n")


if __name__ == "__main__":
    main()

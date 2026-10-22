"""What each strength of level pull does to the skill scores (DESIGN.md), and the ranks check.

One run of player_ratings.compute_player_ratings on a read-only connection, with the database
write and the line-up capture replaced, keeping the inputs it hands to skill_scores; the scores
are then worked out again at each pull in PULLS. A second run, as the file was at BASE, must give
every rank, season rank, position rank, projection and predicted XI identical.

Nothing is written to the database and no API is called. Writes report.json next to this file.

    python experiments/skill_level/report.py
"""
import hashlib
import importlib.util
import inspect
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from thecornerfc.pipeline import db; from thecornerfc.evidence import lineup_snapshots; from thecornerfc.models import player_ratings as pr  # noqa: E402

HERE = Path(__file__).parent
OUT = HERE / "report.json"
BASE = "e51ef39c6"         # the commit the change is made from
BASE_SHA256 = "61f60562fbf697017a21dd86e07cf9c503b1916c85d3d2c532e9d86ab118ee3f"   # player_ratings.py there
PULLS = (0, 0.25, 0.5, 0.75, 1.0)
PLAYERS = {138893: "D. Markanday", 1100: "E. Haaland", 306: "M. Salah", 290: "V. van Dijk"}
COMPARED = ("appearance_scores", "team_out", "lineups", "current", "season_rows", "position_ranks", "projections",
            "components", "history")     # the data outputs, by name (not to_rank, a function)
TOP = 10


def base_module():
    source = subprocess.check_output(["git", "show", f"{BASE}:thecornerfc/models/player_ratings.py"], cwd=ROOT)
    if hashlib.sha256(source).hexdigest() != BASE_SHA256:
        raise SystemExit(f"player_ratings.py at {BASE} is not the file this was registered against")
    spec = importlib.util.spec_from_loader("thecornerfc.models.player_ratings_base", loader=None)
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "thecornerfc.models"
    exec(compile(source, f"player_ratings.py@{BASE}", "exec"), module.__dict__)
    return module


def run(conn, module, keep=None):
    got = {}
    names = inspect.signature(module._write)

    def capture(*args, **kwargs):
        got.update(names.bind(*args, **kwargs).arguments)

    saved = module._write, lineup_snapshots.capture_predictions, module.skill_scores
    module._write, lineup_snapshots.capture_predictions = capture, lambda *a, **k: None
    if keep is not None:
        def kept(*args, **kwargs):
            keep.update(args=args, kwargs=kwargs)
            return saved[2](*args, **kwargs)
        module.skill_scores = kept
    try:
        module.compute_player_ratings(conn)
    finally:
        module._write, lineup_snapshots.capture_predictions, module.skill_scores = saved
        conn.rollback()
    return got


def main():
    conn = db.connect()
    conn.read_only = True
    said = conn.execute("select site.environment()").fetchone()[0]
    conn.rollback()
    inputs = {}
    new = run(conn, pr, keep=inputs)
    base = run(conn, base_module())
    same = {k: base.get(k) == new.get(k) for k in COMPARED}

    players, norms = inputs["args"][0], inputs["args"][1]
    offsets = inputs["args"][2] if len(inputs["args"]) > 2 else inputs["kwargs"].get("offsets")
    main_league = {p: max(((k[1], v) for k, v in sums.items() if isinstance(k, tuple) and k[0] == "lg"), key=lambda x: x[1], default=(None, 0))[0]
                   for p, (sums, _) in players.items()}
    names = dict(conn.execute("select player_id, name from players where player_id = any(%s)",
                              [list(players)]).fetchall())
    conn.rollback()
    by_pull = {}
    for pull in PULLS:
        scores = pr.skill_scores(players, norms, offsets, level_pull=pull)
        minutes = {p: sums["minutes"] for p, (sums, _) in players.items()}
        top = {}
        for skill in ("dribbling", "finishing"):
            listed = sorted(((v[skill], p) for p, v in scores.items() if skill in v and minutes.get(p, 0) >= pr.SKILL_SAMPLE_MINUTES), reverse=True)[:TOP]
            top[skill] = [f"{names.get(p, p)} ({main_league.get(p)}): {round(s, 1)}" for s, p in listed]
        means = defaultdict(lambda: defaultdict(list))
        for p, v in scores.items():
            if minutes.get(p, 0) >= pr.SKILL_SAMPLE_MINUTES:
                for skill, s in v.items():
                    means[main_league.get(p)][skill].append(s)
        by_pull[str(pull)] = {
            "players": {n: scores.get(p) for p, n in PLAYERS.items()},
            "top": top,
            "league_means": {str(lg): {s: round(sum(x) / len(x), 1) for s, x in v.items()} for lg, v in means.items()},
        }
    result = {"database": said, "base": BASE, "ranks_untouched": all(same.values()), "identical_outputs": same,
              "reference_level": pr.skill_reference_level(players), "by_pull": by_pull}
    OUT.write_text(json.dumps(result, indent=1, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"database": said, "ranks_untouched": result["ranks_untouched"], "reference_level": result["reference_level"],
                      "markanday": {k: v["players"]["D. Markanday"] for k, v in by_pull.items()}}, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()

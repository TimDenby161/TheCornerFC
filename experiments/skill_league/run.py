"""Do league offsets make a player's skill score a better guide across leagues? (DESIGN.md)

1. Fits player_ratings.skill_league_offsets on the units of seasons up to TRAIN_TO and scores
   every later move between leagues: his skill z in the new league predicted from the old one,
   as it was (base) and with the two leagues' offsets (adjusted).
2. Runs player_ratings.compute_player_ratings twice on a read-only connection, with the database
   write and the line-up capture replaced: once as the file now is, and once as it was at BASE
   (read from git, checked against its fingerprint). Everything it would write but the skill
   scores must be identical.

Nothing is written to the database and no API is called; the local .cache is refreshed as any
local run does. Writes results.json next to this file and prints the verdict.

    python experiments/skill_league/run.py
"""
import hashlib
import importlib.util
import inspect
import json
import random
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from thecornerfc.pipeline import db; from thecornerfc.evidence import lineup_snapshots; from thecornerfc.models import player_ratings as pr  # noqa: E402

HERE = Path(__file__).parent
OUT = HERE / "results.json"
BASE = "73b96459d"         # the commit the change is made from
BASE_SHA256 = "7d62cc3e0f94437ee73fe0f0c13b14fff0099e41a9112025ce8e05855e2cbffd"   # player_ratings.py there
# fixed before any result was seen (DESIGN.md)
TRAIN_TO = 2024            # offsets fitted on units of seasons up to this
MIN_PAIRS = 200            # test pairs needed for a verdict
MIN_SKILLS_BETTER = 5      # of the seven skills
DRAWS = 2000
SEED = 20261022
MARKANDAY = "Markanday"    # reported alongside, by name


def base_module():
    """player_ratings.py as it was at BASE, loaded as a module of its own."""
    source = subprocess.check_output(["git", "show", f"{BASE}:thecornerfc/models/player_ratings.py"], cwd=ROOT)
    if hashlib.sha256(source).hexdigest() != BASE_SHA256:
        raise SystemExit(f"player_ratings.py at {BASE} is not the file this was registered against")
    spec = importlib.util.spec_from_loader("thecornerfc.models.player_ratings_base", loader=None)
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "thecornerfc.models"
    exec(compile(source, f"player_ratings.py@{BASE}", "exec"), module.__dict__)
    return module


def run(conn, module):
    """One run of the module's routine. Returns what it would have written, by the writer's own
    argument names."""
    got = {}
    names = inspect.signature(module._write)

    def capture(*args, **kwargs):
        got.update(names.bind(*args, **kwargs).arguments)

    saved = module._write, lineup_snapshots.capture_predictions
    module._write, lineup_snapshots.capture_predictions = capture, lambda *a, **k: None
    try:
        module.compute_player_ratings(conn)
    finally:
        module._write, lineup_snapshots.capture_predictions = saved
        conn.rollback()
    return got


def test_moves(units, offsets):
    """[(player, {skill: (base error², adjusted error²)})] for every move from one league in season
    t to another in t+1 after TRAIN_TO."""
    by = defaultdict(list)
    for player, season, league, _, z in units:
        by[(player, season)].append((league, z))
    out = []
    for (player, season), here in by.items():
        if season + 1 <= TRAIN_TO:
            continue
        for a, za in here:
            for b, zb in by.get((player, season + 1), []):
                if a == b:
                    continue
                err = {}
                for skill in pr.SKILLS:
                    if skill in za and skill in zb:
                        shift = offsets.get(b, {}).get(skill, 0.0) - offsets.get(a, {}).get(skill, 0.0)
                        err[skill] = ((za[skill] - zb[skill]) ** 2, (za[skill] + shift - zb[skill]) ** 2)
                out.append((player, err))
    return out


def summarise(pairs):
    """Per skill: base and adjusted mean squared error, and the mean of the seven."""
    per = {}
    for skill in pr.SKILLS:
        e = [err[skill] for _, err in pairs if skill in err]
        if e:
            per[skill] = (sum(b for b, _ in e) / len(e), sum(a for _, a in e) / len(e), len(e))
    overall = (sum(v[0] for v in per.values()) / len(per), sum(v[1] for v in per.values()) / len(per)) if per else (None, None)
    return per, overall


def bootstrap(pairs):
    """95% interval of adjusted minus base (mean over skills), players resampled."""
    players = defaultdict(list)
    for player, err in pairs:
        players[player].append((player, err))
    keys = sorted(players)
    rng = random.Random(SEED)
    diffs = []
    for _ in range(DRAWS):
        sample = [row for _ in keys for row in players[rng.choice(keys)]]
        _, (b, a) = summarise(sample)
        diffs.append(a - b)
    diffs.sort()
    return diffs[int(.025 * DRAWS)], diffs[int(.975 * DRAWS) - 1]


def league_means(scores, leagues):
    """Average score in each skill of each league's listed players (by their main league)."""
    out = defaultdict(lambda: defaultdict(list))
    for p, v in (scores or {}).items():
        lg = leagues.get(p)
        for skill, s in v.items():
            out[lg][skill].append(s)
    return {str(lg): {skill: round(sum(x) / len(x), 1) for skill, x in v.items()} for lg, v in out.items()}


def main():
    conn = db.connect()
    conn.read_only = True                # whatever this machine is switched to, this run writes nothing
    said = conn.execute("select site.environment()").fetchone()[0]
    conn.rollback()

    apps = pr._appearances(conn)
    norms = pr._skill_norms(apps)
    units = pr.skill_units(apps, norms)
    train = [u for u in units if u[1] <= TRAIN_TO]
    offsets = pr.skill_league_offsets(train)
    pairs = test_moves(units, offsets)
    per, (base_err, adj_err) = summarise(pairs)
    low, high = bootstrap(pairs) if pairs else (None, None)

    new = run(conn, pr)
    base = run(conn, base_module())
    same = {k: base[k] == new[k] for k in base if k not in ("conn", "skills")}

    better = sum(a < b for b, a, _ in per.values())
    enough = len(pairs) >= MIN_PAIRS
    checks = {
        "enough_test_pairs": enough,
        "better_overall": enough and adj_err < base_err and high is not None and high < 0,
        "better_in_most_skills": enough and better >= MIN_SKILLS_BETTER,
        "ranks_untouched": all(same.values()),
    }
    main_league = {}
    for player, season, league, minutes, _ in sorted(units, key=lambda u: (u[1], u[3])):
        main_league[player] = league
    names = dict(conn.execute("select player_id, name from players where name ilike %s", [f"%{MARKANDAY}%"]).fetchall())
    conn.rollback()
    result = {
        "database": said, "base": BASE, "checks": checks,
        "passed": enough and all(checks.values()),
        "verdict": None if not enough else ("passed" if all(checks.values()) else "failed"),
        "units": len(units), "train_units": len(train), "test_pairs": len(pairs), "test_players": len({p for p, _ in pairs}),
        "mean_squared_error": {"base": base_err, "adjusted": adj_err, "difference": None if base_err is None else adj_err - base_err,
                               "interval_95": [low, high]},
        "by_skill": {s: {"base": b, "adjusted": a, "pairs": n} for s, (b, a, n) in per.items()},
        "skills_better": better,
        "offsets_train": offsets,
        "offsets_all": pr.skill_league_offsets(units),
        "identical_outputs": same,
        "markanday": {str(p): {"name": n, "before": (base.get("skills") or {}).get(p), "after": (new.get("skills") or {}).get(p)}
                      for p, n in names.items()},
        "league_mean_scores": {"before": league_means(base.get("skills"), main_league), "after": league_means(new.get("skills"), main_league)},
    }
    OUT.write_text(json.dumps(result, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("database", "checks", "passed", "test_pairs", "mean_squared_error", "skills_better")}, indent=1, default=str))
    print("PASSED" if result["passed"] else "NO VERDICT" if not enough else "FAILED")


if __name__ == "__main__":
    main()

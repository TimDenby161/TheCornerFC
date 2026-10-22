"""Skill scores only where the position uses them (DESIGN.md): the ranks check and the report.

Runs player_ratings.compute_player_ratings twice on a read-only connection, with the database
write and the line-up capture replaced: as the file now is, and as it was at BASE (read from git,
checked against its fingerprint). Every data output but the skill scores must be identical.
Nothing is written to the database and no API is called. Writes report.json next to this file.

    python experiments/skill_where/report.py
"""
import hashlib
import importlib.util
import inspect
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from thecornerfc.pipeline import db; from thecornerfc.evidence import lineup_snapshots; from thecornerfc.models import player_ratings as pr  # noqa: E402

HERE = Path(__file__).parent
OUT = HERE / "report.json"
BASE = "12790e628"         # the commit the change is made from
BASE_SHA256 = "7dd0b6d4d72303bbf06f1787f688297b1c8d4d8896a227b9976e1872406884bb"   # player_ratings.py there
PLAYERS = {290: "V. van Dijk", 306: "M. Salah", 1460: "B. Saka", 152982: "C. Palmer", 184: "H. Kane", 1100: "E. Haaland"}
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


def run(conn, module):
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


def main():
    conn = db.connect()
    conn.read_only = True
    said = conn.execute("select site.environment()").fetchone()[0]
    conn.rollback()
    new = run(conn, pr)
    base = run(conn, base_module())
    same = {k: base.get(k) == new.get(k) for k in COMPARED}
    groups = {p: pr.role_group(label) if label else None for p, _, label, _ in new["current"]}
    minutes = {p: m for p, _, _, m in new["current"]}
    names = dict(conn.execute("select player_id, name from players where player_id = any(%s)",
                              [list(new.get("skills") or {})]).fetchall())
    conn.rollback()
    top = {}
    for skill in ("solidity", "finishing"):
        listed = sorted(((v[skill], p) for p, v in (new.get("skills") or {}).items() if skill in v and minutes.get(p, 0) >= pr.SKILL_SAMPLE_MINUTES), reverse=True)[:TOP]
        top[skill] = [f"{names.get(p, p)} ({groups.get(p)}): {round(s, 1)}" for s, p in listed]
    count = lambda scores: dict(Counter(s for v in (scores or {}).values() for s in v))
    result = {"database": said, "base": BASE, "ranks_untouched": all(same.values()), "identical_outputs": same,
              "players": {n: {"before": (base.get("skills") or {}).get(p), "after": (new.get("skills") or {}).get(p)} for p, n in PLAYERS.items()},
              "top": top, "scored": {"before": count(base.get("skills")), "after": count(new.get("skills"))}}
    OUT.write_text(json.dumps(result, indent=1, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("database", "ranks_untouched", "scored")}, indent=1))


if __name__ == "__main__":
    main()

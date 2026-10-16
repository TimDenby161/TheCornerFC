"""Whether a scheduled job should do its work now, or skip because its slot's work is done.

The nightly, match-day and FPL jobs are started two ways: by the timer (timer/, a Cloudflare
Worker that starts them on the minute) and by GitHub's own schedules, kept as a back-up because
GitHub's are late or dropped (2026-10-16: the 01:17 nightly started about 06:00; match day ran
4.6 times a day instead of 48). Each job runs this first, in its `check` job:

    python scripts/already_ran.py nightly.yml

and does its work only if this prints run=true. The rule:
- a run started by hand (Run workflow, without source=timer) always works;
- otherwise it works unless another run of the same workflow has already *done the work* in the
  current slot: its work job succeeded and started at or after the slot began. A run that only
  skipped doesn't count, so a skip never makes the next slot skip too.

Slots: the nightly once a UTC day (its back-up tries skip once one has worked); match day each
half hour; FPL from 07:00, 13:00 and 19:00 UTC. Standard library only (it runs before anything
is installed). Reads GitHub with the job's own token (actions: read).
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

SLOTS = {"nightly.yml": "day", "matchday.yml": "half-hour", "fpl.yml": (7, 13, 19)}
WORK_JOB = {"nightly.yml": "sync", "matchday.yml": "matchday", "fpl.yml": "fpl"}


def slot_start(workflow, now):
    """When the current slot of this workflow began."""
    kind = SLOTS[workflow]
    if kind == "day":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if kind == "half-hour":
        return now.replace(minute=0 if now.minute < 30 else 30, second=0, microsecond=0)
    hours = [h for h in kind if h <= now.hour]
    if hours:
        return now.replace(hour=max(hours), minute=0, second=0, microsecond=0)
    return (now - timedelta(days=1)).replace(hour=max(kind), minute=0, second=0, microsecond=0)


def should_run(event, source, slot, done):
    """done: when the work job started, in each other run where it succeeded."""
    if event == "workflow_dispatch" and source != "timer":
        return True
    return not any(t >= slot for t in done)


def _when(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00")) if text else None


def work_done(get, workflow, slot, this_run):
    """Start times of the work job in other runs that succeeded, for runs touched since the slot."""
    since = (slot - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ")
    runs = get(f"actions/workflows/{workflow}/runs?created=%3E%3D{since}&per_page=50")["workflow_runs"]
    done = []
    for run in runs:
        if run["id"] == this_run or (_when(run["updated_at"]) or slot) < slot:
            continue
        for job in get(f"actions/runs/{run['id']}/jobs")["jobs"]:
            if job["name"] == WORK_JOB[workflow] and job["conclusion"] == "success" and job["started_at"]:
                done.append(_when(job["started_at"]))
    return done


def main(workflow):
    repo, token = os.environ["GITHUB_REPOSITORY"], os.environ["GH_TOKEN"]

    def get(path):
        request = urllib.request.Request(f"https://api.github.com/repos/{repo}/{path}", headers={
            "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)

    now = datetime.now(timezone.utc)
    slot = slot_start(workflow, now)
    event, source = os.environ.get("GITHUB_EVENT_NAME", ""), os.environ.get("SOURCE", "")
    done = [] if event == "workflow_dispatch" and source != "timer" else \
        work_done(get, workflow, slot, int(os.environ.get("GITHUB_RUN_ID", "0")))
    run = should_run(event, source, slot, done)
    print(f"{workflow}: started by {source or event}; slot from {slot:%Y-%m-%d %H:%M} UTC; "
          f"{len(done)} other run(s) did the work in it; {'working' if run else 'skipping'}")
    with open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a") as out:
        out.write(f"run={'true' if run else 'false'}\n")


if __name__ == "__main__":
    main(sys.argv[1])

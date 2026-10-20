---
name: promote-production
description: Promote what staging has tested to production for The Corner FC - check that main can move forward to staging's commit, that the commit holds its checks, list what goes live and any migration it needs, then stop for the owner before the one push that does it. Use when the owner asks to release, promote or go live.
---

# Promoting staging to production

Production is `main`: the C# site workflow deploys the live site from it (`site-csharp.yml`, to
the Azure web app `thecornerfc`) and the scheduled jobs run it.
Promotion moves `main` forward to the commit `staging` is on. It is never a merge and never new
work. GitHub refuses the push unless that commit passed `python`, `site` and `staging-check` and
was deployed to the `staging` environment; the checks below are so nothing is sent that would
be refused, and so the owner sees what is going live.

1. `git fetch origin`. Then `git merge-base --is-ancestor origin/main origin/staging`: if it
   fails, `main` has something `staging` lacks. Stop and say so; nothing is forced.
2. **What goes live.** `git log --oneline origin/main..origin/staging` and
   `git diff --stat origin/main..origin/staging`. If there is nothing, say so and stop.
3. **The checks on that commit.** `gh` is not installed here: ask the owner to confirm, on
   GitHub's page for the commit, that `python`, `site` and `staging-check` are green; or read
   `https://api.github.com/repos/TimDenby161/TheCornerFC/commits/<sha>/check-runs`.
4. **Staging is serving it.** The staging site's `/version` should name that commit (it is
   behind Cloudflare Access: the owner opens it).
5. **Migrations.** For every file in `db/migrations/` that the diff adds or changes: has it
   been applied to staging, and to production? A migration the new Python needs must be applied
   to production before the push; one that needs the new Python, after. Say which.
6. **Model versions.** If a fingerprinted file is in the diff, say which model versions will be
   new on the next run.
7. **Cost.** Say what going live adds to each service (`guide/costs.md`): API-Football calls a
   day, database size and reads, the site's load on its one B1 plan. Anything that would raise a bill the
   owner has not agreed to holds the promotion.
8. **Report and stop.** The commits, the checks, the migrations in order, the cost, and what the push
   does. Push only if the owner asks for this promotion now.
9. **The push**, exactly: `git push origin origin/staging:main`. No other form reaches `main`.
10. **Afterwards.** `https://thecornerfc.com/version` names the commit once the C# site workflow has deployed
   it (a few minutes). Tell the owner to watch the next Match day run. If the site is wrong:
   run the "C# site" workflow on `main` at the last good commit (or redeploy it in Azure → thecornerfc
   → Deployment Center), then fix through `staging`. If
   a job is wrong: revert on `staging` and promote the revert.

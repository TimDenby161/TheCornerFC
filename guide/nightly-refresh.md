# Nightly refresh

`python -m thecornerfc nightly` refreshes everything that changes. It runs these steps in order:
1. Re-checks league metadata, which marks each competition's current season.
2. Refreshes teams, fixtures/results and standings for every current season, plus any season that ended in the last 14 days.
3. Fetches stats for newly finished matches.
4. Pulls odds for upcoming matches.
5. Updates the club rankings (see [Club ranking](club-ranking.md)).
6. Projects the score and win/draw/loss chances for every upcoming fixture, and backfills any finished fixture that has no projection.

A normal night uses about 350–500 API calls and takes a few minutes. If one competition fails, the others still run, and the exit code is non-zero.

**Query cache.** The nightly job keeps a local copy of the big historical query results (every player appearance, finished fixture with xG, rank history and injury list) in `.cache/`, so it doesn't download them from Supabase every night. See `thecornerfc/pipeline/cache.py`.
- Each run, the database sends one fingerprint (row count and a hash) per week of matches, and only weeks whose fingerprint changed are downloaded again. New results, corrected scores, deleted rows and old matches added by a league backfill are all picked up.
- In GitHub Actions the folder is kept between runs with `actions/cache` (about 75 MB). Without it, for example on a new machine, the first run downloads everything once.
- A night's database egress fell from about 350 MB to about 30 MB.

The GitHub Actions workflow [`.github/workflows/nightly.yml`](../.github/workflows/nightly.yml) runs this command every day at 03:00 UTC. You can also start it by hand: open the **Actions** tab, choose **Nightly sync**, then **Run workflow**. It needs two repository secrets, under **Settings → Secrets and variables → Actions**:

- `API_FOOTBALL_KEY`
- `DATABASE_URL`: use the Supabase **Session pooler** string.

**Publication safety.** The nightly workflow only exports after the full critical nightly pipeline succeeds. A failed ingestion/ranking/prediction run leaves the workflow red and the site goes on showing the last export. The export is generated in a temporary directory, validated, swapped into `.export` in the job's working copy and then written to the database, which is what the site reads (nothing is committed: `.export` is not in the repository, see "The site's data in the database"). Invalid JSON, missing critical files or a major data collapse against the export before it stop publication before anything is replaced; with no earlier files beside it, the new export is compared with the stored one, counted in the database (`_stored_shape`).

**Adding a league.** Add its API-Football id to `config.LEAGUES`, and set a starting rank for it with `update leagues set starting_rank = … where league_id = …` once the league row exists. The next nightly run spots that the league has no fixtures yet and pulls every season in `config.DEFAULT_SEASONS`, then keeps it up to date. To get it sooner, run the **Backfill leagues** workflow ([`.github/workflows/backfill.yml`](../.github/workflows/backfill.yml)) with the new ids. It pulls every season's teams, fixtures, standings, match stats and odds, then re-ranks and republishes the site.

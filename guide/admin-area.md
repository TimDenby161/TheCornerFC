# The Admin area and the model change record

Three pages under `/admin` are the site administrator's only: **Model Change Tracker**,
**Model vs Market** and **Paper Simulation**. The two betting pages were public until
2026-10-13 (owner's decision). Nothing here changes a model, a bet or a stored prediction.

**The record is public too (owner's decision 2026-10-16, the most transparent model).** The
public page **The Model** (`/model`) shows the tracker's eight figures and every change with its
past and live results, from `model.json`: the nightly export writes it beside the Admin copy
(`site_record.public_model`), leaving out which database wrote it and the register's internal
mismatch notes. What stays here only: the model switch, where the two models part on matches to
come (both database functions, not documents), the paper bets and the Model vs Market tips. The
model against the bookmakers, market by market, was already public on the Stats page.

## Who gets in

- **An administrator is an address in `site_admins`**, set by hand in the SQL editor of each
  database (`db/migrations/20261013_admin_area.sql`; the address is never in the repository).
  It counts only once Supabase Auth has confirmed it. Being signed in is not enough, and
  neither is being the FPL entry's owner: it is its own list.
- **The server checks before anything runs.** `web/src/hooks.server.ts` asks the database
  (`am_admin()`, with the visitor's own token) for every address under `/admin`: pages, the
  data behind them, and anything added there later. Not signed in: sent to `/account`. Signed
  in and not an administrator: "not found". `web/src/lib/server/admin.ts` holds the gate.
- **The database checks again.** The pages' data are two rows of `admin_docs` (`bets`,
  `model_changes`), read only through `admin_doc()`, which answers `{"ok": false}` to anyone
  but an administrator and can't be called with the public key at all. So a page that forgot
  the gate would still be sent nothing.
- **No key that skips the check exists in the site.** The site holds the public key only;
  every read carries the visitor's token. The documents are never kept between requests and
  the pages answer `private, no-store`. The menu shows the Admin group only when the database
  has said yes for that request.
- **Both environments.** Each database has its own `site_admins`, `admin_docs` and change
  record, and each page says which it is showing. Staging's is test data.

To add or remove an administrator, in the SQL editor of that database:

```sql
insert into site_admins (email) values ('name@example.com') on conflict do nothing;   -- lower case
delete from site_admins where email = 'name@example.com';
```

## The paper bets

`export.export_bets` writes the whole record to `admin_docs` (`store_admin_doc`), never to
`.export` or `site.docs`, and deletes the public row it used to be. The nightly and match-day
jobs both run it. A local run stores nothing.

## The model change record

One file for each change that was ever proposed, `experiments/changes/MC-0000.json`:

| Part | Holds | After it is recorded |
|---|---|---|
| `registration` | What, why, how, the hypothesis, the expected improvement (numbers only with the source that recorded them before the test, otherwise empty and shown as "Not specified"), the success criteria, the code | Never edited |
| `events` | In order: a status, a result, a decision, a deployment, a reversal, a correction, a live test | Only added to |

- **Immutable where it counts.** The export copies both into `model_changes` and
  `model_change_events`, whose triggers refuse any update, delete or truncate
  (`thecornerfc/evidence/model_changes.py`, `sync`). The first version recorded stands. A file
  edited later is listed on the page as differing from the record, and the record is what is
  shown. A mistake is put right with a `correction` event.
- **An experiment can't pass as production.** Only a `production change` can carry a
  `deployed` event, a change counts as deployed only through that event, and every result a
  file gives is marked as an experiment's. `Accepted` (a decision) and deployed are counted
  apart.
- **The forward record is never typed in.** For a deployed match-model change the export works
  out how the predictions stored before each kickoff have done since: from its deployment day
  to the next change's, beside the live record of the same length just before, each scored
  against the bookmakers' prices on its own matches. The verdict compares the distance from
  the market, not the raw scores (the fixtures differ), says "too early" under 1,000 matches,
  and never credits a change alone. A deployment known only to the month is not measured.
- **A live test is counted, not read.** A `live_test` event names a registered prospective
  protocol, its first day and its target. The export counts the finished matches since then
  that have a prediction stored before kickoff, and the page shows that count beside the
  historical matches. No result of a blinded protocol is read to do it.
- **Live matches** (protocols P15 and P16). Until the club-rank release (MC-0028) every runnable
  change was scored on live matches against production by P15 (`experiments/prospective/live_p15.py`).
  The release changed the model they were compared with, so P13, P14 and P15 closed that day
  (`experiments/prospective/PROTOCOLS.md`, amendment 11). From then the Live tracking workflow runs
  `live_p17.py` on Mondays and Thursdays, and by hand, which reads the database once and runs two
  protocols: P16 scores the release against the version it replaced, re-created from each stored
  snapshot (a call is expected at about 27,000 matches, and a worse release is called as quickly
  as a better one); P17 scores the 13 ideas that can be run on top of the live model, on paper
  from the stored predictions, with nothing extra in production. Both go into the one document
  `live_tracking`, in P15's shape, so the page shows each change's live matches, gain and range,
  and says of the rest why they are not run. Both are judged by a confidence sequence, which holds
  however often it is looked at, so the ranges are wide. A future release rebases P17 by a dated
  amendment in the same commit instead of closing it.
- **The live match model** (MC-0029, `db/migrations/20261014_challenger_model.sql`, with
  `20261014_match_model_switch_fix.sql` mending the switch card's answer, and
  `20261014_match_model_compare.sql` the comparison above the button; how an idea
  gets here is `guide/idea-to-live.md`). Two match
  models run side by side in every run of the predictions: the base model and the same with A18's
  boosted trees (`thecornerfc/models/match_trees.py`). The card at the top of the Model Change
  Tracker names the live one and has the one button that switches it, through
  `admin_set_match_model()`, which only an administrator can call and which logs every switch.
  Above the button the card, Model Comparison (`admin_match_model_compare()`), sets the
  bookmakers, the base model and A18 side by side on log loss, Brier and right results: on A18's
  test on past matches and on the same finished matches since P18's start, with how many matches
  each column is on. The twenty upcoming fixtures where the two models differ most are folded
  away under it. P18's verdict is not on the card: it is in the change's own page and the table
  of changes. A Bookmakers column beside them (`20261015_match_model_compare_market.sql`)
  gives the closing prices with the margin taken out, averaged, as the Stats page does: on the
  finished matches with stored prices, with both models on those same matches under it, and for
  an upcoming fixture once prices are stored (about 14 days before kickoff). The log of switches is
  `match_model_switches`. The live model is the one the site, the paper bets and the fantasy
  models use, from the next run. Both models' last predictions before each kickoff are kept in
  `challenger_predictions` whichever is live, and P18 compares them on the same matches; the
  prospective snapshots, and so P6, P16 and P17, stay the base model's. While A18 is live, a
  match's "why" breakdown, which rebuilds the base model's margin, does not match and is left out.
- **Green means implement.** A row is green when there is statistical evidence that the change
  makes the model better, however small the gain (the owner's rule, 2026-10-14; the 0.002 bar no
  longer holds a proven gain back), on live matches or on a test that was not the matches it was
  built on, and the change is neither rejected nor deployed. Nothing else about a change is
  green. Releasing it is still a model release of its own, decided by the owner.
- **Check the files** with `python -m thecornerfc changes` (no database). The unit tests check
  them on every push.

### When a change is proposed (`/model-experiment`)

1. Before any result: add the next `MC-` file with the registration and nothing else, with
   `retrospective: false`. Commit it with the experiment's `DESIGN.md` and evaluator.
2. After each evaluation: add a `result` event naming its source file. A `development` figure
   is one on the matches the change was built on; a `backtest` is held out; a `prospective`
   one is a registered protocol read at its target.
3. When it is decided: add a `decision` event with the reason. Nothing is accepted or deployed
   by the record or by a result.
4. If the owner releases it: that is its own `production change` file, with a `deployed` event
   on the day it reaches `main`. Its forward record then builds by itself.
5. Each experiment whose idea went live in that release, at its own setting or inside a combined
   one, gets a `released` event naming the release (`"as": "MC-0028"`) and saying how it went
   in. The check refuses one that names a change not deployed by then. While the release is in
   production the experiment shows as "In production through MC-0028": the table of changes
   against the current version and the best gain waiting leave it out, and it is never itself
   deployed (no forward record, not in the running total). A16 and A24 (MC-0016, MC-0024) and
   their parts (MC-0013, MC-0014) were marked so on 2026-10-14.

What was imported on 2026-10-13: 27 changes, every one marked as written after its test except
the two formula candidates still blinded under P13 and P14. Three earlier production changes
(xG in the club rank, the injury adjustment, the first Poisson model) are not there: the day,
and for two the month, they went live was never recorded, and the repository's history was
rewritten on 2026-10-09.

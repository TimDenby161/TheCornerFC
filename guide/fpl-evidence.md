# Fantasy Premier League evidence

Evidence for validating a future FPL model: no fantasy model exists yet and nothing here
changes another model, export or the website. Fantasy EFL is out of scope. Apply
`db/migrations/20260927_fpl_evidence.sql` after the model-registry migration (it is also
in `db/schema.sql`); it has **not** been applied automatically. Databases that already have it
also need `db/migrations/20260927_fpl_evidence_guard_fix.sql`, which fixes the evidence trigger
rejecting `fpl_gameweeks`, `fpl_id_map` and `fpl_result_captures` inserts.

**Source and licensing (checked 2026-09-27).** FPL data comes from the JSON endpoints behind
fantasy.premierleague.com (`bootstrap-static/`, `fixtures/`, `event/{id}/live/`). They are
undocumented browser endpoints with no published API, licence, service level or stability
promise. The [Premier League Terms of Use](https://www.premierleague.com/en/terms-and-conditions)
say the sites "must not be used ... for commercial purposes" and that you may not "reproduce,
re-utilise or redistribute it (including ... creating a database ... that includes material
downloaded or otherwise obtained from the Website or App)", and they reserve copyright and
database rights. The FPL-specific terms page (fantasy.premierleague.com/help/terms) is rendered
by JavaScript and was not retrievable for review. Consequences here:

- Reachable endpoints are not treated as a right to use them, commercially or otherwise.
  Storing this evidence is itself the kind of database those terms restrict.
- Capture is **off** unless `FPL_CAPTURE_ENABLED=true`, and it also obeys the local-safety
  guards (`THECORNERFC_NO_API` blocks it; local runs need the override token).
- **Owner's decision (2026-09-27):** the owner chose to turn capture on and show FPL data
  publicly, accepting the risk from the terms above.
- **Owner's decision (2026-10-02, audit L3 / P2 (a)):** FPL data is no longer public. FPL's own
  terms (cl. 28(d), 29) forbid republishing it. The FPL predictions and My FPL team are shown to
  the owner only. The export and `fpl team` write them to `fpl_owner_docs` in Supabase (never
  `.export`), and the page reads them through `fpl_owner_data`, which answers only when
  the visitor is signed in as the owner (`db/migrations/20261004_fpl_owner_login.sql`; a
  passphrase until 2026-10-04). The FPL tab's model validation
  (`fpl.json`) uses no FPL data and is still published, but since 2026-10-04 the FPL and My FPL
  team tabs are in the menu for the signed-in owner only. Fetching FPL still breaches cl. 28(d); the
  `FPL_CAPTURE_ENABLED` kill switch remains.
  - The nightly workflow sets `FPL_CAPTURE_ENABLED=true` for its "Capture FPL state" step
    (`fpl capture` then `fpl results`). That step may fail without stopping the export.
  - The FPL tab shows each player's FPL position, price and status, and FPL's gameweeks,
    through `fpl_predictions` (owner only since 2026-10-02).
  - The owner also approved (2026-09-29) using FPL's squad lists to leave out predicted players
    FPL doesn't list at their club, e.g. players who have left since last season.
  - The owner also approved (2026-09-29) using FPL's captured gameweek results (defensive
    contribution counts, bonus and BPS) to fit and check the fantasy model's defensive
    contribution and bonus parts (experiments/fantasy_dc/).
  - The owner also approved (2026-09-30) using each player's own captured FPL
    defensive-contribution counts and minutes this season as an input to his own prediction
    (fantasy v1.4, experiments/fantasy_v1_4/), and chose v1.4 for the public FPL tab.
  - The owner also approved (2026-09-30) storing FPL's `penalties_order` for each player and
    using it as an input to penalty takers, and adding an "FPL assists" part fitted on captured FPL
    results (assists FPL gives that API-Football doesn't). This is fantasy v1.5
    (experiments/fantasy_v1_5/), which the owner chose for the public FPL tab.
  - The owner also approved (2026-09-30) using FPL's injury status, chance of playing and news
    (return dates) as an input to each player's chance of playing: fantasy v1.6
    (experiments/fantasy_v1_6/), shown on the public FPL tab.
  - Changing this is again the owner's decision. To stop, remove that workflow step. The
    export then falls back to our own positions and rounds, with no price.
- Only the fields needed for fantasy validation and the FPL tab are stored, not whole responses.
- Parsing is separate from `FplClient`, and the tables do not depend on FPL's response shape,
  so a licensed provider can replace the client without migrating the evidence.

```bash
FPL_CAPTURE_ENABLED=true python -m thecornerfc fpl capture   # schedule before each deadline, e.g. daily and deadline day
FPL_CAPTURE_ENABLED=true python -m thecornerfc fpl results   # after gameweeks; re-fetches until FPL marks points final
python -m thecornerfc fpl results --events 5 6                # force a re-check (corrections append)
```

Tables (seasons keyed by start year as API-Football; FPL player/team/fixture ids are per season,
FPL `code` is stable across seasons):

| Table | Holds |
| --- | --- |
| `fpl_gameweeks` | Each gameweek's deadline as observed. A moved deadline appends a row; view `fpl_gameweek_deadlines` gives the latest. |
| `fpl_captures` + `fpl_player_states` | Pre-deadline source state for the **next** gameweek: every player's price (`price_tenths`, 55 = 5.5m), FPL position/element type, club, status code, chance of playing this/next round, news text and time. The header keeps the known fixture schedule (no scores; `event_id` null = unscheduled) and the deadline as `effective_at`. |
| `fpl_id_map` | FPL club/player → API-Football id, with method and FPL names. View `fpl_id_map_current`. |
| `fpl_result_captures` + `fpl_player_results` | Actual points per player per gameweek, minutes, FPL's stat object and per-fixture `explain` (double gameweeks), with FPL's `finished`/`data_checked` flags. |
| `fantasy_prediction_snapshots` | Future fantasy model output: `model_version_id` (a `fantasy` registry version), the `input_capture_id` it read, deadline, per-player `predictions` (`expected_points` required; other numeric fields optional) and `inputs`. |

Timing follows the shared snapshot conventions. `captured_at` is taken straight after the FPL
reads, before mapping work. A capture is `prospective` only when both observed and inserted
before the deadline; a trigger downgrades a late insert to `late_observation`. A new capture is
stored only when that gameweek's content (players, fixtures, deadline) differs from its latest
capture, so repeated runs make a history of distinct states, and A → B → A keeps all three.
All tables block UPDATE, DELETE and TRUNCATE. Points corrections and mapping changes append.

Mapping is conservative. Clubs match on name (with a few FPL short-name aliases) and then short
code, against that season's Premier League clubs. Players match only within their mapped club
(current squad plus this season's league players), by these rules in order: full name, initial
plus surname, web name, then provider-name words all present in the FPL names. When a rule finds
two or more players, the result is `ambiguous` with the candidates listed, never a guess. Manual
fixes go in `thecornerfc/fantasy_games/fpl_overrides.json`, keyed by FPL code. FPL fixtures join API-Football
fixtures through the mapped clubs (league 39, season, home, away).

Fantasy prediction snapshots enforce more in the database: the version must be `fantasy`, the
input capture must be for the same gameweek and observed no later than the prediction, and
`prospective` requires an input capture. A future model should read inputs with
`fpl.state_as_of(conn, season, event_id, as_of)` and write with `make_prediction_snapshot` /
`append_prediction_snapshots` inside its own transaction.

`evaluate fantasy` scores the latest prospective snapshot per gameweek and model version made at
least `--hours-before` the currently known deadline. Labels are the latest points observation
marked `data_checked` and captured by `--as-of`, so later corrections do not leak into an earlier
report. It reports MAE, RMSE and bias of expected versus actual points per player, by model
version, gameweek and horizon, and counts snapshots without final points and predicted players
missing from the results. It deliberately stores no ownership, transfers or FPL's own `ep_next`.
Add those, with their own licensing check, if a later model or benchmark needs them.

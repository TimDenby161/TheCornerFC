# Lineup prediction and availability evidence

Apply `db/migrations/20260926_lineup_snapshots.sql` after the model registry migration
before running this code. It adds `lineup_prediction_snapshots` and
`official_lineup_snapshots`; current predicted lineups, player ratings, injuries and
historical outputs remain in their existing tables. No historical capture times are
invented or populated retrospectively.

`compute_player_ratings` now captures one immutable fixture/team prediction state
for every upcoming team it processes, including empty selections. It preserves the
existing rule: recent minutes ordering, score eligibility, one goalkeeper and up to
ten outfield players. The only intended selection change is that active manual
absences now exclude players through the same backend availability merge as API
reports. Lineup refresh frequency is unchanged: matchday does not rebuild player
ratings/lineups, so new availability affects selection at the next existing rebuild.

Each snapshot stores its lineup registry version, actual capture time, known kickoff
(`effective_at`), DB insertion time, seconds to kickoff, selected players with binary
`predicted_starter`, role/line, rating at prediction and availability state.
`start_probability` is explicitly null: this model provides no probability or
confidence estimate. The `selection_inputs` object retains ordered candidate minutes,
score-eligible candidates (raw score, position, minutes, final rating and binary
selection), unscored candidates and excluded IDs. Together with the resolved
availability and preserved selected output, these allow the selection to be audited
without relying on today's mutable injury lists or player ratings. They do not claim
to archive every upstream player-rating training row.

`availability.py` is the shared merge used by upcoming lineup selection and both
club/player availability exports:

- API reports apply only to their fixture/team. As before, every listed player,
  including doubtful players, is excluded by the lineup algorithm.
- Manual entries in `thecornerfc/models/absences.json` add exclusions. Optional `from` and
  `until` dates are inclusive and evaluated against fixture kickoff, not just today's
  date. Without `from`, an entry applies from observation onward; without `until`, it
  lasts until removed. Manual entries are never applied to historical replay.
- API or manual suspension reasons resolve to `suspended`. Past red cards alone are
  no longer displayed as confirmed upcoming bans: there is no reliable served-ban
  ledger here. Add an explicit dated manual suspension when confirmed externally.
- Overlapping API/manual entries retain both sources; manual entries do not assert
  fitness or cancel API reports. No evidence resolves to `not_reported`, not a claim
  that the player is fit. Historical API lists and prior snapshots are unchanged.

The snapshot's immutable `availability` object retains the exact resolved exclusions
and their source evidence: type/reason, manual dates/name, source, observation time,
and API row update time. Removing a manual entry later affects only future captures.
Current API injury upserts may retain older entries until upstream ingestion is
changed; row update times remain visible rather than asserting that every report is
fresh. The separate match-model missing-strength calculation retains its current
API-based calculation; this change unifies **lineup selection and availability display**,
not the match model's calibrated injury-margin inputs.

Official XI evidence is captured whenever existing fixture ingestion receives a
non-empty `startXI`, including stats/player/cup/coaches fetches and matchday result
refreshes. Snapshots retain provider source, actual observation time, kickoff,
formation, starters and substitutes, positions, grids and derived roles. Corrections
append new states; identical refetches keep the first observation. Empty/missing
lineups do not invent an official empty XI. No extra API calls or new polling schedule
are introduced, so the first official observation may be after kickoff. Such an
observation is valid comparison evidence, not proof the XI was known pre-match.

Both tables block UPDATE, DELETE and TRUNCATE through database triggers and use
INSERT/DO NOTHING for duplicate content. Lineup prediction snapshots are written in
the same transaction as the current player/lineup rebuild. They are `prospective`
only if captured and inserted before kickoff; a late insertion is labelled
`late_observation`. The historical lineup replay is not falsely saved as prospective.
Content changes (including availability, candidate input, rating, model version or
kickoff changes) append rows; observation timestamp changes alone do not.

Example measurement query (one row per predicted starter):

```sql
SELECT s.fixture_id, s.team_id, s.captured_at,
       s.seconds_to_kickoff / 3600 AS hours_to_kickoff,
       s.model_version_id, p->>'player' AS player,
       p->>'role' AS predicted_role, p->>'player_rating' AS rating
FROM lineup_prediction_snapshots s
CROSS JOIN LATERAL jsonb_array_elements(s.players) p
WHERE s.source='prospective';
```

When comparing with official XIs, choose an explicit observation policy (for example,
latest official observation per fixture/team) and retain its `captured_at` and source.
Do not silently substitute future official corrections into an as-known-at-time study.

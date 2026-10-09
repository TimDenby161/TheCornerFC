# Immutable odds and paper-simulation evidence

Apply `db/migrations/20260926_odds_paper_evidence.sql` after the registry and match
snapshot migrations, before deploying these writers. The migration creates only new
history/evidence tables and guards. It does not rewrite existing `odds`, `paper_bets`
or their history. No additional API requests, polling frequency changes or betting
selection rule changes are introduced.

`odds_observations` records pre-kickoff prices already received by `_store_odds`:
fixture, bookmaker, API market ID, selection, decimal odds, local `captured_at`,
provider update time, known kickoff and source. Invalid/absent prices at or below 1
are not meaningful observations. Consecutive identical prices with identical provider
update time and kickoff are suppressed; changed provider timestamps retain a new
observed state even when the price is unchanged. A price reverting A → B → A retains
all three states. Per-fixture transaction locks serialize concurrent writers for
this check. Old snapshots are never overwritten. The mutable `odds` table and its
opening-price behavior remain unchanged.

`paper_decisions` records each newly inserted paper bet in the same transaction:

- Registry strategy version and match-model version, plus the exact matching
  **prospective** match-prediction snapshot ID. Lookup compares all consumed W/D/L,
  over-2.5, BTTS and xG values, kickoff, and observation time; it never just assumes
  the newest snapshot matches. If none exists, placement fails and rolls back.
  Run the normal prediction path before placement after migrating.
- Actual decision capture time, known kickoff, market/selection/bookmaker, model
  probability, `1 / odds_taken` raw implied probability, decision-time fair market
  probability, odds, edge and its formula, one-unit stake and tags.
- The chosen bookmaker's complete-market overround (`sum(1 / odds) - 1`), where
  available. Fair probability remains the existing average of complete bookmaker
  markets after proportional margin removal, not just the chosen bookmaker's value.
- Full bookmaker price inputs for the market, their matching history references,
  consumed prediction values, candidate comparisons, already-taken groups and market
  states needed to inspect the existing selection. Strategy metadata includes rule
  constants, market definitions, goal-line calibration and source digests.

A current price inherited from before history capture began can have no observation
reference. In that case its exact decision-time price inputs are still saved, and
provenance explicitly says `legacy_current_price_without_history`; no earlier
observation time is invented. Existing paper bets are not retrospectively presented
as captured decisions. A long-running placement crossing kickoff is recorded with
its actual decision timestamp and `decided_before_known_kickoff=false`, rather than
backdating it. Evaluation should filter this flag as appropriate.

`paper_outcomes` attaches closing evidence and settlement to a decision without
updating it. Closing quotes come from the last recorded observations strictly before
that decision's known kickoff, using the chosen bookmaker and preserved selection
set. The attached evidence retains every quote reference/time, the comparison cutoff,
market inputs, result status and score. This is **last-observed pre-kickoff** information,
not guaranteed official closing prices; freshness is visible through quote timestamps.
Without qualifying history, closing metrics stay NULL rather than using later prices.
Unchanged repeated attachments are deduplicated; explicit corrections can append
another attachment. The current settlement job continues processing open bets only;
it does not automatically re-evaluate already settled results.

The two new metrics are distinct:

| Field | Definition |
| --- | --- |
| `price_clv` | `odds_taken / closing_odds - 1` |
| `probability_movement` | `closing_fair_probability - decision_fair_probability` |

The existing `paper_bets.clv` (`odds_taken * closing_fair - 1`) and frontend exports
remain for compatibility and are not relabelled as either new metric. All three new
tables block UPDATE, DELETE and TRUNCATE in normal operation. Mutable `paper_bets`
can continue serving settlement/UI state; it is not the authoritative immutable
record of the original decision.

```sql
SELECT d.paper_bet_id, d.captured_at AS decision_at, d.market, d.selection,
       d.strategy_version_id, d.prediction_snapshot_id, d.odds_taken,
       d.fair_probability, o.closing_odds, o.closing_fair_probability,
       o.price_clv, o.probability_movement
FROM paper_decisions d
LEFT JOIN LATERAL (
    SELECT * FROM paper_outcomes o WHERE o.decision_id=d.decision_id
    ORDER BY captured_at DESC, outcome_id DESC LIMIT 1
) o ON true;
```

These records support reproducible measurement; they establish no profitability claim.

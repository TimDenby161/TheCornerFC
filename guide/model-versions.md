# Shared model versions and snapshot conventions

Model provenance is registered in `model_versions`, through
`thecornerfc.evidence.model_versions.register_model_version`. Supported `ModelType` values
are `club`, `player`, `lineup`, `match`, `betting` (including paper strategies), and
`fantasy` (reserved for future models). The registry does not change model formulas, historical outputs, prediction upsert
semantics or paper-bet identities. New immutable match snapshots use it as described below.
No guessed versions or observation times are assigned to historical rows.

Apply `db/migrations/20260926_model_versions.sql` to an existing database through
your normal authorised migration process. Fresh `init-db` also includes the exact
same SQL. The migration is repeatable, creates only the registry/index/immutability
trigger, enables RLS without public policies, and does not update existing datasets.
It has **not** been applied automatically by this implementation.

Register once at the orchestration boundary and pass the resulting ID to domain
writers. Keep release labels and explicit, relevant configuration together there,
rather than putting version strings in individual calculation functions:

```python
from thecornerfc.evidence.model_versions import ModelType, current_code_sha, register_model_version

model_version_id = register_model_version(
    conn, ModelType.MATCH, "initial-provenance-release",
    code_sha=current_code_sha(),
    configuration={"input_club_model_version_id": club_version_id},
    notes="First explicitly versioned match-model deployment",
)
# Pass model_version_id to a domain snapshot writer; caller owns commit/rollback.
```

The example is the convention for writer integration. Existing mutable outputs are
not retroactively versioned; the match snapshot writer below now registers versions. Include all relevant model parameters, upstream
model-version IDs, input dataset revisions and evaluation choices explicitly.
Never pass `.env`, credentials, connection strings or entire module globals.
Obvious credential keys are rejected, but callers must still choose safe metadata.
No configuration or environment secrets are collected automatically.

Registry fields include `model_version_id`, `model_type`, `version_name`, `code_sha`,
JSON `configuration`, optional training/evaluation window pairs, DB-generated
`created_at`, and `notes`. Windows are timezone-aware, half-open `[start, end)`;
NULL pairs mean unknown/not applicable. A missing SHA remains NULL. Git discovery
returns NULL for a dirty tree because a commit alone cannot describe those edits.
Use committed code for reproducible releases.

Identity is a SHA-256 digest of canonical metadata, prefixed `mv_`. Re-registering
identical metadata returns the same ID without overwriting its creation time.
Changing configuration, SHA, windows, label, type or notes creates a new identity;
JSON key order does not. JSON numeric types are significant (`1` versus `1.0`).
Labels are human-readable and not unique identifiers. Registry UPDATE/DELETE is
blocked by a trigger: corrections become new versions. Operational retention/admin
privileges remain the database administrator's responsibility.

Snapshot timestamps have one shared meaning:

| Column | Meaning | How to populate |
| --- | --- | --- |
| `created_at` | When the database inserted the row | `timestamptz NOT NULL DEFAULT clock_timestamp()`; omit from inserts |
| `captured_at` | When source/model state was actually observed | Explicit timezone-aware observation time, normalised to UTC |
| `effective_at` | Event time, such as kickoff or fantasy deadline | Explicit timezone-aware domain event time, normalised to UTC |

`snapshot_times(captured_at=..., effective_at=...)` validates and normalises the
last two values; it deliberately does not generate `created_at`. Capture observation
time at the source boundary, not after a long computation. For reconstructions,
capture the actual reconstruction/observation time and record an explicit source
such as `backfill`; do not backdate it to imply pre-event availability. Therefore
`captured_at > effective_at` is allowed. Use captured time and source when selecting
live evaluation inputs to avoid look-ahead leakage. A postponed kickoff does not
rewrite an old snapshot: a new observation gets a new row/event time.

Use separate domain tables when snapshot writers are introduced, for example
`club_rating_snapshots`, `player_rating_snapshots`, `lineup_snapshots`,
`match_prediction_snapshots`, `paper_strategy_snapshots`, and eventually
`fantasy_prediction_snapshots`. Match, lineup, paper and fantasy snapshot tables are implemented below;
the club and paper-strategy names are future design conventions, not tables created now.
Each should have domain/entity keys, typed output columns, an FK to
`model_versions(model_version_id)` with restricted deletion, the three timestamps,
and explicit live/backfill/source provenance. Validate the referenced model type
at the domain writer boundary (an FK alone does not validate type). Define a
retry/idempotency key per domain/observation; do not use only event ID plus version,
since multiple observations of the same event must coexist. Snapshots are append-only;
mutable latest-state projections remain separate. Avoid a universal JSON snapshot table.

Current `fixture_predictions`, `predicted_lineups`, `fixture_team_ratings`,
`team_rankings` and similar mutable/rebuilt tables are not silently reclassified as
immutable snapshots. Existing `updated_at`, `placed_at`, `kickoff`, settlement and
backfill semantics stay intact. Paper betting `early`/`late` describes placement
timing, not model identity; future paper snapshots should reference the betting
version and the match/lineup versions whose outputs were used.

Tests: `python -m unittest discover -s tests`. The optional real PostgreSQL migration
test requires `MODEL_VERSION_TEST_DSN` pointing at a disposable test database with
schema-creation privileges; it tests reapplication, deduplication, immutability,
DB creation time and preservation of unrelated history, then rolls back its schema.

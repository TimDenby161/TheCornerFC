# The Corner FC

Pulls football data from [API-Football](https://www.api-football.com/) (v3) into a Supabase Postgres database.

**Leagues:** Premier League, Championship, League One, League Two, La Liga, Serie A, Bundesliga, Ligue 1. Edit them in `thecornerfc/config.py`.
**Data:** leagues/seasons, teams and venues, fixtures and results, per-team match statistics (including xG), standings, and pre-match odds.

## Where everything is written down

Each topic has its own page in `guide/`. A note elsewhere that says "README: Accounts" means the page of that name here.

- [Setup](guide/setup.md)
- [Local development safety](guide/local-safety.md)
- [Syncing](guide/syncing.md)
- [Nightly refresh](guide/nightly-refresh.md)
- [Players and injuries](guide/players-and-injuries.md)
- [Player ranks and team XI ratings](guide/player-ranks.md)
- [Club ranking](guide/club-ranking.md)
- [National team ranking](guide/national-team-ranking.md)
- [Match predictions](guide/match-predictions.md)
- [Paper betting](guide/paper-betting.md)
- [EFL Fantasy](guide/efl-fantasy.md)
- [Website](guide/website.md)

The tables and the records they keep:

- [Tables](guide/tables.md)
- [API usage and quota protection](guide/api-usage.md)
- [Pipeline and dataset health](guide/pipeline-health.md)
- [Shared model versions and snapshot conventions](guide/model-versions.md)
- [Immutable match prediction capture](guide/match-prediction-capture.md)
- [Lineup prediction and availability evidence](guide/lineup-evidence.md)
- [Immutable odds and paper-simulation evidence](guide/odds-and-paper-evidence.md)
- [Immutable daily player-rating history](guide/player-rating-history.md)
- [Fantasy Premier League evidence](guide/fpl-evidence.md)
- [My FPL team](guide/my-fpl-team.md)
- [The site's data in the database (step 1)](guide/site-data.md)
- [Accounts](guide/accounts.md)
- [Paid tier (built in part, switched off)](guide/paid-tier.md)
- [Retention and removing a person](guide/retention.md)
- [Fantasy expected points (v1.1, evidence only)](guide/fantasy-expected-points.md)
- [Chronological evaluation](guide/evaluation.md)

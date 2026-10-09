# Fantasy expected points (v1.1, evidence only)

`thecornerfc/fantasy_games/fantasy.py` gives each Premier League player's expected FPL points per fixture from:
- expected minutes (P(start), P(sub), minutes as starter and as sub)
- the match model's team goals, shared out by shots on target and key passes (not by overall rank)
- clean sheets and goals conceded from the same Poisson rates
- goalkeeper saves

Bonus, cards, own goals and penalties are not modelled. The backtest and its limits are in
`experiments/fantasy_v1/REPORT.md`. It could not be compared with official FPL expected points or
price, because no FPL data is captured.

The parameters are frozen in `thecornerfc/fantasy_games/fantasy_params.json`. After predictions,
`fantasy_snapshots.capture_safely` stores every component for every player in upcoming fixtures in
`fantasy_fixture_snapshots`. The nightly run covers the next 8 days; the match-day run covers kickoffs
within 3 hours. Each row also stores the timed availability and the recent-average and PPG
benchmark values used by protocol P8 (`experiments/prospective/`).

- It is keyed by API-Football ids, so it needs no FPL data.
- It is append-only, and a repeated identical state is not stored again.
- A capture failure is logged and never fails the run. Nothing reads the table.
- `python -m thecornerfc fantasy` captures by hand.

Apply `db/migrations/20260927_fantasy_fixture_snapshots.sql` after the model-registry migration.
Until then the capture logs a warning and skips.

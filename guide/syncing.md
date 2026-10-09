# Syncing

```bash
python -m thecornerfc sync all                      # everything, seasons 2020-2026
python -m thecornerfc sync fixtures --seasons 2026  # refresh the current season only
python -m thecornerfc sync stats --limit 5000       # stats backfill, resumable
python -m thecornerfc sync odds                     # upcoming fixtures' odds
```

Run `leagues` before the other targets, because every other table references it. `sync all` does this for you.

Every sync is an upsert, so you can re-run it safely. Match stats are fetched only for finished fixtures that don't have them yet. Each call covers 20 fixtures via `/fixtures?ids=`, so one season across all 8 leagues costs about 170 calls. Syncing stops cleanly when the daily quota drops to `API_DAILY_RESERVE`. Run it again the next day to carry on.

API-Football only serves **odds** from about 14 days before kickoff, so you can't backfill history. Run `sync odds` daily. Each run keeps the latest price per bookmaker and market (the markets are listed in `ODDS_BET_IDS`).

# Players and injuries

For the 22 leagues in `config.PLAYER_LEAGUES`, the sync pulls the tables below. They are the English top five, La Liga, Serie A, the Bundesliga and Ligue 1, plus Turkey, Saudi Arabia, MLS, Portugal, the Netherlands, Belgium, Greece, Ukraine, Czechia, Austria, Norway, Azerbaijan and Slovakia.
- `players`: profiles.
- `player_seasons`: one row per player per club per league-season, with appearances, starts, minutes, rating, goals, assists, shots, passes, tackles, duels, cards and penalties.
- `injuries`: players listed as missing or doubtful for each fixture, with the reason.

The nightly job refreshes the current season. To backfill or add a league:

```bash
python -m thecornerfc sync players  --leagues 39 140 --seasons 2024 2025
python -m thecornerfc sync injuries --leagues 39 140 --seasons 2024 2025
```

Cup and European ties have lists of their own (a UEFA ban shows only there), so the nightly job also fetches the whole list of each competition in `config.CUP_INJURY_LEAGUES` (one call each). It keeps only the clubs from the 22 leagues: those are the clubs whose predicted XIs it uses. The match-day run fetches each such tie's list once more, in the run 60 to 90 minutes before kickoff. That's about 8 calls a night, plus one per tie.

Players out that the lists miss (League Two clubs often have no list) go in `thecornerfc/models/absences.json` by club id, with an optional `until` date. The export adds them to the club's list for its next match.

API-Football's injury lists run from 2021 for the big five, the Championship, Turkey, the Netherlands, MLS and Norway. Elsewhere there's little or nothing before 2025.
- The National League has no player data for 2025 or 2026.
- Azerbaijan has no match ratings, and no player data for 2025 or 2026.
- Ukraine and Slovakia have little or no player data for 2026 so far.

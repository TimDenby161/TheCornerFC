# EFL Fantasy

The **EFL Fantasy** tab predicts [Fantasy EFL](https://fantasy.efl.com) points for Championship, League One and League Two players and clubs over the next six gameweeks (`thecornerfc/fantasy_games/efl_fantasy.py`). Nothing is read from the Fantasy EFL site.

**Owner only since 2026-10-04 (audit L11, owner's decision).** Fantasy EFL's terms bar commercial use of the game (cl. 2.5, 8.1.7), so the tab is shown only to the signed-in owner, like the FPL tabs. The nightly export writes `efl_predictions` to `fpl_owner_docs` in Supabase, never `.export`, and the page reads it through `fpl_owner_data`. Older copies of `.export/efl_predictions.json` remain in git history.

- **The football** is the FPL model's (v1.6 parameters) run on these three leagues' own matches, without FPL's inputs: expected minutes, goals, penalties, assists, clean sheets, goals conceded, saves and cards.
- **Fantasy EFL's extra actions** (tackles, blocks, interceptions, key passes and shots on target) use each player's own rates per 90 over the last year, pulled toward his role group's. API-Football has no clearances, so defenders get a fixed rate for their role.
- **Clubs** score from the match model's win and draw chances and Poisson goals.
- **Gameweeks** run Thursday to Wednesday (UK time), numbered from the week of the season's first match.
- **Positions** are guessed from match data. To correct one, add `"<API-Football player id>": "D"` to `thecornerfc/fantasy_games/efl_positions.json`.
- **Suggested team:** the tab picks the best 7 + 2 for a gameweek (1-2-2-2, 1-2-3-1 or 1-3-2-1, at most two players a club).

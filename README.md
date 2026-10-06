# The Corner FC

Pulls football data from [API-Football](https://www.api-football.com/) (v3) into a Supabase Postgres database.

**Leagues:** Premier League, Championship, League One, League Two, La Liga, Serie A, Bundesliga, Ligue 1. Edit them in `thecornerfc/config.py`.
**Data:** leagues/seasons, teams and venues, fixtures and results, per-team match statistics (including xG), standings, and pre-match odds.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env        # then fill in API_FOOTBALL_KEY and DATABASE_URL
python -m thecornerfc status    # checks the API key and shows quota
python -m thecornerfc init-db   # creates the tables in Supabase
```

For `DATABASE_URL`, go to the Supabase dashboard, click **Connect**, and copy the **Session pooler** string. The direct connection only works over IPv6.

## Local development safety

Local runs default to safe mode through `.env`:

```bash
THECORNERFC_MODE=local
THECORNERFC_READ_ONLY=true
THECORNERFC_NO_API=true
READ_ONLY_DATABASE_URL=postgresql://readonly_user:...@.../postgres
```

In this mode the app can read the latest production Supabase data, run read-only analysis, export `docs/data` locally and preview the static site, but it refuses database-write commands and refuses API-Football access before making network requests. Use a genuinely read-only Supabase/Postgres role for `READ_ONLY_DATABASE_URL`; the application also sets read-only transactions, but database permissions are the real safety net.

Command safety:

| Command | Local safe mode? | Needs DB writes? | Needs API-Football? |
|---|---:|---:|---:|
| `python -m thecornerfc export` | Yes | No | No |
| Static website preview from `docs/` | Yes | No | No |
| Read-only SQL/evaluation scripts using `connect()` | Yes | No | No |
| `python -m thecornerfc status` | Blocked | No | Yes |
| `python -m thecornerfc sync ...` | Blocked | Yes | Yes |
| `python -m thecornerfc nightly` | Blocked | Yes | Yes |
| `python -m thecornerfc matchday` | Blocked | Yes | Yes |
| `python -m thecornerfc init-db` | Blocked | Yes | No |
| `python -m thecornerfc rank` | Blocked | Yes | No |
| `python -m thecornerfc predict` | Blocked | Yes | No |
| `python -m thecornerfc player-ratings` | Blocked | Yes | No |
| `python -m thecornerfc fantasy` | Blocked | Yes | No |

Intentional local writes or API calls require all relevant safety flags to be turned off and `THECORNERFC_LOCAL_OVERRIDE=I_UNDERSTAND_THIS_CAN_WRITE_PRODUCTION_DATA_AND_USE_API_QUOTA`. GitHub Actions sets production mode explicitly, so the scheduled production pipelines continue to use the production Supabase credential and API-Football key.

## Syncing

```bash
python -m thecornerfc sync all                      # everything, seasons 2020-2026
python -m thecornerfc sync fixtures --seasons 2026  # refresh the current season only
python -m thecornerfc sync stats --limit 5000       # stats backfill, resumable
python -m thecornerfc sync odds                     # upcoming fixtures' odds
```

Run `leagues` before the other targets, because every other table references it. `sync all` does this for you.

Every sync is an upsert, so you can re-run it safely. Match stats are fetched only for finished fixtures that don't have them yet. Each call covers 20 fixtures via `/fixtures?ids=`, so one season across all 8 leagues costs about 170 calls. Syncing stops cleanly when the daily quota drops to `API_DAILY_RESERVE`. Run it again the next day to carry on.

API-Football only serves **odds** from about 14 days before kickoff, so you can't backfill history. Run `sync odds` daily. Each run keeps the latest price per bookmaker and market (the markets are listed in `ODDS_BET_IDS`).

## Nightly refresh

`python -m thecornerfc nightly` refreshes everything that changes. It runs these steps in order:
1. Re-checks league metadata, which marks each competition's current season.
2. Refreshes teams, fixtures/results and standings for every current season, plus any season that ended in the last 14 days.
3. Fetches stats for newly finished matches.
4. Pulls odds for upcoming matches.
5. Updates the club rankings (see below).
6. Projects the score and win/draw/loss chances for every upcoming fixture, and backfills any finished fixture that has no projection.

A normal night uses about 350–500 API calls and takes a few minutes. If one competition fails, the others still run, and the exit code is non-zero.

**Query cache.** The nightly job keeps a local copy of the big historical query results (every player appearance, finished fixture with xG, rank history and injury list) in `.cache/`, so it doesn't download them from Supabase every night. See `thecornerfc/cache.py`.
- Each run, the database sends one fingerprint (row count and a hash) per week of matches, and only weeks whose fingerprint changed are downloaded again. New results, corrected scores, deleted rows and old matches added by a league backfill are all picked up.
- In GitHub Actions the folder is kept between runs with `actions/cache` (about 75 MB). Without it, for example on a new machine, the first run downloads everything once.
- A night's database egress fell from about 350 MB to about 30 MB.

The GitHub Actions workflow [`.github/workflows/nightly.yml`](.github/workflows/nightly.yml) runs this command every day at 03:00 UTC. You can also start it by hand: open the **Actions** tab, choose **Nightly sync**, then **Run workflow**. It needs two repository secrets, under **Settings → Secrets and variables → Actions**:

- `API_FOOTBALL_KEY`
- `DATABASE_URL`: use the Supabase **Session pooler** string.

**Publication safety.** The nightly workflow only exports after the full critical nightly pipeline succeeds. A failed ingestion/ranking/prediction run leaves the workflow red and the site goes on showing the last export. The export is generated in a temporary directory, validated, swapped into `docs/data` in the job's working copy and then written to the database, which is what the site reads (nothing is committed: `docs/data` is not in the repository, see "The site's data in the database"). Invalid JSON, missing critical files or a major data collapse against the export before it stop publication before anything is replaced; with no earlier files beside it, the new export is compared with the stored one, counted in the database (`_stored_shape`).

**Adding a league.** Add its API-Football id to `config.LEAGUES`, and set a starting rank for it with `update leagues set starting_rank = … where league_id = …` once the league row exists. The next nightly run spots that the league has no fixtures yet and pulls every season in `config.DEFAULT_SEASONS`, then keeps it up to date. To get it sooner, run the **Backfill leagues** workflow ([`.github/workflows/backfill.yml`](.github/workflows/backfill.yml)) with the new ids. It pulls every season's teams, fixtures, standings, match stats and odds, then re-ranks and republishes the site.

## Players and injuries

For the 22 leagues in `config.PLAYER_LEAGUES`, the sync pulls the tables below. They are the English top five, La Liga, Serie A, the Bundesliga and Ligue 1, plus Turkey, Saudi Arabia, MLS, Portugal, the Netherlands, Belgium, Greece, Ukraine, Czechia, Austria, Norway, Azerbaijan and Slovakia.
- `players`: profiles.
- `player_seasons`: one row per player per club per league-season, with appearances, starts, minutes, rating, goals, assists, shots, passes, tackles, duels, cards and penalties.
- `injuries`: players listed as missing or doubtful for each fixture, with the reason.

The nightly job refreshes the current season. To backfill or add a league:

```bash
python -m thecornerfc sync players  --leagues 39 140 --seasons 2024 2025
python -m thecornerfc sync injuries --leagues 39 140 --seasons 2024 2025
```

Players out that the lists miss (League Two clubs often have no list) go in `thecornerfc/absences.json` by club id, with an optional `until` date. The export adds them to the club's list for its next match.

API-Football's injury lists run from 2021 for the big five, the Championship, Turkey, the Netherlands, MLS and Norway. Elsewhere there's little or nothing before 2025.
- The National League has no player data for 2025 or 2026.
- Azerbaijan has no match ratings, and no player data for 2025 or 2026.
- Ukraine and Slovakia have little or no player data for 2026 so far.

## Player ranks and team XI ratings

`thecornerfc/player_ratings.py` gives every player a **rank from 0 to 100** from his stats, for the 13 leagues with per-match player data (`config.MATCH_PLAYER_LEAGUES`). That's the 10 injury-model leagues plus League One, League Two and the Saudi Pro League, whose match-by-match data runs from 2020/21. Players are always compared with the players in the original 10 leagues (`config.RATING_REFERENCE_LEAGUES`) for stat averages, percentiles and the "regulars" sample. So adding a league doesn't move everyone else's rank. Everything is **backdated**: it's replayed in kickoff order, so every number is what could have been known before that match.

**Player rank**
1. Take the player's last 20 appearances within 18 months.
2. Work out his **role** from the line-ups. `thecornerfc/positions.py` turns each starter's grid position and the team's formation into a role: GK, LB, CB, RB, LWB, RWB, DM, CM, AM, LM, RM, LW, RW or ST. For example, 4-2-3-1 row 4 gives LW, AM and RW. His role is the one he's started in most over the window; players only seen as substitutes use their broad position. A **season** rank uses the role group he started the most minutes in that season, with the roles summed by group. So 30% LW + 30% RW + 40% ST is rated as a winger, not a striker. Roles are compared in groups, with left and right together: GK, CB, full-back, wing-back, DM, CM, AM, winger and ST.
3. Work out his per-90 stats and ratios, with weights set for each role group. **Only counted stats are used.** API-Football's own match rating is not an input (it was 10–12% for outfield players and 75% for keepers until October 2026), and neither are fouls and cards. The weights are shares that add up to 100:

   | Role group | Weights |
   |---|---|
   | Goalkeeper | Save % 50, pass accuracy 25, goals conceded 25 (lower is better) |
   | Centre-back | Duels won 23, passes 19, tackles + interceptions 16, times dribbled past 15 (lower is better), pass accuracy 11, team xG conceded while he played 9 (lower is better), blocks 7 |
   | Full-back | Key passes 18, times dribbled past 15 (lower is better), tackles + interceptions 13, passes 12, pass accuracy 9, assists 8, goals 6, dribbles won 6, shots on target 5, failed dribbles 4 (lower is better), duels won 4 |
   | Wing-back | Key passes 20, assists 14, tackles + interceptions 12, passes 9, dribbles won 8, times dribbled past 7 (lower is better), pass accuracy 7, goals 7, shots on target 6, duels won 5, failed dribbles 5 (lower is better) |
   | Defensive mid | Passes 22, tackles + interceptions 20, duels won 18, key passes 12, times dribbled past 12 (lower is better), pass accuracy 11, blocks 2, shots on target 2 |
   | Central mid | Passes 23, key passes 17, duels won 13, goals 10, tackles + interceptions 9, assists 8, dribbles won 7, pass accuracy 7, shots on target 6 |
   | Attacking mid | Key passes 22, shots on target 18, goals 18, assists 15, dribbles won 10, passes 7, duels won 6, pass accuracy 3 |
   | Winger | Goals 25, shots on target 22, key passes 21, dribbles won 11, assists 9, passes 6, duels won 6 |
   | Striker | Goals 37, shots on target 28, key passes 10, duels won 9, assists 7, passes 6, dribbles won 4 |

   - **Where the weights come from.** The owner set them position by position in October 2026 (`experiments/player_no_rating`), judging each on where known players landed, starting from weights that had been checked two ways:
     - *Against results (2021–26):* with club rank as the baseline, match rating added nothing. Shots on target, key passes, passing volume and duels won did. Goals, assists and save % beyond those were mostly luck that evened out.
     - *For repeatability:* how well a stat repeats from one season to the next, overall and for players who changed club. For centre-backs with 1,500+ minutes in back-to-back seasons: times dribbled past 0.63 (0.55 after a move: a player trait), team xG conceded 0.42 (0.29: mostly the team), penalties conceded 0.04 (noise, not used), goals 0.17 (luck, not used). Goals per 90 repeat 0.44 for strikers who changed club, 0.36 for wingers and 0.27 for attacking mids.
   - **Without the match rating** the outfield ranks kept the same order (0.98 to 0.99 by role group) and repeated from season to season as well as before (0.56 to 0.57 for everyone, 0.45 to 0.46 for players who changed club).
   - **Failed dribbles** are dribbles attempted minus dribbles won (`fixture_players.dribbles`, `dribbles_won`): possession given away. A regular full-back fails 0.63 per 90.
   - **Wing-backs** (LWB, RWB) are a role group of their own. They were rated as full-backs until October 2026, on a defender's weights.
   - **Goalkeepers** have little that repeats. Save % repeats 0.18 from one season to the next. Pass accuracy repeats 0.69, and 0.54 for keepers who changed club, but it is partly style (short passing against long kicking). Goals conceded repeats 0.34 and mostly measures the defence in front of him; it is there by the owner's choice. Saves per 90 (0.18 after a move) and goals prevented against xG (0.05) are noise and not used.
   - **Keeper rank leans on club level.** A keeper's stats percentile is mostly noise, so stretching it over the whole scale gave near-random ranks. A keeper's rank is 100 × club rank ÷ 1200 − 6, plus 0.2 × (stats percentile − 50). Club level carries it, since good clubs sign good keepers, and the stats move it by up to about ±10.
   - **Backup keepers.** A keeper with no minutes this season, at a club that has played 5 or more league matches, and who isn't on the injury list, is marked down by 20%, as a keeper who has played a minute already was. Before this a second choice who hadn't played yet kept his old level.
4. Compare each stat with other players in the same role group.
5. **Mark down players with few minutes:** pull them towards a below-average level (−0.5, weighted as 900 minutes), not towards the average.
6. Turn the result into a **percentile among regulars in that role group**: 50 is an average regular, and 90 is better than 90% of them.
7. **Club level first, stats adjust it** (all players): rank = 100 × club rank ÷ 1200 − 8, plus 0.3 × (stats percentile − 50). The −8 (it was −12) puts an average Premier League regular at about 75. Club level sets the base, because being a regular for a strong club is good evidence of quality, and stats move a player by up to about ±15 (keepers ±10, since their stats are noisier). **Stats count for more at a strong club:** the 0.3 is the weight at a club rated 950 or below, and it rises to 0.6 at 1,080 and above (`TOP_STATS`). Before this an ordinary season at a top club cost nothing, and the club's level alone put an average regular there in the world's top ten for his position; at weaker clubs nothing changes, so big numbers in weaker leagues count as they did. **Elite seasons get extra:** an outfield player earns 1 more point for each percentile above the 90th, up to +10, so a club's level doesn't cap a great player. Everyone below the 90th percentile is unchanged. **The top of the scale is a soft ceiling rather than a hard cap at 100:** above 86, a rank r becomes 86 + 14 × (1 − e^(−(r − 86) / 14)). So the best still spread out below 100 instead of piling up against it, in the same order. Without it, Van Dijk read about 99 in every season and six players had a current rank of exactly 100. With it:

| Player | Season ranks |
|---|---|
| Van Dijk | 91–94.5 |
| Davies | 86–91 |
| Messi at PSG (LT about 1040), 22/23 | 94.2, up from 87 before the elite bonus |
| Kane | up to 96.4 |

The same ceiling applies to keepers.

**Low ranks are lifted more than high ones.** After the ceiling, every rank's gap to 100 is multiplied by 0.85: 95 becomes 95.8, 75 becomes 78.8, and 60 becomes 66. Adding a constant lifted everyone equally, but the lower half of the scale was spread too far down. Squad players at mid-table clubs sat in the 60s, for example Awoniyi at 66. The starting level (64.3) and the hand-set teenage steps (+3.4 a year at 17, +1.7 more for each year younger) are on the same scale. `GAP_SCALE` in `thecornerfc/player_ratings.py`.

**Positions aren't worth the same.** Stats are compared within a role group, so without an adjustment a 97th-percentile full-back counted for more than a 94th-percentile striker. That put Davies above Haaland and Alexander-Arnold above Kane. So each role group's stats part is scaled, and a flat offset is added:

| Role group | Stats × | Offset |
|---|---|---|
| Striker | 1.0 | +2 |
| Winger, attacking mid | 1.0 | +1 |
| Central mid | 0.85 | 0 |
| Defensive mid | 0.85 | −1 |
| Centre-back | 0.7 | −2 |
| Full-back, wing-back | 0.7 | −3 |

These are set by judgement. The results data can't measure position value, because the XI ratings added nothing on top of the club ranks. The settings are `POSITION_STATS` and `POSITION_OFFSET` in `thecornerfc/player_ratings.py`. The club rank is the clubs' **LT ALGO going into each match** he played for them (weighted by his minutes), rather than their rank on the day, so one hot or cold run doesn't swing a whole squad. It's stored as `team_rank_history.lt_before`.

**Where it's stored**
- `fixture_player_ranks` holds each player's rank going into every match. It's a separate table, cleared and refilled on each run, so the 700,000-row `fixture_players` table isn't rewritten every night.
- `players.current_rank` holds his rank now, which is his season rank for the current season (see season ranks below), so the players list follows the same age curve and minutes weighting as his seasons. The last-20-appearances rank above is what goes into each match (`fixture_player_ranks`) and the team XI ratings.

**Team ratings** (`fixture_team_ratings`, for every match and team)
- **Predicted XI rating:** the average rank of the predicted XI. That's 1 goalkeeper plus 10 outfield players with the most minutes over the last 5 matches, leaving out anyone on the injury list.
- **Recent rating:** the average rank of the XIs actually started in the last 5 matches.
- **Actual XI rating:** the average rank of the XI that started, for finished matches.
- **By line:** the same averages for the goalkeeper, defenders, midfielders and forwards, for both the XI that started and the predicted XI (`fixture_team_ratings.actual_gk`, `actual_def`, `actual_mid`, `actual_fwd` and the `predicted_…` columns). A starter's line is the role he started in. LM and RM count as midfield here, although they're rated alongside the wingers; LW, RW and ST are forwards. The match cards show them when you hover the XI rating, and each club result shows them after the competition.
- `predicted_lineups` holds the predicted XI for upcoming matches.
- On a finished match's **Line-ups**, each starter is green if the model predicted him to start and red if it didn't, with the player it picked instead, and his rank going into the match, under a red one's position (paired by position, then position group, then line). The prediction is the last genuine pre-match capture in `lineup_prediction_snapshots`, taken before the official XI was first seen, exported as `prematch_xi` in `players.json` for the last 21 days' results. Matches from before the captures began have no colours.
- The **Line-up record** tab (`#/lineups`, built like the Stats tab) scores every one of those pre-match captures against the official XI, from the start of capturing, with the same selection as the Methodology page's live record (`evaluation.load_lineups`). `export_lineup_record` writes one row per team line-up to `lineups.json` (starters named, right position, hits per line, hours before kick-off, model version, missed and wrongly picked players). The page adds them up itself: totals, the spread of scores out of 11, a daily or weekly trend, and breakdowns by position, time before kick-off, league, club, player and model version, filterable by competition and range.
- The tab's **Reconstructed history** view is kept apart from that live record. The nightly player-ratings replay already picks a predicted XI for every past match from what it knew before kick-off (the last five matches' minutes and formations, and the injury list); it now keeps each finished match's full XI in `reconstructed_lineups` (rebuilt each run), and `export_lineup_history` scores them against `fixture_players` starters with the same rules (`_score_xi`) into the `site.lineup_history` table (rewritten whole each run; it was `lineups_history.json`, 6.5 MB, until 2026-10-05). The view asks the database for what it shows: `site_lineup_history(days, leagues, limit)` adds up the totals and tables for the chosen range and competitions and returns the newest rows listed, about 25 KB for the whole history (`db/migrations/20261005_site_lineup_history.sql`, applied 2026-10-05). The first version read every row on every request and took about 2 seconds for the whole history on the live database, against the public key's 3 second limit. So the whole history is now counted once per export into three small tables (`site.lineup_history_teams`, `_days`, `_often`; `site.lineup_history_refresh()`, called by the export) and summed from those, while a range is still counted from the rows (`db/migrations/20261005_site_lineup_history_fast.sql`, applied 2026-10-05): 38 ms against 592 on a copy of the data, with identical answers, and about a quarter of a second on the live database where it had been 2 seconds. The live record is still a small file totalled in the browser; both become the same summary (`lineupSummary` in `app.js`), which is all the tab draws from. It's today's code run on the past, not what was predicted at the time. Apply `db/migrations/20260928_reconstructed_lineups.sql` once (it's also in `db/schema.sql`); until then the replay skips the table and the view says it isn't ready.

Line-up roles are stored in `fixture_players.role` and `fixture_players.grid`, and formations in `fixture_formations`. The site shows player ranks on the Rankings tab (Players view, filterable by role group). Each row has the player's club badge and photo, with his club and nationality under his name. A player is listed if any of these hold:
- he has 450+ minutes in his last 20 appearances;
- he has a season with 1,500+ minutes among the seasons shown, which keeps established players who've been injured, such as John Stones;
- he's in a current squad, which lists new signings straight away.

**His club** comes from, in order:
1. the squad he's in now: every club in the 13 leagues has its squad fetched nightly from `/players/squads?team=` (`team_squads`, `python -m thecornerfc sync squads`);
2. the club the weekly current-club check found this season, which is often outside our leagues;
3. his last appearance, if neither of those is known.

So a player who has left drops off his old club's list, even before he plays for his new one. A nationality can be corrected by hand in `player_overrides`, for example Elliot Anderson as England. The nightly sync would overwrite a change made on `players` itself. Clicking his name opens a **player page** (`#/player/<id>`). A header shows his club, league, position, age, nationality and Ability (his current rank). Under it are key figures: world, league and position rank by Ability (among ranked players in the leagues with player data), this season's league minutes, goals and assists (saves for keepers), and an **evidence level**. The evidence level counts this season's minutes: Current is 900+, Limited is fewer, and Past seasons means none yet, so his Ability rests on earlier seasons and his age curve. Four tabs sit under it:
- **Overview:**
  - his club's next match, with the win chance, the projected score, and whether he's in the predicted XI, doubtful or out (with the injury reason);
  - a chart of his rank going into each of his last 20 league matches;
  - **a pitch of his positions** (the spots of the position filter): in every position he can play, his rank there and his share of starting minutes in that spot, over the last 12 months or ever (our data runs from 2020/21). Ranks are per role group, so LB and RB share his full-back rank. Positions he hasn't started in (0%) are left blank; hovering over one still shows his rank there if he has one. Starting minutes are the role he started in, from the line-up and formation; minutes off the bench have no position and aren't counted;
  - three separate sections. **Underlying Ability** shows his rank and last season's, plus his rating movement over 7, 30 and 90 days and the season. That movement comes from the stored daily rating captures (`player_rating_movement`, exported as `movement` in his page file), using baselines from the same player model version only, and appears once captures exist. **Current Season** shows this season's league minutes and stats. With none, it says so and that his Ability doesn't come from current form. **Recent Performance** shows his last 10 league appearances (his club's result, his goals and assists), dated. If he hasn't played for 45 days, they're titled "most recent appearances" and marked as not current form.
- **Stats:** one season's league appearances, starts, minutes, goals, assists and cards, as totals or per 90 minutes, added up across his clubs that season. API-Football's other counts (shots, passes, tackles, duels, dribbles, saves) go into the ranks but aren't published (since October 2026).
- **Matches:** his last 20 league appearances, with the result, minutes, position, goals, assists, cards and his rank going into the match. API-Football's match rating is not published anywhere on the site: it is still stored (`fixture_players.rating`), but no exported file carries it.
- **Career:** a chart of his season ranks (estimated seasons hollow), a season-by-season table (club, club rank, minutes, goals and assists, positions, and which position group the season was rated as), and the clubs his current rank is built on.

The Stats and Matches tabs, the injury status (out, doubtful or suspended: the injury itself isn't published), his birth date, his clubs by season and his positions come from `docs/data/players/<player_id>.json`, which is loaded only when the page opens. `export_player_pages` writes one file for each listed player, about 2.5 KB each. It builds them from the query cache (appearances, finished fixtures and the season totals in leagues without per-match data), so the only new database reads are the per-match ranks for those 20 matches and injuries for upcoming fixtures. Season stats in leagues without per-match data come from `player_seasons` totals, so starts are missing there.

Clicking a nationality opens a **nationality page** (`#/nation/<name>`) with:
- how many ranked players it has, the best XI's average rank, and the average age;
- a best XI by current rank (1 keeper, 2 centre-backs, 2 full-backs, 3 midfielders and 3 forwards);
- which leagues they play in;
- every one of those players, ranked.

Player names on club pages and in predicted XIs link to the player page too. Above the league filter there's an age range slider, and a small pitch of positions you click to filter by (you can pick several). A player's position on the site is the one where he's started the most minutes over the last 12 months. Szoboszlai is AM (1,170 minutes) rather than DM (891). A player shows under a position if it's his main one, or if he started there for 25%+ of his starting minutes in the last 12 months (`positions_12m` in his row of `site.players`). Bernardo Silva appears under CM and DM, for example. With positions picked, the table adds an **"As ST"** column (or whichever position) and sorts by it. It shows how good he is now in that position (`player_position_ranks`, one per outfield role group):
- **How good he is in that position, not how good he is:** each position has a level of its own, built like his overall level (season ranks, below). A season he played in that position counts in full. A season in another position is scored with this position's weights, against its players, and counts by how well the two fit: a defensive mid's season counts 0.8 towards his level as a central mid, a winger's 0.4, and an unrelated position's 0.05 (`GROUP_FIT`, the same table the line-up prediction uses).
- **Familiarity:** up to 10 points come off for a position he rarely starts in, and none once it's 40% of his starting minutes over his last three seasons. The penalty is scaled by how far his usual position is from it: a full-back at wing-back pays 3 of the 10, a winger there all 10, and an attacking mid 14.
- **Not anchored on his overall rank:** his rank in the position shown for him needn't equal his overall rank, and a position can be above it. Foden's overall rank carries his seasons as a winger; as a central mid he is rated on the season he has played there, and is lower.
- **Only positions he has played:** a position only gets a rank if he has started there at some point in our data (from 2020/21). With several positions picked, the column shows his best of them.

The player page lists his rank in every position. Under it, **Club & nationality** takes one or more clubs and nationalities, typed or picked from a list. Each shows as a chip you click to remove. They combine with the other filters, except that a club shows its players whatever league is selected. The counts in the filter follow both. The table shows each player's age and his **season ranks** for 26/27 back to 21/22, sorted by the current season (`player_season_ranks`, see below).

**Season ranks follow the age curve.** Every player follows the typical age curve through all his seasons, and only moves off it where he has the minutes to (`season_model` in `thecornerfc/player_ratings.py`):
1. **Evidence for each season he played:** his clubs' average LT ALGO over his matches that season, moved by his stat score. The score is the same as above, as a percentile among player-seasons with 900+ minutes in the same role group. It goes through the same club-first formula as above, with no smoothing across seasons. A player under 70% of his club's minutes (80% for keepers) is scaled down by up to 20%, because a rotation player at a top club is evidence of being below its regulars. Gabriel Jesus played 55% of City's minutes in 21/22 and 44% of Arsenal's in 23/24.
   - **Seasons in leagues without match data** (Portugal, Belgium, Greece and the other player leagues) come from API-Football's season totals (`player_seasons`), scored the same way against the same players and at the club's real level that season. Pass accuracy is left out where the API has none, and failed dribbles everywhere (the season totals have no dribble attempts). Other stats the API doesn't have are left out too, rather than counted as zero. For example, the National League only has minutes, goals and assists. Liam Mandeville's 22/23 at Chesterfield (10 goals) used to be scored as if he had no shots, passes or duels at all. Gyökeres's Sporting seasons (29 and 39 league goals) used to count as average stats at Sporting's level. They now read about 90, and his 26/27 at Arsenal is about 83.
2. **The age curve depends on position.** Each player uses the curve for the role group he's played most minutes in. It's in rank points, measured from how evidence changes from one season to the next, for players with 1,500+ minutes in the first season and 900+ in the next. The lower bar for the next season keeps players who lost their place, so decline isn't understated. Seasons chosen for their minutes tend to be good ones, so the next season is worse on average at every age (regression to the mean, about −0.7 a year). That's measured and taken off, otherwise it looks like players decline from 23.
   - **Growth to 24**, measured: +4.1 a year at 18, +2.4 at 21, +1.1 at 24. Keepers gain about +1 a year from 22 to 24.
   - **A flat prime until 31**, or **33 for keepers.** This is set, not measured: the data is too noisy to place it.
   - **Then decline that speeds up every year:** the yearly change is β × years past the start of the decline, with β fitted for each role group. Groups with less data lean towards the all-outfield β, weighted as 200 season pairs.

     | Role group | β | Curve at 35 | at 40 |
     |---|---|---|---|
     | Striker | −0.33 | −2.0 | −12.0 |
     | Centre-back, full-back, CM, AM | −0.23 to −0.24 | about −1.4 | about −8.5 |
     | Winger | −0.15 | −0.9 | −5.3 |
     | Defensive mid | −0.10 | −0.6 | −3.7 |
     | Keeper (from 33) | −0.29 | −0.3 | −6.2 |

     Kane (32) is still on the flat part of his curve. Giroud's curve is −9 at 39, and Neuer's is −6 at 40.
   - **Below 18** there are too few regulars to measure, so it's set by hand: +3.4 a year at 17, and 1.7 more for each year younger.
3. **His level on the curve** is the average of (evidence − curve) over all his seasons, weighted by minutes. When rating one season, the others count 0.5 ^ years apart (0.7 until October 2026: older seasons held a player up too long after an ordinary year). A starting level of 64.3 (his rank at peak age) is added in, weighted as 450 minutes, so a player with little data anywhere sits below an average regular.
4. **Season rank** = level + curve for that season, plus the season's own difference from it, kept in proportion minutes ÷ (minutes + 1,500). A full season (3,000 minutes) keeps two thirds of its difference. A thin one stays on his curve: an injury year, the first weeks of this season, or a teenager's debut. Rodri's 24/25 (80 minutes, injured) is 93.6, where the old model gave 79. Tah's weak 22/23 (evidence 68) is 72, between his curve (79) and the season.

Holding out each 1,500+ minute season and predicting it from the player's other seasons (level + curve) misses by 6.0 rank points on average. The settings are at the top of `thecornerfc/player_ratings.py`: `PRIOR_LEVEL`, `PRIOR_MINUTES`, `LEVEL_DECAY` and `DEVIATION_MINUTES`.

**Every season from 21/22 to now has a number for every player.** A season with no minutes in these leagues is level + curve. That can be a year in a league without player data, the years before his debut here, or the current season if he hasn't played yet. Lamine Yamal reads 65 at 14, 67 at 15 (11 minutes) and 83 in his first full season. His club that season comes from API-Football's list of the clubs a player has been at (`player_career_teams`, fetched once per player with a gap, and by the nightly job for new ones). A club we have fixtures for but no player data, a lower league say, adds its level as a little evidence, weighted as 450 minutes. For example, Joan García's 23/24 is Espanyol in the Segunda. The hover names the club. It's stored with 0 minutes and shown on the site as an outlined chip in italics.

**Retired players are taken off the list.** API-Football has no retired flag. So every night, players who played in the last 18 months but not yet this season have their current club looked up with `/players/squads`, at most once a week each (`python -m thecornerfc sync retired`, stored in `player_career_checks`). National and youth squads don't count. If a check made after his last season finds him in no club's squad, and he's 34 or older, he counts as retired. A younger player without a club isn't marked retired, because he's usually a free agent or a late transfer the squad lists haven't caught up with yet (Sancho, Ramsdale and Odobert all showed no squad in September 2026). He still leaves the list 18 months after his last match, like everyone else. He comes off the players list, and his season ranks stop at his last season instead of being estimated forward. If he plays again, or a later check finds him at a club, he's back. A free agent of 34+ drops off too, until he signs somewhere. `/players/teams` doesn't work for this: early in a season it often doesn't list the new season yet, even for regulars. It flagged Buongiorno and Ansu Fati.

The top 10% of the scale is spread by how far a player's score is above the 90th percentile, up to the best seasons on record, so the very best stand apart instead of all sitting at about 99. A season is blank after a player has retired. Hovering a season cell shows his age that season: his age now for the current season, and one less for each season before. Then, for each club he played for that season, it shows the club's average rank over his matches, followed by his minutes, goals and assists. That detail comes from his own file (`docs/data/players/<player_id>.json`), fetched on the first hover over his row. (There is no file of every player's detail any more: each player's rows are in his own file and his club's.) It also shows the predicted XI for a team's next match in the team pop-up, and the XI ratings on match cards.

**Backtest (2024/25 onwards):** home XI rating minus away XI rating added nothing on top of the team ranks. Predicted XI against the recent average gave a tiny gain in the unexpected direction, so the XI ratings are shown but not used in the projections.

```bash
python -m thecornerfc player-ratings   # the nightly job runs this after the club rankings
```

## Club ranking

This is based on the Club Ranking Google Sheet. Every finished fixture is replayed oldest first, ordered by kickoff time, with the fixture ID breaking ties. For each fixture:

- Expected goal difference = (home rank − away rank + 30) / 100
- Result = actual goal difference, capped at ±3. When both teams have **xG** for the match, result = 30% capped goal difference + 70% xG difference.
- Rank change = (result − expected goal difference) × K, where K is 6, or 10 for matches with xG.
- One-off curtain-raisers count for a third: the rank change is × 1/3 for the **Community Shield** and the **UEFA Super Cup** (`COMPETITION_WEIGHT`). Sides treat them as pre-season, so a result says less than a league match. The 1/3 is World Football Elo's friendly-to-World-Cup ratio. Only two or three of these games are played a year, too few to backtest a value.
- The home team gains the rank change and the away team loses it.

This differs from the sheet, which uses (home × 1.09 − away) / 100, × 10 and no cap. Backtesting 2023–26 showed the ×1.09 gave 0.4–1.1 goals of home advantage, when the real figure is about 0.3 for every team. A smaller K and the goal cap also stop one freak result from swinging a rank. Prediction error fell from 1.77 to 1.68 goals per match. The settings are at the top of `thecornerfc/ranking.py`.

**Why xG is blended in.** xG exists from 2022/23, for about 35–50% of matches (the bigger leagues). Replaying the rankings and projections from 2024/25 onwards:

| Result used | Log loss, all matches | Log loss, matches with xG |
|---|---|---|
| Goals only (before) | 1.00046 | 1.00446 |
| xG only, K 10 | 0.99889 | 1.00085 |
| 30% goals + 70% xG, K 10 | 0.99834 | 0.99993 |

- The blend was better in 2023/24, 2024/25 and 2025/26 taken separately.
- Anything from 25–35% goals with K 10–11 scored about the same.
- An xG difference is much less noisy than a goal difference, so those matches take a bigger K.
- Capping the xG difference made it worse, and home advantage and K for matches without xG were best left as they were.

`team_rank_history.act_diff` still holds the actual goal difference.

**Tables and xG on the pages are the site's own (since October 2026).**
- **League tables** are worked out from the finished fixtures (`thecornerfc/tables.py`). API-Football's standings supply only the shape: which clubs are in which group, and what a finishing place leads to. Which matches count for a group comes from the round names (the regular season, a cup's league or group stage, the Apertura or Clausura a group is named after). Level clubs are ordered by goal difference and goals scored, except in the competitions listed in `tables.ORDER` (wins first in Belgium and MLS; the matches between the level clubs in Italy, Russia, Ukraine, Andorra and Azerbaijan).
- **What results can't show is kept by hand** in `thecornerfc/table_adjustments.json`, keyed `"<league id>:<season>"`: `{"points": {"<team id>": -4}}` for a deduction and `{"void": [<team id>]}` for a club whose results were annulled. The export logs a warning naming any club whose computed line differs from API-Football's, which is how a new deduction shows up. Checked against all 1,129 standings rows on 6 October 2026: played, won, drawn, lost, goals and points agreed everywhere except where API-Football's own table was behind the results (Kazakhstan, the Conference League).
- **xG on club pages and league tables** is `export.XG_FROM_SHOTS`, an estimate from each side's shot counts, shown with "≈". API-Football's xG still goes into the ratings and projections but is not published.

**On results alone.** The whole match model was replayed with nothing but dates, competitions, clubs and scores: no xG, no predicted line-ups, no injury lists (`experiments/results_only`, October 2026; 44,632 matches from 2024/25 onwards).

| Model | W/D/L log loss | Right result |
|---|---|---|
| As it runs | 0.99744 | 51.0% |
| Results only | 1.00046 | 50.8% |
| Always the base rates | 1.07016 | |

- Results alone keep 96% of the gain over the base rates. Nearly all of the loss is the xG (0.0026 of 0.0030); line-ups and injury lists together are worth 0.0006.
- The loss is about 0.006 to 0.009 in the biggest leagues, where xG, line-ups and injury lists exist, and close to nothing in cups and the leagues without xG.
- The club ratings keep their order (rank correlation 0.992) and move 9 points on average, 60 at most.
- K 6 is still the best K for goals alone: 4 to 10 were tried.
- The full tables are in `experiments/results_only/REPORT.md`.

**Attack, defence, home and away.** These are worked out alongside the rank from the same replay (`side_ratings` in `thecornerfc/ranking.py`). They don't change the rank.
- **Attack and defence** average to the rank (Form), on the same scale. Expected home goals = the competition's average home goals + ((home attack − away defence) / 2 + 15) / 100, and the same the other way round for away goals. So 200 points of attack over the other side's defence is about one more goal. After each match, both sides move by 1.0 × (actual total goals − expected total) / 2: a club in high-scoring games drifts towards attack, one in low-scoring games towards defence. Goals are capped at 5 a side and blended with xG like the rank. Replaying 2024/25 onwards, this cut the error on total goals from 1.4205 to 1.4083. On its own, learning rates from 0.5 to 1 scored about the same; 1.0 was best for the projections. For example, Arsenal lean on defence and Barcelona and Bayern on attack.
- **Home and away** are the rank plus or minus the club's own home edge, on top of the standard 30 points. Both sides' edge moves by 0.2 × (result − expected), so a club doing better at home than away builds a positive edge. The gain was small (goal-difference error 1.3220 → 1.3205). Most clubs' edges are within a few points, because home advantage is mostly the same for everyone.
- Stored after every match in `team_rank_history` (`attack_after`, `defence_after`, `home_after`, `away_after`, plus `split_before`, `edge_before` and `goal_base` going into it, for the projections) and for now in `team_rankings` (`attack`, `defence`, `home_rating`, `away_rating`). The club page and team popup show them.
- The projections use them (see Match predictions). The attack learning rate (1.0) was tuned with the projections on 2023/24.

**Line-ups in the rank update: tested, not used.** The idea: when a club starts a weaker XI than usual and loses, its rank should fall less. The expected goal difference in the update was shifted by the starting XI rating against the club's usual one (actual − recent XI rating), for the 13 leagues with line-up ratings. Replaying every fixture and scoring 2024/25 onwards with line-up-free forecasts, it didn't help: log loss 1.00490 with no shift, 1.00496, 1.00513 and 1.00579 with shifts of 0.06, 0.12 and 0.24 goals per XI point. Goal-difference error was 1.6676 at best, with no shift. Rotation does matter at the extremes: a side starting an XI 4–8 points weaker than its opponent's shortfall does about 0.2 goals worse. But only about 4% of line-up-rated matches have gaps that big. A squad player's rank is built from his club's level too, so reserves rate close to starters. The XI gap's spread is only 1.9 points (about 0.08 goals). The pre-match predicted XI gap also cut goal-difference error by only 0.1% out of sample (1.6299 → 1.6284), in line with the prediction backtests further down.

A team's first rank is `leagues.starting_rank` of the first league it plays in. For a team that only ever appears in cups, it's the `starting_rank` of the first cup it plays in.

- `team_rank_history` holds each team's rank before and after every match, like the Ranking Breakdown tab.
- `team_rankings` holds the current summary, like the Ranking tab: current rank, 30 and 100 Ranking, ST ALGO, LT ALGO, and HG/HA/AG/AA over the last 12 months.
- `team_rankings` also has a `reliability` score from 0 to 100, which isn't in the sheet:
  - It's mainly driven by games played: a team scores 66% after 38 games, 89% after 76 and 96% after 114.
  - It's reduced when a team's rank swings a lot. `rank_volatility` is the standard deviation of the team's last 30 per-match rank changes, measured at K 6: a match with xG moves the rank with K 10, so its change is scaled by 6/10. That way it measures how surprising a team's results are, not the size of the step. At 10.5 or below (about 78% of teams) there's no reduction. Above that the score falls with the cube: 11.8 gives ×0.70 and 14 gives ×0.42.
  - The constants are at the top of `thecornerfc/ranking.py`.

```bash
python -m thecornerfc rank   # the nightly job runs this after syncing
```

Every run replays all fixtures from scratch, which takes seconds. Late results, corrected scores and changes to `starting_rank` are all picked up automatically.

## National team ranking

`thecornerfc/nations.py` runs the club ranking's Elo over every men's full international since 1872, for the **Nations** tab (`docs/data/nations.json`). The formula is the same (100 points = one goal, capped goal difference, `rank_change = (act_diff - exp_diff) * K`), with these differences, tuned by backtest in `experiments/nations_elo`:
- Home advantage is 50 points, and only applies away from neutral venues.
- Goal difference is capped at 8, not 3.
- There's no xG.

Friendlies, qualifiers and tournament finals all count the same. Weighting them differently scored slightly worse, but `TIER_WEIGHT` is there if that changes.

**Data.** The results come from the public [international_results](https://github.com/martj42/international_results) dataset, which has a neutral-venue flag and the tournament for every match. It is downloaded to `.cache/international_results.csv` and refreshed when it's more than 20 hours old. A failed download keeps the cached copy. Nothing goes in the database. The export rebuilds the ranking every night, and it isn't critical: if it fails, the last `nations.json` stays. To rebuild only this file: `python -m thecornerfc nations` (safe in local mode).

Which teams are listed:
- Only FIFA members appear: nations that have played a World Cup qualifier since 2010, which is 211 teams.
- Of those, only nations that have played in the last four years are listed.
- Non-FIFA sides such as Jersey still count as opponents.
- Tournaments for non-FIFA sides (CONIFA, Island Games) and multi-sport games (mostly under-23 teams) are left out.

**API-Football (ready, off).** The dataset usually has results within a few days. API-Football can fill that gap and later supply upcoming fixtures:
1. Run `db/migrations/20260929_national_fixtures.sql`, then `db/migrations/20260929_national_lineups.sql`, then `db/migrations/20260929_national_players.sql`.
2. Run `python -m thecornerfc sync national`. By default it pulls the current season of each competition in `config.NATIONAL_TEAM_LEAGUES`, at about 20–40 calls, and logs each competition's name so you can check the ids. It then fetches the line-ups of every finished match it has (see below).
3. Set `THECORNERFC_NATIONAL_SYNC=true` in the nightly workflow to refresh them every night.

These matches go in their own table, `national_fixtures`, never in `fixtures`. The club ranking, predictions and site export read every row of `fixtures`, so national teams there would enter the club Elo.

**Line-ups.** `ingest.sync_national_lineups` stores each finished international's starting XIs, formations and coaches the same way `sync_cup_lineups` does for clubs: one `/fixtures?ids=` call per 20 matches, each starter's grid and role, and the coach on the line-up. They go in `national_fixture_lineups` and `national_fixture_formations`, not the club tables, which the club models read in full. `national_fixtures.players_fetched_at` marks a match done: once its line-ups arrive, or after the retry window if API-Football never has them. Player ids are API-Football's, so they join to `players`. It runs after the fixtures in `sync national` and in the nightly run. For older matches, pull their seasons first (`python -m thecornerfc sync national --seasons 2022 2023 2024 2025`); the next line-up run picks them up.

**Stat lines and nation pages.** The same calls give each player's stat line (minutes, goals, assists, rating, cards, as `fixture_players` has for clubs), kept in `national_fixture_players` with the player's name as sent (not every international is in `players`), and the coach's name on `national_fixture_formations`. A match is marked done once both line-ups and stat lines arrive, or after the retry window. The `national_players` migration sets matches fetched before it to be fetched once more (about 8 calls for the current seasons). The export writes `docs/data/nations/<team id>.json` for each national team with a finished match in the last four years: its matches with formation and coach, and every appearance (stat lines, plus starters with none, whose minutes are unknown). `nations.json` gives each ranked nation its `team_id`. The nation page's Formations and Players tabs read these files. `ingest.sync_national_coaches` (in `sync national` and the nightly run) stores each national team's head coach and the date he started in `team_coaches`, as `sync_coaches` does for clubs (one `/coachs?team=` call per team that played in the last year, rechecked weekly); the tabs cover the matches since then.

How API-Football matches are merged:
- They're added only where the dataset doesn't have the match (the same two nations within a day), so the dataset's neutral flags win.
- Tournament finals are assumed to be neutral.
- Team names are mapped with `nations.API_NAMES`. A name that doesn't map is logged and its matches skipped, because an unknown name would start a phantom nation at 1000.

## Match predictions

`fixture_predictions` holds one row per fixture. The `upcoming_predictions` view adds team and competition names, and shows percentages. The method is based on the sheet's RG tabs:

1. **Expected margin:** (home match rank − away match rank + 30) / 100. Add 0.2 goals in the Champions League, Europa League and Conference League, where home sides do better.
   - Each team's **match rank** blends its current rank (Now) with LT ALGO. The blend depends on how far away the match is: 60% Now for a match today, sliding in a straight line to 20% Now for a match a year or more away (40% at six months).
   - Why: in a point-in-time backtest, 60% Now + 40% LT beat Now alone in both 2022–23 (log loss 1.0026 → 1.0012) and 2024 onwards (1.0034 → 1.0007), and beat ST, LT, the 30 and 100 Rankings and other blends. Re-running it with ranks as they stood 91, 182 and 365 days before kickoff, the best Now weight fell to 0.4, 0.4 and 0.2. Now alone was worse at every horizon.
2. **Base goals for each side:** the average of the team's own goals scored and the opponent's goals conceded, at home for the home side and away for the away side. The averages cover the last 12 months, use **xG instead of goals** for any match that has it, and are shrunk towards the competition average by 6 games.
3. **Projected goals:** a proportional version of the sheet's "Buff" scales the favourite up and the underdog down by the same factor until the margin matches. The original moved goals in a straight line, which pushed underdogs to around 0 goals and made the model far too sure they wouldn't score.
4. **Injuries**, in the 10 leagues in `config.INJURY_MODEL_LEAGUES` that have injury history: the Premier League, Championship, La Liga, Serie A, the Bundesliga, Ligue 1, Turkey, the Netherlands, MLS and Norway.
   - Each team's **missing strength** is the total, over players listed as out or doubtful, of each player's share of the team's minutes in its last 10 matches. 1.0 means one ever-present player. Long-term absentees have no recent minutes, so they add almost nothing.
   - The expected margin moves by 0.1 goals per unit of (away missing − home missing).
   - Minutes come from `fixture_players` (per-match minutes, fetched for these leagues). See `thecornerfc/injuries.py`.
   - In a train/test backtest (trained on 2021/22–2023/24, tested on 2024/25 onwards), it improved test log loss from 1.0066 to 1.0059. That's small but consistent.
   - Match cards show each side's missing strength.
5. **Attack, defence, home edge and line-ups** (added September 2026; see Club ranking for how each is worked out):
   - **Home edge:** the expected margin moves by (the home side's own home edge + the away side's) / 100.
   - **Line-ups:** the expected margin moves by 0.005 goals per point of difference between the two predicted XIs' average rank in defence, midfield and attack, separately. It's only used when both sides have all four lines (the 13 leagues with line-up ratings). The goalkeeper line made predictions worse, so it isn't used.
   - **How open the game is:** the base goal total is 75% the attack/defence model's (the competition's goal base + both sides' attack/defence split) and 25% the 12-month averages'. The home/away shape stays the 12-month one.
   - These were tuned on 2023/24 and tested on 2024/25 onwards (44,339 matches, injuries left out of both). Each part helped on its own, and together they helped every market:

     | | W/D/L log loss | Over 2.5 | Both teams score | Goals RMSE |
     |---|---|---|---|---|
     | Before | 0.99847 | 0.67923 | 0.68747 | 1.1739 |
     | + attack/defence goals | 0.99822 | 0.67718 | 0.68674 | 1.1717 |
     | + home edge | 0.99812 | 0.67922 | 0.68748 | 1.1735 |
     | + line-ups by line | 0.99795 | 0.67917 | 0.68751 | 1.1738 |
     | All three (current) | **0.99734** | **0.67715** | **0.68678** | **1.1712** |

     In the line-up leagues alone, W/D/L went from 1.00392 to 1.00153. Predictions already made before the change, backfilled or live, are left as they were.
6. **Probabilities:** Poisson distributions for 0–10 goals each side give home win, draw and away win. The draw chance is boosted by up to ×1.1 in close games; the boost fades to nothing at a 1.5-goal margin.

The sheet's "36% × strength ratio" blend is dropped. Backtested log loss on 51,000 matches from 2024 to 2026: the sheet's method 1.016, the first version 1.0053, the current one 1.0035. Guessing base rates scores about 1.07.

These were tested and not adopted:
- A faster rank K for the first games after the summer break. It was worse.
- Pulling ranks towards the league level after the summer. It made no difference.
- Variations on the injury weighting: 5 or 20 recent matches, rating-weighted, or goalkeepers and attackers weighted more. They made no real difference.
- Blending in bookmaker odds. On the first 506 finished matches with odds (16–24 September 2026), the bookmakers alone scored best. Blending still didn't help: the best weight fitted on the first half gave the model 10%, and that blend scored slightly worse than the odds alone on the second half. Re-test once there are a few thousand matches. Scores, with the model recomputed as it stood before each match:

  | | Log loss | Brier | Favourite won |
  |---|---|---|---|
  | Bookmakers, closing odds | 0.9741 | 0.5800 | 52.4% |
  | Model with xG in the ranks (current) | 0.9874 | 0.5897 | 52.0% |
  | Model with goals-only ranks (before) | 0.9920 | 0.5928 | 51.6% |

  - Blending xG into the ranks cut the gap to the bookmakers from 0.018 to 0.013.
  - The 95% range for the current gap is 0.000 to 0.027, so the sample can't yet rule out the model matching the bookmakers.
  - Opening odds scored the same as closing odds (0.9742).
- **When the model and the bookmakers disagree** (checked 25 September 2026, the same 506 matches). On the 82 matches where the new model and the closing consensus differed by 10+ points on some outcome, the bookmakers were right. The model gave its side 42% on average, the bookmakers 30%, and it won 29%. Backing the model's side at the best closing price lost 2.6% (old model: −13%), with a 95% range of −38% to +41%. At 15+ points it showed +48%, but that's 19 bets, 7 winners and three long shots, which is noise. The model's side was the market underdog in 58 of the 82. Overall the model is slightly timid on strong favourites (said 84%, won 87% in the 80–90% band, 2024/25 onwards), but stretching the margin gained almost nothing (test W/D/L 0.99734 → 0.99728 at ×1.1), so it isn't used. Split by league: in the big five the model matched the bookmakers (−0.0013 log loss, 53 matches), and elsewhere it was 0.017 worse.
- **Every market with odds** (same 506 matches, new model reconstructed pre-match, 90-minute results). Log loss is model minus bookmakers, so negative means the model was better. The 10+ column covers matches where the model rated a selection 10+ points above the bookmaker consensus, with the model's, the bookmakers' and the actual rate, and the return at the best closing price. Value bets are the paper-betting rule: model × best price ≥ 1.03.

  | Market | Model − bookmakers (95%) | 10+ above market | Value bets |
  |---|---|---|---|
  | Match result | +0.0147 (+0.001 to +0.028) | 58: 48 / 34 / 36%, +17.6% (−28 to +71) | 359, −8.7% |
  | Double chance | +0.0079 (0.000 to +0.015) | 64: 64 / 50 / 53%, −0.4% | 263, −8.8% |
  | Both teams score | +0.0058 (−0.003 to +0.014) | 25: 45 / 33 / 32%, −5.3% | 240, −4.2% |
  | Over/under 0.5 | −0.0040 (−0.012 to +0.004) | none | 11, −89.5% |
  | Over/under 1.5 | +0.0034 (−0.003 to +0.010) | 1 | 233, −9.7% |
  | Over/under 2.5 | +0.0044 (−0.005 to +0.013) | 22: 46 / 34 / 36%, +5.2% | 301, −1.7% |
  | Over/under 3.5 | +0.0024 (−0.007 to +0.013) | 35: 58 / 46 / 54%, +5.2% | 251, +1.2% |
  | Over/under 4.5 | −0.0022 (−0.012 to +0.008) | 23: 73 / 62 / 70%, −1.7% | 175, −11.8% |

  - Nothing beats the bookmakers with confidence. Every range crosses zero or sits on the bookmakers' side.
  - The goal markets are much closer than the match result: within ±0.005, against 0.015.
  - The lines other than 2.5 use a calibration fitted on 2023/24 (base, shrink): 0.5 (0.96, 1.1), 1.5 (0.76, 0.9), 3.5 (0.36, 0.9), 4.5 (0.04, 1.0).
  - *Opening prices:* these matches' odds were first downloaded on 23 September, after most had been played, so `first_odd` equals the closing price for 99.9% of rows. Opening vs closing can only be tested on matches from 24 September on.
- **Beating one bookmaker instead of the market** (same 506 matches, closing prices, new model reconstructed pre-match). Every bookmaker was more accurate than the model, in both results and goals (model minus bookmaker log loss, with its margin removed):

  | Bookmaker | Margin, results | Results | Goals | Model value bets at its prices only (results, goals) |
  |---|---|---|---|---|
  | SBO | 11.9% | +0.006 | +0.004 | −3%, −5% |
  | Betano | 6.0% | +0.010 | +0.001 | −5%, −5% |
  | BetVictor | 8.2% | +0.010 | +0.003 | −16%, −7% |
  | Bet365 | 8.1% | +0.014 | +0.002 | −12%, −8% |
  | William Hill | 9.8% | +0.014 | +0.008 | −9%, −1% |
  | Pinnacle | 4.8% | +0.014 | +0.002 | −9%, −7% |
  | 1xBet | 6.5% | +0.017 | +0.001 | −17%, −8% |

  - The bookmakers were about equally accurate. Pinnacle stands out for its low margin, not for sharper prices. The softest bookmaker (SBO) charges the highest margin, so it's the worst one to bet with.
  - Soft-bookmaker betting without the model was also tested: bet at one bookmaker when its price beats the other bookmakers' fair consensus, or Pinnacle's. That gave 5–36 bets per bookmaker with ranges of about ±100%, so it's inconclusive.
  - Taking the best price across all 13 bookmakers is the real lever. The margin falls from about 8% at one bookmaker to 3.1% (result), 3.3% (over/under 2.5) and 5.1% (both teams score). Paper bets used the best price until 25 September 2026; they now take Bet365 only, as that is the bookmaker actually bet with. The best prices summed under 100% (an arbitrage) in 24 result markets (4.7%), 8 over/under 2.5 and 4 both-teams-score markets. Each bookmaker's price is stored at a different moment, though, so some of these are snapshot timing rather than prices on offer together.
  - Next: the opening-price comparison (from matches collected before kickoff, 24 September on) will show whether any bookmaker is slow to move. That's the usual way to beat an individual bookmaker.
- **What the disagreements have in common** (the 82 matches where the model and the closing consensus differed by 10+ points on the result).
  - They're most common where the model knows least:

    | Kind of match | Share with a 10+ disagreement |
    |---|---|
    | Cups and European games | 29% |
    | A promoted or relegated club | 28% |
    | Under 25 recent games of data between the two sides | 28% |
    | Other leagues | 13% |

  - The new parts (home edge, line-ups, attack/defence) barely drive them. Correlation with the gap was 0.12 at most.
  - Who was right: the model was better in 40% of them overall. It did worst in streak matches, where one side's Form was 30+ points further from its Rating than the other's (30%), with a promoted or relegated club (37%), and when it backed an outsider (38%). When its pick was the bookmakers' favourite, it broke even (46%, log loss −0.003). Cups and European games were the only kind it won on average (50%, −0.058, 22 matches).
  - A split-sample test found nothing that predicts the good ones yet. Across 500 random halves, the best kind of disagreement on one half scored −0.064, but on the other half it scored +0.031 (bookmakers better), and the model won the other half in only 36% of splits. With 82 disagreements, any pattern found is mostly noise. The same test needs a few hundred more.

**Bookmaker comparison.** `export.market_probabilities` averages each bookmaker's match-winner odds with its margin removed. Match cards show these alongside the model, and the Stats tab compares model and bookmakers on every finished match that has odds.

```bash
python -m thecornerfc predict   # the nightly job runs this after the rankings
```

## Paper betting

`thecornerfc/betting.py` records the bets the model *would* place. It never uses real money. There are two strategies, tracked separately:
- **early:** placed by the nightly run for matches in the next 36 hours.
- **late:** placed by the match-day run within 75 minutes of kickoff, after late injury news.

A bet is placed when model chance × Bet365's price (`betting.BOOKMAKER`, the only bookmaker bet with, since 25 September 2026) is at least 10% better than even, at odds up to 10. The cutoff was 3% until 25 September 2026, which gave around 50 bets on a Saturday. Each bet is 1 unit. A match gets at most one bet of each kind per strategy (result, goal line, both teams score: `betting.GROUP`), so never a draw and an away win, or Under 1.5 and Under 4.5, together. Of several candidates the best is kept (`betting.pick_score`): the return if the true chance is halfway between the model's and the bookmakers', since plain edge favours the bets where the model disagrees most, which are the least reliable. A kind already bet on a match is not bet again by a later run of the same strategy. The fair chances and CLV still use every bookmaker's prices. Bets taken at other bookmakers before the switch stay in `paper_bets` but aren't exported. Markets:
- match result
- over/under 1.5, 2.5, 3.5 and 4.5 goals (2.5 is `p_over25`; the other lines are worked out from the stored projected goals by `predictions.goal_lines`). Lines other than 2.5 were added on 25 September 2026, because the goal markets were the closest to the bookmakers.
- both teams to score (`p_btts`)

The goal-market probabilities come from the same Poisson grid, calibrated towards the base rate. The 1.5, 3.5 and 4.5 calibrations were fitted on 2023/24 (`GOAL_LINE_CALIBRATION`). Bets settle on the 90-minute score and are stored in `paper_bets`.

**Tags and the cautious view** (added 25 September 2026, after the check of what model-vs-bookmaker disagreements have in common). Every bet is tagged with the kind of match and bet it is (`paper_bets.tags`, `betting.bet_tags`), using only what was known before kickoff:
- `cup` (cups and European games), `big5` or `league`
- `promoted`: either club's league changed since last season
- `thin_data`: under 25 games of data (the home side's home games plus the away side's away games in the last 12 months)
- `streak`: one side's Form is 30+ points further from its Rating than the other's
- `favourite` or `outsider` by the bookmakers' fair chances
- `gap10`: the model's chance is 10+ points above the bookmakers'

The Bets tab shows the bets in £: a flat £10 on every bet from a £1,000 bank (`export.BET_STAKE_GBP`, `BET_BANK_GBP`; the database keeps 1-unit profits). It shows the bank, profit, return (profit ÷ staked), bets won and how often the closing price was beaten, then tables by league and by market. Every settled bet is listed, with the bank after each one. Bets still to be played are on the **Tips** tab: one per pick (the night-before bet when both runs chose it), soonest first by day, with the Bet365 odds, stake and what it would win. The Stats and Bets tabs use the same country / league menu as Clubs and Matches (`renderFilterMenu`). Stats are exported per competition; picking a country, region or the European cups combines them in the page (`mergeStats`: counts add up, averages weighted by what they average over). Tags are recorded but not shown. The tab also has a **Cautious** view, which leaves out result-market bets on outsiders and any bet in a streak match (`betting.is_cautious`). Those were the kinds of disagreement the model lost most often. The outsider rule is for results only because that's where the evidence was; on goal lines "outsider" just means Under 1.5 or Over 3.5/4.5. The cautious view is the same bets, prices and timing, not a separate strategy, so the two compare exactly. Streak matches are common (about 40% of matches), so the cautious view keeps roughly a third of the bets. Judge it on CLV after a few hundred bets.

**Closing line value.** `odds.first_odd` keeps the opening price. `odds.odd` is never updated after kickoff, so it holds the closing price. Each bet records `clv` = odds taken × the fair closing probability − 1. Consistently positive CLV is the early sign of a real edge. Profit needs thousands of bets before it means much.

**Match-day job.** `.github/workflows/matchday.yml` runs `python -m thecornerfc matchday` every 30 minutes. For matches starting within 3 hours, it refreshes odds, which captures the closing price, and injury lists. It then re-projects those matches (downloading only their teams' and competitions' results), places the late bets, refreshes recent results and settles bets. It then writes the bets, the injury lists and the manifest to the database, those three rows and nothing else. The site's **Bets** tab shows the results.

A line-up adjustment (the strength of the starting XI against normal) was backtested and didn't help (test log loss 1.0058 against 1.0057), so line-ups aren't used in the projections.

## EFL Fantasy

The **EFL Fantasy** tab predicts [Fantasy EFL](https://fantasy.efl.com) points for Championship, League One and League Two players and clubs over the next six gameweeks (`thecornerfc/efl_fantasy.py`). Nothing is read from the Fantasy EFL site.

**Owner only since 2026-10-04 (audit L11, owner's decision).** Fantasy EFL's terms bar commercial use of the game (cl. 2.5, 8.1.7), so the tab is shown only to the signed-in owner, like the FPL tabs. The nightly export writes `efl_predictions` to `fpl_owner_docs` in Supabase, never `docs/data`, and the page reads it through `fpl_owner_data`. Older copies of `docs/data/efl_predictions.json` remain in git history.

- **The football** is the FPL model's (v1.6 parameters) run on these three leagues' own matches, without FPL's inputs: expected minutes, goals, penalties, assists, clean sheets, goals conceded, saves and cards.
- **Fantasy EFL's extra actions** (tackles, blocks, interceptions, key passes and shots on target) use each player's own rates per 90 over the last year, pulled toward his role group's. API-Football has no clearances, so defenders get a fixed rate for their role.
- **Clubs** score from the match model's win and draw chances and Poisson goals.
- **Gameweeks** run Thursday to Wednesday (UK time), numbered from the week of the season's first match.
- **Positions** are guessed from match data. To correct one, add `"<API-Football player id>": "D"` to `thecornerfc/efl_positions.json`.
- **Suggested team:** the tab picks the best 7 + 2 for a gameweek (1-2-2-2, 1-2-3-1 or 1-3-2-1, at most two players a club).

## Website

`docs/index.html` is a single-page site in the same style as MatchLab. It has two tabs:
- **Matches:** projected scores, win/draw/loss chances and results. Filter by competition and day.
- **Rankings:** club rankings with rating, form and trend, sorted by rating (reliability is kept in the database and isn't exported). Tap a club to see its fixtures.
  - Clubs show a **World** rank (place by Baseline Strength among every ranked club, whatever the list is filtered by) and **In lg** (place by Baseline Strength among the clubs in its league; TheCornerFC's ranking, not the league table). Players show World and League rank by Ability, **Mins** (minutes over the last 20 appearances, the evidence behind Ability; greyed under 450) and their club and league under the name.
  - Filters combine: the competition / country menu, search, and range boxes (clubs: world rank and Current Strength; players: Ability, club world rank and minimum minutes), plus age, position, club and nationality for players.
  - The URL carries the view, so it can be bookmarked or shared: `#/clubs?c=39&rank=1-50&cur=1000-` or `#/players?c=140&age=18-23&pos=RW,LW&ab=70-&crank=1-50&mins=900&sort=minutes`. `c` is the menu filter (a league id, `c:<country>`, `r:<region>`, `e:<cup>` or `k:<cup>`), ranges are `min-max` with either end left open, `club` is team ids and `nat` is nationalities separated by `|`. It is rewritten in place as filters change, so the back button leaves the Rankings rather than stepping through each filter.

The site labels the club rank as an **Elo rating** (**Rating** = LT ALGO, **Form** = current rank, **Trend** = Form minus Rating, how far a club is playing above or below its long-term level). The numbers are the same as the club rank below, and on that scale 100 points is worth one goal a game.

**Club pages.** Club names link to `#/club/<team_id>`. Under the name, key figures come straight from `rankings.json`, the club file and its league's table, with nothing new modelled:
- **Standing:** world rank (place by Baseline Strength, as the Rankings are ordered), league table position, and place by strength among the league's clubs.
- **Strength:** Current Strength, Baseline Strength and Current vs Baseline. The last is a gap in level, not movement.
- **Recent movement:** the Elo change over the last 6 matches (the export's `form`, with the date it runs from, since six matches can reach back into last season), over the last 30 days, and the last match date. The movement is flagged as not recent after 45 days without a match.
- **Attack, defence, home & away:** each with its place among all clubs. Attack and defence average to Current Strength, so the lean is half their difference; home minus away gives the club's own home edge.
- **Evidence:** reliability and matches rated.

The page has tabs:
- **Overview:** the next match and injured and suspended players beside the whole squad on a pitch, then the next 5 fixtures and recent results. The squad pitch shows each player in the positions he plays, with his chance of starting the next match and expected minutes there (from this season's line-ups in every competition, weighted to the next match's kind of competition, with injured players' starts passed to whoever replaced them and a pull towards the best XI by rating)
- **Predicted XI:** the XI from those start chances, with the squad's attack, defence and strength (also on the match cards)
- **Formations:** the manager, and the formations used this season and since he took over
- **Matches:** fixtures with projections, and every result with its rank change
- **History:** Current Strength over time (6 months to all), Elo at the end of each season and season-by-season ranks

Each club's history comes from `docs/data/clubs/<team_id>.json`, which is written by `export_clubs` for clubs active in the last 400 days and loaded only when the page opens. Each match carries the formation from its line-up (`fixture_formations`; only the leagues with match-by-match player data have line-ups).

**League and country pages.** Wherever a club shows "Country · League" (the club page header, and Rankings rows when searching or showing all leagues), both parts are links:
- `#/league/<league_id>` opens with key figures in two groups that are kept apart. **Actual standings** (from the table) shows the leader, most goals scored and fewest conceded. **TheCornerFC model** shows the strongest club by Baseline and by Current Strength, league strength (average Baseline Strength and its place among the covered leagues) and the best attack and defence ratings. The tabs are **Standings** (this season's table worked out from the results by `thecornerfc/tables.py`, with each group, what each place leads to, last-five form, each club's Current Strength for reference, and its xG for and against per 90 over its last five league games, which is the site's own estimate from shots), **Strength ranking** (the clubs by Baseline Strength, with their actual table position alongside), **Projected table** (the rest of the season simulated from the model's predictions) and **Matches** (one round at a time, opening on the round with the next fixture, with the model's chances for upcoming games). Each tab opens with a line saying which kind of table it is. A tab can be linked directly (`#/league/39/clubs`, `/projected`, `/matches`, `/table`). Cups have no Standings or Projected tab and open on Matches. The badge is the average Baseline Strength of the clubs playing in the league.
- `#/country/<country>` lists the country's leagues, strongest first by the average Rating of their clubs, then its cups, then all its league clubs by Rating. UEFA and FIFA competitions are under International (`#/country/World`).

Each competition's current season comes from `docs/data/leagues/<league_id>.json`, written by `export_leagues` and loaded only when the page opens (about 2 MB for all 70). A season starting from June onwards is labelled 2026/27, and a calendar-year one 2026, because API-Football's end dates only reach the last fixture it has scheduled.

**Managers.** Every night, each club in those leagues gets its manager from `/coachs?team=`, at most once a week each, or the next night after a line-up names a different coach (`team_coaches`, `python -m thecornerfc sync coaches`). The API keeps former managers listed with no end date, so the one on the club's latest line-up wins, otherwise the one who started last. Line-ups store their coach in `fixture_formations.coach_id`. API-Football seems to fill a season's line-ups with one coach, so they can't pin down a mid-season change, and the start date comes from `/coachs`.

**Cup line-ups.** For clubs in those leagues, their cup and European matches since July 2020 get starting XIs, formations and coaches from `/fixtures?ids=` too (`fixture_lineups`, `fixture_formations`; `python -m thecornerfc sync cup_lineups`, also nightly). Player stats from them aren't stored, so the player ratings stay league-only, but the club page's formations, starts by position and predicted replacements count every competition.

**Kit colours.** The club page pitches are drawn in the club's home kit: the shirt and number colours from its latest home line-up (`team_colors`). New line-ups update them as they're fetched, and `python -m thecornerfc sync colors` fills in clubs that have none (it also runs nightly).

The site reads the matches (the last 21 days and the next 60) and the rankings from the database, where `python -m thecornerfc export` puts them; it uses the database's public key, which can call only the functions granted to it, so the site holds no credentials. To view it on this PC, run `python -m http.server` in `docs/` and open http://localhost:8000: it shows the published data. Add `?data=files` to the address to read a local export in `docs/data` instead (the files a local `export` writes; views that ask the database for rows, such as the Matches tab, still show the published ones).

**Match explanations.** A match card leads with the projected goals, the likely score, and the model's and the market's home/draw/away chances. Below those it lists up to three **Key reasons**: the model inputs that moved the expected margin (or the expected total) most, at 0.05 goals or more. **Model detail** opens the rest:
- Current, Baseline and match strength.
- Every term of the expected margin: strength gap, home advantage, European tie, the clubs' own home/away records, known absences and predicted line-ups.
- What the attack/defence tendencies add to the expected total.
- The model − market difference, labelled as a disagreement and not a betting edge.
- When the inputs, injury list and odds were captured, and the model version.

None of this is worked out in the browser, and a page asks only for the match it is showing. `match_explanations` works out each match's key reasons, which come with the match from `site_matches`. The full breakdown is a column of the match's row in the `site.matches` table, which the export rewrites whole (`store_matches`: every match on the site with the row the site draws, its key reasons and its detail); the site asks `site_match_detail(fixture)` for it when that card's model detail is opened (`db/migrations/20261005_site_matches.sql`, applied 2026-10-05). Until the table exists the export writes the breakdown to the match's own file, `docs/data/fixtures/<fixture_id>.json`, as it did for a day, and the site reads that. The match's line-ups are not exported at all: when they are opened the site asks the database for that one match (`site_lineups(fixture)`, `db/migrations/20261005_site_lineups.sql`, applied 2026-10-05), which reads the predicted XI, the XI that started and the pre-match prediction from their tables, by team: `xi`, `actual`, `prematch`. Until 2026-10-05 every match's breakdown and line-ups were downloaded together (2 MB in `explanations.json`, 2.7 MB in `players.json`). For each shown prediction it picks the `match_prediction_snapshots` row that produced it, then rebuilds the parts with `predictions.explain`. That uses the same `margin_terms` and base-goal functions `predict_match` sums. A match is left out unless the rebuild gives back the stored margin and projected goals to 1e-6. So a prediction made under different settings, or before snapshots existed, shows no breakdown rather than a wrong one. The snapshots' 12-month record lists are summed in the database, so they never leave it.

**Recording projections.** Predictions for a fixture stop updating at kickoff, so the last nightly projection before the match is kept. `fixture_predictions.source` shows where each projection came from:
- `live`: recorded before kickoff.
- `backfill`: reconstructed afterwards for matches since July 2023, using each team's pre-match rank and goal averages. It shows what the current model would have said at the time.

Result cards show `proj` for live projections and `recon` for backfilled ones. The **Stats** tab (`docs/data/stats.json`) scores the projections over 7, 30 and 90 days and 12 months, by competition. It shows how often the predicted result was right, exact scores, goal error, log loss, Brier score and calibration. **Every market: model vs bookmakers** compares log loss with the bookmakers in each market (result, both teams score, over/under 1.5–4.5) on the same matches. It uses closing prices, and opening prices for matches whose odds were collected before kickoff (`export.market_consensus`, which removes each bookmaker's margin in the database). Beating the opening price is where an early edge would show first.

**Ratings.** Every finished match's projection is rated from 1 (terrible) to 5 (excellent), using MatchLab's grading ported to `thecornerfc/rating.py`. There are five factors, each scored 0–5 and weighted:
- Winner 30%
- Margin 25%
- Clean sheets 20%
- Shape 15%
- Goals 10%

The weighted total is rounded, and a 0 counts as 1. The overall rating and the five factor scores are stored on `fixture_predictions` (`rating`, `rating_winner` and so on). Result cards show the rating as a coloured badge, and tapping a card shows the breakdown. The Stats tab shows the average rating, the spread of 1s to 5s and each factor's average. New results are rated nightly, and the last 14 days are re-rated in case a score was corrected.

Conventions in `docs/assets/app.js` added with the 2026-10 audit:

- **What each tab is.** `TAB_INFO` holds one sentence per tab, a link into `methodology.html`
  and a key to its terms, drawn under the tab's name. A new column or term goes in the key.
- **Addresses.** A tab's choices ride in its address (`#/matches?d=2026-10-11`, `#/stats?r=90d`,
  `#/simulation?m=OU25`, `#/nations?c=UEFA`; `TAB_QUERY`), and a page's sub-tab too
  (`#/club/42/matches`). An address that names no page says so (`showNotFound`).
- **Data files by content hash.** `export.write_manifest` writes `docs/data/manifest.json`, a
  short hash of each top-level data file. The site asks for `file.json?v=<hash>` and keeps the
  browser's copy until the hash changes, checking the copy's hash before trusting it. Anything
  that writes a top-level data file must rewrite the manifest (`tests/test_manifest.py`). A job
  that writes only some of the files (match day, nations) builds it from the stored rows' hashes
  and its own files.
- **Tables and focus.** `describeTables` names every table and marks its headers for screen
  readers; the menu and the pop-ups move focus in and back. The open tab is at least a screen
  tall, so the footer isn't pushed down when the data arrives.

## Tables

`leagues`, `league_seasons`, `venues`, `teams`, `team_seasons`, `fixtures`, `fixture_team_stats`, `standings`, `bookmakers`, `bet_types`, `odds`, `team_rank_history`, `team_rankings`, `fixture_predictions` (and the view `upcoming_predictions`), `players`, `player_seasons`, `injuries`, `fixture_players`, `paper_bets`. See `db/schema.sql`.

### API usage and quota protection

`python -m thecornerfc usage` reports recorded attempts today (UTC), totals by
endpoint and workflow, the latest run, and the last observed daily quota with its
timestamp. It works with `THECORNERFC_NO_API=true` and needs no database connection.
An illustrative populated report is:

```text
API attempts today (UTC): 143; successful: 140
By endpoint: fixtures=120, teams=20, status=3
By workflow: Nightly sync=120, Backfill leagues=23
Latest run 123456/1: 23 attempts
Last observed daily quota: 6850 (at 2026-09-26T10:00:00+00:00)
Subscription allowance period: unconfirmed; no monthly allowance assumed
```

The SQLite ledger defaults to `.api-usage/ledger.sqlite3` (`API_LEDGER_PATH`).
It records each HTTP attempt, including retries and transport failures, with UTC
time, endpoint, SHA-256 parameter digest, workflow, run and process identifiers,
command label, HTTP status, response record count, observed daily quota, duration,
success and a short error category. No API keys, raw parameters or response bodies
are stored. HTTP 200 API errors count as failures. Transport failures have unknown
HTTP status and quota; an attempt is not proof the provider charged a request.
Daily totals reflect this client only, not other consumers of the account.

Actions share the ledger through a separate cache and archive a copy as an artifact
on every run, including failed jobs; summaries appear in logs and the job summary.
The existing shared concurrency group serializes these workflows. Cache eviction,
branch cache scope, artifact retention or abrupt runner termination can leave gaps;
this is lightweight operational tracking, not an authoritative billing ledger.
Download an artifact and point `API_LEDGER_PATH` at its SQLite file to inspect it.
Local ledgers persist on disk. Ledger write errors stop execution rather than silently
continue spending untracked quota. Parallel local processes should use separate run
IDs; the optional budget check is designed for sequential execution, as in Actions.

`API_QUOTA_WARN_THRESHOLDS=2000,1000,500` configures absolute daily remaining-call
warnings. The existing `API_DAILY_RESERVE=200` still applies and is now checked before
retries too. Retry counts and backoff delays are unchanged. The approximately 75,000
subscription allowance has **no confirmed period** in repository configuration;
no monthly or subscription-period reset is assumed or enforced. Quota protection
uses the observed daily remaining header only. A displayed quota may be stale;
the report always includes its observation time.

Manual backfills now accept a `call_budget` (default 2,000 attempts). Before ingestion,
a preflight prints a lower bound for league/team/fixture/standing requests, calls
`status`, and verifies the budget fits above the daily reserve. Stats for newly
fetched fixtures, odds pagination and retries are additional unknown costs. The cap
is enforced across every process in that Actions run, including preflight and retries;
a cap stop may leave a partial backfill that can be resumed in a later run.
For intentional local backfills, use the existing local safety override and share
an explicit unique `API_RUN_ID` and positive `API_RUN_BUDGET` across preflight and sync
commands. `API_RUN_BUDGET=0` disables the extra cap, not the daily reserve. Preflight
requires a positive budget and an observed daily quota header.

Additional SQLite queries (no API calls):

```sql
-- Calls today (UTC)
SELECT count(*) FROM api_calls WHERE timestamp >= date('now');
-- Calls by endpoint / workflow today
SELECT endpoint, count(*) FROM api_calls WHERE timestamp >= date('now') GROUP BY endpoint;
SELECT workflow, count(*) FROM api_calls WHERE timestamp >= date('now') GROUP BY workflow;
-- Processes/commands within runs
SELECT run_id, process_id, command, count(*) FROM api_calls GROUP BY run_id, process_id, command;
-- Last observed remaining daily quota
SELECT quota_remaining, timestamp FROM api_calls
WHERE quota_remaining IS NOT NULL ORDER BY id DESC LIMIT 1;
```

### Pipeline and dataset health

```bash
python -m thecornerfc health
```

This reads recorded health without making API calls or connecting to Postgres, and
works with local `NO_API` / read-only mode. A fresh ledger reports `UNKNOWN` and an
overall `WARNING` until stages have run. Example after several pipeline runs:

```text
Overall: WARNING
teams HEALTHY
fixtures HEALTHY
standings HEALTHY
players HEALTHY
club_ratings HEALTHY
player_ratings HEALTHY
predictions HEALTHY
injuries STALE
odds HEALTHY
exports HEALTHY
```

The actual report includes a concise explanation for each dataset and the latest
command's status/failed stage. `FAIL` exits 1; warnings and informational results
exit 0. `STALE` means no successful monitored stage within `HEALTH_STALE_HOURS`
(default 72), not that a league should have played a match recently. `RUNNING`
without completion can indicate an interrupted process and is a warning.

Two small tables share the existing SQLite API ledger and its Actions cache/artifact:

- `pipeline_runs`: one row per CLI command, linked by Actions run ID/attempt, with
  workflow, command, code SHA, start/completion, status, failed stages, API attempt
  count, last observed quota during that command, warnings and exception type.
- `dataset_status`: latest attempt, last healthy success, status, row count, latest
  underlying timestamp where available, message, command-run ID, and previous
  successful count. Failed/warning observations never replace the healthy baseline.

The health hooks surround existing ingestion/rating/prediction/export stages. They
also record exceptions caught by the nightly runner. A later successful league in
the same command cannot erase a failure or warning. Health queries are SELECT-only;
monitoring does not change football calculations or refresh schedules. Error
records retain exception types rather than potentially sensitive exception text;
use the existing stage logs for debugging. Hard termination can leave `RUNNING`
records, and cache eviction can lose history, as described under API usage.

Checks distinguish fatal failures from coverage warnings:

- **FAIL:** stage exceptions; player/club-rating/player-rating populations below
  `HEALTH_COLLAPSE_RATIO` (default 20%) of their last healthy count, when that count
  was at least `HEALTH_MIN_BASELINE` (default 100). This uses stored populations,
  not short seasonal windows. First observations establish a baseline.
- **FAIL:** existing staged export validation rejects invalid JSON, missing critical
  files and catastrophic major JSON/detail population shrinkage before publication.
  Export failures are now recorded as dataset and pipeline failures. Existing output
  stays in place when build/validation fails. Full export success updates `exports`;
  matchday's partial bets/injuries exports do not claim a full export succeeded.
- **WARNING:** zero teams/fixtures in league seasons between seven days after their
  recorded start and their end; absent standings only where coverage says standings
  are supported. Checks do not rely solely on the provider's `is_current` flag.
- **WARNING:** upcoming fixtures in the next seven days lack predictions; no odds
  for fixtures in the next three days in leagues with odds in the previous 30 days.
  Empty upcoming windows are informational, including off-season.
- **WARNING:** every successful API response for an ingestion stage is empty. This
  catches silent empty responses even when upserts leave historical DB rows intact,
  including zero injury responses across the major leagues. Empty injuries are
  never automatically fatal and may reflect legitimate coverage/season conditions.

Global row counts describe stored datasets, not rows changed by a single league
sync. Underlying timestamps are table update/provider times, except club ratings
use their latest contributing match; player position ranks have no source timestamp.
These timestamps are distinct from the stage's last successful refresh. Checks flag
suspected issues; they do not roll back model outputs already committed by a stage.
Fatal checks stop normal subsequent publication through the CLI's failure status.

All three Actions workflows include an always-run health summary and persist the
ledger even on failure. No external monitoring service or production schema
migration is required. SQL examples against the downloaded/local SQLite ledger:

```sql
SELECT command, started, completed, status, failed_stage, api_calls, quota_remaining
FROM pipeline_runs ORDER BY started DESC LIMIT 20;
SELECT dataset, last_attempt, last_success, status, row_count,
       latest_data_timestamp, message FROM dataset_status ORDER BY dataset;
```

### Shared model versions and snapshot conventions

Model provenance is registered in `model_versions`, through
`thecornerfc.model_versions.register_model_version`. Supported `ModelType` values
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
from thecornerfc.model_versions import ModelType, current_code_sha, register_model_version

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

### Immutable match prediction capture

`match_prediction_snapshots` is now the domain-specific historical store.
`fixture_predictions` continues serving current website state. Apply the registry
migration first, then `db/migrations/20260926_match_prediction_snapshots.sql`, before
running the updated prediction code. Both are included in `db/schema.sql`. No old
prediction rows are copied, rewritten, or claimed as genuinely captured snapshots.

Nightly, matchday and `predict` all capture through `update_predictions`; the existing
nightly reconstruction path captures through `backfill_predictions`. Current output
and snapshot inserts share one transaction and commit together. Missing snapshot
schema or a failed insert fails the prediction stage rather than silently losing
history. Apply the migration before deploying these writers.

Each row preserves fixture/teams/league, registry version, all W/D/L probabilities,
projected xG, expected margin, likely score, over-2.5 and BTTS probabilities, observed
kickoff (`effective_at`), capture time, DB insertion time and seconds to kickoff
(divide by 60 or 3600 for minutes/hours). `model_reference_at` separately records the
clock used for the rank blend and history window: live computation start or the
historical kickoff for a reconstruction. Capture time is taken after inputs were
read and the prediction computed; it is never backdated to the historical event.

The match-specific `inputs` object records actual calculation arguments:

- Current ranks, LT ALGO baseline ranks, blended match ranks; live reliability,
  fallback starting rank and whether a team's default rank was used.
- Home-at-home and away-at-away goal/xG form pairs, and competition goal averages.
- `sides`, in existing function order: home/away attack splits, home/away home-edge
  adjustments, home/away competition goal bases. The attack split is
  `(attack - current_rank) / 2`; edge is `home_rating - current_rank`.
- `predicted_lines`: home and away `[GK, DEF, MID, FWD]` averages, or null. Partial
  lines remain partial; the existing model uses them only when all are present.
- Home/away missing strengths, preserving null versus measured zero. The model's
  actual fallback to zero stays unchanged.

The registry captures the actual match constants, including home advantage,
European bonus, injury beta, home-edge and attack/defence weights, line weights,
Poisson and market calibration constants, plus source-file digests. These constants
and stored arguments permit the existing `predict_match` calculation to be replayed
without querying today's mutable inputs. No artificial explanation components or
unavailable upstream version IDs are invented. Source digests distinguish changed
code even when a working tree has no trustworthy clean Git SHA.

`source` has three explicit values:

- `prospective`: captured **and inserted** before the kickoff known at observation.
- `reconstruction`: historical/backfilled calculation made later; never eligible
  as genuine pre-event evidence, regardless of its calculated inputs.
- `late_observation`: current-state calculation at/after kickoff. The current model
  can process stale `NS`/`TBD` fixtures up to three hours late; those never become
  prospective snapshots. A DB trigger also downgrades a prospective insert that
  crosses kickoff while the batch is being written.

Normal writers use INSERT with conflict DO NOTHING. Database triggers prohibit
UPDATE, DELETE and TRUNCATE, validate match-model references, and generate insertion
time. The content key includes fixture, model version, source, kickoff, actual inputs
and outputs, but excludes observation/reference clock metadata. An identical retry
keeps the first row and timestamp. A changed prediction, model, input or kickoff
creates a new row. The existing rank blend varies with time-to-kickoff; those input
and output changes are scientifically relevant and are retained. This is a history
of distinct prediction states, not a heartbeat log of every computation.

For prospective evaluation, explicitly filter rather than combining sources:

```sql
SELECT fixture_id, captured_at, effective_at AS kickoff,
       seconds_to_kickoff / 3600 AS hours_to_kickoff, model_version_id,
       p_home, p_draw, p_away, home_xg, away_xg, likely_score
FROM match_prediction_snapshots
WHERE source = 'prospective'
ORDER BY fixture_id, captured_at;
```

Prospective means pre-scheduled-kickoff capture based on the fixture state then
available; it does not certify upstream vendor data timeliness or the actual start
of a rescheduled match. Snapshot capture begins with deployment. The existing
backfill still fills only missing current predictions; it does not manufacture a
retrospective snapshot history for every already-populated fixture.

### Lineup prediction and availability evidence

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
- Manual entries in `thecornerfc/absences.json` add exclusions. Optional `from` and
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

### Immutable odds and paper-simulation evidence

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

### Immutable daily player-rating history

Apply `db/migrations/20260926_player_rating_history.sql` after the model registry
migration before deploying this writer. Existing ranking/player tables and formulas
are unchanged. No historical ratings or ranks are fabricated from current data.

The first successful player-rating rebuild each UTC day stores a complete capture:
`player_rating_captures` holds observation time, DB write time, player model version,
season and population; `player_rating_history` holds each player's rating, world
rank, position/group, team and team-source, rolling-window minutes, season minutes,
and season-model versus fallback rating source. `player_rating_snapshot_history`
joins these into one convenient read view. Daily header and rows commit atomically
with the current rating rebuild. A failed transaction leaves the day available for
retry. Later same-day rebuilds do not replace that day's capture, even if values or
versions change; this is daily movement history, not intraday tracking.

World rank is the descending competition rank of the entire **captured currently
rated population** (ties share a rank, e.g. 1, 1, 3). It is not a claim to cover all
players worldwide or necessarily the frontend's filtered population. Ratings are
stored at the same one-decimal precision as the current player table. Team is the
latest observed squad assignment where present, otherwise the season model's team,
otherwise NULL; `team_source` makes that distinction explicit. It records what was
known, not a verified transfer registry. Zero season minutes remain zero (estimated
season evidence), and missing evidence stays NULL.

All UPDATE, DELETE and TRUNCATE operations on the new history tables are blocked
in normal operation. Daily uniqueness plus a transaction lock prevents duplicate
captures. Model versions include relevant configuration and player-code digests.

```sql
SELECT * FROM player_rating_movement WHERE player_id = 123;
```

This view supplies `7d`, `30d`, `90d` and `season` comparisons using only persisted
history. Day horizons select the latest actual observation at or before the cutoff;
season movement uses the earliest earlier observation in the current captured season.
`baseline_at` shows the exact baseline, including gaps or a mid-season start of
capture. Missing baselines produce NULL movement, not zero or a reconstruction.
Positive `rating_change` means increased rating; positive `rank_movement` means an
improved rank. `model_changed` and both model IDs flag cross-version comparisons;
`population` and `baseline_population` expose changing comparison populations.
A player's latest capture time remains visible if they later leave the rated cohort.
The global season label follows the existing model's `this_season` calculation,
not an inferred per-league calendar. Time elapsed before this feature's deployment
has no genuine observations and cannot supply movement baselines.

Expected annual growth at daily frequency is **365 × captured player count** (366
in a leap year), plus 365 tiny header rows. The checked-in player export currently
contains **7,532 players**, a useful proxy rather than a measurement of the full
rated DB population: approximately **2,749,180 rows/year**. Budgeting roughly
**250–400 bytes per row including the heap and two indexes** gives approximately
**0.69–1.10 GB/year** (decimal units), excluding WAL, backups, replicas and bloat.
At 20,000 captured players the estimate is **7.3 million rows / 1.83–2.92 GB/year**.
These are planning estimates; header-level shared metadata avoids repeating long
version IDs/timestamps in every player row. No retention/deletion job is introduced.

Measure the actual population and storage after deployment:

```sql
SELECT captured_at, population, population * 365::bigint AS annual_rows
FROM player_rating_captures ORDER BY captured_at DESC LIMIT 1;
SELECT pg_size_pretty(pg_total_relation_size('player_rating_history')) AS history_with_indexes,
       pg_size_pretty(pg_total_relation_size('player_rating_captures')) AS captures_with_indexes;
```

### Fantasy Premier League evidence

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
  `docs/data`), and the page reads them through `fpl_owner_data`, which answers only when
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
fixes go in `thecornerfc/fpl_overrides.json`, keyed by FPL code. FPL fixtures join API-Football
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

### My FPL team

The **My FPL team** page runs the owner's own FPL team (entry 3996593, `FPL_TEAM_ENTRY`): it
suggests this week's transfers, plans the next six gameweeks, sets the line-up and captain, and
says when to play each chip left. **Owner's decision, 2026-09-30:** read FPL's manager endpoints
for this entry (`entry/{id}/`, `entry/{id}/history/`, `entry/{id}/transfers/`,
`entry/{id}/event/{gw}/picks/`) and show the squad, plan and chip advice publicly. It's a new FPL
source under the licensing notes above, and no other entry is read. Since 2026-10-02 the page is
for the owner only (see the licensing notes): its menu entry, and the FPL tab's, appear once the owner has
signed in in that browser (README: Accounts).

- `python -m thecornerfc fpl team` (in the FPL update and nightly workflows, after the export)
  stores `fpl_team` in `fpl_owner_docs`: the squad after any transfers already made for the next
  deadline, each player's selling price (bought at FPL's start price, or at `element_in_cost` for
  later buys, keeping half of any rise), bank, free transfers (1 a week up to 5, less those used;
  a Wildcard or Free Hit week keeps them), chips with their windows from `bootstrap-static`, and
  the season's history. API-Football ids come from `fpl_id_map_current`.
- The planning runs in the browser (`docs/assets/fpl-planner.js`, tested by
  `tests/fpl_planner.test.mjs`) from `fpl_predictions`. It's a beam search over six weeks.
  Each week it rolls the free transfer or makes the best one, two or three moves, and a move
  beyond the free ones costs 4 points. A squad scores its best legal XI with the captain doubled,
  plus 0.1 of the bench. Each later week is weighted 0.9 of the one before, and a free transfer
  still banked at the end is worth 1.5 points. Chips: Triple Captain's gain is the captain's
  points, Bench Boost's the bench's, Free Hit's the best one-week squad over the planned one, and
  Wildcard's the best squad over six weeks against the plan (first four weeks only). A chip is
  advised once its week's gain reaches 10 / 18 / 12 / 15, which usually takes a double
  gameweek. Otherwise it's held, unless its window closes within the predictions. All of these
  numbers are judgment, not fitted.
- **Locking in.** "I've made these transfers" calls `lock_fpl_transfers` in Supabase with the
  week's moves. The page then plans from the squad after them, until the next FPL update reads
  the real transfers from FPL (FPL's squad wins). The page carries Supabase's public anon key
  (`SUPABASE` in `app.js`), and CSP `connect-src` allows only this project.
  `lock_fpl_transfers` / `unlock_fpl_transfers` and `fpl_owner_data` (which returns the lock-ins)
  are SECURITY DEFINER, can be called by signed-in visitors only, and do nothing unless the
  caller's confirmed email address is the one in `fpl_team_owners` for the entry
  (`db/migrations/20261004_fpl_owner_login.sql`; before 2026-10-04 they checked a passphrase).
  `20260930_fpl_team_locks.sql` also revokes anon's read of the `upcoming_predictions` view,
  since views skip RLS.

  One-time setup:
  1. Run `db/migrations/20260930_fpl_team_locks.sql` in the Supabase SQL editor (it's also in
     `db/schema.sql`).
  2. Put the project's anon (or publishable) key from Supabase → Project Settings → API Keys into
     `SUPABASE.key` in `docs/assets/app.js`.
  3. Run `db/migrations/20261003_fpl_owner_docs.sql` (owner-only FPL data; applied 2026-10-03,
     also in `db/schema.sql`).
  4. Run `db/migrations/20261004_fpl_owner_login.sql` (applied 2026-10-04, also in `db/schema.sql`), then say whose sign-in is the owner's:
     `INSERT INTO fpl_team_owners VALUES (3996593, 'owner@example.com') ON CONFLICT (entry_id) DO UPDATE SET email = EXCLUDED.email;`

### The site's data in the database (step 1)

**The site's data is not in the repository (since 2026-10-05).** The export writes its files to `docs/data` in the job's working copy (ignored by git) and sends them to the database; the workflows commit nothing and have read-only access to the repository. Old copies of the data are still in the repository's history.

`site.docs` holds every file the export writes, one row per file, keyed by its path without `.json` (`matches`, `clubs/42`). `export.mirror_site_docs` writes it after every export, `nations` and `matchday` run: only rows whose file changed are written, in one transaction. After a full export, rows whose file has gone are deleted; a job that writes part of the data (`matchday`: bets and injuries; `nations`) names its files, writes just those rows and deletes nothing, so it doesn't matter that its working copy holds nothing else. A read-only run (a local one) skips it with a log line. A failed write stops the run with an error, so the workflow goes red: the site reads these rows, and would otherwise go on showing the old ones behind a green run. The next run writes every row whose file differs, so it catches up without help.

- The table is in the `site` schema, which the Data API doesn't expose. The only way to read it is `site_doc(key)`, which returns one row's JSON and never a row marked `paid`.
- **A visit loads two files, whatever it opens on** (since 2026-10-05): `site.json` (the competitions, the clubs' names and when the data was made; 60 KB) and `rankings.json`. Everything else is fetched by the views that show it, the first time one opens: the matches by the Matches tab, Model vs Market and club, player and league pages; the model's record by Stats; the paper bets by the two betting tabs; the cup files by the Clubs and Players tables. Before that every visit downloaded all of them (`TAB_NEEDS` in `app.js`).
- **Matches are asked for as they are shown.** The Matches tab asks the database for the day on screen (kick-offs between the visitor's local midnights) or, with one competition picked, that competition's matches for its rounds; a club's page, a player's page and the team pop-up ask for that club's; a league page for that competition's; Model vs Market for its open selections' matches by id. All through `site_matches(from, to, leagues, team, ids)`, which returns the rows and the key reasons each card shows, never more than 2,000 and nothing without an argument. `site_match_days(tz)` gives the date controls and the competition menu what they need without any match: matches per competition per day of the visitor's calendar. The script keeps what it has fetched in `state.data.matches` and draws from that as before (`matchStore` in `app.js`). There is no file of every match: if the database can't answer, the view says it couldn't load. `db/migrations/20261005_site_matches_queries.sql` (applied 2026-10-05).
- **Players are asked for as they are shown.** The export stores every listed player as a row of `site.players` (`store_players`: the columns the queries filter and sort on, and the player as the site draws him, with his world and league places worked out once). The Players table asks `site_players(...)` for the 100 rows on screen: the competition, Exclude, age, position, club, nationality and range filters, the search and the sort are all arguments, and scrolling asks for the next 100. The numbers in its competition menu are the same call with `p_count` (players per league and club for the filters as they are), and what the filter boxes need without any player (the ranges, how many play each position, the clubs and nationalities) is `site_player_facets()`. A club's page and the squad lines and line-ups on a match card ask for that club's players, a nation's page for that nationality's, and views that only name players (the injured list, a national squad, the fantasy tabs) for those ids, 1,000 a request. A club's predicted XI for its next match is `site_next_xi(team)`, read from `predicted_lineups`. The search is split between the two sides: the page knows the clubs' search text (short forms, leagues, countries), so it sends each word with the ids of the clubs it fits, and the database matches the names. The script keeps what it has fetched in `state.players.list` and draws from that as before (`playerStore` in `app.js`); there is no list of every player to fall back on, in the site or the export: if the database can't answer, a page draws without its players and the Players table and a player's page say they couldn't load. `db/migrations/20261005_site_players.sql` (applied 2026-10-05; on the real database a page of 100 players is about 7 KB and answers in 0.2 to 0.4 s, sixteen requests at once included). `site_next_xi` was slow there under load and is rewritten in `db/migrations/20261005_site_next_xi_fast.sql` (applied 2026-10-05: 24 clubs asked at once all answered, where 7 of 24 had timed out). Every request to the database is sent once more if it fails outright or with a server error (`askDatabase` in `data.js`). Before the export rewrites `site.matches` or `site.players` it stops if the table would lose more than half its rows (`_check_table_collapse`), as the files' check does. Checked before it went in: the site as it was and the changed one drew the same text over 93 steps through the Players table and 39 club, player, nation and match pages, with the players read from the database, from the whole file, with the database not answering, and with requests posted.
- **The site reads the database** (since 2026-10-05): every data file comes through `site_doc`, and there are no data files on the published site to fall back on: if the database doesn't answer, the page says it couldn't load. `?data=files` in the address reads `data/` beside the page instead, which only a local copy with its own export has (`docs/assets/data.js`).
- Unchanged data isn't downloaded again. The site asks for a row with its content hash from the `manifest` row (`site_doc(key, hash)`); when the hash is the row's, the database tells the browser to keep the answer for a year. Rows outside the manifest (club, player, league and nation pages) are fetched each time.
- The migrations are `db/migrations/20261004_site_docs.sql` (applied 2026-10-04) and `db/migrations/20261005_site_doc_cache.sql` (the hash argument; applied 2026-10-05) and `db/migrations/20261005_site_doc_raw.sql` (**not applied yet**). All are in `db/schema.sql`, with their checks at the bottom of each file.
- **Speed.** A row is the published file's own text (`json`, not `jsonb`) and `site_doc` returns it as the response body (the `"application/json"` domain), so nothing is rebuilt on a read. That is the third migration: before it, `players` (5 MB) took 2 to 4 seconds and `lineups_history` (8 MB) ran into the anon role's 3 second limit, more so with several readers at once. Browsers get the answer Brotli-compressed (`players` about 0.6 MB).

### Accounts

Visitors can sign in with Google or with an email and password (Supabase Auth; **Sign in** in the
header). The only thing an account unlocks is the owner's: the FPL predictions and My FPL team
answer only the sign-in named in `fpl_team_owners` (My FPL team, below). The code is the "accounts" section of `docs/assets/app.js`.

- **Library.** `docs/assets/lib/supabase-js-2.117.2.js` is `dist/umd/supabase.js` from the npm
  package `@supabase/supabase-js` 2.117.2, unchanged (the page's policy allows scripts from this
  site only). It is fetched only when the sign-in box is opened or a visitor is already signed
  in. To update it: `npm pack @supabase/supabase-js@<version>`, copy that file in under the new
  name, and change `AUTH_LIB` in `app.js` and the name and hash in `tests/test_accounts.py`.
- **Supabase settings** (Authentication): Google and Email providers on, with Confirm email;
  Site URL `https://thecornerfc.com`; Redirect URLs `https://thecornerfc.com/**` and the local
  preview address; custom SMTP for the emails. Google's OAuth client lives in the Google Cloud
  project "The Corner FC"; its secret is held by Supabase only.
- **Email links.** Supabase's default links only work in the browser that asked for them. To
  make them work anywhere, set these in Authentication → Emails → Templates:
  Confirm signup `{{ .RedirectTo }}?token_hash={{ .TokenHash }}&type=email`,
  Reset password `{{ .RedirectTo }}?token_hash={{ .TokenHash }}&type=recovery`.
- **Deleting an account.** Account → Delete account calls `delete_my_account()`
  (`db/migrations/20261004_delete_my_account.sql`), which removes the caller's own row from
  Supabase Auth and nothing else.
- **Retention.** The nightly run deletes email sign-ups never confirmed within 7 days
  (`thecornerfc/accounts.py`; the privacy page promises the same). Confirmed accounts are kept
  until their owner deletes them.


### Paid tier (built in part, switched off)

`db/migrations/20261006_paid_tier.sql` lays the foundation for a subscription. Nothing changes for any visitor while its switch is off, which is how it ships.

- **The switch** is the row `paywall` in `site.settings` (`false`). While it is false, `site.entitled()` is true for everyone and every query answers as before.
- **Who subscribes** is `public.subscriptions`, one row per account (status, plan, paid-up-to date, the payment provider's ids). No key can read or write it; a payment provider's webhook will write it, and until one exists a row can be added by hand in the SQL editor. `site.subscriber()` is true for a signed-in account with a live row (a failed renewal keeps it for 3 days) and for the site's owner (`fpl_team_owners`).
- **What is gated so far: matches.** With the switch on, `site_matches()` gives anyone who isn't entitled a cut-down row for a match that hasn't kicked off: within 7 days the win, draw and loss chances stay and the projected goals, likely score, over 2.5, both-to-score, absences and line-up ratings go (`export.MATCH_PAID_DEPTH`); further ahead the chances go too (`MATCH_PAID_CHANCES`); the key reasons go for both, and `site_match_detail()` answers `"locked": true`. Matches that have kicked off are always whole. The export stores the cut-down rows beside the full one (`site.matches.data_free`, `data_locked`), so nothing is worked out per request.
- **The page.** A subscriber's requests carry their sign-in (`siteAuth` in `data.js`), set up once `my_subscription()` has said this account subscribes; nobody else's requests change. Where the database left the paid fields out, a match card says what is behind the lock, with a "What subscribers get" box. The account box shows the subscription once the switch is on.
- **League pages** (`db/migrations/20261006_site_league.sql`). A league's file carries every remaining fixture's projected goals and chances, which the page plays out for the projected table. Once `site_league()` exists, the export writes two rows per league: `leagues/<id>`, cut down (`export.cut_league_fixtures`: chances for the next 7 days only, no projected goals, `"cut": true`), and `paid_leagues/<id>`, whole and stored as a paid row, which `site_doc()` never returns. `site_league(id)` gives the whole one to anyone entitled and the cut-down one otherwise; the page asks it and, where it gets the cut-down one, says the projected table is for subscribers. Before the function exists the export writes the one whole file as before.
- **Predicted line-ups** (`db/migrations/20261006_paid_lineups.sql`). `site_lineups()` leaves out the predicted XI of a match that hasn't kicked off for anyone not entitled (`"locked": true`), and `site_next_xi()` answers `{"players": null, "locked": true}`; the XI that started and the pre-match prediction of a finished match stay free. Where the page learns it is behind the paywall, a match card has no "Predicted line-ups" button and a club's Predicted XI tab says it is for subscribers (the browser's own stand-in XI, built from who has started this season, isn't offered either).
- **Not gated yet, so the switch must stay off:** the player ranks (`site_players`). There is no checkout: taking payment comes last.
- **Checked** on a throwaway Postgres with the migration applied twice: switched off, the answers are the same as before it; switched on, a signed-out visitor, a plain account and a lapsed subscriber get the cut-down rows, and a subscriber, a late payer inside 3 days and the owner get everything; neither key can read the tables.

### Retention and removing a person

What the privacy page promises, and where it is kept (`thecornerfc/retention.py`, run at the end
of the nightly sync; a failure is logged and never fails the run):

- Sign-ups left unconfirmed for 7 days are deleted.
- The medical reason on `injuries` rows is blanked once the row is two seasons old. Bans, rest
  and the other non-medical reasons are kept, and so is the fact that he missed the match.
- FPL news text (`fpl_player_states.news`, and the copy in the fantasy snapshots) has no job:
  both tables are append-only evidence. Review it each July.

To remove a player or manager who asks (privacy page, "People the site covers"):

1. `python -m thecornerfc suppress --player <API-Football id>` (or `--coach <id>`) lists the
   tables that hold rows for them. Nothing changes yet.
2. Add `--apply`: their rows are deleted, and the id goes into `thecornerfc/suppressed.json`,
   which `db.upsert` reads, so no later sync stores them again. Append-only evidence tables refuse
   the delete and are listed as kept; those rows are never published by name.
3. Commit `suppressed.json`, then run the export (the nightly run does, or run a workflow by hand).
4. Old copies stay in git history. Offer to rewrite it for their files if they ask.
- **Local preview.** `python3 -m http.server 8000 --directory docs`, then `http://localhost:8000`.

### Fantasy expected points (v1.1, evidence only)

`thecornerfc/fantasy.py` gives each Premier League player's expected FPL points per fixture from:
- expected minutes (P(start), P(sub), minutes as starter and as sub)
- the match model's team goals, shared out by shots on target and key passes (not by overall rank)
- clean sheets and goals conceded from the same Poisson rates
- goalkeeper saves

Bonus, cards, own goals and penalties are not modelled. The backtest and its limits are in
`experiments/fantasy_v1/REPORT.md`. It could not be compared with official FPL expected points or
price, because no FPL data is captured.

The parameters are frozen in `thecornerfc/fantasy_params.json`. After predictions,
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

### Chronological evaluation

The evaluation CLI reads immutable evidence without API calls, production writes,
model fitting or changes to formulas:

```bash
python -m thecornerfc evaluate matches --from 2026-09-01 --to 2026-10-01 --hours-before 24 --output match-evaluation.json
python -m thecornerfc evaluate lineups --hours-before 1
python -m thecornerfc evaluate betting
python -m thecornerfc evaluate clubs --include-records --output club-experiment.json
python -m thecornerfc evaluate players --include-records --output player-experiment.json
python -m thecornerfc evaluate fantasy
```

Reports are JSON on stdout and optionally in `--output`. `--include-records` includes
selected snapshot rows, IDs, observed inputs and evaluation labels for downstream
experiments; omit it for aggregate-only reports. The SQL transaction is explicitly
read-only and repeatable-read. Local NO_API mode works; configure the usual read-only
DB connection. Fantasy reads the FPL evidence tables below and reports n=0 until a fantasy model writes snapshots.
Missing migrations or database failures fail visibly; no current-table fallback is used.

Selection rules are part of every report:

- Default source is **prospective immutable snapshots**. `--source reconstruction`
  explicitly selects only reconstructed match evidence (matches/clubs); these are
  never pooled with prospective captures. There is no implicit reconstruction.
- `--from` is inclusive and `--to` exclusive. Defaults cover 90 days ending at
  `--as-of` (now by default). Dates without zones mean UTC. Match/lineup/club windows
  use known kickoff; player windows use capture time; betting uses decision time.
- Match/lineup evaluation chooses the latest eligible snapshot per fixture/team at
  least `--hours-before` kickoff (default 0). Capture and database insertion must
  satisfy the cutoff. Reconstructed matches use their explicitly labelled historical
  evidence and do not pretend their capture clock satisfies a pre-event horizon.
- Match scores use regulation time. AET/PEN matches without regulation scores are
  excluded rather than using extra-time totals. Snapshots whose recorded kickoff
  differs from the fixture's current kickoff are excluded to avoid silently changing
  the horizon. Match labels are current DB results observed when evaluation runs;
  **the repository has no immutable match-result revision history**, so `--as-of`
  controls prediction evidence, not historical truth of subsequently corrected scores.
- Market probabilities use only odds captured before the selected prediction (or
  before kickoff for explicit reconstructions). Each complete 1X2 book is normalized
  proportionally, then averaged. No fresh-price guarantee is invented. Paired model
  versus market metrics use exactly the same labelled fixture subset, with its own n.
- Lineup predictions must precede the first recorded official XI, preventing evaluation
  of selections captured after the answer was observed. Labels use the latest official
  observation available by `--as-of`, and require 11 distinct official starters.
  Missing/incomplete official XIs are counted as exclusions. Official capture may be
  post-kickoff; its timestamp and snapshot ID remain in exported records.
- Betting uses genuine captured decisions made before known kickoff and the latest
  attached outcome available by `--as-of`. It does not evaluate mutable legacy bets.

Matches report sample size, winner accuracy (ties use Home/Draw/Away order), multiclass
log loss, multiclass Brier score, class-wise calibration, exact-score accuracy where
a score prediction exists, competition/model-version groups, favourite-probability
buckets, and model/market disagreement (favourite agreement and maximum probability
gap). Class indices 0/1/2 mean Home/Draw/Away. Calibration bins include both n and mean
predicted/observed probabilities. Multiclass Brier sums the three squared errors
(range 0–2); log loss clips the scored probability at 1e-15 for numerical stability.

Lineups report correct starters out of 11, false positives/negatives and role/line
accuracy among correctly identified starters with known roles/lines. Every metric
shows its denominator. Results are grouped by capture horizon and model version.
Start-probability scoring is supported only for actual stored probabilities; the
current binary model reports n=0 for probability calibration, never invented values.

Paper evaluation reports decision/settled/void/unsettled counts, settled stake, P&L,
ROI, average odds, model/fair probabilities, price CLV and probability movement,
edge buckets and strategy versions. Void bets remain in stake totals (returned stake,
zero P&L), but are excluded from probability scoring. Binary Brier is `(p-y)^2`;
calibration/log loss/Brier show the exact scored sample, with a separate market n
when fair probabilities are missing. Unknown closing metrics remain missing. These
are descriptive measurements, not profitability claims or confidence estimates.

Club/player commands provide **experiment evidence**, not a universal validation
metric. Club records are the strengths preserved within labelled match snapshots
and are clearly identified as such, rather than invented independent club snapshots.
Player records are genuinely observed daily rating history. Reports show row counts,
model versions and (for players) unique players/captures. Export records to test an
explicit future target with a chronological training/evaluation split; rating movement
alone is not predictive validation. Freeze experiment parameters using data strictly
before the evaluation window, and compare versions/targets on identical populations.

All reports include source, cutoffs, selection policy, generated time and evaluator
source digest. History begins when snapshot capture was deployed: early reports may
have n=0. Counts describe eligible observed evidence, not all fixtures the provider
could theoretically cover. Coverage diagnostics separately count selected rows with
missing regulation labels or missing/incomplete official XIs. No p-values or universal
model-quality verdicts are inferred from small samples.

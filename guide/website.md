# Website

The site is the SvelteKit app in `web/`, running as the Cloudflare Worker `thecornerfc` at thecornerfc.com. This page says how it is put together and what each page shows. How it deploys and what gates a deploy are in [Architecture](architecture.md); the rules for changing it are in `.claude/rules/web.md`.

## How it is built

- **Pages.** `web/src/routes/(app)/` holds one folder per page: `clubs`, `players`, `leagues`, `nations`, `matches`, `stats`, `lineups`, `admin` (the administrator's: `changes`, `model-vs-market`, `simulation`; [The Admin area](admin-area.md)), the pages for one `club/[id]`, `player/[id]`, `league/[id]`, `country/[name]`, `nation/[name]` and `match/[id]`, the owner's `fpl`, `my-fpl-team` and `efl-fantasy`, and `account`. `(text)/` holds methodology, privacy and terms, whose words are in `web/src/text/`. The menu is `web/src/lib/menu.ts`: Ratings, Predictions, Against the market, and Fantasy for the owner only.
- **A page is rendered on the server.** Its `+page.server.ts` asks the database (`web/src/lib/server/`, through `siteDoc`, `keptDoc`, `keptAsk` and `askAs` in `database.ts`) and hands the page what it draws. The browser talks only to thecornerfc.com. Logic is in tested `web/src/lib/*.ts`, and pages stay thin; heavy sums, such as the FPL planner (`web/src/lib/fplPlanner.js`), run in the browser because the Worker's free plan allows about 10 ms of CPU a request.
- **What it reads.** The rows `python -m thecornerfc export` writes: `site.docs` (one row per page's JSON, such as `rankings`, `stats`, `clubs/42`, `leagues/39`), `site.matches`, `site.players` and `site.lineup_history`, through database functions with fixed SQL that the public key may call ([Site data](site-data.md)). The site holds no database credential of its own for reading. The matches shown are the last 21 days and the next 60.
- **Who is asking.** `web/src/hooks.server.ts` reads the sign-in cookie. A signed-in visitor's requests carry their own token, so the database decides what a subscriber sees, and their pages are never cached ([Accounts](accounts.md), [Paid tier](paid-tier.md)).
- **Old addresses still work.** The old site's `#/clubs?...` addresses and `/terms.html`-style files are sent to the page here (`oldAddress` and `oldFile` in `menu.ts`): the pages kept their names and their choices' names.
- **To run it on this machine:** in `web/`, `npm run dev`, or `npm run build` then `npm run preview -- --port 4517` (the address `scripts/browser-check.mjs` expects). Either reads the live database with the public key, so it shows the published data; a local `export` in `.export/` is not read by the site.

## What the pages show

The main lists:
- **Matches** (`/matches`): projected scores, win/draw/loss chances and results. Filter by competition and day.
- **Clubs** (`/clubs`) and **Players** (`/players`), the old site's Rankings: club rankings with rating, form and trend, sorted by rating (reliability is kept in the database and isn't exported), and the player ranks. A club's or player's name opens its page.
  - Clubs show a **World** rank (place by Baseline Strength among every ranked club, whatever the list is filtered by) and **In lg** (place by Baseline Strength among the clubs in its league; TheCornerFC's ranking, not the league table). Players show World and League rank by Ability, **Mins** (minutes over the last 20 appearances, the evidence behind Ability; greyed under 450) and their club and league under the name.
  - Filters combine: the competition / country menu and search for both; for players also sliders (age, Ability, club world rank and minimum minutes) and position, club and nationality.
  - The address carries the view, through ordinary GET forms, so it can be bookmarked or shared: `/clubs?c=39&sort=...`, `/players?c=140&age=18-23&ab=70-&mins=900`. `c` is the menu filter (a league id, `c:<country>`, `r:<region>`, `e:<cup>` or `k:<cup>`), `ex` leaves competitions out, `q` is the search, and the players' ranges (`age`, `ab`, `crank`, `mins`) are `min-max` with either end left open.

The site labels the club rank as an **Elo rating** (**Rating** = LT ALGO, **Form** = current rank, **Trend** = Form minus Rating, how far a club is playing above or below its long-term level). The numbers are the same as the club rank below, and on that scale 100 points is worth one goal a game.

**Club pages.** Club names link to `/club/<team_id>`. Under the name, key figures come straight from the `rankings` row, the club's own row and its league's table, with nothing new modelled:
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

Each tab has its own address (`/club/42/xi`, `/formations`, `/matches`, `/history`). Each club's history comes from the `clubs/<team_id>` row of `site.docs`, which `export_clubs` (`thecornerfc/publish/site_clubs.py`) writes for clubs active in the last 400 days and which is read only when the page opens. Each match carries the formation from its line-up (`fixture_formations`; only the leagues with match-by-match player data have line-ups).

**League and country pages.** Wherever a club shows "Country · League" (the club page header, and Rankings rows when searching or showing all leagues), both parts are links:
- `/league/<league_id>` opens with key figures in two groups that are kept apart. **Actual standings** (from the table) shows the leader, most goals scored and fewest conceded. **TheCornerFC model** shows the strongest club by Baseline and by Current Strength, league strength (average Baseline Strength and its place among the covered leagues) and the best attack and defence ratings. The tabs are **Standings** (this season's table worked out from the results by `thecornerfc/publish/tables.py`, with each group, what each place leads to, last-five form, each club's Current Strength for reference, and its xG for and against per 90 over its last five league games, which is the site's own estimate from shots), **Strength ranking** (the clubs by Baseline Strength, with their actual table position alongside), **Projected table** (the rest of the season simulated from the model's predictions) and **Matches** (one round at a time, opening on the round with the next fixture, with the model's chances for upcoming games). Each tab opens with a line saying which kind of table it is. A tab can be linked directly (`/league/39/clubs`, `/projected`, `/matches`, `/table`). Cups have no Standings or Projected tab and open on Matches. The badge is the average Baseline Strength of the clubs playing in the league.
- `/country/<country>` lists the country's leagues, strongest first by the average Rating of their clubs, then its cups, then all its league clubs by Rating. UEFA and FIFA competitions are under International (`/country/World`).

Each competition's current season comes from the `leagues/<league_id>` row of `site.docs`, written by `export_leagues` (`thecornerfc/publish/site_clubs.py`) and read only when the page opens. A season starting from June onwards is labelled 2026/27, and a calendar-year one 2026, because API-Football's end dates only reach the last fixture it has scheduled.

**Managers.** Every night, each club in those leagues gets its manager from `/coachs?team=`, at most once a week each, or the next night after a line-up names a different coach (`team_coaches`, `python -m thecornerfc sync coaches`). The API keeps former managers listed with no end date, so the one on the club's latest line-up wins, otherwise the one who started last. Line-ups store their coach in `fixture_formations.coach_id`. API-Football seems to fill a season's line-ups with one coach, so they can't pin down a mid-season change, and the start date comes from `/coachs`.

**Cup line-ups.** For clubs in those leagues, their cup and European matches since July 2020 get starting XIs, formations and coaches from `/fixtures?ids=` too (`fixture_lineups`, `fixture_formations`; `python -m thecornerfc sync cup_lineups`, also nightly). Player stats from them aren't stored, so the player ratings stay league-only, but the club page's formations, starts by position and predicted replacements count every competition.

**Kit colours.** The club page pitches are drawn in the club's home kit: the shirt and number colours from its latest home line-up (`team_colors`). New line-ups update them as they're fetched, and `python -m thecornerfc sync colors` fills in clubs that have none (it also runs nightly).

**Match explanations.** A match card leads with the projected goals, the likely score, and the model's and the market's home/draw/away chances. Below those it lists up to three **Key reasons**: the model inputs that moved the expected margin (or the expected total) most, at 0.05 goals or more. **Model detail** opens the rest:
- Current, Baseline and match strength.
- Every term of the expected margin: strength gap, home advantage, European tie, the clubs' own home/away records, known absences and predicted line-ups.
- What the attack/defence tendencies add to the expected total.
- The model − market difference, labelled as a disagreement and not a betting edge.
- When the inputs, injury list and odds were captured, and the model version.

None of this is worked out in the browser, and a page asks only for the match it is showing (`/match/<fixture_id>`, with `/detail`, `/lineups` and `/squads`). `match_explanations` (`thecornerfc/publish/site_matches.py`) works out each match's key reasons, which come with the match from `site_matches`. The full breakdown is a column of the match's row in the `site.matches` table, which the export rewrites whole (`store_matches`: every match on the site with the row the site draws, its key reasons and its detail); the site asks `site_match_detail(fixture)` for it when that card's model detail is opened (`db/migrations/20261005_site_matches.sql`, applied 2026-10-05). The match's line-ups are not exported at all: when they are opened the site asks the database for that one match (`site_lineups(fixture)`, `db/migrations/20261005_site_lineups.sql`, applied 2026-10-05), which reads the predicted XI, the XI that started and the pre-match prediction from their tables, by team: `xi`, `actual`, `prematch`. For each shown prediction it picks the `match_prediction_snapshots` row that produced it, then rebuilds the parts with `predictions.explain`. That uses the same `margin_terms` and base-goal functions `predict_match` sums. A match is left out unless the rebuild gives back the stored margin and projected goals to 1e-6. So a prediction made under different settings, or before snapshots existed, shows no breakdown rather than a wrong one. The snapshots' 12-month record lists are summed in the database, so they never leave it.

**Recording projections.** Predictions for a fixture stop updating at kickoff, so the last nightly projection before the match is kept. `fixture_predictions.source` shows where each projection came from:
- `live`: recorded before kickoff.
- `backfill`: reconstructed afterwards for matches since July 2023, using each team's pre-match rank and goal averages. It shows what the current model would have said at the time.

Result cards show `proj` for live projections and `recon` for backfilled ones. The **Stats** page (the `stats` row of `site.docs`) scores the projections over 7, 30 and 90 days and 12 months, by competition. It shows how often the predicted result was right, exact scores, goal error, log loss, Brier score and calibration. **Every market: model vs bookmakers** compares log loss with the bookmakers in each market (result, both teams score, over/under 1.5–4.5) on the same matches. It uses closing prices, and opening prices for matches whose odds were collected before kickoff (`export.market_consensus`, which removes each bookmaker's margin in the database). Beating the opening price is where an early edge would show first.

**Ratings.** Every finished match's projection is rated from 1 (terrible) to 5 (excellent), using MatchLab's grading ported to `thecornerfc/models/rating.py`. There are five factors, each scored 0–5 and weighted:
- Winner 30%
- Margin 25%
- Clean sheets 20%
- Shape 15%
- Goals 10%

The weighted total is rounded, and a 0 counts as 1. The overall rating and the five factor scores are stored on `fixture_predictions` (`rating`, `rating_winner` and so on). Result cards show the rating as a coloured badge, and tapping a card shows the breakdown. The Stats tab shows the average rating, the spread of 1s to 5s and each factor's average. New results are rated nightly, and the last 14 days are re-rated in case a score was corrected.

## Conventions the pages keep

- **What each page is.** `TAB_INFO` in `web/src/lib/tabInfo.ts` holds one sentence per page, the
  part of the methodology page that explains it, and a key to its terms, drawn under the page's
  name. A new column or term goes in the key.
- **Addresses.** A page's choices ride in its address (`/matches?d=2026-10-11`, `/stats?r=90d`,
  `/nations?c=UEFA`), and a sub-tab is part of the path (`/club/42/matches`). An address that
  names no page gets the "Page not found" page (`web/src/routes/(app)/+error.svelte`). There are
  no back buttons: navigation is the menu and the browser.
- **The export's manifest.** `export.write_manifest` writes a short hash of each top-level
  export file, and the export sends to the database only the rows whose file changed. Anything
  that writes a top-level file must rewrite the manifest (`tests/test_manifest.py`). The site
  itself does not use the hashes.
- **Times and places.** Kick-off times go through `LocalTime.svelte`, so each visitor sees their
  own. Computed positions (a pitch, a chart) are classes from `placed.css`, because the security
  policy allows no inline styles.
- **Adverts.** `#ad-top` and `#ad-rail` are kept free on every page and are switched off
  (`ADS` in `web/src/lib/config.ts`).

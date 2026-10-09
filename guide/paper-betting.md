# Paper betting

`thecornerfc/models/betting.py` records the bets the model *would* place. It never uses real money. There are two strategies, tracked separately:
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

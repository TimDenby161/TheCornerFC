# Match predictions

`fixture_predictions` holds one row per fixture. The `upcoming_predictions` view adds team and competition names, and shows percentages. The method is based on the sheet's RG tabs:

1. **Expected margin:** (home match rank − away match rank + 30) / 100. Add 0.2 goals in the Champions League, Europa League and Conference League, where home sides do better.
   - Each team's **match rank** blends its current rank (Now) with LT ALGO. The blend depends on how far away the match is: 60% Now for a match today, sliding in a straight line to 20% Now for a match a year or more away (40% at six months).
   - Why: in a point-in-time backtest, 60% Now + 40% LT beat Now alone in both 2022–23 (log loss 1.0026 → 1.0012) and 2024 onwards (1.0034 → 1.0007), and beat ST, LT, the 30 and 100 Rankings and other blends. Re-running it with ranks as they stood 91, 182 and 365 days before kickoff, the best Now weight fell to 0.4, 0.4 and 0.2. Now alone was worse at every horizon.
2. **Base goals for each side:** the average of the team's own goals scored and the opponent's goals conceded, at home for the home side and away for the away side. The averages cover the last 12 months, use **xG instead of goals** for any match that has it, and are shrunk towards the competition average by 6 games.
3. **Projected goals:** a proportional version of the sheet's "Buff" scales the favourite up and the underdog down by the same factor until the margin matches. The original moved goals in a straight line, which pushed underdogs to around 0 goals and made the model far too sure they wouldn't score.
4. **Injuries**, in the 10 leagues in `config.INJURY_MODEL_LEAGUES` that have injury history: the Premier League, Championship, La Liga, Serie A, the Bundesliga, Ligue 1, Turkey, the Netherlands, MLS and Norway.
   - Each team's **missing strength** is the total, over players listed as out or doubtful, of each player's share of the team's minutes in its last 10 matches. 1.0 means one ever-present player. Long-term absentees have no recent minutes, so they add almost nothing.
   - The expected margin moves by 0.1 goals per unit of (away missing − home missing).
   - Minutes come from `fixture_players` (per-match minutes, fetched for these leagues). See `thecornerfc/models/injuries.py`.
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

# The match model on results alone

`run.py` replays the club ranking and the pre-match projections over every finished fixture (121,461, from 2020 to 6 October 2026), once as the model runs today and again with inputs taken away. The last variant, `results_only`, is given nothing but each match's date, competition, clubs and score: no xG, no predicted line-ups, no injury lists.

- **Validation:** 1 July 2023 to 30 June 2024 (19,464 matches).
- **Test:** 1 July 2024 onwards (44,632 matches, 70 competitions).
- **Check:** the replay of today's model gives the same rank going into every match as the live model stored (242,912 values compared, none differ).
- **Evidence:** a historical reconstruction with today's code, not a prospective record.

## Result

| Model | W/D/L log loss | Brier | Right result | Over 2.5 log loss | Goals RMSE | Log loss against today's model (95% interval) |
|---|---|---|---|---|---|---|
| Today's model | 0.99744 | 0.59561 | 51.0% | 0.67704 | 1.1719 | |
| No injury lists | 0.99763 | 0.59577 | 51.0% | 0.67704 | 1.1720 | +0.00019 (+0.00001 to +0.00035) |
| No line-ups | 0.99789 | 0.59587 | 51.1% | 0.67708 | 1.1719 | +0.00045 (+0.00015 to +0.00073) |
| No xG | 0.99999 | 0.59738 | 50.9% | 0.67732 | 1.1745 | +0.00255 (+0.00185 to +0.00321) |
| **Results only** | **1.00046** | **0.59769** | **50.8%** | **0.67732** | **1.1744** | **+0.00302 (+0.00227 to +0.00378)** |
| Always the base rates (44% / 24.5% / 31.5%) | 1.07016 | | | | | |

Results alone keep 96% of the model's gain over guessing the base rates (0.0697 of 0.0727). Nearly all of the loss is the xG; line-ups and injury lists together are worth 0.0006.

**K for goals-only matches.** With no xG every match moves the rank by K 6. Other values were tried on the validation year: 4, 5, 7, 8, 9 and 10 were all worse than 6 (7 was within 0.00005), on the test years too. So the results-only model needs no retuning.

## Where the loss falls

Test years, W/D/L log loss:

| Matches | n | Today's model | Results only | Difference (95% interval) |
|---|---|---|---|---|
| All | 44,632 | 0.99744 | 1.00046 | +0.00302 |
| With xG recorded | 19,309 | 0.99931 | 1.00564 | +0.00633 (+0.00467 to +0.00797) |
| Without xG | 25,323 | 0.99601 | 0.99651 | +0.00050 (+0.00006 to +0.00096) |
| Premier League | 810 | 1.00777 | 1.01642 | +0.00865 (+0.00021 to +0.01669) |
| Big five leagues | 3,761 | 0.98374 | 0.99072 | +0.00698 (+0.00261 to +0.01117) |
| The ten leagues with injury lists | 8,090 | 0.99563 | 1.00340 | +0.00776 (+0.00495 to +0.01053) |
| Championship, League One, League Two | 3,629 | 1.04417 | 1.04827 | +0.00409 |
| Cups | 6,445 | 0.95577 | 0.95622 | +0.00046 (−0.00063 to +0.00165) |
| 2024/25 | 19,933 | 0.99467 | 0.99754 | +0.00287 |
| 2025/26 onwards | 24,699 | 0.99967 | 1.00282 | +0.00315 |

The cost is concentrated where the fuller inputs exist: about 0.006 to 0.009 in the biggest leagues, and next to nothing in cups and the leagues that never had xG. It is the same size in both test periods.

## The club ratings

Compared for the 1,045 clubs with 30 or more matches and one in the last 120 days:

- Rank order agrees closely (Spearman 0.992).
- A club's rating moves 9 points on average (median 5), 30 at the 95th percentile and 60 at most (Vasco da Gama, 958 to 897). 100 points is one goal.
- Twenty-one of the top 25 are the same clubs. Within the top 100 a club moves 14 places on average.
- The biggest moves are clubs whose results and xG disagree: Feyenoord 983 to 940, Palmeiras 955 to 997, Augsburg 916 to 957.

## A public-domain source for the results

The model needs only scores, so a second question was whether a public-domain results set could supply them. [openfootball/football.json](https://github.com/openfootball/football.json) (CC0) was checked on 6 October 2026:

- This season (2026/27) it has 8 of the site's 70 competitions: the top divisions of England, Germany, Spain, France, Italy, the Netherlands and Portugal, and the Championship. Last season it had 20.
- Its latest scores were from 20 September, 16 days behind.
- Some of last season's files stopped part-way: League Two at 29 December 2025, the Scottish Premiership at 1 November 2025.

So it can't feed the site by itself: too few competitions, and not kept up. The international results set the Nations tab already uses is a separate source and is kept up.

## Rerun

`python experiments/results_only/run.py` replays from the frozen inputs in `.cache/results_only_inputs.pickle` (about 3 minutes) and writes `results.json`. `--read` reads the inputs again first, in a read-only connection; nothing is written to the database.

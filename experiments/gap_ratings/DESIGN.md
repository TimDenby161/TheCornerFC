# GAP ratings: opponent-adjusted shot and corner ratings in the boosted trees

**Registered 2026-10-30, before `run.py` was run on any data.** An offline experiment on the
research frame's frozen inputs (`experiments/research_frame`). Production formulas, stored
predictions, database records and the live A18 challenger stay as they are, and nothing is
deployed by this experiment whatever it finds. It reads no prospective snapshot; P6 and the live
protocols (P16 to P18) are untouched.

## Why this candidate

Chosen after an audit of the model and the October research round
(`experiments/research_frame/REGISTER.md` and its four experiments) and a literature review on
2026-10-30. Of the ideas the literature supports, most are already tested here: Dixon-Coles and
bivariate Poisson score models, a hierarchical time-weighted Poisson model, pooling, home
advantage by competition, rest and congestion, sharpening, draw refits. The boosted trees (A18)
were the one gain, and about half of it came from shots, which production otherwise ignores where
there is no xG (about 40% of matches).

The trees see shots as **raw averages of a side's last 10 shot differences**. The match-statistics
literature does three things they don't:

- **Adjust for the opponent.** Wheatcroft's GAP (Generalised Attacking Performance) ratings give
  each side an attacking and a defensive rating per statistic, updated after every match by the
  gap between what it produced and what the two sides' ratings predicted. Ten shots against the
  best side in the league count for more than ten against the worst.
- **Keep home and away apart.** Four ratings per side and statistic: attack and defence, at home
  and away, with a share of each update passed to the other venue.
- **Use corners.** GAP ratings built on shots and corners alone, with no goals, were profitable
  over twelve seasons of the over/under 2.5 market in ten European leagues (Wheatcroft 2020,
  International Journal of Forecasting 36(3), 916–932), and predicted match statistics added
  information beyond the bookmakers' prices for results (Wheatcroft 2021, Journal of Sports
  Analytics 7(2), 77–97). Nothing in this model uses corners.

Gradient-boosted trees on rating features were the best entries in the 2017 and 2023 Soccer
Prediction Challenges (Hubáček, Šourek and Železný 2019, Machine Learning 108, 29–47), which is
the shape A18 already has. So the test is whether better match-statistic ratings make the
existing trees better.

## Hypothesis

Adding opponent-adjusted, venue-split ratings of shots, shots on target and corners to A18's
features lowers the trees' result log loss on matches they have not been trained on, beyond what
A18's raw shot averages give.

## Baseline and candidate

Both are A18's recipe exactly as `experiments/architectures/chosen.json` fixed it: corrections to
production's expected margin and total from `HistGradientBoostingRegressor` (depth 3, 300
iterations, learning rate 0.03, leaf 200, L2 1.0, seed 20261012), retrained every half-season on
every scored match before the block, applied with shrink 1.0, the hierarchical Poisson model's
margin and total among the features. Production is the research frame's replay.

| | Features |
|---|---|
| **Baseline: A18** | `chosen.json`'s 44 features |
| **Candidate: A18 + GAP** | the same 44, plus nine: for shots, shots on target and corners, the home side's predicted count, the away side's, and the difference |

Nothing else differs: the same matches, blocks, settings and seed. The trees' settings are not
re-tuned for the candidate.

## GAP ratings

For a statistic S and a match between home side i and away side j, with S_i the home side's count
and S_j the away side's, the predictions before the match are

    P_i = (HA_i + AD_j) / 2        P_j = (AA_j + HD_i) / 2

where HA, HD are a side's home attack and defence ratings and AA, AD its away ones. After the
match, with e_i = S_i − P_i and e_j = S_j − P_j:

    HA_i += λ φ1 e_i      AA_i += λ (1 − φ1) e_i      AD_j += λ φ2 e_i      HD_j += λ (1 − φ2) e_i
    AA_j += λ φ1 e_j      HA_j += λ (1 − φ1) e_j      HD_i += λ φ2 e_j      AD_i += λ (1 − φ2) e_j

each floored at zero. A side's ratings start, on its first match with the statistic, at the mean
home count (attack at home, defence away) or away count (attack away, defence at home) of every
earlier match with the statistic; the very first match with it only starts those means. Features are the predictions **before** each match; a side's ratings
are used only once it has had at least 3 updates (otherwise missing, which the trees handle). A
match without the statistic updates nothing. Every competition counts, cups and Europe included.

**λ, φ1, φ2 are chosen for each statistic without looking at any result**: the values with the
lowest mean squared error of P_i and P_j against the actual counts, over matches from 2021-07-01
to 2022-06-30 with the statistic (before the trees' selection window). Grid: λ in {0.02, 0.05,
0.1, 0.15, 0.2, 0.3}, φ1 and φ2 in {0.5, 0.7, 0.9, 1.0}. The whole grid is reported.

## Periods

As the research frame: burn-in before 2021-07-01 (ratings settle), development 2021-07-01 to
2024-06-30 with the trees' selection window 2022-07-01 to 2024-06-30 (blocks from 2022-07-01, as
A18's development), final 2024-07-01 to 2026-10-11 (blocks from 2024-07-01). Walk-forward
throughout: a prediction uses only matches that kicked off before its block for the trees, and
before the match for the ratings.

**The final period is spent.** It has been scored by 14 registered candidates and read since
(lessons-learned: "a period of history can be spent"). The idea was taken from the literature,
not from it, and nothing about GAP ratings or corners has been looked at in any period before
this registration; but a pass here is a strong lead, not proof. The proof is a prospective test,
registered separately, if this passes.

## Measures

Candidate against baseline on identical matches (the scored final matches):

- **Primary:** mean three-outcome log loss, candidate minus baseline, with a paired bootstrap over
  ISO weeks (2,000 draws, seed 20261012), at 99% (the period is reused) and 95%.
- Brier, ranked probability score, top-pick accuracy, calibration error (`frame.compare`); by
  season; by competition with 300 or more matches; leagues against cups; the three European
  competitions; matches where both sides have GAP shot ratings against the rest.
- The five goal markets (over 1.5 to 4.5, both teams to score) as a guard.
- Both against production too, for context (A18 scored −0.0028 against it on this period).
- **The bookmakers, as the benchmark:** on the final matches with complete 1X2 prices in the
  frozen inputs (16 September to 11 October 2026, last price, each bookmaker's book normalised
  proportionally, then averaged), the log loss of production, A18, A18 + GAP and the market.
  Descriptive only: about a thousand matches, already read by the audit.
- Secondary, descriptive: the candidate without the corner ratings, to show how much of any
  difference is corners. It decides nothing.

**Reproduction check.** The baseline must reproduce A18's registered final result against
production (−0.00280 on 44,383 matches, `experiments/architectures/results.json`) within 0.0001. If it does not, the
run is reported as invalid and nothing is concluded.

## Reading it

Fixed here. The candidate **passes the screen** when all of:

1. final log loss better, its 99% interval below zero;
2. development selection-window log loss better (mean below zero);
3. final Brier better;
4. better in 2024/25 and in 2025/26;
5. no goal market worse by more than 0.0005;
6. at least 60% of competitions with 300 or more final matches no worse.

If 1 holds and another fails, it is **a real gain that misses the screen**. Otherwise **no gain
shown**. The size is labelled against the old 0.002 bar.

A pass leads to a proposal to the owner for a prospective test (the P15 method) of A18 + GAP
against A18, not a release, and nothing changes the A18 challenger already live until then.

## Cost

Offline only: the frozen inputs, no database read, no API-Football call. If it were ever taken
live, the counts are already fetched and stored by the nightly (no new calls or rows), and the
ratings take one pass over the fixtures (seconds).

## Running it

```bash
python experiments/gap_ratings/run.py      # needs numpy, scipy, scikit-learn and the frozen inputs
```

`run.py` SHA-256 at registration: `09ad98490e398e1249c196b21d273a94d8cd76b51fb59125b942d49ccf41d6d9`

# Does player rating depend too strongly on club strength?

**Recommendation: do not remove or weaken production club scaling on this evidence. Keep production unchanged; collect prospective component snapshots and test player information against a stronger club-history baseline.**

Strong club dependence is confirmed, but the out-of-sample results do not support broadly removing it. After controlling for historical club level, scaled, fixed-club and residual player signals improve future provider-rating MSE by about 2.1%; their differences are practically negligible. Future-minutes gains are about 0.25%. Scaled player information retains a small match-prediction benefit beyond club history, below the practical threshold set for this experiment. Transfer direction exposes a useful follow-up hypothesis rather than a universal winning representation.

## Scope and chronological controls

- Frozen database extract: 32,023 completed regulation-time fixtures and 961,929 positive-minute appearances, 2020-02-29 18:00:00+00:00 through 2026-09-27 02:30:00+00:00. Extracted 2026-09-27 11:23:19.853932+00:00.
- Immutable captures: 2 observations, from 2026-09-26 09:39:25.885788+00:00 to 2026-09-27 02:21:38.970047+00:00; their model-version IDs differ. This is insufficient for meaningful prospective transfer validation.
- Norms, league rating offsets and percentile references use pre-2022 records only. Prediction training: January 2022–June 2023; validation: July 2023–June 2024; held-out test: July 2024 onward. Validation selects regularization, then coefficients are refitted on training + validation.
- Last-20-appearance / 540-day player windows use only prior matches. All fixtures sharing a kickoff are scored before any of their results update the windows. Every variant uses identical eligible observations within each endpoint.
- Current website season/career ratings are audited descriptively. They are not used as historical predictors because later career evidence and rebuilt history may leak. The predictive experiment replays the rolling match-player formula with chronological reference distributions; it is not an exact backtest of website season ratings.
- Centre-back team-xG-against is unavailable in the early normalization sample and is omitted consistently in every variant. No production functions or constants were changed.
- All database extraction was READ ONLY / REPEATABLE READ. No API-Football calls, migrations, writes, or production rating changes. The restricted database role exposed zero rows, so the main connection was used with writes disabled.

## What is being compared?

1. **Production-formula scaled**: existing `final_rank(percentile, window_club_strength, position)`, with chronological inputs. The active formula uses an additive club-level base, a position-weighted statistical adjustment and a soft ceiling. Dividing today’s rating by a club factor would not recover the pre-club signal.
2. **Pre-club percentile**: the weighted, shrunk statistical score converted to a position-specific percentile using only the pre-2022 reference. This is not context-free ability: passing volume, provider ratings and other statistics can themselves depend on team tactics and competition.
3. **Fixed-club formula**: the same `final_rank` transformation with club strength fixed at 1000 for everyone. Removes explicit club scaling while retaining position offsets, elite bonuses and the ceiling.
4. **Club residual**: scaled rating minus a position-specific quadratic expectation from window club strength, fitted on prediction-training observations only. Residuals are not guaranteed uncorrelated with club strength out of sample.

## 1–2. Correlation by position and within-club distributions

Current website exports: club rankings timestamp 2026-09-27T02:22:19.667250+00:00. Players must have a linked club with a published LT strength. The between-club fraction below is descriptive, unadjusted, and inflated when clubs have few players; it is not the fraction causally explained by strength. Within-club summaries require at least three players in the same position group.

| Position | Players | Clubs | Pearson | Spearman | Between-club variance fraction | Median within-club SD | Median within-club P90−P10 |
|---|---:|---:|---:|---:|---:|---:|---:|
| AM | 402 | 213 | 0.708 | 0.690 | 0.818 | 3.268 | 6.720 |
| CB | 1,466 | 355 | 0.721 | 0.703 | 0.631 | 3.810 | 7.980 |
| CM | 1,129 | 309 | 0.626 | 0.614 | 0.586 | 4.484 | 9.410 |
| DM | 428 | 214 | 0.748 | 0.711 | 0.758 | 3.916 | 7.920 |
| FB | 1,162 | 341 | 0.772 | 0.772 | 0.755 | 3.383 | 6.950 |
| GK | 534 | 303 | 0.684 | 0.659 | 0.697 | 4.716 | 9.200 |
| ST | 1,109 | 338 | 0.595 | 0.583 | 0.515 | 4.726 | 9.550 |
| W | 903 | 299 | 0.669 | 0.660 | 0.655 | 4.371 | 8.800 |

Full-backs show the strongest association in this export. Centre-backs and defensive midfielders are also strongly associated with club strength. Within-club spreads remain material, so the rating is not simply a club label. Better clubs recruiting better players, role/tactical opportunity and the explicit formula all contribute; these correlations cannot separate them.

Historical held-out correlations below use one observation per player per UTC month (latest eligible observation) to reduce fixture-frequency weighting; they remain repeated-player descriptive statistics. Club strength here is the minutes-weighted historical window club input, rather than the current employer’s strength.

| Position | Player-months | Scaled Pearson | Pre-club Pearson | Fixed-club Pearson | Residual Pearson |
|---|---:|---:|---:|---:|---:|
| GK | 8,290 | 0.833 | 0.157 | 0.157 | 0.040 |
| CB | 24,163 | 0.842 | 0.254 | 0.264 | 0.135 |
| FB | 22,552 | 0.840 | 0.216 | 0.218 | 0.054 |
| DM | 9,289 | 0.797 | 0.229 | 0.241 | 0.109 |
| CM | 18,428 | 0.818 | 0.272 | 0.275 | 0.099 |
| AM | 8,441 | 0.767 | 0.254 | 0.255 | -0.016 |
| W | 17,702 | 0.794 | 0.299 | 0.302 | 0.053 |
| ST | 17,835 | 0.749 | 0.262 | 0.264 | 0.030 |

## 3–5. Transfers and direction of club-strength change

Transfers are proxies inferred from changes of observed club in covered domestic competitions, with no more than 365 days between observations. Strong→weak and weak→strong require at least 50 LT points at the move. They are not verified registration transactions. Compare the last old-club pre-match score with pre-match scores at the fifth and twentieth new-club appearances. Early stability is partly mechanical because the window retains old-club appearances. The twentieth-appearance cohort is a selected group that stayed observable and played enough games; it still has one old appearance in a full 20-game pre-match window. Residual transfer trajectories hold the expected-rating position group fixed at transfer entry; actual roles can change.

| Checkpoint | Direction | Moves | Players | Scaled mean change | Fixed-club mean change | Residual mean change | Scaled pre/post correlation |
|---|---|---:|---:|---:|---:|---:|---:|
| 5th | all | 4,164 | 3,153 | -0.508 | -0.161 | -0.092 | 0.936 |
| 5th | strong_to_weak | 1,111 | 1,062 | -1.548 | 0.086 | 0.413 | 0.921 |
| 5th | weak_to_strong | 780 | 759 | 0.798 | -0.080 | -0.234 | 0.949 |
| 20th | all | 2,206 | 2,022 | -0.522 | 0.035 | 0.133 | 0.678 |
| 20th | strong_to_weak | 586 | 579 | -4.415 | 1.490 | 2.648 | 0.647 |
| 20th | weak_to_strong | 437 | 435 | 4.804 | -0.834 | -1.910 | 0.679 |

| 20th-appearance cohort | Scaled change 95% CI | Fixed-club change 95% CI | Scaled change vs club-change correlation | Fixed-club change vs club-change correlation |
|---|---|---|---:|---:|
| all | -0.846602 to -0.199664 | -0.235840 to +0.307459 | 0.454 | -0.135 |
| strong_to_weak | -5.082874 to -3.748097 | +0.905479 to +2.056828 | 0.350 | -0.014 |
| weak_to_strong | +4.162165 to +5.507146 | -1.457062 to -0.173808 | 0.344 | 0.017 |

Scaling makes ratings follow the new club’s level, while unscaled statistical output can improve in an easier environment and decline in a harder one. This is compatible with useful competition adjustment as well as excessive club dependence. Transfer continuity alone cannot decide which representation is better.

## 6. Out-of-sample future minutes and performance

Candidates are players in each club’s previous five observed matches with at least 180 historical minutes. Next-match minutes include zero for absence only when both teams have adequate recorded lineup coverage. This includes injuries, departures and rotation in the outcome; it excludes entirely unseen recruits. Performance is the league/defensive-goal-adjusted provider match rating conditional on at least 30 played minutes and a recorded rating. It is a selected outcome, not independent ground-truth talent.

Controls include current and baseline club/opponent strength, home status, age and age squared, position, competition, prior-five-match minutes share and historical window minutes. Lower MSE/MAE is better. Intervals are paired player-cluster bootstraps.

### Minutes

Train **299,712**, validation **204,019**, test **443,332**, **9,602 test players**.

| Model | Test MSE | MAE | Δ MSE vs controls | 95% CI | Improvement vs controls |
|---|---:|---:|---:|---|---:|
| Context controls only | 1086.308499 | 27.498841 | +0.000000 | +0.000000 to +0.000000 | 0.00% |
| Production-formula scaled | 1082.926852 | 27.395519 | -3.381647 | -3.879826 to -2.872032 | 0.31% |
| Pre-club percentile | 1083.669122 | 27.408277 | -2.639377 | -3.067846 to -2.209748 | 0.24% |
| Fixed-club formula | 1083.580860 | 27.413836 | -2.727639 | -3.177151 to -2.288074 | 0.25% |
| Club residual | 1083.777037 | 27.417097 | -2.531462 | -2.959023 to -2.103914 | 0.23% |

**Stricter historical-club controls** add position-specific linear/quadratic window club strength, so the player rating must add information beyond its own club-level input.

| Model | Test MSE | Δ MSE vs stronger controls | 95% CI | Δ MSE vs scaled | 95% CI vs scaled |
|---|---:|---:|---|---:|---|
| Context controls only | 1085.370757 | +0.000000 | +0.000000 to +0.000000 | +2.652599 | +2.198933 to +3.098738 |
| Production-formula scaled | 1082.718158 | -2.652599 | -3.098738 to -2.198933 | +0.000000 | +0.000000 to +0.000000 |
| Pre-club percentile | 1082.774916 | -2.595841 | -3.029347 to -2.155745 | +0.056758 | -0.039349 to +0.156557 |
| Fixed-club formula | 1082.695283 | -2.675475 | -3.119954 to -2.227295 | -0.022875 | -0.066415 to +0.018827 |
| Club residual | 1082.689555 | -2.681202 | -3.117286 to -2.234368 | -0.028603 | -0.055766 to -0.001219 |

Position and transfer checks, using the first control set (held-out; exploratory):

| Group | n | Controls MSE | Scaled MSE | Fixed-club MSE | Residual MSE |
|---|---:|---:|---:|---:|---:|
| 2024-25 | 202,277 | 1080.722924 | 1077.135041 | 1077.831995 | 1078.064762 |
| 2025-onward | 241,055 | 1090.995534 | 1087.786947 | 1088.404918 | 1088.570391 |
| GK | 28,595 | 1101.233691 | 1095.644082 | 1096.343084 | 1096.557785 |
| CB | 85,995 | 1309.580224 | 1308.351986 | 1308.714997 | 1308.894508 |
| FB | 79,411 | 1172.422729 | 1169.777940 | 1169.998597 | 1170.049973 |
| DM | 31,521 | 1094.406763 | 1092.010767 | 1093.099317 | 1093.270375 |
| CM | 63,557 | 1069.177520 | 1066.768797 | 1067.640941 | 1067.750739 |
| AM | 28,744 | 959.318181 | 954.041670 | 954.864960 | 955.082670 |
| W | 61,223 | 907.999481 | 904.895602 | 905.412421 | 905.690982 |
| ST | 64,286 | 914.185424 | 907.132601 | 908.317406 | 908.716136 |
| strong_to_weak | 4,775 | 1757.994347 | 1595.420591 | 1722.836663 | 1744.852550 |
| weak_to_strong | 3,435 | 1455.143206 | 1524.766369 | 1431.908354 | 1416.302604 |

### Performance

Train **171,339**, validation **115,426**, test **245,791**, **8,666 test players**.

| Model | Test MSE | MAE | Δ MSE vs controls | 95% CI | Improvement vs controls |
|---|---:|---:|---:|---|---:|
| Context controls only | 0.340798 | 0.443595 | +0.000000 | +0.000000 to +0.000000 | 0.00% |
| Production-formula scaled | 0.333666 | 0.438947 | -0.007132 | -0.007871 to -0.006481 | 2.09% |
| Pre-club percentile | 0.334608 | 0.439416 | -0.006190 | -0.006797 to -0.005654 | 1.82% |
| Fixed-club formula | 0.333643 | 0.438893 | -0.007155 | -0.007934 to -0.006490 | 2.10% |
| Club residual | 0.333883 | 0.439073 | -0.006915 | -0.007711 to -0.006246 | 2.03% |

**Stricter historical-club controls** add position-specific linear/quadratic window club strength, so the player rating must add information beyond its own club-level input.

| Model | Test MSE | Δ MSE vs stronger controls | 95% CI | Δ MSE vs scaled | 95% CI vs scaled |
|---|---:|---:|---|---:|---|
| Context controls only | 0.340393 | +0.000000 | +0.000000 to +0.000000 | +0.007035 | +0.006378 to +0.007817 |
| Production-formula scaled | 0.333358 | -0.007035 | -0.007817 to -0.006378 | +0.000000 | +0.000000 to +0.000000 |
| Pre-club percentile | 0.334299 | -0.006094 | -0.006699 to -0.005562 | +0.000941 | +0.000709 to +0.001246 |
| Fixed-club formula | 0.333390 | -0.007003 | -0.007732 to -0.006369 | +0.000032 | -0.000066 to +0.000153 |
| Club residual | 0.333347 | -0.007046 | -0.007829 to -0.006388 | -0.000011 | -0.000015 to -0.000007 |

Position and transfer checks, using the first control set (held-out; exploratory):

| Group | n | Controls MSE | Scaled MSE | Fixed-club MSE | Residual MSE |
|---|---:|---:|---:|---:|---:|
| 2024-25 | 113,956 | 0.285902 | 0.278515 | 0.278409 | 0.278618 |
| 2025-onward | 131,835 | 0.388250 | 0.381337 | 0.381387 | 0.381653 |
| GK | 20,662 | 0.559529 | 0.551961 | 0.552015 | 0.552565 |
| CB | 51,441 | 0.270330 | 0.266218 | 0.266059 | 0.266258 |
| FB | 43,694 | 0.267890 | 0.263120 | 0.263014 | 0.263183 |
| DM | 18,160 | 0.225644 | 0.218815 | 0.218394 | 0.218656 |
| CM | 35,663 | 0.274456 | 0.264283 | 0.264094 | 0.264299 |
| AM | 15,197 | 0.406576 | 0.393246 | 0.393446 | 0.393430 |
| W | 30,178 | 0.408008 | 0.398474 | 0.398695 | 0.399369 |
| ST | 30,796 | 0.461610 | 0.455125 | 0.455475 | 0.455405 |
| strong_to_weak | 3,814 | 0.383090 | 0.378944 | 0.379372 | 0.381033 |
| weak_to_strong | 2,208 | 0.359006 | 0.360715 | 0.359550 | 0.361088 |

The residual and scaled player regressions with position-specific quadratic historical-club controls span the same linear predictor space: the residual subtracts a function already in the controls. Tiny differences between them are regularization effects, not independent proof that residualization discovers new information. Fixed-club performance is also effectively tied with scaled performance: its MSE difference versus scaled is +0.000032 (95% CI −0.000066 to +0.000153).

Transfer prediction subgroups include eligible observations among the first five new-club appearances; the first appearance itself is usually absent because the player was not previously observed at the new club. These subsets condition on playing and therefore omit new-club nonselections. They do not measure the ability to forecast an unseen signing’s playing time.

The first-control-set transfer check is asymmetric: for 4,775 strong→weak observations, scaled minutes MSE falls from 1757.99 to 1595.42 (about 9.2%); for 3,435 weak→strong observations, it rises from 1455.14 to 1524.77 (about 4.8%). The fixed-club and residual versions do better for upward movers. This is an exploratory, selected subgroup result; test transfer-specific adaptation prospectively with zero-minute nonselections included before changing scaling.

## 7–8. Incremental match value and alternatives

An offline multinomial model predicts Home/Draw/Away from club Current/Baseline differences, average levels and competition. The added player feature is the difference between predicted-XI means. Each XI is one goalkeeper plus ten outfield players selected using only prior-five-match minutes; require eleven eligible players per team. No actual future lineup or retrospective injury list is used. This is an incremental information test against a club baseline, not a replacement or measured lift to the deployed match predictor.

Train **7,653**, validation **5,152**, test **10,995 fixtures**, **112 test weeks**.

### Club controls

| Added feature | Log loss | Brier | ECE | Accuracy | Δ log loss vs controls | 95% CI |
|---|---:|---:|---:|---:|---:|---|
| Context controls only | 1.003344 | 0.599720 | 0.00816 | 51.13% | +0.000000 | +0.000000 to +0.000000 |
| Production-formula scaled | 1.001598 | 0.598545 | 0.00834 | 51.11% | -0.001746 | -0.002931 to -0.000559 |
| Pre-club percentile | 1.002471 | 0.599117 | 0.00766 | 51.09% | -0.000873 | -0.002236 to +0.000477 |
| Fixed-club formula | 1.002298 | 0.599023 | 0.00728 | 51.10% | -0.001046 | -0.002432 to +0.000286 |
| Club residual | 1.002449 | 0.599128 | 0.00714 | 51.05% | -0.000895 | -0.002272 to +0.000368 |

### Stricter historical-club controls

| Added feature | Log loss | Brier | ECE | Accuracy | Δ log loss vs controls | 95% CI |
|---|---:|---:|---:|---:|---:|---|
| Context controls only | 1.002746 | 0.599336 | 0.00668 | 51.01% | +0.000000 | +0.000000 to +0.000000 |
| Production-formula scaled | 1.001520 | 0.598500 | 0.00785 | 51.13% | -0.001226 | -0.002377 to -0.000139 |
| Pre-club percentile | 1.001940 | 0.598775 | 0.00763 | 51.09% | -0.000806 | -0.002162 to +0.000534 |
| Fixed-club formula | 1.001789 | 0.598696 | 0.00771 | 51.15% | -0.000958 | -0.002322 to +0.000350 |
| Club residual | 1.001802 | 0.598712 | 0.00768 | 51.15% | -0.000944 | -0.002331 to +0.000378 |

The stricter baseline adds the predicted XI’s historical window club-strength means and mean squares, as home-away differences and combined means. The scaled-rating improvement shrinks from 0.001746 to 0.001226 log loss but survives this check (95% improvement CI 0.000139–0.002377). Thus some benefit is duplicated club information, but not all of the measured gain disappears. The point estimate remains below the 0.002 practical threshold. Brier improves; binned ECE worsens from 0.00668 to 0.00785. Neither the neutral-club nor residual signal beats the scaled version on match proper scores. The scaled-versus-neutral loss advantage is only 0.000268, too small to settle broader rating-design decisions.

| Test period | n | Controls loss | Scaled loss | Fixed-club loss | Residual loss |
|---|---:|---:|---:|---:|---:|
| 2024-25 | 5,077 | 0.999296 | 0.997877 | 0.998661 | 0.998738 |
| 2025-onward | 5,918 | 1.006817 | 1.004791 | 1.005418 | 1.005633 |

## Confidence and interpretation limits

- 1,000 paired bootstrap draws; player clusters for player targets/transfers, UTC ISO-week clusters for matches. Pointwise 95% intervals, without multiple-testing adjustment. Shared-club dependence, longer temporal dependence, model-fitting uncertainty and revised historical data are not fully captured.
- Calibration is mean classwise ECE in 0.1-width bins; full counts, predicted probabilities and observed frequencies are in results.json. It is bin-sensitive and is not used to choose a coefficient alone. Brier uses the sum across three classes.
- The practical review criteria are 1% player-target MSE improvement or 0.002 match-log-loss improvement with corroborating Brier, uncertainty and temporal consistency. Smaller statistically detectable changes need not justify model complexity.
- Existing statistical weights and position adjustments were designed using historical results, including these years. Chronological inputs prevent direct lookahead but cannot undo model-development leakage. This is not a pristine untouched historical holdout.
- Historical-club controls were added after a diagnostic fit to probe confounding; they are a robustness check, not independent confirmation. No coefficient was optimized around an individual club.
- Provider ratings reflect team outcomes and match roles; neither those ratings nor minutes isolate intrinsic player ability. Transfers out of covered competitions and players not selected are incompletely observed.
- The actual website season/career rating has only two immutable captures, under different model versions. Its out-of-sample incremental value remains unresolved; do not substitute reconstructed rolling results for that claim.

## Recommended next experiment

Freeze the current production model. Prospectively capture, for every eligible squad member and each forecast time, the exact website season rating, rolling rating, raw score/percentile, window club strength, neutral-club value, residual, position, history minutes, team and model version. Use the same candidate set and predicted XI for all variants; retain nonselections and coverage exits rather than selecting only future appearances.

Preregister a fixed evaluation window and a player/club-clustered power calculation. Compare (a) full club-history baseline, (b) baseline plus scaled player signal, (c) baseline plus neutral signal and (d) baseline plus residual. Test future minutes, adjusted performance and match proper scores, with separate verified-transfer and CB/FB cohorts. Keep normalization/residual fits frozen or update them on past data only, and explicitly test models against a later untouched period. Extend capture metadata to retain component values before drawing conclusions about weakening the website formula.

**Review decision: retain production ratings. The evidence supports testing a separate context-neutral statistical component alongside the contextual rating; it does not justify automatically replacing the current rating or changing the defender/full-back club coefficient.**

## Reproduction and artifacts

- Protocol: `DESIGN.md`; read-only extraction: `extract.py`; replay/model fitting: `run.py`; numerical results and subgroup intervals: `results.json`.
- Input SHA-256: `682608eebfcd29912b754fe251d9f099799c0e09670c51cc89562fc48c0bdcef`. Run source SHA-256: `d0ec4e46a2ab08faf2cc83a07063f4eedecc71354385f49eb7af420b982ebce4`. Production source and current-export fingerprints are recorded in results.json.
- Inputs remain in ignored `.cache/player_club_strength_inputs.json.gz`; the replay cache is also local and ignored. No credentials are included in tracked artifacts.

```bash
/tmp/thecornerfc-experiment-venv/bin/pip install -r experiments/player_club_strength/requirements.txt
# Optional fresh extraction; requires .env DATABASE_URL and uses enforced read-only mode:
/tmp/thecornerfc-experiment-venv/bin/python experiments/player_club_strength/extract.py
OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 /tmp/thecornerfc-experiment-venv/bin/python experiments/player_club_strength/run.py
/tmp/thecornerfc-experiment-venv/bin/python experiments/player_club_strength/write_report.py
/tmp/thecornerfc-experiment-venv/bin/python -m unittest discover -s tests -p "test_player_club_experiment.py"
```

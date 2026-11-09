# Against FiveThirtyEight: our match model and their club forecasts

**Registered 2026-11-06, before `evaluate.py` was run.** A benchmark, not a model change: no
model file, database row, scheduled job or live protocol is touched, and nothing is proposed for
release whatever it finds. It reads the research frame's frozen inputs
(`experiments/research_frame`) and FiveThirtyEight's archived file, and calls no API.

## Why

FiveThirtyEight's Soccer Power Index (SPI) forecasts were the best-known free club model until
the site stopped its sports models in June 2023. Their final file of match-by-match forecasts,
back to 2016, is still published (CC BY 4.0) through the Internet Archive. It is an outside
yardstick for our model on the same matches, which bookmakers' prices can't be before our odds
evidence starts in September 2026.

## Question, measure and rows

- **Question:** on the matches both forecast, is our result forecast better or worse than
  FiveThirtyEight's, and by how much?
- **Measure:** mean three-outcome log loss on the 90-minute result, theirs minus ours on
  identical matches (below zero: theirs better), with a 95% bootstrap interval resampling whole
  ISO weeks (`frame.compare`). Brier, ranked probability score, accuracy and the sharpness power
  as well, and the gap by season and by competition.
- **Ours:** production's stored projection for each fixture through the production probability
  step (`frame.baseline_probabilities`), the baseline of every research-round experiment.
- **Theirs:** `prob1`, `probtie`, `prob2`, rescaled to sum to one.
- **Rows:** the frame's scored matches (finished in 90 minutes, regulation score, a stored
  projection) from 2021-07-01, the end of our burn-in, that `pair.py` paired: about 20,000
  matches in 33 competitions, to 13 June 2023, their last scored match. No minimum gap counts as
  a pass: the size is reported as it is.

## Pairing

The frame holds team ids, not names, so `pair.py` gives each of their teams the API-Football id
that turns up in at least 80% of its matches since our first fixture (fixtures within a day with
the same score vote), at least 10 of them, and pairs a match when exactly one fixture within a
day has those two sides. It reads no forecast of theirs or ours. Their women's competitions are
left out (we hold none, and their women's sides share the men's names). The paired final score
agrees with ours on 30,164 of 30,167 pairs. Not covered: the USL, the J League, South Africa's
league, and a few clubs with too few overlapping matches.

## What to read into it

- **Neither side was a live forecast kept untouched.** Ours for 2021–23 are reconstructions:
  walk-forward (each uses only earlier matches), but made with today's formulas, chosen partly
  on this period (it is our development period). Theirs are as their final file left them, and
  FiveThirtyEight re-ran past seasons when its method changed, so they may be fitted with
  hindsight too. Both carry some advantage of hindsight; the comparison is indicative, not blind.
- **Their model had more information:** Opta's match data, non-shot xG and preseason ratings
  that used transfer market values. Ours uses API-Football's data only.
- **Results only.** Their file has no goal-market probabilities that match ours.

## Files

| File | |
|---|---|
| `fetch.sh` | Downloads their final file from the Internet Archive and checks its SHA-256. |
| `pair.py` | Pairs their matches with our fixtures (SHA-256 `e702e3570eacde29b8bab6f821661e002ca25550d2ce81ab5adfb5f1975239ff`). |
| `evaluate.py` | Scores both on the paired matches (SHA-256 `bd2bb23367110fdae4831f4b7f7924059f6776365a0950000a7157479dc27f30`, recorded before it was run). |
| `results.json` | Its output. |
| `spi_matches.csv`, `pairs.json` | Their file and the pairing: gitignored. |

**Amendment 2026-11-06:** its first run stopped before printing or saving anything, on the line
that writes the date window (numpy can't take the minimum of date strings). That line alone was
changed; the rows and measures are as registered. SHA-256 now `573f1fc757ec7476bbe4309756ab75046605fdf47b5cc82245c09ab2e93b6bb3`.

Cost: none. One 2.9 MB download from the Internet Archive; no API-Football call, no database
read, nothing on any bill.

## Result (2026-11-06, `results.json`)

On 20,632 matches in 33 competitions, 1 July 2021 to 13 June 2023:

| | Log loss | Accuracy |
|---|---|---|
| Base rates | 1.0734 | |
| The Corner FC | 1.0179 | 49.4% |
| FiveThirtyEight | 1.0132 | 49.7% |

FiveThirtyEight was better by 0.0047 log loss (95% 0.0006 to 0.0080) and by 0.0041 Brier
(0.0027 to 0.0055). The gap shrank from 0.0084 in 2021/22 to 0.0010 in 2022/23. It was ahead in
25 of 33 competitions, most of all in La Liga, the Europa League, MLS and the Segunda; we were
ahead in eight, most of all in Serie B and Denmark's league. Both were well calibrated (sharpness
power 0.99 and 1.00).

# After Europe: sides back in their league after a European match with a week's rest

**Written 2026-10-30.** A lead, found by looking, not a tested result. On 2026-10-29, while
checking whether line-up changes help (`experiments/rotation`), about 45 groups of matches were
compared with the model after the fact. One stood out: in a **league** match, a side whose
previous match was in the Champions League, Europa League or Conference League, **five or more
days** earlier, beat the stored projection by **+0.19 goals** (95%: +0.07 to +0.31, 779
side-matches, July 2021 to October 2026; won 56.5% against the model's 51.4%). With four days or
less there was nothing (+0.02). With 45 groups, two or three would stand out by chance, so this
can only be tested on matches not yet played.

The published work on European matches and league form finds little effect either way, at most a
cost for Europa League sides with three days' rest or less (BJSM 2015; UEFA's CIES study; Keele).
Nothing found looks at a full week's rest after Europe.

## The candidate

In a league match, the expected margin moves by **DELTA = +0.19 goals** towards each side that
qualifies (its previous match in the data was European, at least five days before), keeping the
product of the projected goals (`frame.moved`); both sides qualifying cancel out. DELTA is the
history's estimate, fixed by `run.py` in `chosen.json` before any live match is read.

## The test

P19 (`experiments/prospective/PROTOCOLS.md`), on the live model's stored snapshots: the candidate
against the live model, matches from 2026-10-31. Only the qualifying matches change, a few hundred
a season, so a call will take a long time.

## Cost

None: the fixtures are already stored; no API calls, no new rows.

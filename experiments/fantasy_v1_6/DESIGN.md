# Fantasy v1.6: FPL's injury status in the minutes model

Written 2026-09-30, before any outcome. The owner approved this use of FPL data the same day ("combine the two ways of measuring an injury and figure out the best method going forward").

## What the data allows (checked 2026-09-30)

- **API-Football's injury lists arrive only on match days,** from `matchday.py` 3 hours before kickoff; the nightly run re-saves them after the match. Ten days before GW6, no upcoming Premier League fixture has a single API row. The FPL tab shows ten gameweeks ahead, so FPL is its only injury source for everything but the last hours before kickoff.
- **When API lists exist, they mean "out".** Premier League 2024-26:
  - "Missing Fixture" players played 0.4% of the time (6,077 player-fixtures);
  - "Questionable" players played 1.8% (598).
  - v1.1's fitted start coefficients reflect this: −13.2 (missing) and −6.7 (questionable), which cut P(start) to about 0.
  - The rows' timestamps are all after kickoff because they are re-saved, so how early each first appeared can't be recovered.
- **FPL's status can't be fitted yet.** Every FPL capture so far (from 2026-09-27) is for GW6, which hasn't been played. No FPL status has been recorded before a finished gameweek.
- **What FPL gives:**
  - a status: available, doubtful, injured, suspended, unavailable, or not in squad;
  - a chance of playing in the next round: 0, 25, 50 or 75%;
  - news, often with a date: "Expected back 10 Oct", "Suspended until 17 Oct".
  - Latest capture: 71 injured (most "Unknown return date"), 4 suspended, 29 doubtful (26 at 75%), 105 unavailable.

## Method (v1.6 = v1.5 + an availability factor)

Each player gets a factor a for each fixture, from FPL's latest capture before the prediction. P(start), P(play), P(60+) and expected minutes are multiplied by a. His goal, assist and penalty shares then move to teammates through the existing allocation.

| FPL state | a |
|---|---|
| A return date in the news ("Expected back D", "Suspended until D"), status not available | 0 before D, 1 from D |
| Injured, suspended, unavailable or not in squad, with no date | 0 for every gameweek, until FPL changes it |
| Doubtful, chance c | c / 100 for the gameweek FPL's chance refers to; 1 after it |
| Available, or not flagged | 1 |

API-Football's lists keep v1.1's fitted flags. When both sources flag a player near kickoff, the product of the two means the more severe one wins. The API flags are close to certain, and FPL is the only early source.

These rule values are judgment, fixed here before any outcome. Measuring whether they are right is P12's job.

## Validation (P12, PROTOCOLS.md)

Prospective, v1.6 against v1.5 on the same player-fixtures. The target is whether he played and whether he started, from API-Football's match lines.
- **Primary:** log loss of P(play), for all players and for FPL-flagged players.
- **At target:** calibration by FPL bucket:
  - dated absence before its date;
  - no date;
  - doubtful at 25, 50 and 75%;
  - API missing or questionable;
  - both sources.
- These give the fitted a for each bucket (observed P(play) over v1.5's unflagged P(play)). That is the pre-registered route to "the best method going forward": a v1.7 with fitted values replacing the judgment ones.

## Limits

- The rule values are not fitted.
- "Available from the return date" ignores a player being eased back in. The minutes model's gap feature already lowers P(start) after an absence.
- A long injury with no date stays at 0 until FPL updates it, so gameweeks far ahead may be too pessimistic.

# Beat the Model and Fantasy points (free with an account)

Two pages give a free account something to do (owner's decisions of 2026-11-23). Both are in the
menu's **Play** group, are shells that the browser fills as the signed-in visitor, and answer a
signed-out visitor with what they are and a way to sign in.

## Beat the Model (`/beat-the-model`)

Players predict the score of every Premier League match of a round before kick-off: 3 points for
the exact score, 1 for the right result. The model plays too, with its most likely score (the
`likely` field of the match row). Once a player has picked a match they see the model's score for
it, so a pick is final once saved; everyone sees it at kick-off. One table, by season and by
round, under a display name the player chooses (never their email). No mini-leagues.

| Part | Where |
|---|---|
| Tables and functions | `db/migrations/20261123_beat_the_model.sql` |
| Scoring | `public.btm_score()`, called by every match-day run (`thecornerfc/pipeline/beat_the_model.py`) |
| Site endpoints | `site/TheCornerFC.Web/Site/BeatTheModel.cs`: `/btm/round`, `/btm/pick`, `/btm/name`, `/btm/table` |
| Page | `site/client/src/BeatTheModelPage.tsx`, logic in `web/src/lib/beatTheModel.ts` |

- **The tables.** `btm_players` (display names, unique whatever the case), `btm_picks` (one row
  a player and match), `btm_model` (the model's score, frozen at the first match-day run after
  kick-off), `btm_rounds` and `btm_seasons` (each player's totals). Row level security is on
  and the public key reaches none of them; players reach only the four functions, as themselves.
- **Scoring adds, never rebuilds.** Each run freezes the model's score of matches that have
  kicked off, marks the picks of finished ones (a partial index finds the unmarked) and adds them
  to the round and season totals. A rerun, or two runs at once, adds nothing twice.
- **A season** is named by the year it starts (August 2026 to May 2027 is 2026); **a round** is
  the number at the end of the match's round label. Picks open two weeks before kick-off.
- **Leaving the site** removes a player's rows (`ON DELETE CASCADE` on the account).
- **Cost.** About 150 bytes a pick, 380 picks a player a season: about 57 MB a season at 1,000
  players. No API-Football calls: the results are already stored.

## Fantasy points (`/fantasy-points`)

Every Premier League player's expected fantasy points for the next 10 rounds, with price,
position and injury news: the owner's [FPL](fantasy-expected-points.md) table without the owner's
Mine and Target ticks, and without the FPL name or logo. The data is the `fpl_predictions`
document the export writes (`fpl_owner_docs`); the rest of that table stays owner-only.

- **Asked for by the browser, never written into a page** (`site/client/src/FantasyPointsPage.tsx`).
- **One copy on the server.** `/fantasy/points` (`site/TheCornerFC.Web/Site/FantasyPoints.cs`)
  checks each visitor with `fantasy_points_stamp()` (about 100 bytes, with their own token) and
  keeps the document (about 1 MB), gzipped once, until the stamp says the nightly export has
  changed it; then `fantasy_points_doc()` is asked once. Database egress stays under 0.1 GB a
  month whatever the number of visitors.
- **Who may read it** is decided by the database: any signed-in account that isn't an anonymous
  sign-in (`db/migrations/20261123_fantasy_points_public.sql`).

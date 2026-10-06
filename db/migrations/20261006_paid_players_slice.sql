-- Repeatable. Not applied yet: the owner runs it in the Supabase SQL editor.
-- The free slice of the player ranks is the top 50 overall and the top 10 of the five big
-- leagues only (owner, 2026-10-06), not the top 10 of every league: with the paywall on, a
-- nation's page showed lower-league players' ranks above internationals whose ranks were hidden.
-- The export marks the slice from its next run (export.FREE_LEAGUES); this marks the rows already
-- stored. A player who leaves the slice keeps a whole page file ("players/<id>") until that
-- export writes his cut-down one, so run a nightly sync after this.
-- The positions are those of export.SITE_PLAYER_FIELDS: world is 15 and lg 16.
UPDATE site.players p SET
    free = coalesce((p.data->>15)::integer <= 50, false)
        OR (p.league_id = ANY (ARRAY[39, 140, 135, 78, 61]) AND coalesce((p.data->>16)::integer <= 10, false));

-- Check afterwards:
--   select count(*) filter (where free), count(*) from site.players;      -- about 90 of 7,500

-- Repeatable. Applied 2026-10-22.
-- The player names 20261022_repair_player_names.sql left garbled (T-049, 2026-10-22): three that
-- are garbled only in part ("A. Ã\u0096ztürk", "O. Ã\u0087akıroÄ\u009flu") or in the Windows-1252
-- form ("QarÉ™hmÉ™dov"), which a whole-string repair can't put back. Each garbled character is
-- put back on its own, as the jobs now do as names arrive (pipeline/api.py repair_text): a match
-- changes only if it reads back as one valid UTF-8 character. Needs nothing else. Also in
-- db/schema.sql.
BEGIN;

CREATE OR REPLACE FUNCTION pg_temp.unmangle_each(t text) RETURNS text LANGUAGE plpgsql AS $$
DECLARE
    m text;
    fixed text;
    out text := t;
BEGIN
    IF t IS NULL THEN
        RETURN t;
    END IF;
    FOR m IN SELECT (regexp_matches(t, '[Â-ß][\u0080-¿ŒœŠšŸŽžƒˆ˜–—‘-„†-•…‰‹›€™]|[à-ï][\u0080-¿€™ŒœŠš]{2}', 'g'))[1] LOOP
        fixed := NULL;
        BEGIN
            fixed := convert_from(convert_to(m, 'LATIN1'), 'UTF8');
        EXCEPTION WHEN others THEN
            BEGIN
                fixed := convert_from(convert_to(m, 'WIN1252'), 'UTF8');
            EXCEPTION WHEN others THEN
                fixed := NULL;
            END;
        END;
        IF fixed IS NOT NULL THEN
            out := replace(out, m, fixed);
        END IF;
    END LOOP;
    RETURN out;
END; $$;

UPDATE public.players
SET name = pg_temp.unmangle_each(name), firstname = pg_temp.unmangle_each(firstname), lastname = pg_temp.unmangle_each(lastname)
WHERE name IS DISTINCT FROM pg_temp.unmangle_each(name)
   OR firstname IS DISTINCT FROM pg_temp.unmangle_each(firstname)
   OR lastname IS DISTINCT FROM pg_temp.unmangle_each(lastname);

COMMIT;

-- Check afterwards (should be 0, and A. Öztürk):
--   select count(*) from players where name ~ '[Â-ß][\u0080-¿]|[à-ï][\u0080-¿]{2}';
--   select name from players where player_id = 493965;

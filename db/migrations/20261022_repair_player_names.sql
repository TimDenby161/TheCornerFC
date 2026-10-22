-- Repeatable. Applied 2026-10-22.
-- Player names as API-Football sent them, garbled (T-049, 2026-10-22): UTF-8 read as Latin-1,
-- "M. CvetkoviÄ\u0087" for M. Cvetković, "O. SÃ¸e" for O. Søe. Seen in production on 2026-10-22:
-- 75 names, 3 first names, 9 last names in players, nothing in any other table. The jobs repair
-- such text as it arrives from now on (pipeline/api.py repair_text); this puts back the rows
-- already stored, the same way: a value changes only if it reads back as valid UTF-8 (anything
-- else stays as it is), so a real name that merely looks odd is left alone. The site's tables
-- (site.players and the player pages) follow at the next nightly export. About 90 rows.
-- Also in db/schema.sql.
BEGIN;

CREATE OR REPLACE FUNCTION pg_temp.unmangle(t text) RETURNS text LANGUAGE plpgsql AS $$
BEGIN
    IF t IS NULL OR t !~ '[Â-ß][\u0080-¿]|[à-ï][\u0080-¿]{2}' THEN
        RETURN t;
    END IF;
    RETURN convert_from(convert_to(t, 'LATIN1'), 'UTF8');
EXCEPTION WHEN others THEN
    RETURN t;
END; $$;

UPDATE public.players
SET name = pg_temp.unmangle(name), firstname = pg_temp.unmangle(firstname), lastname = pg_temp.unmangle(lastname)
WHERE name IS DISTINCT FROM pg_temp.unmangle(name)
   OR firstname IS DISTINCT FROM pg_temp.unmangle(firstname)
   OR lastname IS DISTINCT FROM pg_temp.unmangle(lastname);

COMMIT;

-- Check afterwards (should be 0):
--   select count(*) from players where name ~ '[Â-ß][\u0080-¿]|[à-ï][\u0080-¿]{2}';
--   select name from players where player_id = 398190;     -- M. Cvetković

-- Additive and repeatable. The 90-minute score of national team matches (owner, 2026-10-07: paper bets on
-- internationals). national_fixtures has only the score after extra time; bookmakers settle on
-- 90 minutes, so a match that went to extra time needs this one. Filled by the nightly and
-- match-day runs from the day this is applied (ingest._national_rows leaves the columns out
-- until then). Until it is applied, a paper bet on a match that went to extra time is settled
-- void; one that finished in 90 minutes is settled as normal. Also in db/schema.sql.
ALTER TABLE national_fixtures ADD COLUMN IF NOT EXISTS ft_home integer;   -- after 90 minutes
ALTER TABLE national_fixtures ADD COLUMN IF NOT EXISTS ft_away integer;
-- Check:
--   select count(*) from information_schema.columns where table_name = 'national_fixtures' and column_name in ('ft_home', 'ft_away');   -- 2

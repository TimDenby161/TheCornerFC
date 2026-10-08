-- Repeatable. Not yet applied.
-- Personal data the site stored and never read (owner, 2026-10-08; audit D8): every player's
-- height, weight and photo link, and every coach's photo link. No model uses height or weight,
-- and the site draws initials, not photos. The sync stopped saving them in the same change.
--
-- Apply only once that change is on main: the older sync still writes these columns, and its
-- nightly run would fail without them.
alter table players drop column if exists height_cm, drop column if exists weight_kg, drop column if exists photo;
alter table team_coaches drop column if exists photo;

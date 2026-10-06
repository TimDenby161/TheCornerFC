-- The Corner FC schema for API-Football data (Supabase / Postgres).
-- Idempotent: safe to re-run.

create table if not exists leagues (
    league_id     int primary key,
    name          text not null,
    type          text,
    country       text,
    country_code  text,
    logo          text,
    updated_at    timestamptz not null default now()
);

create table if not exists league_seasons (
    league_id   int not null references leagues(league_id),
    season      int not null,
    start_date  date,
    end_date    date,
    is_current  boolean,
    coverage    jsonb,
    updated_at  timestamptz not null default now(),
    primary key (league_id, season)
);

create table if not exists venues (
    venue_id  int primary key,
    name      text,
    address   text,
    city      text,
    capacity  int,
    surface   text,
    image     text,
    updated_at timestamptz not null default now()
);

create table if not exists teams (
    team_id   int primary key,
    name      text not null,
    code      text,
    country   text,
    founded   int,
    national  boolean,
    logo      text,
    venue_id  int references venues(venue_id),
    updated_at timestamptz not null default now()
);

-- Which teams took part in which league season
create table if not exists team_seasons (
    team_id    int not null references teams(team_id),
    league_id  int not null references leagues(league_id),
    season     int not null,
    primary key (team_id, league_id, season)
);

create table if not exists fixtures (
    fixture_id     int primary key,
    league_id      int not null references leagues(league_id),
    season         int not null,
    round          text,
    kickoff        timestamptz,
    referee        text,
    venue_id       int,
    venue_name     text,
    venue_city     text,
    status_short   text,
    status_long    text,
    elapsed        int,
    home_team_id   int not null references teams(team_id),
    away_team_id   int not null references teams(team_id),
    home_goals     int,
    away_goals     int,
    ht_home        int,
    ht_away        int,
    ft_home        int,
    ft_away        int,
    et_home        int,
    et_away        int,
    pen_home       int,
    pen_away       int,
    home_winner    boolean,
    away_winner    boolean,
    stats_fetched_at timestamptz,
    updated_at     timestamptz not null default now()
);
create index if not exists fixtures_league_season_idx on fixtures (league_id, season);
create index if not exists fixtures_kickoff_idx on fixtures (kickoff);
create index if not exists fixtures_home_idx on fixtures (home_team_id);
create index if not exists fixtures_away_idx on fixtures (away_team_id);

-- One row per team per fixture
create table if not exists fixture_team_stats (
    fixture_id         int not null references fixtures(fixture_id) on delete cascade,
    team_id            int not null references teams(team_id),
    is_home            boolean,
    shots_on_goal      int,
    shots_off_goal     int,
    total_shots        int,
    blocked_shots      int,
    shots_inside_box   int,
    shots_outside_box  int,
    fouls              int,
    corners            int,
    offsides           int,
    possession_pct     numeric(5,2),
    yellow_cards       int,
    red_cards          int,
    goalkeeper_saves   int,
    passes_total       int,
    passes_accurate    int,
    passes_pct         numeric(5,2),
    expected_goals     numeric(6,2),
    goals_prevented    numeric(6,2),
    raw                jsonb,
    updated_at         timestamptz not null default now(),
    primary key (fixture_id, team_id)
);

create table if not exists standings (
    league_id       int not null references leagues(league_id),
    season          int not null,
    group_name      text not null,
    team_id         int not null references teams(team_id),
    rank            int,
    points          int,
    goal_diff       int,
    form            text,
    status          text,
    description     text,
    played          int,
    win             int,
    draw            int,
    lose            int,
    goals_for       int,
    goals_against   int,
    home_played     int,
    home_win        int,
    home_draw       int,
    home_lose       int,
    home_goals_for  int,
    home_goals_against int,
    away_played     int,
    away_win        int,
    away_draw       int,
    away_lose       int,
    away_goals_for  int,
    away_goals_against int,
    api_updated_at  timestamptz,
    updated_at      timestamptz not null default now(),
    primary key (league_id, season, group_name, team_id)
);

create table if not exists bookmakers (
    bookmaker_id  int primary key,
    name          text not null
);

create table if not exists bet_types (
    bet_id  int primary key,
    name    text not null
);

-- Latest pre-match price per fixture / bookmaker / market / selection.
-- API-Football only serves odds ~1-14 days before kickoff, so run the odds sync regularly.
create table if not exists odds (
    fixture_id      int not null,
    bookmaker_id    int not null references bookmakers(bookmaker_id),
    bet_id          int not null references bet_types(bet_id),
    selection       text not null,
    odd             numeric(10,3),
    api_updated_at  timestamptz,
    updated_at      timestamptz not null default now(),
    primary key (fixture_id, bookmaker_id, bet_id, selection)
);
create index if not exists odds_fixture_idx on odds (fixture_id);
-- Opening price (first time seen). `odd` stops updating at kickoff, so it's the closing price.
alter table odds add column if not exists first_odd numeric(10,3);
alter table odds add column if not exists first_seen_at timestamptz;
update odds set first_odd = odd, first_seen_at = updated_at where first_odd is null;

-- Players (config.PLAYER_LEAGUES) and their per-season stats from API-Football /players
create table if not exists players (
    player_id    int primary key,
    name         text not null,
    firstname    text,
    lastname     text,
    birth_date   date,
    nationality  text,
    height_cm    int,
    weight_kg    int,
    photo        text,
    updated_at   timestamptz not null default now()
);

-- One row per player per team per league season (a mid-season transfer gives two rows)
create table if not exists player_seasons (
    player_id           int not null references players(player_id),
    team_id             int not null,
    league_id           int not null,
    season              int not null,
    position            text,
    shirt_number        int,
    appearances         int,
    starts              int,
    minutes             int,
    rating              numeric(5,3),
    captain             boolean,
    subbed_in           int,
    subbed_out          int,
    bench               int,
    goals               int,
    assists             int,
    goals_conceded      int,
    saves               int,
    shots               int,
    shots_on            int,
    passes              int,
    key_passes          int,
    pass_accuracy       int,
    tackles             int,
    blocks              int,
    interceptions       int,
    duels               int,
    duels_won           int,
    dribbles            int,
    dribbles_won        int,
    dribbled_past       int,
    fouls_drawn         int,
    fouls_committed     int,
    yellow_cards        int,
    yellow_red_cards    int,
    red_cards           int,
    penalties_won       int,
    penalties_committed int,
    penalties_scored    int,
    penalties_missed    int,
    penalties_saved     int,
    updated_at          timestamptz not null default now(),
    primary key (player_id, team_id, league_id, season)
);
create index if not exists player_seasons_team_idx on player_seasons (team_id, season);

-- Players listed as missing or doubtful for a fixture (API-Football /injuries)
create table if not exists injuries (
    fixture_id   int not null,
    player_id    int not null,
    team_id      int not null,
    league_id    int,
    season       int,
    type         text,     -- 'Missing Fixture' or 'Questionable'
    reason       text,     -- e.g. 'Hamstring Injury', 'Suspended'
    updated_at   timestamptz not null default now(),
    primary key (fixture_id, player_id)
);
create index if not exists injuries_team_idx on injuries (team_id, fixture_id);

-- Who played in each match and for how long (config.INJURY_MODEL_LEAGUES only), from the
-- player block of /fixtures?ids=. Only players with minutes are stored.
create table if not exists fixture_players (
    fixture_id  int not null,
    team_id     int not null,
    player_id   int not null,
    minutes     smallint not null,
    started     boolean,
    position    text,          -- G / D / M / F
    rating      numeric(3,1),
    primary key (fixture_id, player_id)
);
create index if not exists fixture_players_team_idx on fixture_players (team_id, fixture_id);
-- Per-match stat line (smallint; nulls take no space)
alter table fixture_players add column if not exists goals smallint;
alter table fixture_players add column if not exists assists smallint;
alter table fixture_players add column if not exists shots smallint;
alter table fixture_players add column if not exists shots_on smallint;
alter table fixture_players add column if not exists key_passes smallint;
alter table fixture_players add column if not exists passes smallint;
alter table fixture_players add column if not exists passes_accurate smallint;
alter table fixture_players add column if not exists tackles smallint;
alter table fixture_players add column if not exists interceptions smallint;
alter table fixture_players add column if not exists blocks smallint;
alter table fixture_players add column if not exists duels smallint;
alter table fixture_players add column if not exists duels_won smallint;
alter table fixture_players add column if not exists dribbles smallint;
alter table fixture_players add column if not exists dribbles_won smallint;
alter table fixture_players add column if not exists fouls_committed smallint;
alter table fixture_players add column if not exists fouls_drawn smallint;
alter table fixture_players add column if not exists yellow_cards smallint;
alter table fixture_players add column if not exists red_cards smallint;
alter table fixture_players add column if not exists saves smallint;
alter table fixture_players add column if not exists goals_conceded smallint;
alter table fixture_players add column if not exists penalties_saved smallint;
alter table fixture_players add column if not exists dribbled_past smallint;        -- times an opponent dribbled past him
alter table fixture_players add column if not exists penalties_committed smallint;
alter table fixture_players add column if not exists penalties_won smallint;      -- fantasy v1.5 penalty takers
alter table fixture_players add column if not exists penalties_scored smallint;
alter table fixture_players add column if not exists penalties_missed smallint;
-- Starting position from the line-up: grid "row:col" and the role derived from it with the
-- formation (positions.py), e.g. 'LB', 'DM', 'RW'. Null for substitutes.
alter table fixture_players add column if not exists grid text;
alter table fixture_players add column if not exists role text;
create table if not exists fixture_formations (
    fixture_id  int not null,
    team_id     int not null,
    formation   text,
    primary key (fixture_id, team_id)
);
alter table fixture_formations add column if not exists coach_id int;   -- the manager on the line-up
-- Starting XIs for cup and European matches of clubs in the per-match player leagues
-- (ingest.sync_cup_lineups): who started where, for the club page's formations and starts.
-- Kept apart from fixture_players so the player ratings stay league-only.
create table if not exists fixture_lineups (
    fixture_id  int not null,
    team_id     int not null,
    player_id   int not null,
    grid        text,
    role        text,
    primary key (fixture_id, player_id)
);
-- Each club's home kit colours (hex, no #) from its latest home line-up, for the club page pitch
create table if not exists team_colors (
    team_id     int primary key,
    fixture_id  int not null,
    kickoff     timestamptz not null,
    shirt       text,
    number      text
);
-- Each club's and national team's current manager (/coachs?team=, ingest.sync_coaches and
-- sync_national_coaches) and when he started there
create table if not exists team_coaches (
    team_id     int primary key,
    coach_id    int,
    name        text,
    photo       text,
    since       date,
    fetched_at  timestamptz not null default now()
);
-- Player rank (0-100) going into each match, from matches before it (player_ratings.py).
-- Its own table, rebuilt with truncate + copy, so fixture_players isn't rewritten nightly.
-- No key or index: it's only ever rebuilt in full, and an index would double its size.
create table if not exists fixture_player_ranks (
    fixture_id   int not null,
    player_id    int not null,
    player_rank  numeric(4,1)
);
alter table fixture_player_ranks drop constraint if exists fixture_player_ranks_pkey;
alter table fixture_players drop column if exists player_rank;
alter table fixtures add column if not exists players_fetched_at timestamptz;

-- Clubs each player was at, by season, in any league (/players/teams). Used to name the club
-- (and its level) for seasons with no minutes in the player-data leagues.
create table if not exists player_career_teams (
    player_id  int not null,
    season     int not null,
    team_id    int not null,
    primary key (player_id, season, team_id)
);

-- Current squads of the clubs in the per-match player leagues (/players/squads?team=, nightly):
-- a player's club on the site, and squad members are listed whatever their minutes
create table if not exists team_squads (
    team_id     int not null,
    player_id   int not null,
    fetched_at  timestamptz not null default now(),
    primary key (team_id, player_id)
);
create index if not exists team_squads_player_idx on team_squads (player_id);

-- How good each player would be in each outfield position group now (player_ratings.py,
-- rebuilt on every run): his recent stats scored as that position, against its players
create table if not exists player_position_ranks (
    player_id      int not null,
    role_group     text not null,       -- CB FB WB DM CM AM W ST
    position_rank  numeric(4,1),
    primary key (player_id, role_group)
);

-- Each player's next seasons (player_ratings.py, rebuilt on every run): his current rank
-- moved along the age curve for his position
create table if not exists player_projected_ranks (
    player_id       int not null,
    season          int not null,
    projected_rank  numeric(4,1),
    primary key (player_id, season)
);

-- Hand corrections to player details from API-Football (which the nightly sync would
-- overwrite on players itself); applied when the site data is exported
create table if not exists player_overrides (
    player_id    int primary key,
    nationality  text              -- null: keep API-Football's
);

-- Latest current-club check (/players/squads) of a player who hasn't played this season
-- (ingest.check_retired): one made after his last season finding no club marks him retired
create table if not exists player_career_checks (
    player_id   int primary key,
    season      int not null,              -- the current season when checked
    team_id     int,                       -- a club whose squad he's in; null: none
    checked_at  timestamptz not null default now()
);
alter table player_career_checks add column if not exists team_id int;

-- Player rank for each season: minutes-weighted average of his rank after each match that
-- season (player_ratings.py, rebuilt on every run)
create table if not exists player_season_ranks (
    player_id    int not null,
    season       int not null,
    season_rank  numeric(4,1),
    minutes      int,
    primary key (player_id, season)
);
-- for a gap season (minutes = 0): the club he was at, from player_career_teams
alter table player_season_ranks add column if not exists team_id int;

-- Team ratings per fixture from player ranks (player_ratings.py), all as known before kickoff
create table if not exists fixture_team_ratings (
    fixture_id           int not null,
    team_id              int not null,
    predicted_xi_rating  numeric(5,2),   -- average rank of the predicted XI
    predicted_xi_size    smallint,
    recent_xi_rating     numeric(5,2),   -- average rank of the XIs started in the last 5 matches
    actual_xi_rating     numeric(5,2),   -- average rank of the XI that started (finished matches)
    primary key (fixture_id, team_id)
);
-- The same averages by line (GK, DEF, MID, FWD), for the XI that started and the predicted XI.
-- A starter's line is the role he started in (LM/RM count as MID, LW/RW as FWD).
alter table fixture_team_ratings add column if not exists actual_gk  numeric(5,2);
alter table fixture_team_ratings add column if not exists actual_def numeric(5,2);
alter table fixture_team_ratings add column if not exists actual_mid numeric(5,2);
alter table fixture_team_ratings add column if not exists actual_fwd numeric(5,2);
alter table fixture_team_ratings add column if not exists predicted_gk  numeric(5,2);
alter table fixture_team_ratings add column if not exists predicted_def numeric(5,2);
alter table fixture_team_ratings add column if not exists predicted_mid numeric(5,2);
alter table fixture_team_ratings add column if not exists predicted_fwd numeric(5,2);
-- Predicted XI for upcoming fixtures (rebuilt nightly)
create table if not exists predicted_lineups (
    fixture_id   int not null,
    team_id      int not null,
    player_id    int not null,
    position     text,
    player_rank  numeric(4,1),
    primary key (fixture_id, player_id)
);
-- Predicted XI the replay works out for every finished match, from what it knew before kick-off
-- (rebuilt nightly; the Line-up record tab's reconstructed history, not captured evidence)
create table if not exists reconstructed_lineups (
    fixture_id   int not null,
    team_id      int not null,
    players      int[] not null,   -- the predicted XI, in slot order
    roles        text[] not null,  -- each one's predicted role, same order
    primary key (fixture_id, team_id)
);
alter table players add column if not exists current_rank numeric(4,1);
alter table players add column if not exists rank_position text;
alter table players add column if not exists rank_minutes int;

-- Club ranking (see thecornerfc/ranking.py). Rebuilt from scratch on every run.
-- Every team starts from leagues.starting_rank of the first league it plays in.
alter table leagues add column if not exists starting_rank numeric;

create table if not exists team_rank_history (
    fixture_id   int not null,
    team_id      int not null,
    match_no     int not null,
    kickoff      timestamptz,
    is_home      boolean,
    opponent_id  int,
    rank_before  double precision,
    rank_after   double precision,
    exp_diff     double precision,
    act_diff     int,
    rank_change  double precision,
    primary key (fixture_id, team_id)
);
create index if not exists team_rank_history_team_idx on team_rank_history (team_id, match_no);
-- LT ALGO going into the match: the club level used by the player ranks
alter table team_rank_history add column if not exists lt_before double precision;
-- Attack / defence and home / away after the match (ranking.side_ratings): attack and defence
-- average to rank_after; home and away are rank_after plus / minus the club's own home edge
alter table team_rank_history add column if not exists attack_after double precision;
alter table team_rank_history add column if not exists defence_after double precision;
alter table team_rank_history add column if not exists home_after double precision;
alter table team_rank_history add column if not exists away_after double precision;
-- What the projections need going into the match: the club's attack/defence split s and home
-- edge e before it, and its expected goals base in that competition (ranking.side_ratings)
alter table team_rank_history add column if not exists split_before double precision;
alter table team_rank_history add column if not exists edge_before double precision;
alter table team_rank_history add column if not exists goal_base double precision;
-- Each competition's goal base now (home, away), for projecting upcoming fixtures
alter table leagues add column if not exists goal_base_home double precision;
alter table leagues add column if not exists goal_base_away double precision;

create table if not exists team_rankings (
    team_id        int primary key,
    league_id      int,
    starting_rank  double precision,
    played         int,
    last_match     timestamptz,
    current_rank   double precision,
    st_algo        double precision,
    rank_30        double precision,
    rank_100       double precision,
    lt_algo        double precision,
    hg             double precision,
    ha             double precision,
    ag             double precision,
    aa             double precision
);
alter table team_rankings add column if not exists rank_volatility double precision;
alter table team_rankings add column if not exists reliability double precision;
alter table team_rankings add column if not exists attack double precision;       -- now, as above
alter table team_rankings add column if not exists defence double precision;
alter table team_rankings add column if not exists home_rating double precision;
alter table team_rankings add column if not exists away_rating double precision;

-- Projected score and win/draw/loss chances for upcoming fixtures (see
-- thecornerfc/predictions.py). Rebuilt nightly after the rankings.
create table if not exists fixture_predictions (
    fixture_id        int primary key,
    kickoff           timestamptz,
    league_id         int,
    home_team_id      int,
    away_team_id      int,
    home_rank         double precision,
    away_rank         double precision,
    exp_diff          double precision,   -- expected goal difference (home - away)
    home_xg           double precision,   -- projected home goals
    away_xg           double precision,   -- projected away goals
    p_home            double precision,
    p_draw            double precision,
    p_away            double precision,
    likely_score      text,               -- single most likely scoreline
    home_reliability  double precision,
    away_reliability  double precision,
    updated_at        timestamptz not null default now()
);

-- 'live' = made before kickoff by the nightly run; 'backfill' = reconstructed afterwards
-- from pre-match ranks and goal averages (what the current model would have said)
alter table fixture_predictions add column if not exists source text not null default 'live';
-- 1 (terrible) - 5 (excellent) grade of the projection once the match is finished, plus the
-- five 0-5 factor scores it is weighted from (see thecornerfc/rating.py)
-- Missing-player strength from the injury lists (1.0 = one ever-present player), see
-- thecornerfc/injuries.py; null where there's no injury list
alter table fixture_predictions add column if not exists home_missing double precision;
alter table fixture_predictions add column if not exists away_missing double precision;
alter table fixture_predictions add column if not exists p_over25 double precision;
alter table fixture_predictions add column if not exists p_btts double precision;
alter table fixture_predictions add column if not exists rating smallint;
alter table fixture_predictions add column if not exists rating_winner smallint;
alter table fixture_predictions add column if not exists rating_margin smallint;
alter table fixture_predictions add column if not exists rating_clean_sheets smallint;
alter table fixture_predictions add column if not exists rating_shape smallint;
alter table fixture_predictions add column if not exists rating_goals smallint;

create or replace view upcoming_predictions as
select p.kickoff, l.name as competition, l.country, f.round,
       h.name as home_team, a.name as away_team,
       round(p.home_xg::numeric, 2) as home_goals, round(p.away_xg::numeric, 2) as away_goals,
       p.likely_score,
       round((100 * p.p_home)::numeric, 1) as home_win_pct,
       round((100 * p.p_draw)::numeric, 1) as draw_pct,
       round((100 * p.p_away)::numeric, 1) as away_win_pct,
       round(p.exp_diff::numeric, 2) as expected_margin,
       round(p.home_rank::numeric, 0) as home_rank, round(p.away_rank::numeric, 0) as away_rank,
       round(least(p.home_reliability, p.away_reliability)::numeric, 0) as reliability,
       p.fixture_id
from fixture_predictions p
join fixtures f using (fixture_id)
join leagues l on l.league_id = p.league_id
join teams h on h.team_id = p.home_team_id
join teams a on a.team_id = p.away_team_id
order by p.kickoff;

-- Paper bets placed by the model (see thecornerfc/betting.py): never real money.
create table if not exists paper_bets (
    bet_id          bigserial primary key,
    strategy        text not null,       -- 'early' (night before) or 'late' (just before kickoff)
    fixture_id      int not null,
    league_id       int,
    kickoff         timestamptz,
    market          text not null,       -- '1X2', 'OU15', 'OU25', 'OU35', 'OU45', 'BTTS'
    selection       text not null,       -- e.g. 'Home', 'Over 2.5', 'Yes'
    model_prob      double precision,
    fair_prob       double precision,    -- bookmakers' average, margin removed, when placed
    odds_taken      numeric(10,3),       -- best price across bookmakers when placed
    bookmaker_id    int,
    edge            double precision,    -- model_prob * odds_taken - 1
    stake           numeric(10,2) not null default 1,
    placed_at       timestamptz not null default now(),
    closing_odds    numeric(10,3),       -- best price at kickoff
    closing_fair    double precision,    -- fair probability at kickoff
    clv             double precision,    -- odds_taken * closing_fair - 1 (beat the close if > 0)
    result          text,                -- 'win', 'loss', 'void'
    profit          numeric(10,3),
    settled_at      timestamptz,
    unique (strategy, fixture_id, market, selection)
);
-- Kind of disagreement (betting.bet_tags): cup / big5 / league, promoted, thin_data, streak,
-- favourite / outsider, gap10
alter table paper_bets add column if not exists tags text[];
create index if not exists paper_bets_fixture_idx on paper_bets (fixture_id);

-- Supabase exposes the public schema through its REST API; enable RLS with no
-- policies so these tables are only reachable via the postgres/service role.
alter table leagues            enable row level security;
alter table league_seasons     enable row level security;
alter table venues             enable row level security;
alter table teams              enable row level security;
alter table team_seasons       enable row level security;
alter table fixtures           enable row level security;
alter table fixture_team_stats enable row level security;
alter table standings          enable row level security;
alter table bookmakers         enable row level security;
alter table bet_types          enable row level security;
alter table odds               enable row level security;
alter table team_rank_history  enable row level security;
alter table team_rankings      enable row level security;
alter table fixture_predictions enable row level security;
alter table players            enable row level security;
alter table player_seasons     enable row level security;
alter table injuries           enable row level security;
alter table fixture_players    enable row level security;
alter table paper_bets         enable row level security;
alter table fixture_team_ratings enable row level security;
alter table predicted_lineups  enable row level security;
alter table reconstructed_lineups enable row level security;
alter table fixture_formations enable row level security;
alter table team_coaches       enable row level security;
alter table team_colors        enable row level security;
alter table fixture_lineups    enable row level security;
-- Additive and repeatable. No existing model output/history is modified.
CREATE TABLE IF NOT EXISTS model_versions (
    model_version_id text PRIMARY KEY CHECK (model_version_id ~ '^mv_[0-9a-f]{64}$'),
    model_type text NOT NULL CHECK (model_type IN ('club','player','lineup','match','betting','fantasy')),
    version_name text NOT NULL CHECK (length(trim(version_name)) > 0),
    code_sha text CHECK (code_sha IS NULL OR code_sha ~ '^[0-9a-f]{40}([0-9a-f]{24})?$'),
    configuration jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(configuration) = 'object'),
    training_start timestamptz,
    training_end timestamptz,
    evaluation_start timestamptz,
    evaluation_end timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    notes text NOT NULL DEFAULT '',
    CHECK ((training_start IS NULL AND training_end IS NULL) OR
           (training_start IS NOT NULL AND training_end IS NOT NULL AND training_start < training_end)),
    CHECK ((evaluation_start IS NULL AND evaluation_end IS NULL) OR
           (evaluation_start IS NOT NULL AND evaluation_end IS NOT NULL AND evaluation_start < evaluation_end))
);
CREATE INDEX IF NOT EXISTS model_versions_type_created_idx ON model_versions(model_type, created_at);
-- Names are labels, not unique identities. Changed configuration/SHA gets a new ID.
COMMENT ON TABLE model_versions IS 'Immutable model provenance registry shared by domain-specific outputs/snapshots. Register through thecornerfc.model_versions.';
COMMENT ON COLUMN model_versions.created_at IS 'Database row insertion time. Never source observation time or event time.';
COMMENT ON COLUMN model_versions.training_start IS 'Inclusive training window start; end is exclusive. NULL pair means not applicable/unknown.';
COMMENT ON COLUMN model_versions.evaluation_start IS 'Inclusive evaluation window start; end is exclusive. NULL pair means not applicable/unknown.';

CREATE OR REPLACE FUNCTION prevent_model_version_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Model versions are immutable; register a new version instead';
END;
$$;
DROP TRIGGER IF EXISTS model_versions_immutable ON model_versions;
CREATE TRIGGER model_versions_immutable BEFORE UPDATE OR DELETE ON model_versions
FOR EACH ROW EXECUTE FUNCTION prevent_model_version_mutation();
ALTER TABLE model_versions ENABLE ROW LEVEL SECURITY;
-- Requires 20260926_model_versions.sql. Existing prediction rows are untouched.
CREATE TABLE IF NOT EXISTS match_prediction_snapshots (
    snapshot_id bigserial PRIMARY KEY,
    fixture_id integer NOT NULL,
    league_id integer NOT NULL,
    home_team_id integer NOT NULL,
    away_team_id integer NOT NULL,
    model_version_id text NOT NULL REFERENCES model_versions(model_version_id) ON DELETE RESTRICT,
    source text NOT NULL CHECK (source IN ('prospective','reconstruction','late_observation')),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    captured_at timestamptz NOT NULL,
    effective_at timestamptz NOT NULL, -- kickoff known at capture time
    model_reference_at timestamptz NOT NULL, -- clock used for rank blend/history window
    seconds_to_kickoff double precision NOT NULL,
    p_home double precision NOT NULL CHECK (p_home BETWEEN 0 AND 1),
    p_draw double precision NOT NULL CHECK (p_draw BETWEEN 0 AND 1),
    p_away double precision NOT NULL CHECK (p_away BETWEEN 0 AND 1),
    home_xg double precision NOT NULL CHECK (home_xg >= 0),
    away_xg double precision NOT NULL CHECK (away_xg >= 0),
    exp_diff double precision NOT NULL,
    likely_score text,
    p_over25 double precision NOT NULL,
    p_btts double precision NOT NULL,
    inputs jsonb NOT NULL CHECK (jsonb_typeof(inputs)='object'),
    content_hash text NOT NULL,
    CHECK (abs(p_home+p_draw+p_away-1) < 0.000001),
    CHECK (source <> 'prospective' OR (captured_at < effective_at AND created_at < effective_at)),
    UNIQUE(fixture_id, model_version_id, source, content_hash)
);
CREATE INDEX IF NOT EXISTS match_snapshots_fixture_capture_idx ON match_prediction_snapshots(fixture_id,captured_at);
CREATE OR REPLACE FUNCTION guard_match_snapshot() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'Match prediction snapshots are append only';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM model_versions WHERE model_version_id=NEW.model_version_id AND model_type='match') THEN
        RAISE EXCEPTION 'Match snapshots require a match model version';
    END IF;
    NEW.created_at := clock_timestamp();
    IF NEW.source='prospective' AND (NEW.captured_at >= NEW.effective_at OR NEW.created_at >= NEW.effective_at) THEN
        NEW.source := 'late_observation';
    END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS match_snapshots_guard ON match_prediction_snapshots;
CREATE TRIGGER match_snapshots_guard BEFORE INSERT OR UPDATE OR DELETE ON match_prediction_snapshots
FOR EACH ROW EXECUTE FUNCTION guard_match_snapshot();
DROP TRIGGER IF EXISTS match_snapshots_no_truncate ON match_prediction_snapshots;
CREATE TRIGGER match_snapshots_no_truncate BEFORE TRUNCATE ON match_prediction_snapshots
FOR EACH STATEMENT EXECUTE FUNCTION guard_match_snapshot();
ALTER TABLE match_prediction_snapshots ENABLE ROW LEVEL SECURITY;
COMMENT ON TABLE match_prediction_snapshots IS 'Append-only predictions. Only source=prospective is genuine pre-event capture; reconstructions and late observations must be excluded from prospective evaluation.';
-- Requires model_versions. No existing lineups/injuries are modified.
CREATE TABLE IF NOT EXISTS lineup_prediction_snapshots (
    snapshot_id bigserial PRIMARY KEY,
    fixture_id integer NOT NULL,
    team_id integer NOT NULL,
    model_version_id text NOT NULL REFERENCES model_versions(model_version_id) ON DELETE RESTRICT,
    source text NOT NULL CHECK(source IN ('prospective','late_observation')),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    captured_at timestamptz NOT NULL,
    effective_at timestamptz NOT NULL,
    seconds_to_kickoff double precision NOT NULL,
    players jsonb NOT NULL CHECK(jsonb_typeof(players)='array'),
    selection_inputs jsonb NOT NULL CHECK(jsonb_typeof(selection_inputs)='object'),
    availability jsonb NOT NULL CHECK(jsonb_typeof(availability)='object'),
    content_hash text NOT NULL,
    CHECK(source <> 'prospective' OR (captured_at < effective_at AND created_at < effective_at)),
    UNIQUE(fixture_id,team_id,model_version_id,source,content_hash)
);
CREATE INDEX IF NOT EXISTS lineup_snapshot_fixture_idx ON lineup_prediction_snapshots(fixture_id,team_id,captured_at);
CREATE TABLE IF NOT EXISTS official_lineup_snapshots (
    snapshot_id bigserial PRIMARY KEY,
    fixture_id integer NOT NULL,
    team_id integer NOT NULL,
    source text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    captured_at timestamptz NOT NULL,
    effective_at timestamptz NOT NULL,
    formation text,
    players jsonb NOT NULL CHECK(jsonb_typeof(players)='array'),
    content_hash text NOT NULL,
    UNIQUE(fixture_id,team_id,source,content_hash)
);
CREATE INDEX IF NOT EXISTS official_lineup_fixture_idx ON official_lineup_snapshots(fixture_id,team_id,captured_at);
CREATE OR REPLACE FUNCTION guard_lineup_snapshot() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'Lineup evidence is append only';
    END IF;
    NEW.created_at := clock_timestamp();
    IF TG_TABLE_NAME='lineup_prediction_snapshots' THEN
        IF NOT EXISTS (SELECT 1 FROM model_versions WHERE model_version_id=NEW.model_version_id AND model_type='lineup') THEN
            RAISE EXCEPTION 'Lineup predictions require a lineup model version';
        END IF;
        IF NEW.captured_at>=NEW.effective_at OR NEW.created_at>=NEW.effective_at THEN
            NEW.source := 'late_observation';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS lineup_prediction_guard ON lineup_prediction_snapshots;
CREATE TRIGGER lineup_prediction_guard BEFORE INSERT OR UPDATE OR DELETE ON lineup_prediction_snapshots
FOR EACH ROW EXECUTE FUNCTION guard_lineup_snapshot();
DROP TRIGGER IF EXISTS lineup_prediction_truncate_guard ON lineup_prediction_snapshots;
CREATE TRIGGER lineup_prediction_truncate_guard BEFORE TRUNCATE ON lineup_prediction_snapshots
FOR EACH STATEMENT EXECUTE FUNCTION guard_lineup_snapshot();
DROP TRIGGER IF EXISTS official_lineup_guard ON official_lineup_snapshots;
CREATE TRIGGER official_lineup_guard BEFORE INSERT OR UPDATE OR DELETE ON official_lineup_snapshots
FOR EACH ROW EXECUTE FUNCTION guard_lineup_snapshot();
DROP TRIGGER IF EXISTS official_lineup_truncate_guard ON official_lineup_snapshots;
CREATE TRIGGER official_lineup_truncate_guard BEFORE TRUNCATE ON official_lineup_snapshots
FOR EACH STATEMENT EXECUTE FUNCTION guard_lineup_snapshot();
ALTER TABLE lineup_prediction_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE official_lineup_snapshots ENABLE ROW LEVEL SECURITY;
-- Requires model_versions and match_prediction_snapshots. No legacy rows are rewritten.
CREATE TABLE IF NOT EXISTS odds_observations (
    observation_id bigserial PRIMARY KEY,
    fixture_id integer NOT NULL,
    bookmaker_id integer NOT NULL,
    market_id integer NOT NULL,
    selection text NOT NULL,
    odds numeric NOT NULL CHECK(odds > 1),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    captured_at timestamptz NOT NULL,
    effective_at timestamptz,
    provider_updated_at timestamptz,
    source text NOT NULL
);
CREATE INDEX IF NOT EXISTS odds_observations_lookup_idx
ON odds_observations(fixture_id,bookmaker_id,market_id,selection,captured_at DESC,observation_id DESC);
CREATE TABLE IF NOT EXISTS paper_decisions (
    decision_id bigserial PRIMARY KEY,
    paper_bet_id bigint NOT NULL UNIQUE REFERENCES paper_bets(bet_id) ON DELETE RESTRICT,
    fixture_id integer NOT NULL,
    strategy text NOT NULL,
    strategy_version_id text NOT NULL REFERENCES model_versions(model_version_id) ON DELETE RESTRICT,
    model_version_id text NOT NULL REFERENCES model_versions(model_version_id) ON DELETE RESTRICT,
    prediction_snapshot_id bigint NOT NULL REFERENCES match_prediction_snapshots(snapshot_id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    captured_at timestamptz NOT NULL, -- decision timestamp
    effective_at timestamptz NOT NULL, -- known kickoff
    market text NOT NULL,
    market_id integer NOT NULL,
    selection text NOT NULL,
    bookmaker_id integer NOT NULL,
    model_probability double precision NOT NULL,
    raw_implied_probability double precision NOT NULL,
    fair_probability double precision,
    odds_taken numeric NOT NULL,
    market_margin double precision, -- chosen bookmaker's complete market overround
    edge double precision NOT NULL,
    edge_formula text NOT NULL,
    stake_units numeric NOT NULL,
    odds_observation_id bigint REFERENCES odds_observations(observation_id) ON DELETE RESTRICT,
    evidence jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS paper_outcomes (
    outcome_id bigserial PRIMARY KEY,
    decision_id bigint NOT NULL REFERENCES paper_decisions(decision_id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    captured_at timestamptz NOT NULL,
    source text NOT NULL,
    closing_odds numeric,
    closing_fair_probability double precision,
    price_clv double precision,
    probability_movement double precision,
    result text NOT NULL,
    profit_units numeric NOT NULL,
    evidence jsonb NOT NULL,
    content_hash text NOT NULL,
    UNIQUE(decision_id,content_hash)
);
CREATE OR REPLACE FUNCTION guard_paper_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'Odds and paper evidence are append only';
    END IF;
    NEW.created_at := clock_timestamp();
    IF TG_TABLE_NAME='paper_decisions' THEN
        IF NOT EXISTS (SELECT 1 FROM model_versions WHERE model_version_id=NEW.strategy_version_id AND model_type='betting') THEN
            RAISE EXCEPTION 'Paper decisions require a betting strategy version';
        END IF;
        IF NOT EXISTS (SELECT 1 FROM match_prediction_snapshots s WHERE s.snapshot_id=NEW.prediction_snapshot_id
            AND s.model_version_id=NEW.model_version_id AND s.fixture_id=NEW.fixture_id
            AND s.source='prospective' AND s.captured_at<=NEW.captured_at AND s.created_at<=NEW.captured_at) THEN
            RAISE EXCEPTION 'Paper decision requires its actual prospective prediction snapshot';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['odds_observations','paper_decisions','paper_outcomes'] LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS evidence_guard ON %I',t);
        EXECUTE format('CREATE TRIGGER evidence_guard BEFORE INSERT OR UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION guard_paper_evidence()',t);
        EXECUTE format('DROP TRIGGER IF EXISTS evidence_truncate_guard ON %I',t);
        EXECUTE format('CREATE TRIGGER evidence_truncate_guard BEFORE TRUNCATE ON %I FOR EACH STATEMENT EXECUTE FUNCTION guard_paper_evidence()',t);
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',t);
    END LOOP;
END;
$$;
-- Requires model_versions. Existing player tables/history are untouched.
CREATE TABLE IF NOT EXISTS player_rating_captures (
    capture_id bigserial PRIMARY KEY,
    capture_date date NOT NULL UNIQUE,
    captured_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    model_version_id text NOT NULL REFERENCES model_versions(model_version_id) ON DELETE RESTRICT,
    season integer NOT NULL,
    population integer NOT NULL CHECK(population>=0),
    CHECK(capture_date=(captured_at AT TIME ZONE 'UTC')::date)
);
CREATE TABLE IF NOT EXISTS player_rating_history (
    capture_id bigint NOT NULL REFERENCES player_rating_captures(capture_id) ON DELETE RESTRICT,
    player_id integer NOT NULL,
    rating numeric(4,1) NOT NULL,
    world_rank integer NOT NULL,
    position text,
    rating_group text,
    team_id integer,
    team_source text NOT NULL,
    window_minutes integer,
    season_minutes integer,
    rating_source text NOT NULL,
    PRIMARY KEY(capture_id,player_id)
);
CREATE INDEX IF NOT EXISTS player_rating_history_player_idx ON player_rating_history(player_id,capture_id);
CREATE OR REPLACE FUNCTION guard_player_history() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'Player rating history is append only';
    END IF;
    IF TG_TABLE_NAME='player_rating_captures' THEN
        NEW.created_at:=clock_timestamp();
        IF NOT EXISTS(SELECT 1 FROM model_versions WHERE model_version_id=NEW.model_version_id AND model_type='player') THEN
            RAISE EXCEPTION 'Player captures require a player model version';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
DO $$ DECLARE t text; BEGIN
    FOREACH t IN ARRAY ARRAY['player_rating_captures','player_rating_history'] LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS player_history_guard ON %I',t);
        EXECUTE format('CREATE TRIGGER player_history_guard BEFORE INSERT OR UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION guard_player_history()',t);
        EXECUTE format('DROP TRIGGER IF EXISTS player_history_truncate_guard ON %I',t);
        EXECUTE format('CREATE TRIGGER player_history_truncate_guard BEFORE TRUNCATE ON %I FOR EACH STATEMENT EXECUTE FUNCTION guard_player_history()',t);
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',t);
    END LOOP;
END; $$;
CREATE OR REPLACE VIEW player_rating_snapshot_history AS
SELECT h.*, c.captured_at,c.created_at,c.capture_date,c.model_version_id,c.season,c.population
FROM player_rating_history h JOIN player_rating_captures c USING(capture_id);
-- Positive rating change = improved rating. Positive rank movement = moved up.
-- Baselines use actual stored observations at/before the requested horizon.
CREATE OR REPLACE VIEW player_rating_movement AS
WITH latest AS (
    SELECT DISTINCT ON(player_id) * FROM player_rating_snapshot_history
    ORDER BY player_id,captured_at DESC,capture_id DESC
)
SELECT n.player_id,n.captured_at,n.rating,n.world_rank,n.model_version_id,n.season,
       horizon.label AS horizon, b.captured_at AS baseline_at,b.model_version_id AS baseline_model_version_id,
       n.rating-b.rating AS rating_change,b.world_rank-n.world_rank AS rank_movement,
       CASE WHEN b.capture_id IS NOT NULL THEN n.model_version_id IS DISTINCT FROM b.model_version_id END AS model_changed,
       n.population AS population,b.population AS baseline_population
FROM latest n CROSS JOIN (VALUES ('7d',7),('30d',30),('90d',90),('season',0)) horizon(label,days)
LEFT JOIN LATERAL (
    SELECT p.* FROM player_rating_snapshot_history p
    WHERE p.player_id=n.player_id AND
      ((horizon.days>0 AND p.captured_at<=n.captured_at-make_interval(days=>horizon.days))
       OR (horizon.days=0 AND p.season=n.season AND p.captured_at<n.captured_at))
    ORDER BY CASE WHEN horizon.days=0 THEN p.captured_at END ASC,
             CASE WHEN horizon.days>0 THEN p.captured_at END DESC,p.capture_id DESC
    LIMIT 1
) b ON true;

REVOKE ALL ON player_rating_snapshot_history,player_rating_movement FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('REVOKE ALL ON player_rating_snapshot_history,player_rating_movement FROM %I',r);
        END IF;
    END LOOP;
END; $$;

-- Prospective capture for protocols P1/P2 (experiments/prospective/PROTOCOLS.md). Additive only:
-- new append-only tables and nullable columns; no existing rows are rewritten.
-- Dated registered squads: one row whenever a club's /players/squads list changes.
CREATE TABLE IF NOT EXISTS squad_snapshots (
    snapshot_id bigserial PRIMARY KEY,
    team_id integer NOT NULL,
    source text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    captured_at timestamptz NOT NULL,
    players jsonb NOT NULL CHECK(jsonb_typeof(players)='array'), -- API ids plus the mapped match-data id
    content_hash text NOT NULL
);
CREATE INDEX IF NOT EXISTS squad_snapshots_team_idx ON squad_snapshots(team_id,captured_at DESC);
-- Verified transfer events as reported by /transfers; identical reports are stored once.
CREATE TABLE IF NOT EXISTS transfer_observations (
    observation_id bigserial PRIMARY KEY,
    player_id integer NOT NULL, -- API-Football player id
    player_name text,
    transfer_date date,
    transfer_type text,
    team_in integer,
    team_out integer,
    source text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    captured_at timestamptz NOT NULL,
    content_hash text NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS transfer_observations_player_idx ON transfer_observations(player_id,transfer_date);
-- One row per /transfers?team= request, so unchanged squads are not re-fetched.
CREATE TABLE IF NOT EXISTS transfer_fetches (
    team_id integer NOT NULL,
    fetched_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    records integer NOT NULL
);
CREATE INDEX IF NOT EXISTS transfer_fetches_team_idx ON transfer_fetches(team_id,fetched_at DESC);
CREATE OR REPLACE FUNCTION guard_squad_transfer_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'Squad and transfer evidence is append only';
    END IF;
    IF TG_TABLE_NAME IN ('squad_snapshots','transfer_observations') THEN
        NEW.created_at := clock_timestamp();
    END IF;
    RETURN NEW;
END;
$$;
DO $$ DECLARE t text; BEGIN
    FOREACH t IN ARRAY ARRAY['squad_snapshots','transfer_observations','transfer_fetches'] LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS squad_transfer_guard ON %I',t);
        EXECUTE format('CREATE TRIGGER squad_transfer_guard BEFORE INSERT OR UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION guard_squad_transfer_evidence()',t);
        EXECUTE format('DROP TRIGGER IF EXISTS squad_transfer_truncate_guard ON %I',t);
        EXECUTE format('CREATE TRIGGER squad_transfer_truncate_guard BEFORE TRUNCATE ON %I FOR EACH STATEMENT EXECUTE FUNCTION guard_squad_transfer_evidence()',t);
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',t);
    END LOOP;
END; $$;
-- Rating components for each daily player capture (NULL for captures before 2026-09-27):
-- rolling stat percentile, the window's minutes-weighted club rank, the rolling club-scaled
-- rating, and the same formula with club strength fixed at 1000 (club-neutral).
ALTER TABLE player_rating_history ADD COLUMN IF NOT EXISTS stat_percentile double precision;
ALTER TABLE player_rating_history ADD COLUMN IF NOT EXISTS window_club_rank double precision;
ALTER TABLE player_rating_history ADD COLUMN IF NOT EXISTS window_rating numeric(4,1);
ALTER TABLE player_rating_history ADD COLUMN IF NOT EXISTS neutral_rating numeric(4,1);

-- Fantasy Premier League evidence for future fantasy-model validation. Requires model_versions.
-- Additive and repeatable; nothing existing is modified. No fantasy model reads these tables yet.
-- Source licensing: README "Fantasy Premier League evidence". Capture is off unless FPL_CAPTURE_ENABLED.
-- Seasons are keyed by start year, as API-Football (2026 = 2026/27). FPL ids are per season.

-- Gameweek deadlines as observed. A moved deadline appends a row; the old one stays.
CREATE TABLE IF NOT EXISTS fpl_gameweeks (
    season integer NOT NULL,
    event_id integer NOT NULL,                  -- FPL gameweek number
    name text,
    deadline timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    first_captured_at timestamptz NOT NULL,
    PRIMARY KEY (season, event_id, deadline)
);
-- Pre-deadline source state: one header per distinct state of the next gameweek's inputs.
CREATE TABLE IF NOT EXISTS fpl_captures (
    capture_id bigserial PRIMARY KEY,
    season integer NOT NULL,
    event_id integer NOT NULL,                  -- next gameweek whose deadline had not passed
    source text NOT NULL CHECK(source IN ('prospective','late_observation')),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    captured_at timestamptz NOT NULL,
    effective_at timestamptz NOT NULL,          -- that gameweek's deadline as observed
    seconds_to_deadline double precision NOT NULL,
    fixtures jsonb NOT NULL CHECK(jsonb_typeof(fixtures)='array'),  -- schedule known at capture
    player_count integer NOT NULL,
    content_hash text NOT NULL,
    CHECK(source <> 'prospective' OR (captured_at < effective_at AND created_at < effective_at))
);
CREATE INDEX IF NOT EXISTS fpl_captures_event_idx ON fpl_captures(season,event_id,captured_at DESC);
CREATE TABLE IF NOT EXISTS fpl_player_states (
    capture_id bigint NOT NULL REFERENCES fpl_captures(capture_id) ON DELETE RESTRICT,
    fpl_player_id integer NOT NULL,             -- FPL element id (this season only)
    fpl_code integer,                           -- FPL player code (stable across seasons)
    web_name text,
    fpl_team_id integer,
    element_type smallint,
    position text,                              -- FPL's own short label for element_type
    price_tenths integer,                       -- now_cost: 55 = 5.5m
    status text,                                -- FPL code as given (a, d, i, s, u, n)
    chance_this_round smallint,
    chance_next_round smallint,
    news text,
    news_added timestamptz,
    PRIMARY KEY (capture_id, fpl_player_id)
);
-- FPL team/player -> API-Football id. A changed mapping appends a row; unmatched stays NULL.
CREATE TABLE IF NOT EXISTS fpl_id_map (
    map_id bigserial PRIMARY KEY,
    kind text NOT NULL CHECK(kind IN ('team','player')),
    season integer NOT NULL,
    fpl_id integer NOT NULL,
    fpl_code integer,
    api_id integer,
    method text NOT NULL,
    detail jsonb NOT NULL CHECK(jsonb_typeof(detail)='object'),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    captured_at timestamptz NOT NULL,
    content_hash text NOT NULL,
    CHECK((api_id IS NULL) = (method IN ('unmatched','ambiguous')))
);
CREATE INDEX IF NOT EXISTS fpl_id_map_idx ON fpl_id_map(kind,season,fpl_id,captured_at DESC);
-- Actual points as observed after a gameweek. Bonus/correction changes append a new state.
CREATE TABLE IF NOT EXISTS fpl_result_captures (
    result_capture_id bigserial PRIMARY KEY,
    season integer NOT NULL,
    event_id integer NOT NULL,
    finished boolean NOT NULL,
    data_checked boolean NOT NULL,              -- FPL marks the gameweek's points final
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    captured_at timestamptz NOT NULL,
    player_count integer NOT NULL,
    content_hash text NOT NULL
);
CREATE INDEX IF NOT EXISTS fpl_result_captures_event_idx ON fpl_result_captures(season,event_id,captured_at DESC);
CREATE TABLE IF NOT EXISTS fpl_player_results (
    result_capture_id bigint NOT NULL REFERENCES fpl_result_captures(result_capture_id) ON DELETE RESTRICT,
    fpl_player_id integer NOT NULL,
    total_points integer NOT NULL,
    minutes integer,
    stats jsonb NOT NULL CHECK(jsonb_typeof(stats)='object'),
    explain jsonb NOT NULL CHECK(jsonb_typeof(explain)='array'),  -- per fixture (double gameweeks)
    PRIMARY KEY (result_capture_id, fpl_player_id)
);
-- Fantasy model outputs. No model writes here yet; see thecornerfc.fpl.make_prediction_snapshot.
CREATE TABLE IF NOT EXISTS fantasy_prediction_snapshots (
    snapshot_id bigserial PRIMARY KEY,
    season integer NOT NULL,
    event_id integer NOT NULL,
    model_version_id text NOT NULL REFERENCES model_versions(model_version_id) ON DELETE RESTRICT,
    input_capture_id bigint REFERENCES fpl_captures(capture_id) ON DELETE RESTRICT,
    source text NOT NULL CHECK(source IN ('prospective','reconstruction','late_observation')),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    captured_at timestamptz NOT NULL,
    effective_at timestamptz NOT NULL,          -- deadline
    seconds_to_deadline double precision NOT NULL,
    predictions jsonb NOT NULL CHECK(jsonb_typeof(predictions)='array'),
    inputs jsonb NOT NULL CHECK(jsonb_typeof(inputs)='object'),
    content_hash text NOT NULL,
    CHECK(source <> 'prospective' OR (input_capture_id IS NOT NULL
          AND captured_at < effective_at AND created_at < effective_at)),
    UNIQUE(season,event_id,model_version_id,source,content_hash)
);
CREATE INDEX IF NOT EXISTS fantasy_snapshots_event_idx ON fantasy_prediction_snapshots(season,event_id,captured_at);
CREATE OR REPLACE FUNCTION guard_fpl_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE input record;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'Fantasy evidence is append only';
    END IF;
    IF TG_TABLE_NAME IN ('fpl_player_states','fpl_player_results') THEN
        RETURN NEW;
    END IF;
    NEW.created_at := clock_timestamp();
    -- Nested: PL/pgSQL does not short-circuit AND, and only some guarded tables have source.
    IF TG_TABLE_NAME = 'fpl_captures' THEN
        IF NEW.source = 'prospective'
           AND (NEW.captured_at >= NEW.effective_at OR NEW.created_at >= NEW.effective_at) THEN
            NEW.source := 'late_observation';
        END IF;
    END IF;
    IF TG_TABLE_NAME = 'fantasy_prediction_snapshots' THEN
        IF NOT EXISTS (SELECT 1 FROM model_versions WHERE model_version_id=NEW.model_version_id AND model_type='fantasy') THEN
            RAISE EXCEPTION 'Fantasy predictions require a fantasy model version';
        END IF;
        IF NEW.input_capture_id IS NOT NULL THEN
            SELECT season, event_id, captured_at INTO input FROM fpl_captures WHERE capture_id=NEW.input_capture_id;
            IF input.season <> NEW.season OR input.event_id <> NEW.event_id THEN
                RAISE EXCEPTION 'Input capture is for a different gameweek';
            END IF;
            IF input.captured_at > NEW.captured_at THEN
                RAISE EXCEPTION 'Input capture was observed after the prediction';
            END IF;
        END IF;
        IF NEW.source = 'prospective' AND (NEW.captured_at >= NEW.effective_at OR NEW.created_at >= NEW.effective_at) THEN
            NEW.source := 'late_observation';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
DO $$ DECLARE t text; BEGIN
    FOREACH t IN ARRAY ARRAY['fpl_gameweeks','fpl_captures','fpl_player_states','fpl_id_map',
                             'fpl_result_captures','fpl_player_results','fantasy_prediction_snapshots'] LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS fpl_evidence_guard ON %I',t);
        EXECUTE format('CREATE TRIGGER fpl_evidence_guard BEFORE INSERT OR UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION guard_fpl_evidence()',t);
        EXECUTE format('DROP TRIGGER IF EXISTS fpl_evidence_truncate_guard ON %I',t);
        EXECUTE format('CREATE TRIGGER fpl_evidence_truncate_guard BEFORE TRUNCATE ON %I FOR EACH STATEMENT EXECUTE FUNCTION guard_fpl_evidence()',t);
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',t);
    END LOOP;
END; $$;
-- Latest observed deadline per gameweek, and latest mapping per FPL id.
CREATE OR REPLACE VIEW fpl_gameweek_deadlines AS
SELECT DISTINCT ON (season,event_id) season, event_id, name, deadline, first_captured_at
FROM fpl_gameweeks ORDER BY season, event_id, first_captured_at DESC, deadline DESC;
CREATE OR REPLACE VIEW fpl_id_map_current AS
SELECT DISTINCT ON (kind,season,fpl_id) kind, season, fpl_id, fpl_code, api_id, method, detail, captured_at
FROM fpl_id_map ORDER BY kind, season, fpl_id, captured_at DESC, map_id DESC;
REVOKE ALL ON fpl_gameweek_deadlines,fpl_id_map_current FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('REVOKE ALL ON fpl_gameweek_deadlines,fpl_id_map_current FROM %I',r);
        END IF;
    END LOOP;
END; $$;
-- Fantasy model output per team-fixture, keyed by API-Football ids (no FPL data needed). Requires
-- model_versions. Additive: nothing existing is modified. Written by thecornerfc.fantasy_snapshots.
-- fantasy_prediction_snapshots (FPL ids, per gameweek) stays for when FPL capture is licensed.
CREATE TABLE IF NOT EXISTS fantasy_fixture_snapshots (
    snapshot_id bigserial PRIMARY KEY,
    fixture_id integer NOT NULL,
    team_id integer NOT NULL,
    model_version_id text NOT NULL REFERENCES model_versions(model_version_id) ON DELETE RESTRICT,
    source text NOT NULL CHECK(source IN ('prospective','late_observation')),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    captured_at timestamptz NOT NULL,
    effective_at timestamptz NOT NULL,          -- kickoff
    seconds_to_kickoff double precision NOT NULL,
    predictions jsonb NOT NULL CHECK(jsonb_typeof(predictions)='array'),  -- per player: every component
    inputs jsonb NOT NULL CHECK(jsonb_typeof(inputs)='object'),            -- team goals, availability, benchmarks
    content_hash text NOT NULL,
    CHECK(source <> 'prospective' OR (captured_at < effective_at AND created_at < effective_at)),
    UNIQUE(fixture_id,team_id,model_version_id,source,content_hash)
);
CREATE INDEX IF NOT EXISTS fantasy_fixture_snapshots_idx ON fantasy_fixture_snapshots(fixture_id,team_id,captured_at);
CREATE OR REPLACE FUNCTION guard_fantasy_fixture_snapshot() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'Fantasy snapshots are append only';
    END IF;
    NEW.created_at := clock_timestamp();
    IF NOT EXISTS (SELECT 1 FROM model_versions WHERE model_version_id=NEW.model_version_id AND model_type='fantasy') THEN
        RAISE EXCEPTION 'Fantasy snapshots require a fantasy model version';
    END IF;
    IF NEW.captured_at>=NEW.effective_at OR NEW.created_at>=NEW.effective_at THEN
        NEW.source := 'late_observation';
    END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS fantasy_fixture_snapshot_guard ON fantasy_fixture_snapshots;
CREATE TRIGGER fantasy_fixture_snapshot_guard BEFORE INSERT OR UPDATE OR DELETE ON fantasy_fixture_snapshots
FOR EACH ROW EXECUTE FUNCTION guard_fantasy_fixture_snapshot();
DROP TRIGGER IF EXISTS fantasy_fixture_snapshot_truncate_guard ON fantasy_fixture_snapshots;
CREATE TRIGGER fantasy_fixture_snapshot_truncate_guard BEFORE TRUNCATE ON fantasy_fixture_snapshots
FOR EACH STATEMENT EXECUTE FUNCTION guard_fantasy_fixture_snapshot();
ALTER TABLE fantasy_fixture_snapshots ENABLE ROW LEVEL SECURITY;

-- Additive and repeatable. National team matches from API-Football (config.NATIONAL_TEAM_LEAGUES),
-- for the Nations ranking (nations.py), which adds them to the public results dataset where it
-- doesn't have them yet. Kept apart from fixtures: every club model reads all of fixtures.
-- Team names are stored as sent, since national teams aren't in teams.
CREATE TABLE IF NOT EXISTS national_fixtures (
    fixture_id    integer PRIMARY KEY,
    league_id     integer NOT NULL,
    season        integer NOT NULL,
    tournament    text,               -- API-Football's competition name
    round         text,
    kickoff       timestamptz,
    venue_name    text,
    venue_city    text,
    status_short  text,
    home_team_id  integer NOT NULL,
    away_team_id  integer NOT NULL,
    home_name     text NOT NULL,
    away_name     text NOT NULL,
    home_goals    integer,            -- after extra time, before penalties
    away_goals    integer,
    neutral       boolean,            -- null: not known (nations.py assumes finals are neutral)
    updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS national_fixtures_kickoff ON national_fixtures (kickoff);
ALTER TABLE national_fixtures ENABLE ROW LEVEL SECURITY;
-- Starting XIs, formations and coaches for national_fixtures (ingest.sync_national_lineups), as
-- fixture_lineups and fixture_formations hold them for clubs. Own tables: the club models read
-- every row of those two.
ALTER TABLE national_fixtures ADD COLUMN IF NOT EXISTS players_fetched_at timestamptz;
CREATE TABLE IF NOT EXISTS national_fixture_formations (
    fixture_id  integer NOT NULL,
    team_id     integer NOT NULL,
    formation   text,
    coach_id    integer,              -- the manager on the line-up
    PRIMARY KEY (fixture_id, team_id)
);
CREATE TABLE IF NOT EXISTS national_fixture_lineups (
    fixture_id  integer NOT NULL,
    team_id     integer NOT NULL,
    player_id   integer NOT NULL,
    grid        text,
    role        text,
    PRIMARY KEY (fixture_id, player_id)
);
CREATE INDEX IF NOT EXISTS national_fixture_lineups_player ON national_fixture_lineups (player_id);
ALTER TABLE national_fixture_formations ENABLE ROW LEVEL SECURITY;
ALTER TABLE national_fixture_lineups ENABLE ROW LEVEL SECURITY;
-- Each player's stat line in national_fixtures matches, and the coach's and players' names
-- (ingest.sync_national_lineups). Own table, as fixture_players is for clubs: the player ratings
-- read every row of that one.
ALTER TABLE national_fixture_formations ADD COLUMN IF NOT EXISTS coach_name text;
ALTER TABLE national_fixture_lineups ADD COLUMN IF NOT EXISTS player_name text;
CREATE TABLE IF NOT EXISTS national_fixture_players (LIKE fixture_players INCLUDING DEFAULTS);
ALTER TABLE national_fixture_players ADD COLUMN IF NOT EXISTS player_name text;  -- as sent: not every international is in players
CREATE UNIQUE INDEX IF NOT EXISTS national_fixture_players_key ON national_fixture_players (fixture_id, player_id);
CREATE INDEX IF NOT EXISTS national_fixture_players_team ON national_fixture_players (team_id, fixture_id);
ALTER TABLE national_fixture_players ENABLE ROW LEVEL SECURITY;

-- FPL's penalty order, 1 = first choice (fantasy v1.5; db/migrations/20260930_fpl_penalty_order.sql)
ALTER TABLE fpl_player_states ADD COLUMN IF NOT EXISTS penalties_order smallint;

-- My FPL team locks (db/migrations/20260930_fpl_team_locks.sql)
-- Additive and repeatable. My FPL team page (README: My FPL team; owner's decision 2026-09-30):
-- the owner's "I've made these transfers" locks, written from the public site. The page carries
-- Supabase's public anon key, so anon gets exactly this: read the locks (the plan they record is
-- on the page anyway) and call lock_fpl_transfers / unlock_fpl_transfers, which check a
-- passphrase whose hash only the owner sets (in the SQL editor, see README). After 10 wrong
-- passphrases in an hour an entry is locked out for the rest of that hour.
-- Also closes anon's read of the upcoming_predictions view: views skip RLS, and nothing reads it
-- through the API.
CREATE SCHEMA IF NOT EXISTS extensions;
CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA extensions;
CREATE TABLE IF NOT EXISTS fpl_team_locks (
    entry_id integer NOT NULL,
    season integer NOT NULL,
    event_id integer NOT NULL,
    -- [{out, in, out_name, in_name, sell, buy}]: API-Football ids (negative FPL id if unmatched), tenths
    transfers jsonb NOT NULL CHECK (jsonb_typeof(transfers) = 'array' AND jsonb_array_length(transfers) <= 15),
    locked_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (entry_id, season, event_id)
);
CREATE TABLE IF NOT EXISTS fpl_team_keys (
    entry_id integer PRIMARY KEY,
    key_hash text NOT NULL            -- extensions.crypt(passphrase, extensions.gen_salt('bf'))
);
CREATE TABLE IF NOT EXISTS fpl_team_key_failures (
    entry_id integer NOT NULL,
    failed_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS fpl_team_key_failures_idx ON fpl_team_key_failures (entry_id, failed_at);
ALTER TABLE fpl_team_locks ENABLE ROW LEVEL SECURITY;
ALTER TABLE fpl_team_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE fpl_team_key_failures ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS fpl_team_locks_read ON fpl_team_locks;
CREATE POLICY fpl_team_locks_read ON fpl_team_locks FOR SELECT USING (true);

-- NULL when the passphrase is right, else why not. Wrong ones are counted (the caller returns
-- rather than raising, so the count is kept).
CREATE OR REPLACE FUNCTION fpl_team_key_check(p_entry integer, p_key text) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, extensions, pg_temp AS $$
DECLARE
    h text;
BEGIN
    DELETE FROM fpl_team_key_failures WHERE failed_at < now() - interval '1 day';
    IF (SELECT count(*) FROM fpl_team_key_failures
        WHERE entry_id = p_entry AND failed_at > now() - interval '1 hour') >= 10 THEN
        RETURN 'Too many wrong passphrases: try again in an hour';
    END IF;
    SELECT key_hash INTO h FROM fpl_team_keys WHERE entry_id = p_entry;
    IF h IS NULL THEN
        RETURN 'No passphrase set for this team yet';
    END IF;
    IF p_key IS NOT NULL AND crypt(p_key, h) = h THEN
        RETURN NULL;
    END IF;
    INSERT INTO fpl_team_key_failures (entry_id) VALUES (p_entry);
    RETURN 'Wrong passphrase';
END;
$$;

CREATE OR REPLACE FUNCTION lock_fpl_transfers(p_entry integer, p_season integer, p_event integer,
                                              p_transfers jsonb, p_key text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, extensions, pg_temp AS $$
DECLARE
    why text := fpl_team_key_check(p_entry, p_key);
    stamp timestamptz;
BEGIN
    IF why IS NOT NULL THEN
        RETURN jsonb_build_object('ok', false, 'error', why);
    END IF;
    IF p_season IS NULL OR p_event IS NULL OR p_season NOT BETWEEN 2020 AND 2100 OR p_event NOT BETWEEN 1 AND 38
       OR jsonb_typeof(p_transfers) IS DISTINCT FROM 'array' OR jsonb_array_length(p_transfers) > 15
       OR octet_length(p_transfers::text) > 8000 THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Not a valid lock');
    END IF;
    INSERT INTO fpl_team_locks (entry_id, season, event_id, transfers) VALUES (p_entry, p_season, p_event, p_transfers)
    ON CONFLICT (entry_id, season, event_id) DO UPDATE SET transfers = EXCLUDED.transfers, locked_at = now()
    RETURNING locked_at INTO stamp;
    RETURN jsonb_build_object('ok', true, 'locked_at', stamp);
END;
$$;

CREATE OR REPLACE FUNCTION unlock_fpl_transfers(p_entry integer, p_season integer, p_event integer, p_key text)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, extensions, pg_temp AS $$
DECLARE
    why text := fpl_team_key_check(p_entry, p_key);
BEGIN
    IF why IS NOT NULL THEN
        RETURN jsonb_build_object('ok', false, 'error', why);
    END IF;
    DELETE FROM fpl_team_locks WHERE entry_id = p_entry AND season = p_season AND event_id = p_event;
    RETURN jsonb_build_object('ok', true);
END;
$$;

-- New tables and functions get Supabase's default grants to anon; replace them with the above
REVOKE ALL ON fpl_team_locks, fpl_team_keys, fpl_team_key_failures FROM PUBLIC;
REVOKE ALL ON FUNCTION fpl_team_key_check(integer, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION lock_fpl_transfers(integer, integer, integer, jsonb, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION unlock_fpl_transfers(integer, integer, integer, text) FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('REVOKE ALL ON fpl_team_locks, fpl_team_keys, fpl_team_key_failures FROM %I', r);
            EXECUTE format('GRANT SELECT ON fpl_team_locks TO %I', r);
            EXECUTE format('REVOKE ALL ON FUNCTION fpl_team_key_check(integer, text) FROM %I', r);
            EXECUTE format('GRANT EXECUTE ON FUNCTION lock_fpl_transfers(integer, integer, integer, jsonb, text) TO %I', r);
            EXECUTE format('GRANT EXECUTE ON FUNCTION unlock_fpl_transfers(integer, integer, integer, text) TO %I', r);
            IF to_regclass('upcoming_predictions') IS NOT NULL THEN
                EXECUTE format('REVOKE ALL ON upcoming_predictions FROM %I', r);
            END IF;
        END IF;
    END LOOP;
    IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='local_readonly') THEN
        GRANT SELECT ON fpl_team_locks TO local_readonly;
    END IF;
END; $$;

-- Owner-only FPL data (db/migrations/20261003_fpl_owner_docs.sql)
-- Additive and repeatable. Applied 2026-10-03.
-- FPL data for the owner only (audit/findings.md L3, decision P2 (a), owner's decision 2026-10-02).
-- FPL's terms (cl. 28(d), 29) don't allow its data to be republished, so the FPL predictions
-- (FPL prices, positions, status, gameweeks) and the owner's team are no longer in docs/data. The
-- export and `fpl team` write them here instead, and the site reads them through fpl_owner_data,
-- which checks the same passphrase as the lock-in (fpl_team_key_check: 10 wrong in an hour locks
-- the entry out for the rest of that hour). The lock-ins are read the same way, so anon loses its
-- direct read of fpl_team_locks.
CREATE TABLE IF NOT EXISTS fpl_owner_docs (
    name text PRIMARY KEY CHECK (name IN ('fpl_predictions', 'fpl_team')),
    doc jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE fpl_owner_docs ENABLE ROW LEVEL SECURITY;

-- {ok, docs: {fpl_predictions, fpl_team}, locks: [{season, event_id, transfers, locked_at}]} when
-- the passphrase is right, else {ok: false, error}
CREATE OR REPLACE FUNCTION fpl_owner_data(p_entry integer, p_key text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, extensions, pg_temp AS $$
DECLARE
    why text := fpl_team_key_check(p_entry, p_key);
BEGIN
    IF why IS NOT NULL THEN
        RETURN jsonb_build_object('ok', false, 'error', why);
    END IF;
    RETURN jsonb_build_object('ok', true,
        'docs', coalesce((SELECT jsonb_object_agg(name, doc) FROM fpl_owner_docs), '{}'::jsonb),
        'locks', coalesce((SELECT jsonb_agg(jsonb_build_object('season', season, 'event_id', event_id,
                                                               'transfers', transfers, 'locked_at', locked_at))
                           FROM fpl_team_locks WHERE entry_id = p_entry), '[]'::jsonb));
END;
$$;

REVOKE ALL ON fpl_owner_docs FROM PUBLIC;
REVOKE ALL ON FUNCTION fpl_owner_data(integer, text) FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('REVOKE ALL ON fpl_owner_docs FROM %I', r);
            EXECUTE format('REVOKE ALL ON fpl_team_locks FROM %I', r);
            EXECUTE format('GRANT EXECUTE ON FUNCTION fpl_owner_data(integer, text) TO %I', r);
        END IF;
    END LOOP;
END; $$;
DROP POLICY IF EXISTS fpl_team_locks_read ON fpl_team_locks;

-- Owner-only FPL pages check the sign-in (db/migrations/20261004_fpl_owner_login.sql)
-- Repeatable. Applied 2026-10-04, with the site change that goes with it (the site before it
-- called the passphrase functions this drops).
-- The owner-only FPL pages check who is signed in instead of a passphrase (owner's decision
-- 2026-10-04; README: Accounts, My FPL team). fpl_team_owners holds the email address allowed for
-- an entry; it is set in the SQL editor (README: My FPL team), not here. fpl_owner_data and
-- lock/unlock_fpl_transfers lose their passphrase argument and can be called by signed-in
-- visitors only (authenticated), not with the public key alone, and answer {ok: false} to anyone
-- but the owner. An address only counts once Supabase Auth has confirmed it (Google sign-in, or
-- the emailed link), so signing up with the owner's address doesn't pass without that mailbox.
-- The passphrase functions and tables are dropped. Don't re-run 20260930_fpl_team_locks.sql or
-- 20261003_fpl_owner_docs.sql on their own after this: they would bring the passphrase back.
-- Also in db/schema.sql.
CREATE TABLE IF NOT EXISTS fpl_team_owners (
    entry_id integer PRIMARY KEY,
    email text NOT NULL
);
ALTER TABLE fpl_team_owners ENABLE ROW LEVEL SECURITY;

DROP FUNCTION IF EXISTS fpl_owner_data(integer, text);
DROP FUNCTION IF EXISTS lock_fpl_transfers(integer, integer, integer, jsonb, text);
DROP FUNCTION IF EXISTS unlock_fpl_transfers(integer, integer, integer, text);
DROP FUNCTION IF EXISTS fpl_team_key_check(integer, text);
DROP TABLE IF EXISTS fpl_team_key_failures, fpl_team_keys;

-- NULL when the caller is signed in as the entry's owner, else why not
CREATE OR REPLACE FUNCTION fpl_team_owner_check(p_entry integer) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
    SELECT CASE
        WHEN auth.uid() IS NULL THEN 'Sign in to see this'
        WHEN EXISTS (SELECT 1 FROM auth.users u JOIN fpl_team_owners o ON lower(o.email) = lower(u.email)
                     WHERE u.id = auth.uid() AND o.entry_id = p_entry AND u.email_confirmed_at IS NOT NULL) THEN NULL
        ELSE 'This account isn''t the site owner''s'
    END;
$$;

-- {ok, docs: {fpl_predictions, fpl_team}, locks: [{season, event_id, transfers, locked_at}]} for
-- the owner, else {ok: false, error}
CREATE OR REPLACE FUNCTION fpl_owner_data(p_entry integer) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
    why text := fpl_team_owner_check(p_entry);
BEGIN
    IF why IS NOT NULL THEN
        RETURN jsonb_build_object('ok', false, 'error', why);
    END IF;
    RETURN jsonb_build_object('ok', true,
        'docs', coalesce((SELECT jsonb_object_agg(name, doc) FROM fpl_owner_docs), '{}'::jsonb),
        'locks', coalesce((SELECT jsonb_agg(jsonb_build_object('season', season, 'event_id', event_id,
                                                               'transfers', transfers, 'locked_at', locked_at))
                           FROM fpl_team_locks WHERE entry_id = p_entry), '[]'::jsonb));
END;
$$;

CREATE OR REPLACE FUNCTION lock_fpl_transfers(p_entry integer, p_season integer, p_event integer,
                                              p_transfers jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
    why text := fpl_team_owner_check(p_entry);
    stamp timestamptz;
BEGIN
    IF why IS NOT NULL THEN
        RETURN jsonb_build_object('ok', false, 'error', why);
    END IF;
    IF p_season IS NULL OR p_event IS NULL OR p_season NOT BETWEEN 2020 AND 2100 OR p_event NOT BETWEEN 1 AND 38
       OR jsonb_typeof(p_transfers) IS DISTINCT FROM 'array' OR jsonb_array_length(p_transfers) > 15
       OR octet_length(p_transfers::text) > 8000 THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Not a valid lock');
    END IF;
    INSERT INTO fpl_team_locks (entry_id, season, event_id, transfers) VALUES (p_entry, p_season, p_event, p_transfers)
    ON CONFLICT (entry_id, season, event_id) DO UPDATE SET transfers = EXCLUDED.transfers, locked_at = now()
    RETURNING locked_at INTO stamp;
    RETURN jsonb_build_object('ok', true, 'locked_at', stamp);
END;
$$;

CREATE OR REPLACE FUNCTION unlock_fpl_transfers(p_entry integer, p_season integer, p_event integer)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
    why text := fpl_team_owner_check(p_entry);
BEGIN
    IF why IS NOT NULL THEN
        RETURN jsonb_build_object('ok', false, 'error', why);
    END IF;
    DELETE FROM fpl_team_locks WHERE entry_id = p_entry AND season = p_season AND event_id = p_event;
    RETURN jsonb_build_object('ok', true);
END;
$$;

REVOKE ALL ON fpl_team_owners FROM PUBLIC;
REVOKE ALL ON FUNCTION fpl_team_owner_check(integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION fpl_owner_data(integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION lock_fpl_transfers(integer, integer, integer, jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION unlock_fpl_transfers(integer, integer, integer) FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('REVOKE ALL ON fpl_team_owners FROM %I', r);
            EXECUTE format('REVOKE ALL ON FUNCTION fpl_team_owner_check(integer) FROM %I', r);
            EXECUTE format('REVOKE ALL ON FUNCTION fpl_owner_data(integer) FROM %I', r);
            EXECUTE format('REVOKE ALL ON FUNCTION lock_fpl_transfers(integer, integer, integer, jsonb) FROM %I', r);
            EXECUTE format('REVOKE ALL ON FUNCTION unlock_fpl_transfers(integer, integer, integer) FROM %I', r);
        END IF;
    END LOOP;
    IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
        GRANT EXECUTE ON FUNCTION fpl_owner_data(integer) TO authenticated;
        GRANT EXECUTE ON FUNCTION lock_fpl_transfers(integer, integer, integer, jsonb) TO authenticated;
        GRANT EXECUTE ON FUNCTION unlock_fpl_transfers(integer, integer, integer) TO authenticated;
    END IF;
END; $$;

-- Check afterwards (expect no rows: the public key alone can call nothing):
--   select p.oid::regprocedure from pg_proc p where p.pronamespace='public'::regnamespace
--     and has_function_privilege('anon', p.oid, 'execute');

-- Deleting your own account (db/migrations/20261004_delete_my_account.sql)
-- Additive and repeatable. Applied 2026-10-04.
-- Accounts (README: Accounts): a signed-in visitor can delete their own account from the site's
-- account box. Supabase's API has no call for that with the public key, so this function does it,
-- for the caller only: auth.uid() comes from their sign-in token and is null for anyone else, so
-- nothing is deleted. Removing the auth.users row removes their sign-in identities and sessions
-- with it. Also in db/schema.sql.
CREATE OR REPLACE FUNCTION delete_my_account() RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = '' AS $$
    DELETE FROM auth.users WHERE id = (SELECT auth.uid());
$$;

REVOKE ALL ON FUNCTION delete_my_account() FROM PUBLIC;
DO $$ BEGIN
    IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
        REVOKE ALL ON FUNCTION delete_my_account() FROM anon;
    END IF;
    IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
        GRANT EXECUTE ON FUNCTION delete_my_account() TO authenticated;
    END IF;
END; $$;

-- Check afterwards (expect one row: authenticated):
--   select grantee from information_schema.routine_privileges
--    where routine_schema='public' and routine_name='delete_my_account' and grantee in ('anon','authenticated','PUBLIC');

-- Trigger functions: fixed search_path (db/migrations/20261004_guard_search_path.sql)

-- Repeatable. Applied 2026-10-04.
-- Supabase's Security Advisor warns that the eight trigger functions behind the append-only
-- tables have no fixed search_path ("Function Search Path Mutable"). They read only tables in
-- public, so pinning the path changes nothing they do; it stops a same-named object in another
-- schema being picked up instead. Also in db/schema.sql.
ALTER FUNCTION prevent_model_version_mutation() SET search_path = public, pg_temp;
ALTER FUNCTION guard_match_snapshot()           SET search_path = public, pg_temp;
ALTER FUNCTION guard_lineup_snapshot()          SET search_path = public, pg_temp;
ALTER FUNCTION guard_paper_evidence()           SET search_path = public, pg_temp;
ALTER FUNCTION guard_player_history()           SET search_path = public, pg_temp;
ALTER FUNCTION guard_squad_transfer_evidence()  SET search_path = public, pg_temp;
ALTER FUNCTION guard_fpl_evidence()             SET search_path = public, pg_temp;
ALTER FUNCTION guard_fantasy_fixture_snapshot() SET search_path = public, pg_temp;

-- Check afterwards (expect no rows):
--   select p.proname from pg_proc p where p.pronamespace='public'::regnamespace
--     and (p.proname like 'guard\_%' or p.proname = 'prevent_model_version_mutation')
--     and not exists (select 1 from unnest(coalesce(p.proconfig, '{}')) c where c like 'search_path=%');

-- The site's data in the database (db/migrations/20261004_site_docs.sql)

-- Additive and repeatable. Applied 2026-10-04.
-- The site's data in the database (audit/db-api-plan.md; owner's go-ahead 2026-10-04). Step 1 of
-- the move away from docs/data: every file the export publishes is also kept here, one row per
-- file, keyed by its path without ".json" ('matches', 'clubs/42'). The export writes the rows
-- (export.mirror_site_docs); nothing on the site reads them yet.
--   site.docs    in its own schema, which the Data API doesn't expose: no key can reach the table.
--   site_doc()   the only way in. Fixed SQL, one row by primary key, 3 second limit.
--   paid         rows marked paid are never returned by site_doc. A later migration adds the
--                subscriber check; until then nothing is marked paid.
-- Also in db/schema.sql.
CREATE SCHEMA IF NOT EXISTS site;
REVOKE ALL ON SCHEMA site FROM PUBLIC;

CREATE TABLE IF NOT EXISTS site.docs (
    key text PRIMARY KEY CHECK (key ~ '^[a-z_]+(/[0-9]+)?$'),
    body jsonb NOT NULL,
    sha256 text NOT NULL,                       -- of the published file: unchanged rows aren't rewritten
    paid boolean NOT NULL DEFAULT false,
    updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE site.docs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON site.docs FROM PUBLIC;

CREATE OR REPLACE FUNCTION public.site_doc(p_key text) RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' SET statement_timeout = '3s' AS $$
    SELECT body FROM site.docs WHERE key = p_key AND NOT paid;
$$;

REVOKE ALL ON FUNCTION public.site_doc(text) FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('REVOKE ALL ON SCHEMA site FROM %I', r);
            EXECUTE format('REVOKE ALL ON site.docs FROM %I', r);
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.site_doc(text) TO %I', r);
        END IF;
    END LOOP;
END; $$;

-- Check afterwards:
--   select has_schema_privilege('anon', 'site', 'usage'), has_table_privilege('anon', 'site.docs', 'select');   -- f, f
--   select count(*), pg_size_pretty(pg_total_relation_size('site.docs')) from site.docs;    -- after the next export: about 9,700 rows
--   select jsonb_typeof(public.site_doc('rankings'));                                       -- object

-- Repeatable. Applied 2026-10-05.
-- Step 3 of the move away from docs/data (audit/db-api-plan.md): the site reads its data through
-- site_doc(). A file on GitHub Pages is kept by the browser for as long as its content hash stands
-- (data/manifest.json); a database row needs the same, or every visit downloads everything again.
--   p_v          the 16-character content hash the site has for the row (from the 'manifest' row).
--                When it is the row's hash the answer may be kept for a year: the address changes
--                when the content does. Without it, or with a stale one, the answer is not kept.
--   site_doc()   still the only way in, still one row by primary key, still never a paid row.
-- The one-argument function is replaced, not kept: two functions that both answer
-- site_doc(p_key) would make the call ambiguous.
-- Also in db/schema.sql.
BEGIN;

DROP FUNCTION IF EXISTS public.site_doc(text);

CREATE OR REPLACE FUNCTION public.site_doc(p_key text, p_v text DEFAULT NULL) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' SET statement_timeout = '3s' AS $$
DECLARE
    doc record;
BEGIN
    SELECT body, sha256 INTO doc FROM site.docs WHERE key = p_key AND NOT paid;
    PERFORM pg_catalog.set_config('response.headers',
        CASE WHEN doc.sha256 IS NOT NULL AND p_v = pg_catalog.left(doc.sha256, 16)
             THEN '[{"Cache-Control": "public, max-age=31536000, immutable"}]'
             ELSE '[{"Cache-Control": "no-cache"}]' END, true);
    RETURN doc.body;
END; $$;

REVOKE ALL ON FUNCTION public.site_doc(text, text) FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.site_doc(text, text) TO %I', r);
        END IF;
    END LOOP;
END; $$;

COMMIT;

-- Check afterwards:
--   select jsonb_typeof(public.site_doc('rankings'));                                        -- object
--   select jsonb_typeof(public.site_doc('rankings', left(sha256, 16))) from site.docs where key = 'rankings';   -- object
--   select has_table_privilege('anon', 'site.docs', 'select');                               -- f

-- Repeatable. Applied 2026-10-05.
-- site_doc() was slow on the big rows: 2 to 4 seconds for 'players' (5 MB) and over the anon
-- role's 3 second limit for 'lineups_history' (8 MB), more so with several readers at once
-- (measured 2026-10-05, the day the site started reading the table). The time went on rebuilding
-- the JSON on every read: the row was stored as jsonb, turned back into text, wrapped by the
-- Data API and unwrapped again. Now nothing is rebuilt:
--   body         is json, not jsonb: the published file's own text, stored and returned as it is.
--                Nothing queries inside it, which is all jsonb was for.
--   site_doc()   returns the "application/json" domain, which tells the Data API (PostgREST 12+)
--                that the value is already the response body. A key with no row answers null,
--                as before.
-- Also in db/schema.sql.
BEGIN;

ALTER TABLE site.docs ALTER COLUMN body TYPE json USING body::json;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_type t JOIN pg_catalog.pg_namespace n ON n.oid = t.typnamespace
                   WHERE n.nspname = 'public' AND t.typname = 'application/json') THEN
        CREATE DOMAIN public."application/json" AS json;
    END IF;
END; $$;

DROP FUNCTION IF EXISTS public.site_doc(text, text);     -- the return type changes, so it can't be replaced in place

CREATE FUNCTION public.site_doc(p_key text, p_v text DEFAULT NULL) RETURNS public."application/json"
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    doc record;
BEGIN
    SELECT body, sha256 INTO doc FROM site.docs WHERE key = p_key AND NOT paid;
    PERFORM pg_catalog.set_config('response.headers',
        CASE WHEN doc.sha256 IS NOT NULL AND p_v = pg_catalog.left(doc.sha256, 16)
             THEN '[{"Cache-Control": "public, max-age=31536000, immutable"}]'
             ELSE '[{"Cache-Control": "no-cache"}]' END, true);
    RETURN coalesce(doc.body, 'null'::json);
END; $$;

REVOKE ALL ON FUNCTION public.site_doc(text, text) FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.site_doc(text, text) TO %I', r);
        END IF;
    END LOOP;
END; $$;

COMMIT;

NOTIFY pgrst, 'reload schema';      -- the Data API picks up the new return type straight away

-- Check afterwards:
--   select pg_typeof(body) from site.docs limit 1;                                           -- json
--   select left(public.site_doc('manifest')::text, 20), public.site_doc('nothing_here')::text;   -- {"files": ...   null
--   select has_table_privilege('anon', 'site.docs', 'select');                               -- f
-- To go back: run db/migrations/20261005_site_doc_cache.sql again after
--   DROP FUNCTION public.site_doc(text, text);   (the column can stay json)

-- Repeatable. Applied 2026-10-05.
-- A match's line-ups, asked for when its card is opened (owner, 2026-10-05: a page gets the data
-- it shows, when it shows it). Until now the export worked out every match's line-ups ahead of
-- time (2.7 MB inside players.json, then 7,000 one-match files for a few hours). They are already
-- in the database, so the site asks for one match's:
--   site_lineups(fixture)   {"id", "xi", "actual", "prematch"}, each {team: [[player, name, role, rank], ...]}
--                           or null. xi: the predicted XI. actual: the XI that started, for a
--                           finished match from the last 21 days (export.PAST_DAYS), each player
--                           with his rank going into it. prematch: the XI the model predicted
--                           before the team sheet was first seen. The same rows, rules and order
--                           the export used (export_players before this), nothing more.
-- Fixed SQL, one match by its id, definer's rights with an empty search path; the tables
-- themselves stay closed to the public key. The answer is not kept by the browser: a line-up
-- can change before kick-off.
-- fixture_player_ranks had no index (it is truncated and copied every night); one is added so
-- a match's ranks are a lookup, not a scan of 945,000 rows.
-- Needs public."application/json" (20261005_site_doc_raw.sql). Also in db/schema.sql.
BEGIN;

CREATE INDEX IF NOT EXISTS fixture_player_ranks_fixture_idx ON public.fixture_player_ranks (fixture_id, player_id);

CREATE OR REPLACE FUNCTION public.site_lineups(p_fixture integer) RETURNS public."application/json"
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-cache"}]', true);
    RETURN (
        SELECT pg_catalog.json_build_object(
            'id', p_fixture,
            -- the predicted XI, in team-sheet order: keeper, defence right to left, midfield, attack
            'xi', (SELECT pg_catalog.json_object_agg(t.team_id, t.players) FROM (
                       SELECT pl.team_id, pg_catalog.json_agg(
                                  pg_catalog.json_build_array(pl.player_id, p.name, pl.position, pl.player_rank::float8)
                                  ORDER BY coalesce(pg_catalog.array_position(roles.sheet, pl.position), 99),
                                           coalesce(pl.player_rank, 0) DESC, pl.player_id) AS players
                       FROM public.predicted_lineups pl JOIN public.players p USING (player_id)
                       WHERE pl.fixture_id = p_fixture GROUP BY pl.team_id) t),
            -- the XI that started a finished match on the site, each player with his rank going into it
            'actual', (SELECT pg_catalog.json_object_agg(t.team_id, t.players) FROM (
                       SELECT x.team_id, pg_catalog.json_agg(
                                  pg_catalog.json_build_array(x.player_id, p.name, x.role, coalesce(r.player_rank, p.current_rank)::float8)
                                  ORDER BY coalesce(pg_catalog.array_position(roles.sheet, x.role), 99),
                                           coalesce(r.player_rank, p.current_rank, 0) DESC, x.player_id) AS players
                       FROM (SELECT DISTINCT ON (s.team_id, s.player_id) s.team_id, s.player_id, s.role
                             FROM (SELECT fp.team_id, fp.player_id,
                                          coalesce(fp.role, CASE fp.position WHEN 'G' THEN 'GK' WHEN 'D' THEN 'CB'
                                                                             WHEN 'M' THEN 'CM' WHEN 'F' THEN 'ST' END) AS role, 1 AS src
                                   FROM public.fixture_players fp WHERE fp.fixture_id = p_fixture AND fp.started
                                   UNION ALL
                                   SELECT fl.team_id, fl.player_id, fl.role, 2 FROM public.fixture_lineups fl WHERE fl.fixture_id = p_fixture) s
                             ORDER BY s.team_id, s.player_id, s.src) x
                       JOIN public.fixtures f ON f.fixture_id = p_fixture
                       JOIN public.players p ON p.player_id = x.player_id
                       LEFT JOIN public.fixture_player_ranks r ON r.fixture_id = p_fixture AND r.player_id = x.player_id
                       WHERE f.status_short IN ('FT', 'AET', 'PEN') AND f.kickoff > pg_catalog.now() - interval '21 days'
                       GROUP BY x.team_id) t),
            -- the XI the model predicted for it: its last capture before the team sheet was first seen
            'prematch', (SELECT pg_catalog.json_object_agg(t.team_id, t.players) FROM (
                       SELECT s.team_id, (SELECT pg_catalog.json_agg(pg_catalog.json_build_array(
                                                     (e.v->>'player')::int, coalesce(n.name, ''), e.v->>'role', (e.v->>'player_rating')::float8)
                                                 ORDER BY e.i)
                                          FROM pg_catalog.jsonb_array_elements(s.players) WITH ORDINALITY e(v, i)
                                          LEFT JOIN public.players n ON n.player_id = (e.v->>'player')::int
                                          WHERE (e.v->>'predicted_starter')::boolean) AS players
                       FROM (SELECT DISTINCT ON (s.team_id) s.team_id, s.players
                             FROM public.lineup_prediction_snapshots s JOIN public.fixtures f ON f.fixture_id = s.fixture_id
                             WHERE s.fixture_id = p_fixture AND s.source = 'prospective'
                               AND f.status_short IN ('FT', 'AET', 'PEN') AND f.kickoff > pg_catalog.now() - interval '21 days'
                               AND s.captured_at < coalesce((SELECT min(o.captured_at) FROM public.official_lineup_snapshots o
                                                             WHERE o.fixture_id = s.fixture_id AND o.team_id = s.team_id
                                                               AND o.effective_at = s.effective_at), 'infinity'::timestamptz)
                             ORDER BY s.team_id, s.captured_at DESC, s.snapshot_id DESC) s) t
                       WHERE t.players IS NOT NULL))
        FROM (SELECT ARRAY['GK','RB','RWB','CB','LB','LWB','DM','CM','RM','LM','AM','RW','LW','ST'] AS sheet) roles
    );
END; $$;

REVOKE ALL ON FUNCTION public.site_lineups(integer) FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.site_lineups(integer) TO %I', r);
        END IF;
    END LOOP;
END; $$;

COMMIT;

NOTIFY pgrst, 'reload schema';

-- Check afterwards:
--   select left(public.site_lineups((select fixture_id from predicted_lineups limit 1))::text, 120);   -- {"id" : ..., "xi" : {...
--   select public.site_lineups(1)::text;                                                                -- every part null
--   select has_table_privilege('anon', 'public.predicted_lineups', 'select');                           -- f

-- Repeatable. Applied 2026-10-05. The function was replaced the same day by
-- 20261005_site_lineup_history_fast.sql: this version read every row on every request.
-- The Line-up record's reconstructed history, asked for as it is shown (owner, 2026-10-05: a page
-- gets the data it shows). Until now the site downloaded every scored line-up (63,000 rows,
-- 6.5 MB) and added them up in the browser to show four totals, a few tables and 50 rows.
--   site.lineup_history    one row per team line-up, scored by the export in Python
--                          (export.export_lineup_history; rewritten whole on each run). In the
--                          site schema, which the Data API doesn't expose.
--   site_lineup_history()  the totals, tables and the newest p_limit rows for a range (p_days:
--                          the last so many days, null for all) and competitions (p_leagues, null
--                          for all), with the names of the clubs and players in them and no
--                          others. The same sums the browser did, so the tab reads the same.
-- Fixed SQL, definer's rights with an empty search path, at most 1,000 rows listed.
-- Needs public."application/json" (20261005_site_doc_raw.sql). Also in db/schema.sql.
BEGIN;

CREATE TABLE IF NOT EXISTS site.lineup_history (
    fixture_id integer NOT NULL,
    team_id integer NOT NULL,
    kickoff timestamptz NOT NULL,
    day date NOT NULL,                       -- the match date, as the tab shows it
    league_id integer,
    opponent_id integer,
    home boolean NOT NULL,
    correct smallint NOT NULL,               -- starters the predicted XI named
    roles_right smallint NOT NULL,           -- of them, put where they played
    roles_known smallint NOT NULL,           -- of them, with both positions known
    lines smallint[] NOT NULL,               -- [starters, of them named] for GK, DEF, MID, FWD
    missed integer[] NOT NULL,               -- starters it left out
    wrong integer[] NOT NULL,                -- players it picked instead
    PRIMARY KEY (fixture_id, team_id)
);
ALTER TABLE site.lineup_history ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON site.lineup_history FROM PUBLIC;

CREATE OR REPLACE FUNCTION public.site_lineup_history(p_days integer DEFAULT NULL, p_leagues integer[] DEFAULT NULL,
                                                      p_limit integer DEFAULT 50) RETURNS public."application/json"
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-cache"}]', true);
    RETURN (
        WITH h AS (SELECT * FROM site.lineup_history),
        -- the chosen range, before the competition menu (the menu's counts come from this)
        scope AS (SELECT * FROM h WHERE p_days IS NULL
                     OR h.day::timestamp + interval '12 hours' >= (pg_catalog.now() AT TIME ZONE 'UTC') - pg_catalog.make_interval(days => p_days)),
        -- pos: a line-up's place oldest first, so clubs and competitions that tie stay in the order they first appear
        list AS (SELECT scope.*, pg_catalog.row_number() OVER (ORDER BY scope.kickoff, scope.fixture_id, scope.team_id) AS pos
                 FROM scope WHERE p_leagues IS NULL OR scope.league_id = ANY (p_leagues)),
        t AS (SELECT count(*) AS n, coalesce(sum(correct), 0) AS correct, count(*) FILTER (WHERE correct = 11) AS perfect,
                     coalesce(sum(roles_right), 0) AS roles_right, coalesce(sum(roles_known), 0) AS roles_known,
                     count(DISTINCT fixture_id) AS matches, min(day) AS first, max(day) AS last FROM list),
        -- average per day; per week past four weeks, per month past six months
        step AS (SELECT CASE WHEN t.last - t.first > 183 THEN 'month' WHEN t.last - t.first > 28 THEN 'week' ELSE 'day' END AS unit FROM t),
        shown AS (SELECT * FROM list ORDER BY kickoff DESC, fixture_id DESC, team_id DESC
                  LIMIT least(greatest(coalesce(p_limit, 50), 1), 1000)),
        tally AS (SELECT 'missed' AS kind, u.player, l.team_id, l.kickoff, l.fixture_id FROM list l, pg_catalog.unnest(l.missed) u(player)
                  UNION ALL
                  SELECT 'wrong', u.player, l.team_id, l.kickoff, l.fixture_id FROM list l, pg_catalog.unnest(l.wrong) u(player)),
        -- the players it got wrong most often (twice or more), each with the club of his first row: the top
        -- 15 by times, with everyone level with the 15th (the page puts those in name order and cuts)
        often AS (SELECT x.kind, x.player, x.n, x.team_id FROM (
                      SELECT g.kind, g.player, g.n, g.team_id, pg_catalog.rank() OVER (PARTITION BY g.kind ORDER BY g.n DESC) AS place
                      FROM (SELECT kind, player, count(*) AS n,
                                   (pg_catalog.array_agg(team_id ORDER BY kickoff, fixture_id, team_id))[1] AS team_id
                            FROM tally GROUP BY kind, player HAVING count(*) >= 2) g) x
                  WHERE x.place <= 15),
        club AS (SELECT team_id, count(*) AS n, sum(correct) AS correct, count(*) FILTER (WHERE correct = 11) AS perfect, min(pos) AS pos
                 FROM list GROUP BY team_id)
        SELECT pg_catalog.json_build_object(
            'available', true,
            'any', EXISTS (SELECT 1 FROM h),
            'leagues', (SELECT coalesce(pg_catalog.json_agg(x.league_id), '[]'::json) FROM (SELECT DISTINCT league_id FROM h) x),
            'scope', (SELECT coalesce(pg_catalog.json_object_agg(x.league_id, x.n), '{}'::json)
                      FROM (SELECT league_id, count(*) AS n FROM scope GROUP BY league_id) x),
            'total', t.n, 'correct', t.correct, 'perfect', t.perfect, 'roles_right', t.roles_right, 'roles_known', t.roles_known,
            'matches', t.matches, 'first', t.first, 'last', t.last,
            'counts', (SELECT coalesce(pg_catalog.json_object_agg(x.correct, x.n), '{}'::json)
                       FROM (SELECT correct, count(*) AS n FROM list GROUP BY correct) x),
            'step', step.unit,
            'trend', (SELECT coalesce(pg_catalog.json_agg(pg_catalog.json_build_array(x.k, x.n, x.correct, x.perfect) ORDER BY x.k DESC), '[]'::json)
                      FROM (SELECT pg_catalog.date_trunc(step.unit, l.day::timestamp)::date AS k, count(*) AS n, sum(l.correct) AS correct,
                                   count(*) FILTER (WHERE l.correct = 11) AS perfect
                            FROM list l GROUP BY 1) x),
            'lines', (SELECT pg_catalog.json_build_array(sum(lines[1]), sum(lines[2]), sum(lines[3]), sum(lines[4]),
                                                         sum(lines[5]), sum(lines[6]), sum(lines[7]), sum(lines[8])) FROM list),
            'comps', (SELECT coalesce(pg_catalog.json_agg(pg_catalog.json_build_array(x.league_id, x.n, x.correct, x.perfect, x.roles_right, x.roles_known) ORDER BY x.pos), '[]'::json)
                      FROM (SELECT league_id, count(*) AS n, sum(correct) AS correct, count(*) FILTER (WHERE correct = 11) AS perfect,
                                   sum(roles_right) AS roles_right, sum(roles_known) AS roles_known, min(pos) AS pos FROM list GROUP BY league_id) x),
            'clubs', (SELECT coalesce(pg_catalog.json_agg(pg_catalog.json_build_array(c.team_id, c.n, c.correct, c.perfect) ORDER BY c.pos), '[]'::json) FROM club c),
            'missed', (SELECT coalesce(pg_catalog.json_agg(pg_catalog.json_build_array(o.player, o.team_id, o.n) ORDER BY o.n DESC, o.player), '[]'::json)
                       FROM often o WHERE o.kind = 'missed'),
            'wrong', (SELECT coalesce(pg_catalog.json_agg(pg_catalog.json_build_array(o.player, o.team_id, o.n) ORDER BY o.n DESC, o.player), '[]'::json)
                      FROM often o WHERE o.kind = 'wrong'),
            'missed_total', (SELECT coalesce(sum(pg_catalog.cardinality(missed)), 0) FROM list),
            -- the line-ups on screen, newest first: [date, team, opponent, home, competition, right, missed]
            'rows', (SELECT coalesce(pg_catalog.json_agg(pg_catalog.json_build_array(s.day, s.team_id, s.opponent_id, s.home::int, s.league_id, s.correct,
                                                                                    pg_catalog.to_json(s.missed))
                                                         ORDER BY s.kickoff DESC, s.fixture_id DESC, s.team_id DESC), '[]'::json) FROM shown s),
            -- names for the ids above, and no others
            'teams', (SELECT coalesce(pg_catalog.json_object_agg(tm.team_id, tm.name), '{}'::json) FROM public.teams tm
                      WHERE tm.team_id IN (SELECT team_id FROM club UNION SELECT opponent_id FROM shown UNION SELECT team_id FROM often)),
            'players', (SELECT coalesce(pg_catalog.json_object_agg(pp.player_id, pp.name), '{}'::json) FROM public.players pp
                        WHERE pp.player_id IN (SELECT player FROM often UNION SELECT pg_catalog.unnest(missed) FROM shown)))
        FROM t, step
    );
END; $$;

REVOKE ALL ON FUNCTION public.site_lineup_history(integer, integer[], integer) FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('REVOKE ALL ON site.lineup_history FROM %I', r);
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.site_lineup_history(integer, integer[], integer) TO %I', r);
        END IF;
    END LOOP;
END; $$;

COMMIT;

NOTIFY pgrst, 'reload schema';

-- Check afterwards:
--   select has_table_privilege('anon', 'site.lineup_history', 'select');                    -- f
--   select public.site_lineup_history()::json->>'any';                                      -- false until the next export, then true
--   select public.site_lineup_history(30, '{39}', 5)::json->>'total';                       -- after it: Premier League line-ups in the last 30 days

-- Repeatable. Applied 2026-10-05.
-- site_lineup_history() was too slow for the whole history. Measured on 2026-10-05, the evening
-- it went live: about 2 seconds for all 63,369 line-ups against the public key's 3 second limit
-- (filtered views 0.3 to 0.5 seconds), and several at once failed. It read every row for each
-- total, and unpacked 340,000 missed and wrong picks, on every request, for figures that only
-- change when the export runs. Now:
--   site.lineup_history_teams, _days, _often   the whole history counted once per export: per
--                          competition and club, per competition and match date, and per player
--                          the model got wrong and competition. A few hundred to a few thousand
--                          short rows each.
--   site.lineup_history_refresh()   fills them from site.lineup_history. The export calls it after
--                          rewriting that table (export.export_lineup_history); this migration
--                          calls it once, so no export is needed first.
--   site_lineup_history()  same arguments, same answer. The whole history is summed from the
--                          counted tables; a range (a year is under 10,000 line-ups) is counted
--                          from the rows, found by an index on the match date. The rows listed
--                          come by an index, newest first.
-- On a copy of the data the answers were identical to the first version's in fourteen
-- combinations of range, competitions and rows listed, and the whole history took 38 ms where it
-- had taken 592.
-- Needs 20261005_site_lineup_history.sql. Also in db/schema.sql.
BEGIN;

-- counted once per export, so the whole history is read from a few hundred rows, not 63,000
CREATE TABLE IF NOT EXISTS site.lineup_history_teams (      -- per competition and club
    league_id integer, team_id integer NOT NULL,
    n integer NOT NULL, correct integer NOT NULL, perfect integer NOT NULL, roles_right integer NOT NULL, roles_known integer NOT NULL,
    counts integer[] NOT NULL,               -- line-ups by starters named, 0 to 11
    lines integer[] NOT NULL,                -- [starters, of them named] for GK, DEF, MID, FWD, added up
    pos bigint[] NOT NULL                    -- its first line-up: [kick-off in seconds, fixture, team]
);
CREATE TABLE IF NOT EXISTS site.lineup_history_days (       -- per competition and match date
    league_id integer, day date NOT NULL,
    n integer NOT NULL, correct integer NOT NULL, perfect integer NOT NULL, matches integer NOT NULL
);
CREATE TABLE IF NOT EXISTS site.lineup_history_often (      -- per player it got wrong, and competition
    kind text NOT NULL,                      -- 'missed': started but not picked; 'wrong': picked but didn't start
    player integer NOT NULL, league_id integer,
    n integer NOT NULL,
    pos bigint[] NOT NULL                    -- the first line-up it happened in
);
CREATE INDEX IF NOT EXISTS lineup_history_day_idx ON site.lineup_history (day);
CREATE INDEX IF NOT EXISTS lineup_history_newest_idx ON site.lineup_history (kickoff DESC, fixture_id DESC, team_id DESC);

DO $$ DECLARE t text; r text; BEGIN
    FOREACH t IN ARRAY ARRAY['site.lineup_history_teams', 'site.lineup_history_days', 'site.lineup_history_often'] LOOP
        EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('REVOKE ALL ON %s FROM PUBLIC', t);
        FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
            IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
                EXECUTE format('REVOKE ALL ON %s FROM %I', t, r);
            END IF;
        END LOOP;
    END LOOP;
END; $$;

CREATE OR REPLACE FUNCTION site.lineup_history_refresh() RETURNS void
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
    DELETE FROM site.lineup_history_teams;
    INSERT INTO site.lineup_history_teams (league_id, team_id, n, correct, perfect, roles_right, roles_known, counts, lines, pos)
    SELECT h.league_id, h.team_id, count(*), sum(h.correct), count(*) FILTER (WHERE h.correct = 11), sum(h.roles_right), sum(h.roles_known),
           ARRAY[count(*) FILTER (WHERE h.correct = 0), count(*) FILTER (WHERE h.correct = 1), count(*) FILTER (WHERE h.correct = 2),
                 count(*) FILTER (WHERE h.correct = 3), count(*) FILTER (WHERE h.correct = 4), count(*) FILTER (WHERE h.correct = 5),
                 count(*) FILTER (WHERE h.correct = 6), count(*) FILTER (WHERE h.correct = 7), count(*) FILTER (WHERE h.correct = 8),
                 count(*) FILTER (WHERE h.correct = 9), count(*) FILTER (WHERE h.correct = 10), count(*) FILTER (WHERE h.correct = 11)],
           ARRAY[sum(h.lines[1]), sum(h.lines[2]), sum(h.lines[3]), sum(h.lines[4]), sum(h.lines[5]), sum(h.lines[6]), sum(h.lines[7]), sum(h.lines[8])],
           min(ARRAY[pg_catalog.date_part('epoch', h.kickoff)::bigint, h.fixture_id, h.team_id])
    FROM site.lineup_history h GROUP BY h.league_id, h.team_id;
    DELETE FROM site.lineup_history_days;
    INSERT INTO site.lineup_history_days (league_id, day, n, correct, perfect, matches)
    SELECT h.league_id, h.day, count(*), sum(h.correct), count(*) FILTER (WHERE h.correct = 11), count(DISTINCT h.fixture_id)
    FROM site.lineup_history h GROUP BY h.league_id, h.day;
    DELETE FROM site.lineup_history_often;
    INSERT INTO site.lineup_history_often (kind, player, league_id, n, pos)
    SELECT u.kind, u.player, h.league_id, count(*), min(ARRAY[pg_catalog.date_part('epoch', h.kickoff)::bigint, h.fixture_id, h.team_id])
    FROM site.lineup_history h,
         LATERAL (SELECT 'missed' AS kind, pg_catalog.unnest(h.missed) AS player
                  UNION ALL SELECT 'wrong', pg_catalog.unnest(h.wrong)) u
    GROUP BY u.kind, u.player, h.league_id;
    ANALYZE site.lineup_history;
    ANALYZE site.lineup_history_teams;
    ANALYZE site.lineup_history_days;
    ANALYZE site.lineup_history_often;
END; $$;
REVOKE ALL ON FUNCTION site.lineup_history_refresh() FROM PUBLIC;

CREATE OR REPLACE FUNCTION public.site_lineup_history(p_days integer DEFAULT NULL, p_leagues integer[] DEFAULT NULL,
                                                      p_limit integer DEFAULT 50) RETURNS public."application/json"
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-cache"}]', true);
    RETURN (
        WITH since AS (-- the first match date in the range: a match counts from noon on its day
                       SELECT ((pg_catalog.now() AT TIME ZONE 'UTC') - pg_catalog.make_interval(days => p_days) + interval '12 hours'
                               - interval '1 microsecond')::date AS day),
        -- The range's line-ups added up per competition and club, and per competition and match
        -- date: read ready-counted for the whole history, counted from the rows for a range (a
        -- year is under 10,000 of them). Everything below is summed from these, so the whole
        -- history costs no more than a week. pos: a group's first line-up, as an array that sorts
        -- oldest first.
        teams AS (SELECT a.league_id, a.team_id, a.n, a.correct, a.perfect, a.roles_right, a.roles_known, a.counts, a.lines, a.pos
                  FROM site.lineup_history_teams a WHERE p_days IS NULL
                  UNION ALL
                  SELECT h.league_id, h.team_id, count(*)::int, sum(h.correct)::int, (count(*) FILTER (WHERE h.correct = 11))::int,
                         sum(h.roles_right)::int, sum(h.roles_known)::int,
                         ARRAY[count(*) FILTER (WHERE h.correct = 0), count(*) FILTER (WHERE h.correct = 1), count(*) FILTER (WHERE h.correct = 2),
                               count(*) FILTER (WHERE h.correct = 3), count(*) FILTER (WHERE h.correct = 4), count(*) FILTER (WHERE h.correct = 5),
                               count(*) FILTER (WHERE h.correct = 6), count(*) FILTER (WHERE h.correct = 7), count(*) FILTER (WHERE h.correct = 8),
                               count(*) FILTER (WHERE h.correct = 9), count(*) FILTER (WHERE h.correct = 10), count(*) FILTER (WHERE h.correct = 11)]::int[],
                         ARRAY[sum(h.lines[1]), sum(h.lines[2]), sum(h.lines[3]), sum(h.lines[4]), sum(h.lines[5]), sum(h.lines[6]), sum(h.lines[7]), sum(h.lines[8])]::int[],
                         min(ARRAY[pg_catalog.date_part('epoch', h.kickoff)::bigint, h.fixture_id, h.team_id])
                  FROM site.lineup_history h, since WHERE p_days IS NOT NULL AND h.day >= since.day GROUP BY h.league_id, h.team_id),
        days AS (SELECT a.league_id, a.day, a.n, a.correct, a.perfect, a.matches FROM site.lineup_history_days a WHERE p_days IS NULL
                 UNION ALL
                 SELECT h.league_id, h.day, count(*)::int, sum(h.correct)::int, (count(*) FILTER (WHERE h.correct = 11))::int, (count(DISTINCT h.fixture_id))::int
                 FROM site.lineup_history h, since WHERE p_days IS NOT NULL AND h.day >= since.day GROUP BY h.league_id, h.day),
        -- ... and for the chosen competitions (teams itself is the range before the menu, for the menu's counts)
        lt AS (SELECT * FROM teams WHERE p_leagues IS NULL OR teams.league_id = ANY (p_leagues)),
        ld AS (SELECT * FROM days WHERE p_leagues IS NULL OR days.league_id = ANY (p_leagues)),
        t AS (SELECT a.n, a.correct, a.perfect, a.roles_right, a.roles_known, b.matches, b.first, b.last
              FROM (SELECT coalesce(sum(n), 0) AS n, coalesce(sum(correct), 0) AS correct, coalesce(sum(perfect), 0) AS perfect,
                           coalesce(sum(roles_right), 0) AS roles_right, coalesce(sum(roles_known), 0) AS roles_known FROM lt) a,
                   (SELECT coalesce(sum(matches), 0) AS matches, min(day) AS first, max(day) AS last FROM ld) b),
        -- average per day; per week past four weeks, per month past six months
        step AS (SELECT CASE WHEN t.last - t.first > 183 THEN 'month' WHEN t.last - t.first > 28 THEN 'week' ELSE 'day' END AS unit FROM t),
        -- the line-ups listed, newest first
        shown AS (SELECT h.* FROM site.lineup_history h, since
                  WHERE (p_days IS NULL OR h.day >= since.day) AND (p_leagues IS NULL OR h.league_id = ANY (p_leagues))
                  ORDER BY h.kickoff DESC, h.fixture_id DESC, h.team_id DESC
                  LIMIT least(greatest(coalesce(p_limit, 50), 1), 1000)),
        -- the players it got wrong, by competition: ready-counted for the whole history, from the rows for a range
        tally AS (SELECT o.kind, o.player, o.n, o.pos FROM site.lineup_history_often o
                  WHERE p_days IS NULL AND (p_leagues IS NULL OR o.league_id = ANY (p_leagues))
                  UNION ALL
                  SELECT u.kind, u.player, 1, ARRAY[pg_catalog.date_part('epoch', h.kickoff)::bigint, h.fixture_id, h.team_id]
                  FROM site.lineup_history h, since,
                       LATERAL (SELECT 'missed' AS kind, pg_catalog.unnest(h.missed) AS player
                                UNION ALL SELECT 'wrong', pg_catalog.unnest(h.wrong)) u
                  WHERE p_days IS NOT NULL AND h.day >= since.day AND (p_leagues IS NULL OR h.league_id = ANY (p_leagues))),
        -- the ones it got wrong most often (twice or more), each with the club of his first row: the top
        -- 15 by times, with everyone level with the 15th (the page puts those in name order and cuts)
        often AS (SELECT x.kind, x.player, x.n, x.team_id FROM (
                      SELECT g.kind, g.player, g.n, g.team_id, pg_catalog.rank() OVER (PARTITION BY g.kind ORDER BY g.n DESC) AS place
                      FROM (SELECT kind, player, sum(n) AS n, (min(pos))[3]::int AS team_id
                            FROM tally GROUP BY kind, player HAVING sum(n) >= 2) g) x
                  WHERE x.place <= 15),
        club AS (SELECT team_id, sum(n) AS n, sum(correct) AS correct, sum(perfect) AS perfect, min(pos) AS pos FROM lt GROUP BY team_id)
        SELECT pg_catalog.json_build_object(
            'available', true,
            'any', EXISTS (SELECT 1 FROM site.lineup_history),
            'leagues', (SELECT coalesce(pg_catalog.json_agg(x.league_id ORDER BY x.league_id), '[]'::json) FROM (SELECT league_id FROM site.lineup_history_teams GROUP BY league_id) x),
            'scope', (SELECT coalesce(pg_catalog.json_object_agg(x.league_id, x.n), '{}'::json)
                      FROM (SELECT league_id, sum(n) AS n FROM teams GROUP BY league_id) x),
            'total', t.n, 'correct', t.correct, 'perfect', t.perfect, 'roles_right', t.roles_right, 'roles_known', t.roles_known,
            'matches', t.matches, 'first', t.first, 'last', t.last,
            'counts', (SELECT coalesce(pg_catalog.json_object_agg(x.k, x.n), '{}'::json)
                       FROM (SELECT u.i - 1 AS k, sum(u.v) AS n FROM lt, pg_catalog.unnest(lt.counts) WITH ORDINALITY u(v, i)
                             GROUP BY u.i HAVING sum(u.v) > 0) x),
            'step', step.unit,
            'trend', (SELECT coalesce(pg_catalog.json_agg(pg_catalog.json_build_array(x.k, x.n, x.correct, x.perfect) ORDER BY x.k DESC), '[]'::json)
                      FROM (SELECT pg_catalog.date_trunc(step.unit, l.day::timestamp)::date AS k, sum(l.n) AS n, sum(l.correct) AS correct,
                                   sum(l.perfect) AS perfect
                            FROM ld l GROUP BY 1) x),
            'lines', (SELECT coalesce(pg_catalog.json_agg(x.s ORDER BY x.i), '[null,null,null,null,null,null,null,null]'::json)
                      FROM (SELECT u.i, sum(u.v) AS s FROM lt, pg_catalog.unnest(lt.lines) WITH ORDINALITY u(v, i) GROUP BY u.i) x),
            'comps', (SELECT coalesce(pg_catalog.json_agg(pg_catalog.json_build_array(x.league_id, x.n, x.correct, x.perfect, x.roles_right, x.roles_known) ORDER BY x.pos), '[]'::json)
                      FROM (SELECT league_id, sum(n) AS n, sum(correct) AS correct, sum(perfect) AS perfect,
                                   sum(roles_right) AS roles_right, sum(roles_known) AS roles_known, min(pos) AS pos FROM lt GROUP BY league_id) x),
            'clubs', (SELECT coalesce(pg_catalog.json_agg(pg_catalog.json_build_array(c.team_id, c.n, c.correct, c.perfect) ORDER BY c.pos), '[]'::json) FROM club c),
            'missed', (SELECT coalesce(pg_catalog.json_agg(pg_catalog.json_build_array(o.player, o.team_id, o.n) ORDER BY o.n DESC, o.player), '[]'::json)
                       FROM often o WHERE o.kind = 'missed'),
            'wrong', (SELECT coalesce(pg_catalog.json_agg(pg_catalog.json_build_array(o.player, o.team_id, o.n) ORDER BY o.n DESC, o.player), '[]'::json)
                      FROM often o WHERE o.kind = 'wrong'),
            'missed_total', (SELECT coalesce(sum(n), 0) FROM tally WHERE kind = 'missed'),
            -- the line-ups on screen, newest first: [date, team, opponent, home, competition, right, missed]
            'rows', (SELECT coalesce(pg_catalog.json_agg(pg_catalog.json_build_array(s.day, s.team_id, s.opponent_id, s.home::int, s.league_id, s.correct,
                                                                                    pg_catalog.to_json(s.missed))
                                                         ORDER BY s.kickoff DESC, s.fixture_id DESC, s.team_id DESC), '[]'::json) FROM shown s),
            -- names for the ids above, and no others
            'teams', (SELECT coalesce(pg_catalog.json_object_agg(tm.team_id, tm.name), '{}'::json) FROM public.teams tm
                      WHERE tm.team_id IN (SELECT team_id FROM club UNION SELECT opponent_id FROM shown UNION SELECT team_id FROM often)),
            'players', (SELECT coalesce(pg_catalog.json_object_agg(pp.player_id, pp.name), '{}'::json) FROM public.players pp
                        WHERE pp.player_id IN (SELECT player FROM often UNION SELECT pg_catalog.unnest(missed) FROM shown)))
        FROM t, step
    );
END; $$;

REVOKE ALL ON FUNCTION public.site_lineup_history(integer, integer[], integer) FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('REVOKE ALL ON FUNCTION site.lineup_history_refresh() FROM %I', r);
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.site_lineup_history(integer, integer[], integer) TO %I', r);
        END IF;
    END LOOP;
END; $$;

SELECT site.lineup_history_refresh();       -- count what the last export stored

COMMIT;

-- Check afterwards:
--   select (select count(*) from site.lineup_history_teams), (select count(*) from site.lineup_history_days), (select count(*) from site.lineup_history_often);   -- a few hundred, about 15,000, about 37,000
--   select public.site_lineup_history()::json->>'total';                                   -- 63,369 on 2026-10-05
--   select has_table_privilege('anon', 'site.lineup_history_teams', 'select');             -- f

-- Repeatable. Applied 2026-10-05.
-- The matches as rows in the database, not as files (owner, 2026-10-05: convert Matches and the
-- match model detail to tables and queries, with Players to follow). First use: a match's model
-- detail, which was one stored file per match (4,088 of them).
--   site.matches             one row per match on the site: when, who, its competition, the match
--                            as the site draws it (data: an array in the order of the export's
--                            SITE_MATCH_FIELDS), the key reasons its card shows and the full model
--                            detail. Rewritten whole by each export (export.store_matches). In the
--                            site schema, which the Data API doesn't expose.
--   site_match_detail(fixture)   {"id", "why"} for one match on the site (why is null where the
--                            prediction has no breakdown), or null for a match that isn't there.
-- The queries for a day's, a club's and a competition's matches come in a later migration; the
-- indexes they need are here so the table doesn't have to be rebuilt.
-- Needs public."application/json" (20261005_site_doc_raw.sql). Also in db/schema.sql.
BEGIN;

CREATE TABLE IF NOT EXISTS site.matches (
    fixture_id integer PRIMARY KEY,
    kickoff timestamptz NOT NULL,
    league_id integer,
    home_id integer,
    away_id integer,
    status text,
    data json NOT NULL,
    reasons json,
    why json
);
CREATE INDEX IF NOT EXISTS matches_kickoff_idx ON site.matches (kickoff);
CREATE INDEX IF NOT EXISTS matches_league_idx ON site.matches (league_id, kickoff);
CREATE INDEX IF NOT EXISTS matches_home_idx ON site.matches (home_id, kickoff);
CREATE INDEX IF NOT EXISTS matches_away_idx ON site.matches (away_id, kickoff);
ALTER TABLE site.matches ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON site.matches FROM PUBLIC;

CREATE OR REPLACE FUNCTION public.site_match_detail(p_fixture integer) RETURNS public."application/json"
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-cache"}]', true);
    RETURN coalesce((SELECT pg_catalog.json_build_object('id', m.fixture_id, 'why', m.why)
                     FROM site.matches m WHERE m.fixture_id = p_fixture), 'null'::json);
END; $$;

REVOKE ALL ON FUNCTION public.site_match_detail(integer) FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('REVOKE ALL ON site.matches FROM %I', r);
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.site_match_detail(integer) TO %I', r);
        END IF;
    END LOOP;
END; $$;

COMMIT;

NOTIFY pgrst, 'reload schema';

-- Check afterwards:
--   select has_table_privilege('anon', 'site.matches', 'select');        -- f
--   select public.site_match_detail(1)::text;                            -- null (no such match)
--   select count(*), count(why) from site.matches;                       -- after the next export: about 5,200 and 4,100

-- Repeatable. Applied 2026-10-05.
-- The Matches tab and every other view that shows matches ask the database for the ones they
-- show (owner, 2026-10-05), where each downloaded all 5,200 matches across 80 days (1.2 MB) and
-- the key reasons for 4,100 of them.
--   site_matches(from, to, leagues, team, ids)   the matches that fit every argument given: a
--                          day (kick-off from..to, which the page works out from the visitor's
--                          own clock), a competition's (its rounds), a club's (its page), or a
--                          list of ids (the ones Model vs Market lists). {"matches": the rows in
--                          the export's SITE_MATCH_FIELDS order, oldest first, "reasons": {id:
--                          the key reasons its card shows}}. With no argument it returns nothing,
--                          and never more than 2,000 rows.
--   site_match_days(tz)    what the date controls and the competition menu need without any
--                          match: how many matches (postponed ones left out) each competition has
--                          on each day of the visitor's calendar, the competitions with matches,
--                          and the international ones, most matches first. tz is an IANA zone
--                          name ("Europe/London"); one the database doesn't know counts as UTC.
--   site_match_detail(fixture)   as before, now with the name and code of the model version that
--                          made the prediction, which came from the file of every match's reasons.
--   site.matches.intl      whether it is a national team match (the last of SITE_MATCH_FIELDS),
--                          as a column the menu query can count.
-- Needs 20261005_site_matches.sql. Also in db/schema.sql.
BEGIN;

ALTER TABLE site.matches ADD COLUMN IF NOT EXISTS intl boolean NOT NULL DEFAULT false;

CREATE OR REPLACE FUNCTION public.site_matches(p_from timestamptz DEFAULT NULL, p_to timestamptz DEFAULT NULL,
                                               p_leagues integer[] DEFAULT NULL, p_team integer DEFAULT NULL,
                                               p_ids integer[] DEFAULT NULL) RETURNS public."application/json"
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-cache"}]', true);
    RETURN (
        SELECT pg_catalog.json_build_object(
            'matches', coalesce(pg_catalog.json_agg(x.data ORDER BY x.kickoff, x.fixture_id), '[]'::json),
            'reasons', coalesce(pg_catalog.json_object_agg(x.fixture_id, x.reasons) FILTER (WHERE x.reasons IS NOT NULL), '{}'::json))
        FROM (SELECT m.fixture_id, m.kickoff, m.data, m.reasons FROM site.matches m
              WHERE (p_from IS NOT NULL OR p_to IS NOT NULL OR p_leagues IS NOT NULL OR p_team IS NOT NULL OR p_ids IS NOT NULL)
                AND (p_from IS NULL OR m.kickoff >= p_from) AND (p_to IS NULL OR m.kickoff < p_to)
                AND (p_leagues IS NULL OR m.league_id = ANY (p_leagues))
                AND (p_team IS NULL OR m.home_id = p_team OR m.away_id = p_team)
                AND (p_ids IS NULL OR m.fixture_id = ANY (p_ids))
              ORDER BY m.kickoff, m.fixture_id LIMIT 2000) x
    );
END; $$;

CREATE OR REPLACE FUNCTION public.site_match_days(p_tz text DEFAULT 'UTC') RETURNS public."application/json"
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    tz text := coalesce(pg_catalog.left(p_tz, 64), 'UTC');
BEGIN
    BEGIN
        PERFORM pg_catalog.now() AT TIME ZONE tz;
    EXCEPTION WHEN OTHERS THEN
        tz := 'UTC';
    END;
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-cache"}]', true);
    RETURN pg_catalog.json_build_object(
        'days', (SELECT coalesce(pg_catalog.json_agg(pg_catalog.json_build_array(x.day, x.league_id, x.n) ORDER BY x.day, x.league_id), '[]'::json)
                 FROM (SELECT (m.kickoff AT TIME ZONE tz)::date AS day, m.league_id, count(*) AS n
                       FROM site.matches m WHERE m.status IS DISTINCT FROM 'PST' GROUP BY 1, 2) x),
        'leagues', (SELECT coalesce(pg_catalog.json_agg(x.league_id ORDER BY x.league_id), '[]'::json)
                    FROM (SELECT m.league_id FROM site.matches m WHERE m.league_id IS NOT NULL GROUP BY 1) x),
        'intl', (SELECT coalesce(pg_catalog.json_agg(pg_catalog.json_build_array(x.league_id, x.n) ORDER BY x.n DESC, x.league_id), '[]'::json)
                 FROM (SELECT m.league_id, count(*) AS n FROM site.matches m WHERE m.intl GROUP BY 1) x));
END; $$;

CREATE OR REPLACE FUNCTION public.site_match_detail(p_fixture integer) RETURNS public."application/json"
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-cache"}]', true);
    RETURN coalesce((SELECT pg_catalog.json_build_object(
                                'id', m.fixture_id, 'why', m.why,
                                'model', (SELECT pg_catalog.json_build_object('name', v.version_name, 'code', pg_catalog.left(v.code_sha, 7))
                                          FROM public.model_versions v WHERE v.model_version_id = m.why->>'model'))
                     FROM site.matches m WHERE m.fixture_id = p_fixture), 'null'::json);
END; $$;

REVOKE ALL ON FUNCTION public.site_matches(timestamptz, timestamptz, integer[], integer, integer[]) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.site_match_days(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.site_match_detail(integer) FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.site_matches(timestamptz, timestamptz, integer[], integer, integer[]) TO %I', r);
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.site_match_days(text) TO %I', r);
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.site_match_detail(integer) TO %I', r);
        END IF;
    END LOOP;
END; $$;

COMMIT;

NOTIFY pgrst, 'reload schema';

-- Check afterwards:
--   select public.site_matches()::text;                                                     -- {"matches" : [], "reasons" : {}}
--   select json_array_length(public.site_matches(p_leagues => '{39}')::json->'matches');    -- after the next export: the Premier League's matches on the site
--   select json_array_length(public.site_match_days('Europe/London')::json->'days');        -- after it: a row per day and competition

-- Repeatable. Applied 2026-10-05.
-- The players as rows in the database, not as one file (owner, 2026-10-05: convert Players to a
-- table and query functions). Until now every view that showed a player downloaded all 7,500 of
-- them (players.json, 1.4 MB) and filtered, sorted and searched them in the browser.
--   site.players             one row per listed player: the columns the queries filter and sort
--                            on, and the player as the site draws him (data: an array in the
--                            order of the export's SITE_PLAYER_FIELDS). Rewritten whole by each
--                            export (export.store_players). In the site schema, which the Data
--                            API doesn't expose.
--   site_players(...)        the players that fit every argument given, in the order asked for,
--                            p_limit of them from p_offset: {"total": how many fit, "rows": [...]}.
--                            The Players table asks for the 100 rows on screen; a club's page
--                            asks for that club's players (p_teams), a nation's page for that
--                            nationality (p_nats), other views for players by id (p_ids).
--                            With p_count it returns, for the same arguments, how many fit per
--                            league and club ({"counts": [[league, club, n], ...]}): the numbers
--                            in the Players view's competition menu.
--   site_player_facets()     what the Players view's filters need without any player: the age,
--                            Ability and minutes ranges, how many play each position, the clubs
--                            (with the league each is listed under) and the nationalities.
--   site_next_xi(team)       a club's predicted XI for its next match, {"fixture", "players":
--                            [[player, name, position, rank], ...]} in team-sheet order, or null.
--                            Read from predicted_lineups, as the export did for every club at once.
-- Arguments of site_players (all optional; a range is '{from,to}', either end NULL for open):
--   p_ids, p_leagues, p_teams, p_nats   he is one of these players, in one of these leagues, at
--                            one of these clubs, of one of these nationalities
--   p_not_leagues            he isn't in one of these leagues (the view's Exclude chips)
--   p_positions              he plays one of these (his main position, or one he has started in
--                            for a quarter of his minutes over 12 months)
--   p_age, p_ab, p_crank, p_mins   his age, Ability as shown, club's world rank, and minutes
--                            over his last 20 appearances are inside the range
--   p_q, p_words             the search: his name contains p_q (lower case, as typed), or every
--                            word starts a word of his name or of his club's search text. The
--                            page knows the clubs' search text (short forms, leagues, countries),
--                            so each element of p_words is "word|1 if it fits a player with no
--                            club|the ids of the clubs it fits, comma-separated".
--   p_sort, p_groups         "age" (youngest first), "ga" (goals and assists), "pos" (his best
--                            rank in the role groups p_groups), "s0", "s1", ... (a season's rank,
--                            newest first) or "f0", "f1", ... (a projected season); highest
--                            first, blanks last, ties in the export's order. Default "s0".
--   p_limit, p_offset        at most 2,000 rows a call
-- Fixed SQL, definer's rights with an empty search path; the tables stay closed to the public
-- key. Needs public."application/json" (20261005_site_doc_raw.sql). Also in db/schema.sql.
BEGIN;

CREATE TABLE IF NOT EXISTS site.players (
    player_id integer PRIMARY KEY,
    ord integer NOT NULL,                     -- his place in the export's order (current rank, highest first)
    name_lc text NOT NULL,                    -- his name in lower case
    name_fold text NOT NULL,                  -- and without accents or punctuation, as the site's search folds text
    team_id integer,
    league_id integer,
    age integer,
    nationality text,
    plays text[] NOT NULL,
    ability integer,                          -- this season's rank, rounded as the site shows it
    club_world integer,                       -- his club's place among every ranked club
    minutes integer,
    seasons double precision[] NOT NULL,      -- his rank each season, newest first
    future double precision[] NOT NULL,       -- and each projected season, oldest first
    pos_ranks jsonb NOT NULL,                 -- {role group: his rank as that position}
    ga double precision,                      -- goals + assists this season, goals breaking ties
    data json NOT NULL
);
CREATE INDEX IF NOT EXISTS players_team_idx ON site.players (team_id);
CREATE INDEX IF NOT EXISTS players_league_idx ON site.players (league_id);
CREATE INDEX IF NOT EXISTS players_nationality_idx ON site.players (nationality);
ALTER TABLE site.players ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON site.players FROM PUBLIC;

-- a club's next predicted XI is looked up by club (the table's key is the fixture and the player)
CREATE INDEX IF NOT EXISTS predicted_lineups_team_idx ON public.predicted_lineups (team_id);

CREATE OR REPLACE FUNCTION public.site_players(
    p_ids integer[] DEFAULT NULL, p_leagues integer[] DEFAULT NULL, p_teams integer[] DEFAULT NULL,
    p_nats text[] DEFAULT NULL, p_not_leagues integer[] DEFAULT NULL, p_positions text[] DEFAULT NULL,
    p_age integer[] DEFAULT NULL, p_ab integer[] DEFAULT NULL, p_crank integer[] DEFAULT NULL,
    p_mins integer[] DEFAULT NULL, p_q text DEFAULT NULL, p_words text[] DEFAULT NULL,
    p_sort text DEFAULT 's0', p_groups text[] DEFAULT NULL, p_limit integer DEFAULT 100,
    p_offset integer DEFAULT 0, p_count boolean DEFAULT false) RETURNS public."application/json"
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    sort_key text := CASE WHEN p_sort IN ('age', 'ga', 'pos') OR p_sort ~ '^[sf][0-9]{1,2}$' THEN p_sort ELSE 's0' END;
    sort_at integer := CASE WHEN sort_key ~ '^[sf][0-9]' THEN pg_catalog.substr(sort_key, 2)::integer + 1 END;
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-cache"}]', true);
    RETURN (
        WITH fit AS MATERIALIZED (
            SELECT p.league_id, p.team_id, p.ord, p.data,
                   CASE WHEN sort_key = 'age' THEN -p.age::double precision
                        WHEN sort_key = 'ga' THEN p.ga
                        WHEN sort_key = 'pos' THEN (SELECT max((p.pos_ranks->>g.g)::double precision) FROM pg_catalog.unnest(p_groups) g(g))
                        WHEN pg_catalog.left(sort_key, 1) = 's' THEN p.seasons[sort_at]
                        ELSE p.future[sort_at] END AS v
            FROM site.players p
            WHERE (p_ids IS NULL OR p.player_id = ANY (p_ids))
              AND (p_leagues IS NULL OR p.league_id = ANY (p_leagues))
              AND (p_teams IS NULL OR p.team_id = ANY (p_teams))
              AND (p_nats IS NULL OR p.nationality = ANY (p_nats))
              AND (p_not_leagues IS NULL OR p.league_id IS NULL OR p.league_id <> ALL (p_not_leagues))
              AND (p_positions IS NULL OR p.plays && p_positions)
              AND (p_age IS NULL OR (p_age[1] IS NULL AND p_age[2] IS NULL)
                   OR (p.age IS NOT NULL AND (p_age[1] IS NULL OR p.age >= p_age[1]) AND (p_age[2] IS NULL OR p.age <= p_age[2])))
              AND (p_ab IS NULL OR (p_ab[1] IS NULL AND p_ab[2] IS NULL)
                   OR (p.ability IS NOT NULL AND (p_ab[1] IS NULL OR p.ability >= p_ab[1]) AND (p_ab[2] IS NULL OR p.ability <= p_ab[2])))
              AND (p_crank IS NULL OR (p_crank[1] IS NULL AND p_crank[2] IS NULL)
                   OR (p.club_world IS NOT NULL AND (p_crank[1] IS NULL OR p.club_world >= p_crank[1]) AND (p_crank[2] IS NULL OR p.club_world <= p_crank[2])))
              AND (p_mins IS NULL OR (p_mins[1] IS NULL AND p_mins[2] IS NULL)
                   OR (p.minutes IS NOT NULL AND (p_mins[1] IS NULL OR p.minutes >= p_mins[1]) AND (p_mins[2] IS NULL OR p.minutes <= p_mins[2])))
              AND (p_q IS NULL OR pg_catalog.strpos(p.name_lc, p_q) > 0
                   OR (coalesce(pg_catalog.cardinality(p_words), 0) > 0 AND NOT EXISTS (
                           SELECT 1 FROM pg_catalog.unnest(p_words) w(w)
                           WHERE NOT (pg_catalog.strpos(' ' || p.name_fold, ' ' || pg_catalog.split_part(w.w, '|', 1)) > 0
                                      OR CASE WHEN p.team_id IS NULL THEN pg_catalog.split_part(w.w, '|', 2) = '1'
                                              ELSE p.team_id::text = ANY (pg_catalog.string_to_array(pg_catalog.split_part(w.w, '|', 3), ',')) END))))
        )
        SELECT CASE WHEN p_count THEN pg_catalog.json_build_object(
                   'counts', (SELECT coalesce(pg_catalog.json_agg(pg_catalog.json_build_array(c.league_id, c.team_id, c.n)), '[]'::json)
                              FROM (SELECT f.league_id, f.team_id, count(*) AS n FROM fit f GROUP BY 1, 2) c))
               ELSE pg_catalog.json_build_object(
                   'total', (SELECT count(*) FROM fit),
                   'rows', (SELECT coalesce(pg_catalog.json_agg(r.data ORDER BY r.v DESC NULLS LAST, r.ord), '[]'::json)
                            FROM (SELECT f.data, f.v, f.ord FROM fit f ORDER BY f.v DESC NULLS LAST, f.ord
                                  LIMIT least(greatest(coalesce(p_limit, 100), 0), 2000) OFFSET greatest(coalesce(p_offset, 0), 0)) r))
               END
    );
END; $$;

CREATE OR REPLACE FUNCTION public.site_player_facets() RETURNS public."application/json"
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-cache"}]', true);
    RETURN (
        SELECT pg_catalog.json_build_object(
            'players', count(*),
            'age', CASE WHEN min(p.age) IS NOT NULL THEN pg_catalog.json_build_array(min(p.age), max(p.age)) END,
            'ability', CASE WHEN min(p.ability) IS NOT NULL THEN pg_catalog.json_build_array(min(p.ability), max(p.ability)) END,
            'minutes', coalesce(max(p.minutes), 0),
            'positions', (SELECT coalesce(pg_catalog.json_object_agg(x.pos, x.n), '{}'::json)
                          FROM (SELECT r.pos, count(*) AS n FROM site.players q, pg_catalog.unnest(q.plays) r(pos) GROUP BY 1) x),
            -- each club once, with the league of its highest-ranked player
            'clubs', (SELECT coalesce(pg_catalog.json_agg(pg_catalog.json_build_array(x.team_id, x.league_id) ORDER BY x.ord), '[]'::json)
                      FROM (SELECT DISTINCT ON (q.team_id) q.team_id, q.league_id, q.ord FROM site.players q
                            WHERE q.team_id IS NOT NULL ORDER BY q.team_id, q.ord) x),
            'nats', (SELECT coalesce(pg_catalog.json_agg(x.nationality ORDER BY x.nationality), '[]'::json)
                     FROM (SELECT DISTINCT q.nationality FROM site.players q WHERE q.nationality <> '') x))
        FROM site.players p
    );
END; $$;

CREATE OR REPLACE FUNCTION public.site_next_xi(p_team integer) RETURNS public."application/json"
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-cache"}]', true);
    RETURN coalesce((
        SELECT pg_catalog.json_build_object(
            'fixture', x.fixture_id,
            -- team-sheet order: keeper, defence right to left, midfield, attack
            'players', pg_catalog.json_agg(
                pg_catalog.json_build_array(x.player_id, x.name, x.position, x.player_rank::float8)
                ORDER BY coalesce(pg_catalog.array_position(
                             ARRAY['GK','RB','RWB','CB','LB','LWB','DM','CM','RM','LM','AM','RW','LW','ST'], x.position), 99),
                         coalesce(x.player_rank, 0) DESC, x.player_id))
        FROM (SELECT pl.fixture_id, pl.player_id, p.name, pl.position, pl.player_rank
              FROM public.predicted_lineups pl JOIN public.players p USING (player_id)
              WHERE pl.team_id = p_team
                AND pl.fixture_id = (SELECT pl2.fixture_id FROM public.predicted_lineups pl2
                                     JOIN public.fixtures f2 ON f2.fixture_id = pl2.fixture_id
                                     WHERE pl2.team_id = p_team ORDER BY f2.kickoff, pl2.fixture_id LIMIT 1)) x
        GROUP BY x.fixture_id), 'null'::json);
END; $$;

REVOKE ALL ON FUNCTION public.site_players(integer[], integer[], integer[], text[], integer[], text[], integer[], integer[], integer[], integer[], text, text[], text, text[], integer, integer, boolean) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.site_player_facets() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.site_next_xi(integer) FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('REVOKE ALL ON site.players FROM %I', r);
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.site_players(integer[], integer[], integer[], text[], integer[], text[], integer[], integer[], integer[], integer[], text, text[], text, text[], integer, integer, boolean) TO %I', r);
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.site_player_facets() TO %I', r);
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.site_next_xi(integer) TO %I', r);
        END IF;
    END LOOP;
END; $$;

COMMIT;

NOTIFY pgrst, 'reload schema';

-- Check afterwards:
--   select has_table_privilege('anon', 'site.players', 'select');                         -- f
--   select public.site_players()::text;                                                   -- {"total" : 0, "rows" : []} until the next export
--   select (public.site_players(p_limit => 1)::json->>'total')::int;                      -- after it: about 7,500
--   select public.site_player_facets()::json->'age';                                      -- after it: [15, 45] or so
--   select left(public.site_next_xi((select team_id from predicted_lineups limit 1))::text, 80);   -- {"fixture" : ..., "players" : [[...

-- Repeatable. Applied 2026-10-05.
-- site_next_xi(team) was slow on the real database: about 0.2 s of work a call, 4 to 7 s each
-- with twenty at once, and some stopped at the public key's 3 second limit. To find a club's
-- next match with a predicted XI, the database walked every fixture in kick-off order from the
-- oldest (124,000 of them) looking for one of that club's, where the club has about thirty.
-- Now it takes the club's own fixtures first (by the index on predicted_lineups.team_id) and
-- picks the earliest of those: 0.4 ms. The answer is the same. (It was fast on the test copy,
-- which only held the fixtures with a predicted line-up.)
-- Replaces the function from 20261005_site_players.sql. Also in db/schema.sql.
BEGIN;

CREATE OR REPLACE FUNCTION public.site_next_xi(p_team integer) RETURNS public."application/json"
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    next_fixture integer;
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-cache"}]', true);
    -- the club's fixtures with a predicted XI, then the earliest (OFFSET 0 keeps the two steps apart)
    SELECT f.fixture_id INTO next_fixture
    FROM (SELECT DISTINCT pl.fixture_id FROM public.predicted_lineups pl WHERE pl.team_id = p_team OFFSET 0) mine
    JOIN public.fixtures f ON f.fixture_id = mine.fixture_id
    ORDER BY f.kickoff, f.fixture_id LIMIT 1;
    RETURN coalesce((
        SELECT pg_catalog.json_build_object(
            'fixture', next_fixture,
            -- team-sheet order: keeper, defence right to left, midfield, attack
            'players', pg_catalog.json_agg(
                pg_catalog.json_build_array(pl.player_id, p.name, pl.position, pl.player_rank::float8)
                ORDER BY coalesce(pg_catalog.array_position(
                             ARRAY['GK','RB','RWB','CB','LB','LWB','DM','CM','RM','LM','AM','RW','LW','ST'], pl.position), 99),
                         coalesce(pl.player_rank, 0) DESC, pl.player_id))
        FROM public.predicted_lineups pl JOIN public.players p USING (player_id)
        WHERE pl.fixture_id = next_fixture AND pl.team_id = p_team
        HAVING count(*) > 0), 'null'::json);
END; $$;

REVOKE ALL ON FUNCTION public.site_next_xi(integer) FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.site_next_xi(integer) TO %I', r);
        END IF;
    END LOOP;
END; $$;

COMMIT;

NOTIFY pgrst, 'reload schema';

-- Check afterwards:
--   select left(public.site_next_xi((select team_id from predicted_lineups limit 1))::text, 80);   -- {"fixture" : ..., "players" : [[...
--   select public.site_next_xi(-1)::text;                                                          -- null

-- Repeatable. Applied 2026-10-06.
-- The paid tier's foundation, switched off (owner, 2026-10-06: build everything but the
-- checkout; nothing changes for visitors until the switch is turned on).
--   subscriptions          who has paid: one row per account, written only by the payment
--                          provider's webhook when there is one (and by hand until then). No key
--                          can read or write it.
--   site.settings          the site's switches. 'paywall' is false: while it is, everyone gets
--                          everything, exactly as before this migration.
--   site.subscriber()      whether the caller is signed in with a live subscription, or is the
--                          site's owner (fpl_team_owners, as the FPL pages check).
--   site.entitled()        whether the caller gets the paid content: the paywall is off, or
--                          site.subscriber().
--   my_subscription()      what the page needs to know about the caller: {"paywall", "signed_in",
--                          "subscriber", "status", "plan", "renews_at", "ends"}.
--   site.matches.data_free, data_locked   a match's row with the paid fields blanked, written by
--                          the export beside the full row (export.store_matches):
--                            data_free    no projected goals, likely score, over 2.5, both to
--                                         score, absences or line-up ratings; the win, draw and
--                                         loss chances stay
--                            data_locked  the chances gone as well
--   site_matches(...)      as before for anyone entitled. Otherwise a match that hasn't kicked
--                          off comes back as data_free when it is within 7 days and data_locked
--                          beyond that, without its key reasons, and the answer carries
--                          "paywall": true so the page can say what is behind the lock. Matches
--                          that have kicked off are always whole: the record is free.
--   site_match_detail(fixture)   the model detail of a match that hasn't kicked off is for the
--                          entitled only ("locked": true otherwise).
-- The free and paid line is the owner's of 2026-10-04 (audit/commercial-plan.md): free is the
-- chances for the next 7 days; depth and matches further ahead are paid.
-- To switch the paywall on later (not now: the league pages, line-ups and player ranks aren't
-- gated yet):  update site.settings set value = 'true' where key = 'paywall';
-- Needs 20261005_site_matches_queries.sql and 20261004_fpl_owner_login.sql. Also in db/schema.sql.
BEGIN;

CREATE TABLE IF NOT EXISTS public.subscriptions (
    user_id uuid PRIMARY KEY REFERENCES auth.users (id) ON DELETE CASCADE,
    status text NOT NULL CHECK (status IN ('active', 'trialing', 'past_due', 'canceled')),
    plan text,                                -- 'monthly' or 'yearly'
    current_period_end timestamptz,           -- paid up to here
    cancel_at_period_end boolean NOT NULL DEFAULT false,
    provider text,                            -- who takes the payment, and its ids for this customer
    provider_customer text,
    provider_subscription text,
    updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.subscriptions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.subscriptions FROM PUBLIC;

CREATE TABLE IF NOT EXISTS site.settings (
    key text PRIMARY KEY,
    value jsonb NOT NULL
);
ALTER TABLE site.settings ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON site.settings FROM PUBLIC;
INSERT INTO site.settings (key, value) VALUES ('paywall', 'false') ON CONFLICT (key) DO NOTHING;

-- A subscription counts while it is paid up; a failed renewal keeps it for 3 days of retries
CREATE OR REPLACE FUNCTION site.subscriber() RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
    SELECT EXISTS (SELECT 1 FROM public.subscriptions b
                   WHERE b.user_id = auth.uid() AND b.status IN ('active', 'trialing', 'past_due')
                     AND (b.current_period_end IS NULL OR b.current_period_end + interval '3 days' > pg_catalog.now()))
        OR EXISTS (SELECT 1 FROM auth.users u JOIN public.fpl_team_owners o ON pg_catalog.lower(o.email) = pg_catalog.lower(u.email)
                   WHERE u.id = auth.uid() AND u.email_confirmed_at IS NOT NULL);
$$;
CREATE OR REPLACE FUNCTION site.entitled() RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
    SELECT NOT coalesce((SELECT s.value = 'true'::jsonb FROM site.settings s WHERE s.key = 'paywall'), false)
        OR site.subscriber();
$$;
REVOKE ALL ON FUNCTION site.subscriber() FROM PUBLIC;
REVOKE ALL ON FUNCTION site.entitled() FROM PUBLIC;

CREATE OR REPLACE FUNCTION public.my_subscription() RETURNS public."application/json"
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    b public.subscriptions;
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-store"}]', true);
    SELECT * INTO b FROM public.subscriptions s WHERE s.user_id = auth.uid();
    RETURN pg_catalog.json_build_object(
        'paywall', coalesce((SELECT s.value = 'true'::jsonb FROM site.settings s WHERE s.key = 'paywall'), false),
        'signed_in', auth.uid() IS NOT NULL,
        'subscriber', site.subscriber(),
        'status', b.status, 'plan', b.plan, 'renews_at', b.current_period_end,
        'ends', coalesce(b.cancel_at_period_end, false));
END; $$;

ALTER TABLE site.matches ADD COLUMN IF NOT EXISTS data_free json;
ALTER TABLE site.matches ADD COLUMN IF NOT EXISTS data_locked json;
-- The rows already stored, until the next export rewrites them. The positions are those of
-- export.SITE_MATCH_FIELDS (export.MATCH_PAID_DEPTH, MATCH_PAID_CHANCES; a test keeps them in step)
UPDATE site.matches m SET
    data_free = (SELECT pg_catalog.json_agg(CASE WHEN e.i - 1 = ANY (ARRAY[14,15,16,28,29,30,31,32,33,34,35]) THEN 'null'::json ELSE e.v END ORDER BY e.i)
                 FROM pg_catalog.json_array_elements(m.data) WITH ORDINALITY e(v, i)),
    data_locked = (SELECT pg_catalog.json_agg(CASE WHEN e.i - 1 = ANY (ARRAY[11,12,13,14,15,16,28,29,30,31,32,33,34,35]) THEN 'null'::json ELSE e.v END ORDER BY e.i)
                   FROM pg_catalog.json_array_elements(m.data) WITH ORDINALITY e(v, i))
WHERE m.data_free IS NULL OR m.data_locked IS NULL;

CREATE OR REPLACE FUNCTION public.site_matches(p_from timestamptz DEFAULT NULL, p_to timestamptz DEFAULT NULL,
                                               p_leagues integer[] DEFAULT NULL, p_team integer DEFAULT NULL,
                                               p_ids integer[] DEFAULT NULL) RETURNS public."application/json"
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    whole boolean := site.entitled();
    soon timestamptz := pg_catalog.now() + interval '7 days';
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-cache"}]', true);
    RETURN (
        SELECT pg_catalog.json_build_object(
            'matches', coalesce(pg_catalog.json_agg(x.data ORDER BY x.kickoff, x.fixture_id), '[]'::json),
            'reasons', coalesce(pg_catalog.json_object_agg(x.fixture_id, x.reasons) FILTER (WHERE x.reasons IS NOT NULL), '{}'::json),
            'paywall', NOT whole)
        FROM (SELECT m.fixture_id, m.kickoff,
                     CASE WHEN whole OR m.kickoff <= pg_catalog.now() THEN m.data
                          WHEN m.kickoff <= soon THEN coalesce(m.data_free, m.data_locked)
                          ELSE m.data_locked END AS data,
                     CASE WHEN whole OR m.kickoff <= pg_catalog.now() THEN m.reasons END AS reasons
              FROM site.matches m
              WHERE (p_from IS NOT NULL OR p_to IS NOT NULL OR p_leagues IS NOT NULL OR p_team IS NOT NULL OR p_ids IS NOT NULL)
                AND (p_from IS NULL OR m.kickoff >= p_from) AND (p_to IS NULL OR m.kickoff < p_to)
                AND (p_leagues IS NULL OR m.league_id = ANY (p_leagues))
                AND (p_team IS NULL OR m.home_id = p_team OR m.away_id = p_team)
                AND (p_ids IS NULL OR m.fixture_id = ANY (p_ids))
                -- a row the export hasn't given its blanked copies yet is left out for the
                -- unentitled, not shown whole
                AND (whole OR m.kickoff <= pg_catalog.now() OR m.data_locked IS NOT NULL)
              ORDER BY m.kickoff, m.fixture_id LIMIT 2000) x
    );
END; $$;

CREATE OR REPLACE FUNCTION public.site_match_detail(p_fixture integer) RETURNS public."application/json"
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    whole boolean := site.entitled();
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-cache"}]', true);
    RETURN coalesce((SELECT CASE WHEN whole OR m.kickoff <= pg_catalog.now() THEN pg_catalog.json_build_object(
                                'id', m.fixture_id, 'why', m.why,
                                'model', (SELECT pg_catalog.json_build_object('name', v.version_name, 'code', pg_catalog.left(v.code_sha, 7))
                                          FROM public.model_versions v WHERE v.model_version_id = m.why->>'model'))
                            ELSE pg_catalog.json_build_object('id', m.fixture_id, 'why', NULL, 'locked', true) END
                     FROM site.matches m WHERE m.fixture_id = p_fixture), 'null'::json);
END; $$;

REVOKE ALL ON FUNCTION public.my_subscription() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.site_matches(timestamptz, timestamptz, integer[], integer, integer[]) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.site_match_detail(integer) FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('REVOKE ALL ON public.subscriptions FROM %I', r);
            EXECUTE format('REVOKE ALL ON site.settings FROM %I', r);
            EXECUTE format('REVOKE ALL ON FUNCTION site.subscriber() FROM %I', r);
            EXECUTE format('REVOKE ALL ON FUNCTION site.entitled() FROM %I', r);
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.my_subscription() TO %I', r);
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.site_matches(timestamptz, timestamptz, integer[], integer, integer[]) TO %I', r);
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.site_match_detail(integer) TO %I', r);
        END IF;
    END LOOP;
END; $$;

COMMIT;

NOTIFY pgrst, 'reload schema';

-- Check afterwards:
--   select value from site.settings where key = 'paywall';                                  -- false
--   select has_table_privilege('anon', 'public.subscriptions', 'select');                   -- f
--   select public.my_subscription()::text;                                                  -- {"paywall" : false, "signed_in" : false, "subscriber" : false, ...}
--   select count(*), count(data_free), count(data_locked) from site.matches;                -- three equal numbers
--   select public.site_matches(p_leagues => '{39}')::json->>'paywall';                      -- false

-- Repeatable. Applied 2026-10-06.
-- A league's page from one question, so the paid tier can cut it down (owner, 2026-10-06). A
-- league's file carries every remaining fixture's projected goals and chances, which the page
-- plays out for the projected table: paid content, by the owner's line of 2026-10-04.
--   site_league(id)   the league's page data. Once this function exists the export writes two
--                     rows for each league (export.export_leagues): "leagues/<id>", cut down
--                     (chances only for fixtures in the next 7 days, no projected goals, and
--                     "cut": true so the page can say what is behind the lock), and
--                     "paid_leagues/<id>", whole and marked paid, which site_doc() never
--                     returns. This returns the whole one to anyone entitled (everyone, while
--                     the paywall is off: site.entitled()) and the cut-down one otherwise. Until
--                     the export has written the paid row, everyone gets "leagues/<id>", which
--                     is still whole.
-- Needs 20261006_paid_tier.sql. Also in db/schema.sql.
BEGIN;

CREATE OR REPLACE FUNCTION public.site_league(p_id integer) RETURNS public."application/json"
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    doc json;
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-cache"}]', true);
    IF site.entitled() THEN
        SELECT d.body INTO doc FROM site.docs d WHERE d.key = 'paid_leagues/' || p_id AND d.paid;
    END IF;
    IF doc IS NULL THEN
        SELECT d.body INTO doc FROM site.docs d WHERE d.key = 'leagues/' || p_id AND NOT d.paid;
    END IF;
    RETURN coalesce(doc, 'null'::json);
END; $$;

REVOKE ALL ON FUNCTION public.site_league(integer) FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.site_league(integer) TO %I', r);
        END IF;
    END LOOP;
END; $$;

COMMIT;

NOTIFY pgrst, 'reload schema';

-- Check afterwards:
--   select left(public.site_league(39)::text, 60);                                  -- {"id":39,"season":2026,...
--   select public.site_league(-1)::text;                                            -- null
--   select count(*) from site.docs where paid;                                      -- after the next export: one per league (70)
--   select public.site_doc('paid_leagues/39')::text;                                -- null, always

-- Repeatable. Applied 2026-10-06.
-- Predicted line-ups for the paid tier (owner's line of 2026-10-04: predicted line-ups are
-- paid). Both functions are the ones already live with one thing added; while the paywall is
-- off (site.entitled() true for everyone) they answer exactly as before, plus "locked": false.
--   site_lineups(fixture)   the predicted XI ("xi") of a match that hasn't kicked off is null
--                           for anyone not entitled, with "locked": true. The XI that started
--                           and the one predicted before the team sheet ("actual", "prematch")
--                           only exist for finished matches and stay free: the record is free.
--   site_next_xi(team)      {"fixture", "players": null, "locked": true} for anyone not entitled.
-- Needs 20261006_paid_tier.sql, 20261005_site_lineups.sql and 20261005_site_next_xi_fast.sql.
-- Also in db/schema.sql.
BEGIN;

CREATE OR REPLACE FUNCTION public.site_lineups(p_fixture integer) RETURNS public."application/json"
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    -- the predicted XI of a match that hasn't kicked off is for the entitled
    whole boolean := site.entitled()
        OR coalesce((SELECT f.kickoff <= pg_catalog.now() FROM public.fixtures f WHERE f.fixture_id = p_fixture), true);
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-cache"}]', true);
    RETURN (
        SELECT pg_catalog.json_build_object(
            'id', p_fixture,
            -- the predicted XI, in team-sheet order: keeper, defence right to left, midfield, attack
            'locked', NOT whole,
            'xi', CASE WHEN whole THEN (SELECT pg_catalog.json_object_agg(t.team_id, t.players) FROM (
                       SELECT pl.team_id, pg_catalog.json_agg(
                                  pg_catalog.json_build_array(pl.player_id, p.name, pl.position, pl.player_rank::float8)
                                  ORDER BY coalesce(pg_catalog.array_position(roles.sheet, pl.position), 99),
                                           coalesce(pl.player_rank, 0) DESC, pl.player_id) AS players
                       FROM public.predicted_lineups pl JOIN public.players p USING (player_id)
                       WHERE pl.fixture_id = p_fixture GROUP BY pl.team_id) t) END,
            -- the XI that started a finished match on the site, each player with his rank going into it
            'actual', (SELECT pg_catalog.json_object_agg(t.team_id, t.players) FROM (
                       SELECT x.team_id, pg_catalog.json_agg(
                                  pg_catalog.json_build_array(x.player_id, p.name, x.role, coalesce(r.player_rank, p.current_rank)::float8)
                                  ORDER BY coalesce(pg_catalog.array_position(roles.sheet, x.role), 99),
                                           coalesce(r.player_rank, p.current_rank, 0) DESC, x.player_id) AS players
                       FROM (SELECT DISTINCT ON (s.team_id, s.player_id) s.team_id, s.player_id, s.role
                             FROM (SELECT fp.team_id, fp.player_id,
                                          coalesce(fp.role, CASE fp.position WHEN 'G' THEN 'GK' WHEN 'D' THEN 'CB'
                                                                             WHEN 'M' THEN 'CM' WHEN 'F' THEN 'ST' END) AS role, 1 AS src
                                   FROM public.fixture_players fp WHERE fp.fixture_id = p_fixture AND fp.started
                                   UNION ALL
                                   SELECT fl.team_id, fl.player_id, fl.role, 2 FROM public.fixture_lineups fl WHERE fl.fixture_id = p_fixture) s
                             ORDER BY s.team_id, s.player_id, s.src) x
                       JOIN public.fixtures f ON f.fixture_id = p_fixture
                       JOIN public.players p ON p.player_id = x.player_id
                       LEFT JOIN public.fixture_player_ranks r ON r.fixture_id = p_fixture AND r.player_id = x.player_id
                       WHERE f.status_short IN ('FT', 'AET', 'PEN') AND f.kickoff > pg_catalog.now() - interval '21 days'
                       GROUP BY x.team_id) t),
            -- the XI the model predicted for it: its last capture before the team sheet was first seen
            'prematch', (SELECT pg_catalog.json_object_agg(t.team_id, t.players) FROM (
                       SELECT s.team_id, (SELECT pg_catalog.json_agg(pg_catalog.json_build_array(
                                                     (e.v->>'player')::int, coalesce(n.name, ''), e.v->>'role', (e.v->>'player_rating')::float8)
                                                 ORDER BY e.i)
                                          FROM pg_catalog.jsonb_array_elements(s.players) WITH ORDINALITY e(v, i)
                                          LEFT JOIN public.players n ON n.player_id = (e.v->>'player')::int
                                          WHERE (e.v->>'predicted_starter')::boolean) AS players
                       FROM (SELECT DISTINCT ON (s.team_id) s.team_id, s.players
                             FROM public.lineup_prediction_snapshots s JOIN public.fixtures f ON f.fixture_id = s.fixture_id
                             WHERE s.fixture_id = p_fixture AND s.source = 'prospective'
                               AND f.status_short IN ('FT', 'AET', 'PEN') AND f.kickoff > pg_catalog.now() - interval '21 days'
                               AND s.captured_at < coalesce((SELECT min(o.captured_at) FROM public.official_lineup_snapshots o
                                                             WHERE o.fixture_id = s.fixture_id AND o.team_id = s.team_id
                                                               AND o.effective_at = s.effective_at), 'infinity'::timestamptz)
                             ORDER BY s.team_id, s.captured_at DESC, s.snapshot_id DESC) s) t
                       WHERE t.players IS NOT NULL))
        FROM (SELECT ARRAY['GK','RB','RWB','CB','LB','LWB','DM','CM','RM','LM','AM','RW','LW','ST'] AS sheet) roles
    );
END; $$;

CREATE OR REPLACE FUNCTION public.site_next_xi(p_team integer) RETURNS public."application/json"
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    next_fixture integer;
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-cache"}]', true);
    -- the club's fixtures with a predicted XI, then the earliest (OFFSET 0 keeps the two steps apart)
    SELECT f.fixture_id INTO next_fixture
    FROM (SELECT DISTINCT pl.fixture_id FROM public.predicted_lineups pl WHERE pl.team_id = p_team OFFSET 0) mine
    JOIN public.fixtures f ON f.fixture_id = mine.fixture_id
    ORDER BY f.kickoff, f.fixture_id LIMIT 1;
    IF next_fixture IS NOT NULL AND NOT site.entitled() THEN
        RETURN pg_catalog.json_build_object('fixture', next_fixture, 'players', NULL, 'locked', true);
    END IF;
    RETURN coalesce((
        SELECT pg_catalog.json_build_object(
            'fixture', next_fixture,
            -- team-sheet order: keeper, defence right to left, midfield, attack
            'players', pg_catalog.json_agg(
                pg_catalog.json_build_array(pl.player_id, p.name, pl.position, pl.player_rank::float8)
                ORDER BY coalesce(pg_catalog.array_position(
                             ARRAY['GK','RB','RWB','CB','LB','LWB','DM','CM','RM','LM','AM','RW','LW','ST'], pl.position), 99),
                         coalesce(pl.player_rank, 0) DESC, pl.player_id))
        FROM public.predicted_lineups pl JOIN public.players p USING (player_id)
        WHERE pl.fixture_id = next_fixture AND pl.team_id = p_team
        HAVING count(*) > 0), 'null'::json);
END; $$;

REVOKE ALL ON FUNCTION public.site_lineups(integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.site_next_xi(integer) FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.site_lineups(integer) TO %I', r);
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.site_next_xi(integer) TO %I', r);
        END IF;
    END LOOP;
END; $$;

COMMIT;

NOTIFY pgrst, 'reload schema';

-- Check afterwards:
--   select public.site_lineups((select fixture_id from predicted_lineups limit 1))::json->>'locked';        -- false
--   select left(public.site_next_xi((select team_id from predicted_lineups limit 1))::text, 80);            -- {"fixture" : ..., "players" : [[...

-- Repeatable. Applied 2026-10-06.
-- Player ranks for the paid tier (owner's line of 2026-10-04: the top 50 overall and the top 10
-- of each league are free, the full list is paid). While the paywall is off (site.entitled()
-- true for everyone) every answer is as before, plus "paywall": false.
--   site.players.free, data_free   whether he is in the free slice, and his row with the paid
--                          fields null (rank, season ranks, projected seasons, position ranks,
--                          his places): written by the export (export.site_player_rows). Who he
--                          is, his club, age, minutes, goals and assists stay.
--   site_players(...)      the live function with this added: for anyone not entitled, a player
--                          outside the free slice comes back as data_free; he has no place in
--                          an order by rank (he follows the ranked ones, by name), and a filter
--                          on Ability leaves him out. The answer carries "paywall": true.
--   site_player_page(id)   a player's page file. Once this function exists the export writes a
--                          player outside the free slice two rows: "players/<id>" without his
--                          rank going into each match or his rating movement ("cut": true), and
--                          "paid_players/<id>", whole and marked paid, which site_doc() never
--                          returns. This returns the whole one to anyone entitled and the
--                          cut-down one otherwise. A player in the free slice has one, whole.
-- Needs 20261006_paid_tier.sql and 20261005_site_players.sql. Also in db/schema.sql.
BEGIN;

ALTER TABLE site.players ADD COLUMN IF NOT EXISTS free boolean NOT NULL DEFAULT false;
ALTER TABLE site.players ADD COLUMN IF NOT EXISTS data_free json;
-- The rows already stored, until the next export rewrites them. The positions are those of
-- export.SITE_PLAYER_FIELDS (export.PLAYER_PAID_FIELDS; world is 15 and lg 16; a test keeps them in step)
UPDATE site.players p SET
    free = coalesce((p.data->>15)::integer <= 50, false) OR coalesce((p.data->>16)::integer <= 10, false),
    data_free = (SELECT pg_catalog.json_agg(CASE WHEN e.i - 1 = ANY (ARRAY[3,7,9,12,13,15,16,18,20]) THEN 'null'::json ELSE e.v END ORDER BY e.i)
                 FROM pg_catalog.json_array_elements(p.data) WITH ORDINALITY e(v, i))
WHERE p.data_free IS NULL;

CREATE OR REPLACE FUNCTION public.site_players(
    p_ids integer[] DEFAULT NULL, p_leagues integer[] DEFAULT NULL, p_teams integer[] DEFAULT NULL,
    p_nats text[] DEFAULT NULL, p_not_leagues integer[] DEFAULT NULL, p_positions text[] DEFAULT NULL,
    p_age integer[] DEFAULT NULL, p_ab integer[] DEFAULT NULL, p_crank integer[] DEFAULT NULL,
    p_mins integer[] DEFAULT NULL, p_q text DEFAULT NULL, p_words text[] DEFAULT NULL,
    p_sort text DEFAULT 's0', p_groups text[] DEFAULT NULL, p_limit integer DEFAULT 100,
    p_offset integer DEFAULT 0, p_count boolean DEFAULT false) RETURNS public."application/json"
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    sort_key text := CASE WHEN p_sort IN ('age', 'ga', 'pos') OR p_sort ~ '^[sf][0-9]{1,2}$' THEN p_sort ELSE 's0' END;
    sort_at integer := CASE WHEN sort_key ~ '^[sf][0-9]' THEN pg_catalog.substr(sort_key, 2)::integer + 1 END;
    whole boolean := site.entitled();
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-cache"}]', true);
    RETURN (
        WITH fit AS MATERIALIZED (
            SELECT p.league_id, p.team_id, p.name_lc,
                   -- a player outside the free slice, for anyone not entitled: his blanked row, no
                   -- place in an order by rank, and the same place as the others like him otherwise
                   CASE WHEN whole OR p.free THEN p.ord ELSE 1000000 END AS ord,
                   CASE WHEN whole OR p.free THEN p.data ELSE p.data_free END AS data,
                   CASE WHEN NOT (whole OR p.free) AND sort_key NOT IN ('age', 'ga') THEN NULL
                        WHEN sort_key = 'age' THEN -p.age::double precision
                        WHEN sort_key = 'ga' THEN p.ga
                        WHEN sort_key = 'pos' THEN (SELECT max((p.pos_ranks->>g.g)::double precision) FROM pg_catalog.unnest(p_groups) g(g))
                        WHEN pg_catalog.left(sort_key, 1) = 's' THEN p.seasons[sort_at]
                        ELSE p.future[sort_at] END AS v
            FROM site.players p
            WHERE (whole OR p.free OR p.data_free IS NOT NULL)      -- never the whole row for want of a blanked one
              AND (p_ids IS NULL OR p.player_id = ANY (p_ids))
              AND (p_leagues IS NULL OR p.league_id = ANY (p_leagues))
              AND (p_teams IS NULL OR p.team_id = ANY (p_teams))
              AND (p_nats IS NULL OR p.nationality = ANY (p_nats))
              AND (p_not_leagues IS NULL OR p.league_id IS NULL OR p.league_id <> ALL (p_not_leagues))
              AND (p_positions IS NULL OR p.plays && p_positions)
              AND (p_age IS NULL OR (p_age[1] IS NULL AND p_age[2] IS NULL)
                   OR (p.age IS NOT NULL AND (p_age[1] IS NULL OR p.age >= p_age[1]) AND (p_age[2] IS NULL OR p.age <= p_age[2])))
              AND (p_ab IS NULL OR (p_ab[1] IS NULL AND p_ab[2] IS NULL)
                   OR ((whole OR p.free) AND p.ability IS NOT NULL AND (p_ab[1] IS NULL OR p.ability >= p_ab[1]) AND (p_ab[2] IS NULL OR p.ability <= p_ab[2])))
              AND (p_crank IS NULL OR (p_crank[1] IS NULL AND p_crank[2] IS NULL)
                   OR (p.club_world IS NOT NULL AND (p_crank[1] IS NULL OR p.club_world >= p_crank[1]) AND (p_crank[2] IS NULL OR p.club_world <= p_crank[2])))
              AND (p_mins IS NULL OR (p_mins[1] IS NULL AND p_mins[2] IS NULL)
                   OR (p.minutes IS NOT NULL AND (p_mins[1] IS NULL OR p.minutes >= p_mins[1]) AND (p_mins[2] IS NULL OR p.minutes <= p_mins[2])))
              AND (p_q IS NULL OR pg_catalog.strpos(p.name_lc, p_q) > 0
                   OR (coalesce(pg_catalog.cardinality(p_words), 0) > 0 AND NOT EXISTS (
                           SELECT 1 FROM pg_catalog.unnest(p_words) w(w)
                           WHERE NOT (pg_catalog.strpos(' ' || p.name_fold, ' ' || pg_catalog.split_part(w.w, '|', 1)) > 0
                                      OR CASE WHEN p.team_id IS NULL THEN pg_catalog.split_part(w.w, '|', 2) = '1'
                                              ELSE p.team_id::text = ANY (pg_catalog.string_to_array(pg_catalog.split_part(w.w, '|', 3), ',')) END))))
        )
        SELECT CASE WHEN p_count THEN pg_catalog.json_build_object(
                   'counts', (SELECT coalesce(pg_catalog.json_agg(pg_catalog.json_build_array(c.league_id, c.team_id, c.n)), '[]'::json)
                              FROM (SELECT f.league_id, f.team_id, count(*) AS n FROM fit f GROUP BY 1, 2) c))
               ELSE pg_catalog.json_build_object(
                   'total', (SELECT count(*) FROM fit),
                   'paywall', NOT whole,
                   'rows', (SELECT coalesce(pg_catalog.json_agg(r.data ORDER BY r.v DESC NULLS LAST, r.ord, r.name_lc), '[]'::json)
                            FROM (SELECT f.data, f.v, f.ord, f.name_lc FROM fit f ORDER BY f.v DESC NULLS LAST, f.ord, f.name_lc
                                  LIMIT least(greatest(coalesce(p_limit, 100), 0), 2000) OFFSET greatest(coalesce(p_offset, 0), 0)) r))
               END
    );
END; $$;

CREATE OR REPLACE FUNCTION public.site_player_page(p_id integer) RETURNS public."application/json"
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    doc json;
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-cache"}]', true);
    IF site.entitled() THEN
        SELECT d.body INTO doc FROM site.docs d WHERE d.key = 'paid_players/' || p_id AND d.paid;
    END IF;
    IF doc IS NULL THEN
        SELECT d.body INTO doc FROM site.docs d WHERE d.key = 'players/' || p_id AND NOT d.paid;
    END IF;
    RETURN coalesce(doc, 'null'::json);
END; $$;

REVOKE ALL ON FUNCTION public.site_players(integer[], integer[], integer[], text[], integer[], text[], integer[], integer[], integer[], integer[], text, text[], text, text[], integer, integer, boolean) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.site_player_page(integer) FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.site_players(integer[], integer[], integer[], text[], integer[], text[], integer[], integer[], integer[], integer[], text, text[], text, text[], integer, integer, boolean) TO %I', r);
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.site_player_page(integer) TO %I', r);
        END IF;
    END LOOP;
END; $$;

COMMIT;

NOTIFY pgrst, 'reload schema';

-- Check afterwards:
--   select count(*), count(*) filter (where free), count(data_free) from site.players;      -- about 7,500, several hundred, 7,500
--   select public.site_players(p_limit => 1)::json->>'paywall';                             -- false
--   select left(public.site_player_page((select player_id from site.players limit 1))::text, 40);   -- {"id":...

-- Repeatable. Applied 2026-10-06.
-- Ranks in the line-ups of finished matches are for subscribers too (owner, 2026-10-06: "hide
-- those ranks"): they would give away the paid player ranks one match at a time. site_lineups()
-- is the function of 20261006_paid_lineups.sql with this added: for anyone not entitled, each
-- player in "actual" and "prematch" comes without his rank ([player, name, role, null]). Who
-- started and who the model predicted stay free. While the paywall is off nothing changes.
-- Needs 20261006_paid_lineups.sql. Also in db/schema.sql.
BEGIN;

CREATE OR REPLACE FUNCTION public.site_lineups(p_fixture integer) RETURNS public."application/json"
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    -- the predicted XI of a match that hasn't kicked off is for the entitled (whole), and so is
    -- each player's rank in the line-ups of one that has (paid)
    paid boolean := site.entitled();
    whole boolean := paid
        OR coalesce((SELECT f.kickoff <= pg_catalog.now() FROM public.fixtures f WHERE f.fixture_id = p_fixture), true);
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-cache"}]', true);
    RETURN (
        SELECT pg_catalog.json_build_object(
            'id', p_fixture,
            -- the predicted XI, in team-sheet order: keeper, defence right to left, midfield, attack
            'locked', NOT whole,
            'xi', CASE WHEN whole THEN (SELECT pg_catalog.json_object_agg(t.team_id, t.players) FROM (
                       SELECT pl.team_id, pg_catalog.json_agg(
                                  pg_catalog.json_build_array(pl.player_id, p.name, pl.position, pl.player_rank::float8)
                                  ORDER BY coalesce(pg_catalog.array_position(roles.sheet, pl.position), 99),
                                           coalesce(pl.player_rank, 0) DESC, pl.player_id) AS players
                       FROM public.predicted_lineups pl JOIN public.players p USING (player_id)
                       WHERE pl.fixture_id = p_fixture GROUP BY pl.team_id) t) END,
            -- the XI that started a finished match on the site, each player with his rank going into it
            'actual', (SELECT pg_catalog.json_object_agg(t.team_id, t.players) FROM (
                       SELECT x.team_id, pg_catalog.json_agg(
                                  pg_catalog.json_build_array(x.player_id, p.name, x.role, CASE WHEN paid THEN coalesce(r.player_rank, p.current_rank)::float8 END)
                                  ORDER BY coalesce(pg_catalog.array_position(roles.sheet, x.role), 99),
                                           coalesce(r.player_rank, p.current_rank, 0) DESC, x.player_id) AS players
                       FROM (SELECT DISTINCT ON (s.team_id, s.player_id) s.team_id, s.player_id, s.role
                             FROM (SELECT fp.team_id, fp.player_id,
                                          coalesce(fp.role, CASE fp.position WHEN 'G' THEN 'GK' WHEN 'D' THEN 'CB'
                                                                             WHEN 'M' THEN 'CM' WHEN 'F' THEN 'ST' END) AS role, 1 AS src
                                   FROM public.fixture_players fp WHERE fp.fixture_id = p_fixture AND fp.started
                                   UNION ALL
                                   SELECT fl.team_id, fl.player_id, fl.role, 2 FROM public.fixture_lineups fl WHERE fl.fixture_id = p_fixture) s
                             ORDER BY s.team_id, s.player_id, s.src) x
                       JOIN public.fixtures f ON f.fixture_id = p_fixture
                       JOIN public.players p ON p.player_id = x.player_id
                       LEFT JOIN public.fixture_player_ranks r ON r.fixture_id = p_fixture AND r.player_id = x.player_id
                       WHERE f.status_short IN ('FT', 'AET', 'PEN') AND f.kickoff > pg_catalog.now() - interval '21 days'
                       GROUP BY x.team_id) t),
            -- the XI the model predicted for it: its last capture before the team sheet was first seen
            'prematch', (SELECT pg_catalog.json_object_agg(t.team_id, t.players) FROM (
                       SELECT s.team_id, (SELECT pg_catalog.json_agg(pg_catalog.json_build_array(
                                                     (e.v->>'player')::int, coalesce(n.name, ''), e.v->>'role', CASE WHEN paid THEN (e.v->>'player_rating')::float8 END)
                                                 ORDER BY e.i)
                                          FROM pg_catalog.jsonb_array_elements(s.players) WITH ORDINALITY e(v, i)
                                          LEFT JOIN public.players n ON n.player_id = (e.v->>'player')::int
                                          WHERE (e.v->>'predicted_starter')::boolean) AS players
                       FROM (SELECT DISTINCT ON (s.team_id) s.team_id, s.players
                             FROM public.lineup_prediction_snapshots s JOIN public.fixtures f ON f.fixture_id = s.fixture_id
                             WHERE s.fixture_id = p_fixture AND s.source = 'prospective'
                               AND f.status_short IN ('FT', 'AET', 'PEN') AND f.kickoff > pg_catalog.now() - interval '21 days'
                               AND s.captured_at < coalesce((SELECT min(o.captured_at) FROM public.official_lineup_snapshots o
                                                             WHERE o.fixture_id = s.fixture_id AND o.team_id = s.team_id
                                                               AND o.effective_at = s.effective_at), 'infinity'::timestamptz)
                             ORDER BY s.team_id, s.captured_at DESC, s.snapshot_id DESC) s) t
                       WHERE t.players IS NOT NULL))
        FROM (SELECT ARRAY['GK','RB','RWB','CB','LB','LWB','DM','CM','RM','LM','AM','RW','LW','ST'] AS sheet) roles
    );
END; $$;

REVOKE ALL ON FUNCTION public.site_lineups(integer) FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.site_lineups(integer) TO %I', r);
        END IF;
    END LOOP;
END; $$;

COMMIT;

NOTIFY pgrst, 'reload schema';

-- Check afterwards (a finished match from the last 21 days):
--   select public.site_lineups((select fixture_id from fixtures where status_short = 'FT' order by kickoff desc limit 1))::json->'actual' is not null;   -- t, with ranks while the paywall is off

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

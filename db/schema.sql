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

-- Repeatable. Not applied yet: the owner runs it in the Supabase SQL editor.
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

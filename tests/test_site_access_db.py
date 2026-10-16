"""Who sees what, asked of a real Postgres built from db/schema.sql (guide/paid-tier.md).

Every other test here uses stand-in connections. These need a throwaway Postgres server: set
SITE_DB_TEST_DSN to a superuser address on one (tests.yml starts one beside the tests; on this Mac,
`docker run --rm -e POSTGRES_PASSWORD=test -p 127.0.0.1:55432:5432 postgres:17` and
SITE_DB_TEST_DSN=postgresql://postgres:test@127.0.0.1:55432/postgres). Each run makes its own
database, builds it from tests/db/supabase_stand_in.sql and db/schema.sql, fills it with a few
rows, and drops it at the end. Without the address the tests are skipped.

What they hold the database to, with the paywall on:
- the public key and a signed-in visitor reach no table, and only the functions listed here;
- a visitor who isn't entitled (signed out, no subscription, lapsed, cancelled, an owner whose
  email isn't confirmed) gets the cut-down matches, league, player page, players list and
  line-ups, and a subscriber, a late payer inside 3 days and the owner get them whole;
- site_doc never hands out a paid row, to anyone;
- the Admin documents are the administrator's only, and the FPL data the owner's only.
"""
import json
import os
import unittest
import uuid
from pathlib import Path

DSN = os.getenv("SITE_DB_TEST_DSN")
ROOT = Path(__file__).resolve().parents[1]

# What the public key may call (anon), and what a signed-in visitor may call besides
ANON_FUNCTIONS = {
    "public.my_subscription()",
    "public.site_doc(p_key text, p_v text)",
    "public.site_league(p_id integer)",
    "public.site_lineup_history(p_days integer, p_leagues integer[], p_limit integer)",
    "public.site_lineups(p_fixture integer)",
    "public.site_match_days(p_tz text)",
    "public.site_match_detail(p_fixture integer)",
    "public.site_matches(p_from timestamp with time zone, p_to timestamp with time zone, p_leagues integer[], "
    "p_team integer, p_ids integer[])",
    "public.site_next_xi(p_team integer)",
    "public.site_player_facets()",
    "public.site_player_page(p_id integer)",
    "public.site_players(p_ids integer[], p_leagues integer[], p_teams integer[], p_nats text[], "
    "p_not_leagues integer[], p_positions text[], p_age integer[], p_ab integer[], p_crank integer[], "
    "p_mins integer[], p_q text, p_words text[], p_sort text, p_groups text[], p_limit integer, "
    "p_offset integer, p_count boolean)",
}
SIGNED_IN_FUNCTIONS = ANON_FUNCTIONS | {
    "public.admin_doc(p_name text)",
    "public.admin_match_model()",
    "public.admin_match_model_compare()",
    "public.admin_set_match_model(p_live text)",
    "public.am_admin()",
    "public.delete_my_account()",
    "public.fpl_owner_data(p_entry integer)",
    "public.lock_fpl_transfers(p_entry integer, p_season integer, p_event integer, p_transfers jsonb)",
    "public.mark_fpl_player(p_entry integer, p_player integer, p_mine boolean, p_target boolean)",
    "public.unlock_fpl_transfers(p_entry integer, p_season integer, p_event integer)",
}

# The visitors: (role, account). Accounts are made in setUpClass.
ENTITLED = ["subscriber", "late_payer", "owner"]
NOT_ENTITLED = ["signed_out", "free_account", "lapsed", "cancelled", "owner_unconfirmed"]

SEED = """
INSERT INTO auth.users (id, email, email_confirmed_at) VALUES
    (%(free_account)s, 'free@example.test', now()),
    (%(subscriber)s, 'paid@example.test', now()),
    (%(late_payer)s, 'late@example.test', now()),
    (%(lapsed)s, 'lapsed@example.test', now()),
    (%(cancelled)s, 'cancelled@example.test', now()),
    (%(owner)s, 'Owner@example.test', now()),
    (%(owner_unconfirmed)s, 'owner2@example.test', NULL),
    (%(admin)s, 'admin@example.test', now()),
    (%(admin_unconfirmed)s, 'admin2@example.test', NULL);
INSERT INTO public.subscriptions (user_id, status, plan, current_period_end) VALUES
    (%(subscriber)s, 'active', 'monthly', now() + interval '20 days'),
    (%(late_payer)s, 'past_due', 'monthly', now() - interval '1 day'),
    (%(lapsed)s, 'active', 'monthly', now() - interval '5 days'),
    (%(cancelled)s, 'canceled', 'yearly', now() + interval '20 days');
INSERT INTO public.fpl_team_owners (entry_id, email) VALUES (1, 'owner@example.test'), (2, 'owner2@example.test');
INSERT INTO public.site_admins (email) VALUES ('admin@example.test'), ('admin2@example.test');
INSERT INTO public.admin_docs (name, doc) VALUES ('live_tracking', '{"secret": "admin"}');
INSERT INTO public.fpl_owner_docs (name, doc) VALUES ('fpl_team', '{"secret": "fpl"}');

INSERT INTO site.docs (key, body, sha256, paid) VALUES
    ('players/1', '{"cut": true}', 'a', false), ('paid_players/1', '{"whole": true}', 'b', true),
    ('leagues/39', '{"cut": true}', 'c', false), ('paid_leagues/39', '{"whole": true}', 'd', true),
    ('rankings', '{"free": true}', 'e', false);

-- 101 within 7 days, 102 beyond them, 103 played, 104 coming but not yet given its blanked copies
INSERT INTO site.matches (fixture_id, kickoff, league_id, home_id, away_id, data, data_free, data_locked, reasons, why) VALUES
    (101, now() + interval '2 days', 39, 10, 20, '["whole"]', '["free"]', '["locked"]', '{"r": 1}', '{"w": 1}'),
    (102, now() + interval '20 days', 39, 10, 20, '["whole"]', '["free"]', '["locked"]', '{"r": 1}', '{"w": 1}'),
    (103, now() - interval '2 days', 39, 10, 20, '["whole"]', '["free"]', '["locked"]', '{"r": 1}', '{"w": 1}'),
    (104, now() + interval '1 day', 39, 10, 20, '["whole"]', NULL, NULL, '{"r": 1}', '{"w": 1}');

-- 1 in the free slice; 2 outside it, with his blanked row; 3 outside it with no blanked row yet
INSERT INTO site.players (player_id, ord, name_lc, name_fold, team_id, league_id, ability, plays, seasons, future,
                          pos_ranks, data, free, data_free) VALUES
    (1, 1, 'one', 'one', 10, 39, 90, '{ST}', '{90}', '{90}', '{"ST": 90}', '["one whole"]', true, '["one cut"]'),
    (2, 2, 'two', 'two', 10, 39, 80, '{ST}', '{80}', '{80}', '{"ST": 80}', '["two whole"]', false, '["two cut"]'),
    (3, 3, 'three', 'three', 10, 39, 70, '{ST}', '{70}', '{70}', '{"ST": 70}', '["three whole"]', false, NULL);

INSERT INTO public.leagues (league_id, name) VALUES (39, 'League');
INSERT INTO public.teams (team_id, name) VALUES (10, 'Home'), (20, 'Away');
INSERT INTO public.players (player_id, name) VALUES (1, 'One'), (2, 'Two'), (3, 'Three');
-- 201 coming, with a predicted XI; 202 finished, with the XI that started and its ranks
INSERT INTO public.fixtures (fixture_id, league_id, season, kickoff, status_short, home_team_id, away_team_id) VALUES
    (201, 39, 2026, now() + interval '2 days', 'NS', 10, 20),
    (202, 39, 2026, now() - interval '2 days', 'FT', 10, 20);
INSERT INTO public.predicted_lineups (fixture_id, team_id, player_id, position, player_rank) VALUES (201, 10, 1, 'ST', 90);
INSERT INTO public.fixture_players (fixture_id, team_id, player_id, minutes, started, position) VALUES (202, 10, 2, 90, true, 'F');
INSERT INTO public.fixture_player_ranks (fixture_id, player_id, player_rank) VALUES (202, 2, 80);

UPDATE site.settings SET value = 'true' WHERE key = 'paywall';
"""


@unittest.skipUnless(DSN, "needs SITE_DB_TEST_DSN: a throwaway Postgres server (see this file's docstring)")
class SiteAccess(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        from psycopg.conninfo import make_conninfo
        cls.psycopg = psycopg
        cls.name = f"site_access_{uuid.uuid4().hex[:10]}"
        with psycopg.connect(DSN, autocommit=True) as server:
            server.execute(f'CREATE DATABASE "{cls.name}"')
        cls.conn = psycopg.connect(make_conninfo(DSN, dbname=cls.name), autocommit=True)
        cls.conn.execute((ROOT / "tests/db/supabase_stand_in.sql").read_text())
        cls.conn.execute((ROOT / "db/schema.sql").read_text())
        cls.ids = {k: str(uuid.uuid4()) for k in
                   ["free_account", "subscriber", "late_payer", "lapsed", "cancelled", "owner",
                    "owner_unconfirmed", "admin", "admin_unconfirmed"]}
        # (several statements with parameters: bound on this side, as one script)
        psycopg.ClientCursor(cls.conn).execute(SEED, cls.ids)

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()
        with cls.psycopg.connect(DSN, autocommit=True) as server:
            server.execute(f'DROP DATABASE IF EXISTS "{cls.name}" WITH (FORCE)')

    def ask(self, visitor, sql, params=None, paywall=True):
        """Run one query as a visitor would reach it through the API, then undo everything."""
        role = "anon" if visitor == "signed_out" else "authenticated"
        claims = {"role": role} if role == "anon" else {"role": role, "sub": self.ids[visitor]}
        with self.conn.transaction(force_rollback=True):
            if not paywall:
                self.conn.execute("UPDATE site.settings SET value = 'false' WHERE key = 'paywall'")
            self.conn.execute("SELECT set_config('request.jwt.claims', %s, true)", [json.dumps(claims)])
            self.conn.execute(f"SET LOCAL ROLE {role}")
            value = self.conn.execute(sql, params).fetchone()[0]
        return json.loads(value) if isinstance(value, str) else value

    # --- what each key can reach ---

    def functions(self, role):
        return {r[0] for r in self.conn.execute(
            "SELECT n.nspname || '.' || p.proname || '(' || pg_get_function_identity_arguments(p.oid) || ')' "
            "FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname IN ('public', 'site', 'auth') AND p.proname <> 'uid' "
            "AND has_function_privilege(%s, p.oid, 'execute')", [role])}

    def test_the_public_key_calls_only_the_sites_functions(self):
        self.assertEqual(self.functions("anon"), ANON_FUNCTIONS)

    def test_a_signed_in_visitor_calls_only_these_besides(self):
        self.assertEqual(self.functions("authenticated"), SIGNED_IN_FUNCTIONS)

    def test_neither_key_reaches_any_table_or_view(self):
        reachable = self.conn.execute(
            "SELECT r.rolname, n.nspname || '.' || c.relname, x.p FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "CROSS JOIN (VALUES ('anon'), ('authenticated')) r(rolname) "
            "CROSS JOIN (VALUES ('select'), ('insert'), ('update'), ('delete')) x(p) "
            "WHERE c.relkind IN ('r', 'v', 'm', 'p', 'f') AND n.nspname IN ('public', 'site', 'auth') "
            "AND has_table_privilege(r.rolname, c.oid, x.p)").fetchall()
        self.assertEqual(reachable, [])

    def test_the_paywalls_own_checks_cant_be_called_from_outside(self):
        for visitor in ["signed_out", "free_account"]:
            for fn in ["site.entitled()", "site.subscriber()", "site.is_admin()"]:
                with self.subTest(visitor=visitor, fn=fn), self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
                    self.ask(visitor, f"SELECT {fn}")

    # --- the paywall, visitor by visitor ---

    def site_matches(self, visitor, paywall=True):
        got = self.ask(visitor, "SELECT public.site_matches(p_ids => '{101,102,103,104}')::text", paywall=paywall)
        return got["paywall"], [m[0] for m in got["matches"]], sorted(got["reasons"])

    def test_matches_are_cut_down_for_anyone_not_entitled(self):
        for visitor in NOT_ENTITLED:
            with self.subTest(visitor=visitor):
                # in kickoff order: 103 played (whole), 101 within 7 days (free copy), 102 beyond
                # them (locked copy); 104 has no blanked copy yet, so it's left out, never whole
                self.assertEqual(self.site_matches(visitor), (True, ["whole", "free", "locked"], ["103"]))

    def test_matches_are_whole_for_the_entitled(self):
        for visitor in ENTITLED:
            with self.subTest(visitor=visitor):
                self.assertEqual(self.site_matches(visitor),
                                 (False, ["whole", "whole", "whole", "whole"], ["101", "102", "103", "104"]))

    def test_with_the_paywall_off_everyone_gets_everything(self):
        self.assertEqual(self.site_matches("signed_out", paywall=False),
                         (False, ["whole", "whole", "whole", "whole"], ["101", "102", "103", "104"]))
        self.assertEqual(self.ask("signed_out", "SELECT public.site_league(39)::text", paywall=False), {"whole": True})

    def test_a_coming_matchs_detail_is_locked_unless_entitled(self):
        for visitor in NOT_ENTITLED + ENTITLED:
            with self.subTest(visitor=visitor):
                coming = self.ask(visitor, "SELECT public.site_match_detail(101)::text")
                played = self.ask(visitor, "SELECT public.site_match_detail(103)::text")
                self.assertEqual(played["why"], {"w": 1})
                if visitor in ENTITLED:
                    self.assertEqual(coming["why"], {"w": 1})
                else:
                    self.assertEqual((coming["why"], coming["locked"]), (None, True))

    def test_league_and_player_pages(self):
        for visitor in NOT_ENTITLED + ENTITLED:
            with self.subTest(visitor=visitor):
                whole = visitor in ENTITLED
                self.assertEqual(self.ask(visitor, "SELECT public.site_league(39)::text"),
                                 {"whole": True} if whole else {"cut": True})
                self.assertEqual(self.ask(visitor, "SELECT public.site_player_page(1)::text"),
                                 {"whole": True} if whole else {"cut": True})

    def test_players_outside_the_free_slice_are_hidden_but_keep_their_place(self):
        for visitor in NOT_ENTITLED + ENTITLED:
            with self.subTest(visitor=visitor):
                got = self.ask(visitor, "SELECT public.site_players(p_ids => '{1,2,3}')::text")
                rows = [r[0] for r in got["rows"]]
                if visitor in ENTITLED:
                    self.assertEqual((got["paywall"], rows), (False, ["one whole", "two whole", "three whole"]))
                else:
                    # 3 has no blanked row yet: left out rather than shown whole
                    self.assertEqual((got["paywall"], rows), (True, ["one whole", "two cut"]))
                    # and a filter on Ability can't be used to find the hidden ones
                    by_ability = self.ask(visitor, "SELECT public.site_players(p_ids => '{1,2,3}', p_ab => '{75,85}')::text")
                    self.assertEqual(by_ability["rows"], [])

    def test_predicted_line_ups_and_ranks_in_played_ones(self):
        for visitor in NOT_ENTITLED + ENTITLED:
            with self.subTest(visitor=visitor):
                whole = visitor in ENTITLED
                coming = self.ask(visitor, "SELECT public.site_lineups(201)::text")
                self.assertEqual(coming["locked"], not whole)
                self.assertEqual(coming["xi"], {"10": [[1, "One", "ST", 90.0]]} if whole else None)
                played = self.ask(visitor, "SELECT public.site_lineups(202)::text")
                self.assertEqual(played["actual"], {"10": [[2, "Two", "ST", 80.0 if whole else None]]})
                next_xi = self.ask(visitor, "SELECT public.site_next_xi(10)::text")
                self.assertEqual(next_xi["fixture"], 201)
                if whole:
                    self.assertEqual(next_xi["players"], [[1, "One", "ST", 90.0]])
                else:
                    self.assertEqual((next_xi["players"], next_xi["locked"]), (None, True))

    def test_each_visitor_is_told_whether_they_subscribe(self):
        for visitor in NOT_ENTITLED + ENTITLED:
            with self.subTest(visitor=visitor):
                got = self.ask(visitor, "SELECT public.my_subscription()::text")
                self.assertEqual((got["paywall"], got["subscriber"], got["signed_in"]),
                                 (True, visitor in ENTITLED, visitor != "signed_out"))

    def test_site_doc_never_hands_out_a_paid_row(self):
        for visitor in NOT_ENTITLED + ENTITLED:
            with self.subTest(visitor=visitor):
                self.assertIsNone(self.ask(visitor, "SELECT public.site_doc('paid_players/1')::text"))
                self.assertIsNone(self.ask(visitor, "SELECT public.site_doc('paid_leagues/39')::text"))
                self.assertEqual(self.ask(visitor, "SELECT public.site_doc('players/1')::text"), {"cut": True})
                self.assertEqual(self.ask(visitor, "SELECT public.site_doc('rankings')::text"), {"free": True})

    # --- the administrator's and the owner's own data ---

    def test_admin_documents_are_the_administrators_only(self):
        sql = "SELECT public.admin_doc('live_tracking')::text"
        with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
            self.ask("signed_out", sql)
        for visitor in ["free_account", "subscriber", "owner", "admin_unconfirmed"]:
            with self.subTest(visitor=visitor):
                self.assertEqual(self.ask(visitor, sql), {"ok": False})
        got = self.ask("admin", sql)
        self.assertEqual((got["ok"], got["doc"]), (True, {"secret": "admin"}))

    def test_fpl_data_is_the_owners_only(self):
        sql = "SELECT public.fpl_owner_data(1)::text"
        with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
            self.ask("signed_out", sql)
        for visitor, entry in [("free_account", 1), ("subscriber", 1), ("admin", 1), ("owner_unconfirmed", 2)]:
            with self.subTest(visitor=visitor):
                got = self.ask(visitor, f"SELECT public.fpl_owner_data({entry})::text")
                self.assertEqual((got["ok"], "docs" in got), (False, False))
        got = self.ask("owner", sql)
        self.assertEqual((got["ok"], got["docs"]), (True, {"fpl_team": {"secret": "fpl"}}))


if __name__ == "__main__":
    unittest.main()

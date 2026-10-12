import importlib
import os
import unittest
from unittest.mock import MagicMock, patch

OVERRIDE = "I_UNDERSTAND_THIS_CAN_WRITE_PRODUCTION_DATA_AND_USE_API_QUOTA"
PRODUCTION = "bookkurhdabdeccckjbn"
STAGING = "stagingstagingstagin"
# the forms Supabase gives an address: the shared pooler (the project is in the user name) and
# the direct one (the project is in the host)
POOLER = "postgresql://postgres.{}:pw@aws-0-eu-central-1.pooler.supabase.com:5432/postgres"
DIRECT = "postgresql://postgres:pw@db.{}.supabase.co:5432/postgres"


def load_config(env):
    # only what the test names: the local .env (which the switch writes) is not read
    with patch.dict(os.environ, env, clear=True), patch("dotenv.load_dotenv", lambda *a, **k: False):
        import thecornerfc.config as config
        return importlib.reload(config)


def a_database(says):
    """A stand-in connection whose database answers site.environment() with `says` (an error
    when says is an Exception: the function isn't there)."""
    conn = MagicMock()
    conn.read_only = False
    if isinstance(says, Exception):
        conn.execute.side_effect = says
    else:
        conn.execute.return_value.fetchone.return_value = (says,)
    return conn


class SafetyGuardTests(unittest.TestCase):
    def test_local_defaults_block_db_writes_and_api_access(self):
        config = load_config({
            "THECORNERFC_MODE": "local",
            "THECORNERFC_READ_ONLY": "true",
            "THECORNERFC_NO_API": "true",
            "READ_ONLY_DATABASE_URL": "postgresql://readonly@example/db",
            "DATABASE_URL": "postgresql://writer@example/db",
        })

        self.assertTrue(config.READ_ONLY)
        self.assertTrue(config.NO_API)
        self.assertEqual(config.DATABASE_URL, "postgresql://readonly@example/db")
        with self.assertRaises(config.SafetyError):
            config.require_db_write("rank")
        with self.assertRaises(config.SafetyError):
            config.require_api_access("status")

    def test_the_override_lifts_nothing_for_production_or_for_no_named_environment(self):
        # it used to allow local production writes; now nothing on this machine does
        for env in ("", "production"):
            with self.subTest(env=env):
                config = load_config({
                    "THECORNERFC_ENV": env,
                    "THECORNERFC_MODE": "production",
                    "THECORNERFC_READ_ONLY": "false",
                    "THECORNERFC_NO_API": "false",
                    "THECORNERFC_LOCAL_OVERRIDE": OVERRIDE,
                    "READ_ONLY_DATABASE_URL": POOLER.format(PRODUCTION).replace("postgres.", "local_readonly."),
                    "DATABASE_URL": POOLER.format(PRODUCTION),
                    "API_FOOTBALL_KEY": "example-key",
                    "FPL_CAPTURE_ENABLED": "true",
                })
                self.assertFalse(config.writes_allowed())
                self.assertIn("local_readonly", config.DATABASE_URL)
                for refused in (config.require_db_write, config.require_api_access, config.require_fpl_access):
                    with self.assertRaises(config.SafetyError):
                        refused("anything")

    def test_staging_may_be_written_locally_and_calls_no_api_unless_the_override_is_carried(self):
        config = load_config({
            "THECORNERFC_ENV": "staging",
            "THECORNERFC_READ_ONLY": "false",
            "DATABASE_URL": POOLER.format(STAGING),
            "API_FOOTBALL_KEY": "example-key",
        })
        self.assertTrue(config.writes_allowed())
        config.require_db_write("rank")
        self.assertTrue(config.NO_API)                      # off by default in staging
        with self.assertRaises(config.SafetyError):
            config.require_api_access("status")

        config = load_config({"THECORNERFC_ENV": "staging", "THECORNERFC_NO_API": "false"})
        with self.assertRaises(config.SafetyError):         # the flag alone is not enough
            config.require_api_access("status")
        config = load_config({"THECORNERFC_ENV": "staging", "THECORNERFC_NO_API": "false",
                              "THECORNERFC_LOCAL_OVERRIDE": OVERRIDE})
        config.require_api_access("status")

    def test_an_environment_that_is_neither_is_an_error(self):
        with self.assertRaises(ValueError):
            load_config({"THECORNERFC_ENV": "prod"})
        load_config({})                                     # leave the module loadable for later tests

    def test_read_only_switched_off_alone_still_connects_read_only(self):
        # no Actions run and not staging: the flag on its own must not reach the write address
        config = load_config({
            "THECORNERFC_MODE": "local",
            "THECORNERFC_READ_ONLY": "false",
            "READ_ONLY_DATABASE_URL": "postgresql://readonly@example/db",
            "DATABASE_URL": "postgresql://writer@example/db",
        })

        self.assertFalse(config.writes_allowed())
        self.assertEqual(config.DATABASE_URL, "postgresql://readonly@example/db")
        with self.assertRaises(config.SafetyError):
            config.require_db_write("rank")
        import thecornerfc.pipeline.db as db
        with patch.object(db, "config", config), patch.object(db.psycopg, "connect") as connect:
            conn = db.connect()
        connect.assert_called_once_with("postgresql://readonly@example/db", prepare_threshold=None, sslmode="require")
        self.assertTrue(conn.read_only)

    def test_production_mode_alone_is_not_enough_outside_actions(self):
        config = load_config({
            "THECORNERFC_ENV": "production",
            "THECORNERFC_MODE": "production",
            "THECORNERFC_READ_ONLY": "false",   # (as production mode sets it; named so a local .env can't)
            "GITHUB_ACTIONS": "false",
            "THECORNERFC_LOCAL_OVERRIDE": "",
            "READ_ONLY_DATABASE_URL": "postgresql://readonly@example/db",
            "DATABASE_URL": "postgresql://writer@example/db",
        })

        self.assertFalse(config.READ_ONLY)
        self.assertFalse(config.writes_allowed())
        self.assertEqual(config.DATABASE_URL, "postgresql://readonly@example/db")

    def test_no_read_only_address_means_no_connection_not_the_write_one(self):
        config = load_config({
            "THECORNERFC_READ_ONLY": "false",
            "READ_ONLY_DATABASE_URL": "",       # (set empty, so a local .env can't fill it in)
            "DATABASE_URL": "postgresql://writer@example/db",
        })

        self.assertFalse(config.DATABASE_URL)
        import thecornerfc.pipeline.db as db
        with patch.object(db, "config", config), patch.object(db.psycopg, "connect") as connect:
            with self.assertRaisesRegex(RuntimeError, "not set"):
                db.connect()
        connect.assert_not_called()

    def test_an_actions_run_uses_the_write_address_of_its_own_project_once_the_database_agrees(self):
        import thecornerfc.pipeline.db as db
        for address in (POOLER, DIRECT):
            with self.subTest(address=address):
                actions = load_config({
                    "GITHUB_ACTIONS": "true",
                    "THECORNERFC_ENV": "production",
                    "THECORNERFC_MODE": "production",
                    "THECORNERFC_READ_ONLY": "false",
                    "READ_ONLY_DATABASE_URL": "postgresql://readonly@example/db",
                    "DATABASE_URL": address.format(PRODUCTION),
                })
                self.assertTrue(actions.writes_allowed())
                self.assertEqual(actions.DATABASE_URL, address.format(PRODUCTION))
                actions.require_db_write("nightly")
                with patch.object(db, "config", actions), \
                     patch.object(db.psycopg, "connect", return_value=a_database("production")) as connect:
                    conn = db.connect()
                connect.assert_called_once()
                self.assertFalse(conn.read_only)
                conn.execute.assert_called_once_with("select site.environment()")
                conn.rollback.assert_called_once()          # no transaction left open by the check
                conn.close.assert_not_called()

    def test_a_run_that_may_write_never_reaches_another_projects_address(self):
        # staging given production's address (a secret that fell back, a pasted line): refused
        # before anything is sent. And the same for an address that names no project.
        import thecornerfc.pipeline.db as db
        cases = [
            ("staging", {}, POOLER.format(PRODUCTION)),
            ("staging", {}, DIRECT.format(PRODUCTION)),
            ("staging", {}, "postgresql://postgres:pw@aws-0-eu-central-1.pooler.supabase.com:5432/postgres"),
            ("staging", {}, "postgresql://u:p@localhost:5432/postgres"),
            ("staging", {}, DIRECT.format(STAGING).replace("postgres:pw", f"postgres.{PRODUCTION}:pw")),  # says both
            ("staging", {"GITHUB_ACTIONS": "true"}, POOLER.format(PRODUCTION)),
            ("production", {"GITHUB_ACTIONS": "true"}, POOLER.format(STAGING)),
            ("production", {"GITHUB_ACTIONS": "true"}, "postgresql://writer@example/db"),
            ("", {"GITHUB_ACTIONS": "true"}, POOLER.format(PRODUCTION)),      # a job that names no environment
        ]
        for env, more, url in cases:
            with self.subTest(env=env, url=url.split("@")[1], user=url.split("//")[1].split(":")[0]):
                config = load_config({"THECORNERFC_ENV": env, "THECORNERFC_READ_ONLY": "false",
                                      "DATABASE_URL": url, **more})
                self.assertTrue(config.writes_allowed())
                with patch.object(config, "PROJECTS", {"production": PRODUCTION, "staging": STAGING}), \
                     patch.object(db, "config", config), patch.object(db.psycopg, "connect") as connect:
                    with self.assertRaises(config.SafetyError):
                        db.connect()
                connect.assert_not_called()

    def test_staging_cannot_be_written_until_its_project_is_recorded(self):
        import thecornerfc.pipeline.db as db
        config = load_config({"THECORNERFC_ENV": "staging", "THECORNERFC_READ_ONLY": "false",
                              "DATABASE_URL": POOLER.format(STAGING)})
        self.assertEqual(config.PROJECTS["production"], PRODUCTION)
        self.assertNotEqual(config.PROJECTS["staging"], PRODUCTION)
        with patch.object(config, "PROJECTS", {"production": PRODUCTION, "staging": ""}), \
             patch.object(db, "config", config), patch.object(db.psycopg, "connect") as connect:
            with self.assertRaisesRegex(config.SafetyError, "No Supabase project is recorded"):
                db.connect()
        connect.assert_not_called()

    def test_a_database_that_does_not_say_it_is_this_environment_is_closed_unused(self):
        import thecornerfc.pipeline.db as db
        for env, says in (("staging", "production"), ("staging", None), ("staging", RuntimeError("no such function")),
                          ("production", "staging"), ("production", None), ("production", RuntimeError("no such function"))):
            with self.subTest(env=env, says=says):
                config = load_config({"THECORNERFC_ENV": env, "THECORNERFC_READ_ONLY": "false",
                                      "GITHUB_ACTIONS": "true",
                                      "DATABASE_URL": POOLER.format(STAGING if env == "staging" else PRODUCTION)})
                conn = a_database(says)
                with patch.object(config, "PROJECTS", {"production": PRODUCTION, "staging": STAGING}), \
                     patch.object(db, "config", config), patch.object(db.psycopg, "connect", return_value=conn):
                    with self.assertRaises(config.SafetyError):
                        db.connect()
                conn.close.assert_called_once()

    def test_local_staging_writes_once_the_address_and_the_database_both_say_staging(self):
        import thecornerfc.pipeline.db as db
        config = load_config({"THECORNERFC_ENV": "staging", "THECORNERFC_READ_ONLY": "false",
                              "DATABASE_URL": POOLER.format(STAGING)})
        conn = a_database("staging")
        with patch.object(config, "PROJECTS", {"production": PRODUCTION, "staging": STAGING}), \
             patch.object(db, "config", config), patch.object(db.psycopg, "connect", return_value=conn):
            self.assertIs(db.connect(), conn)
        self.assertFalse(conn.read_only)

    def test_the_project_is_read_from_every_form_of_address(self):
        config = load_config({})
        for url, project in (
            (POOLER.format(PRODUCTION), PRODUCTION),
            (DIRECT.format(PRODUCTION), PRODUCTION),
            (POOLER.format(PRODUCTION).replace("postgres.", "local_readonly."), PRODUCTION),
            (f"postgresql://postgres:pw@pooler.example:6543/postgres?options=reference%3D{STAGING}", STAGING),
            (f"host=db.{STAGING}.supabase.co user=postgres password=pw dbname=postgres", STAGING),
            ("postgresql://postgres:pw@db.example.test:5432/postgres", None),
            ("", None),
            ("not an address at all ://", None),
        ):
            with self.subTest(url=url[:40]):
                self.assertEqual(config.database_project(url), project)

    def test_a_refusal_never_shows_the_address(self):
        config = load_config({"THECORNERFC_ENV": "staging", "THECORNERFC_READ_ONLY": "false"})
        url = POOLER.format(PRODUCTION).replace(":pw@", ":a-secret-password@")
        with patch.object(config, "PROJECTS", {"production": PRODUCTION, "staging": STAGING}):
            with self.assertRaises(config.SafetyError) as refused:
                config.require_write_address(url)
        for part in ("a-secret-password", PRODUCTION, "pooler.supabase.com"):
            self.assertNotIn(part, str(refused.exception))

    def test_a_destructive_local_command_needs_the_environments_name_typed_at_a_terminal(self):
        config = load_config({"THECORNERFC_ENV": "staging", "THECORNERFC_READ_ONLY": "false"})
        with patch("sys.stdin") as stdin, patch("builtins.print"):
            stdin.isatty.return_value = False               # run unattended: refused, nothing asked
            with patch("builtins.input") as asked, self.assertRaises(config.SafetyError):
                config.confirm_destructive("init-db")
            asked.assert_not_called()
            stdin.isatty.return_value = True
            for typed in ("", "y", "yes", "production", "STAGING "):
                with self.subTest(typed=typed), patch("builtins.input", return_value=typed):
                    if typed.strip() == "staging":
                        config.confirm_destructive("init-db")
                    else:
                        with self.assertRaises(config.SafetyError):
                            config.confirm_destructive("init-db")
            with patch("builtins.input", return_value="staging"):
                config.confirm_destructive("init-db")

    def test_init_db_and_removing_a_person_ask_before_they_change_anything(self):
        import inspect
        import thecornerfc.__main__ as main
        source = inspect.getsource(main._execute)
        self.assertLess(source.index('config.confirm_destructive("init-db")'), source.index("init_schema(conn)"))
        self.assertLess(source.index('config.confirm_destructive("suppress --apply")'), source.index("suppression.remove("))

    def test_an_actions_run_left_read_only_stays_read_only(self):
        config = load_config({
            "GITHUB_ACTIONS": "true",
            "READ_ONLY_DATABASE_URL": "postgresql://readonly@example/db",
            "DATABASE_URL": "postgresql://writer@example/db",
        })

        self.assertTrue(config.READ_ONLY)
        self.assertEqual(config.DATABASE_URL, "postgresql://readonly@example/db")

    def test_api_client_refuses_no_api_mode_before_network_setup(self):
        load_config({
            "THECORNERFC_MODE": "local",
            "THECORNERFC_NO_API": "true",
            "API_FOOTBALL_KEY": "example-key",
        })
        import thecornerfc.pipeline.api as api
        api = importlib.reload(api)

        with self.assertRaises(api.config.SafetyError):
            api.ApiFootball()

    def test_the_identity_migration_is_in_the_schema_and_carries_no_value(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        migration = (root / "db/migrations/20261012_database_environment.sql").read_text()
        self.assertIn(migration, (root / "db/schema.sql").read_text())
        # the same file runs in both databases, so it must not say which one it is in
        statements = "\n".join(line for line in migration.splitlines() if not line.lstrip().startswith("--"))
        self.assertNotIn("INSERT INTO", statements.upper())
        for needed in ("BEFORE INSERT OR UPDATE OR DELETE ON site.settings", "BEFORE TRUNCATE ON site.settings",
                       "REVOKE ALL ON FUNCTION site.environment() FROM PUBLIC"):
            self.assertIn(needed, migration)

    def test_every_job_that_writes_names_production(self):
        from pathlib import Path
        for path in sorted((Path(__file__).resolve().parents[1] / ".github/workflows").glob("*.yml")):
            text = path.read_text()
            if "secrets.DATABASE_URL" in text:
                with self.subTest(workflow=path.name):
                    self.assertIn("THECORNERFC_ENV: production", text)


if __name__ == "__main__":
    unittest.main()

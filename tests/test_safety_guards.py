import importlib
import os
import unittest
from unittest.mock import patch


def load_config(env):
    with patch.dict(os.environ, env, clear=True):
        import thecornerfc.config as config
        return importlib.reload(config)


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

    def test_local_override_allows_intentional_db_writes_and_api_access(self):
        config = load_config({
            "THECORNERFC_MODE": "local",
            "THECORNERFC_READ_ONLY": "false",
            "THECORNERFC_NO_API": "false",
            "THECORNERFC_LOCAL_OVERRIDE": "I_UNDERSTAND_THIS_CAN_WRITE_PRODUCTION_DATA_AND_USE_API_QUOTA",
            "DATABASE_URL": "postgresql://writer@example/db",
            "API_FOOTBALL_KEY": "example-key",
        })

        config.require_db_write("rank")
        config.require_api_access("status")

    def test_read_only_switched_off_alone_still_connects_read_only(self):
        # no Actions run and no override token: the flag on its own must not reach the write address
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

    def test_an_actions_run_and_a_local_override_use_the_write_address(self):
        actions = load_config({
            "GITHUB_ACTIONS": "true",
            "THECORNERFC_MODE": "production",
            "THECORNERFC_READ_ONLY": "false",
            "READ_ONLY_DATABASE_URL": "postgresql://readonly@example/db",
            "DATABASE_URL": "postgresql://writer@example/db",
        })
        self.assertTrue(actions.writes_allowed())
        self.assertEqual(actions.DATABASE_URL, "postgresql://writer@example/db")
        actions.require_db_write("nightly")
        import thecornerfc.pipeline.db as db
        with patch.object(db, "config", actions), patch.object(db.psycopg, "connect") as connect:
            connect.return_value.read_only = False
            conn = db.connect()
        self.assertFalse(conn.read_only)

        local = load_config({
            "THECORNERFC_READ_ONLY": "false",
            "THECORNERFC_LOCAL_OVERRIDE": "I_UNDERSTAND_THIS_CAN_WRITE_PRODUCTION_DATA_AND_USE_API_QUOTA",
            "DATABASE_URL": "postgresql://writer@example/db",
        })
        self.assertEqual(local.DATABASE_URL, "postgresql://writer@example/db")

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


if __name__ == "__main__":
    unittest.main()

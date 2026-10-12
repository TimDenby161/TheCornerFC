"""What the one-off copy from production to staging may take (scripts/staging_copy.py): only the
football tables on its list, never accounts, payment, fantasy game data or the evidence record.
No database: these read the script's own list and the schema file."""
import importlib.util
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("staging_copy", ROOT / "scripts/staging_copy.py")
copy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(copy)
SCHEMA = (ROOT / "db/schema.sql").read_text().lower()


class StagingCopyTests(unittest.TestCase):
    def test_nothing_private_or_owner_only_is_on_the_list(self):
        for table in copy.COPIED:
            for never in copy.NEVER:
                with self.subTest(table=table, never=never):
                    self.assertNotIn(never, table)
                    self.assertNotIn(never, copy.query(table).split(" from public." + table, 1)[1])
        for must_be_barred in ("auth.", "subscriptions", "fpl_", "fantasy_", "snapshot"):
            self.assertIn(must_be_barred, copy.NEVER)

    def test_every_copied_table_is_a_table_of_the_public_schema(self):
        for table in copy.COPIED:
            with self.subTest(table=table):
                self.assertRegex(SCHEMA, r"create table if not exists " + re.escape(table) + r"\s*\(")

    def test_a_query_reads_one_table_of_production_and_names_only_whole_numbers(self):
        for table in copy.COPIED:
            sql = copy.query(table, leagues=(39, 40))
            with self.subTest(table=table):
                self.assertTrue(sql.startswith(f"select {{columns}} from public.{table} where "))
                self.assertNotIn(";", sql)
                self.assertNotIn("{leagues}", sql)
                self.assertNotRegex(sql.lower(), r"\b(insert|update|delete|truncate|drop|alter|create|grant)\b")

    def test_parents_are_copied_before_the_rows_that_point_at_them(self):
        order = list(copy.COPIED)
        for parent, child in (("leagues", "fixtures"), ("venues", "teams"), ("teams", "fixtures"), ("teams", "team_seasons"),
                              ("fixtures", "fixture_team_stats"), ("bookmakers", "odds"), ("bet_types", "odds"),
                              ("players", "player_seasons"), ("teams", "standings"), ("leagues", "league_seasons")):
            with self.subTest(parent=parent, child=child):
                self.assertLess(order.index(parent), order.index(child))

    def test_a_database_built_from_the_schema_file_is_shut_to_the_public_key_as_the_live_one_is(self):
        # the migration that takes every table grant from the public key must be in the schema
        # file, and before the site's own functions, which grant themselves after it
        schema = (ROOT / "db/schema.sql").read_text()
        grants = (ROOT / "db/migrations/20261001_anon_grants.sql").read_text()
        self.assertIn(grants, schema)
        at = schema.index(grants)
        self.assertLess(schema.index("CREATE OR REPLACE FUNCTION fpl_owner_data(p_entry integer)"), at)
        for later in ("CREATE SCHEMA IF NOT EXISTS site;", "GRANT EXECUTE ON FUNCTION public.site_doc(text, text)",
                      "GRANT EXECUTE ON FUNCTION public.my_subscription()"):
            self.assertGreater(schema.index(later), at, later)

    def test_it_reads_production_read_only_checks_staging_and_asks_first(self):
        source = (ROOT / "scripts/staging_copy.py").read_text()
        self.assertIn("default_transaction_read_only=on", source)
        self.assertIn("src.read_only = True", source)
        self.assertIn('environment.prove("production"', source)          # refuses a role that can write
        self.assertIn('if said != "staging"', source)
        self.assertLess(source.index('input("Type staging to go on: ")'), source.index("writing.write(block)"))
        self.assertNotIn("getenv", source)                                # the addresses come from the profiles only


if __name__ == "__main__":
    unittest.main()

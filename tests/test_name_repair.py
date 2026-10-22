import unittest
from pathlib import Path

from thecornerfc.pipeline.api import repair_payload, repair_text

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "db/migrations/20261022_repair_player_names.sql"
PART = ROOT / "db/migrations/20261022_repair_player_names_part.sql"


class NameRepairTests(unittest.TestCase):
    """API-Football sends some names as UTF-8 read as Latin-1 (T-049): they are put back as they
    arrive, and the rows already stored by a migration."""

    def test_garbled_names_are_put_back(self):
        for garbled, right in (("M. CvetkoviÄ\x87", "M. Cvetković"), ("O. SÃ¸e", "O. Søe"), ("Rafael LuÃ\xads", "Rafael Luís"),
                               ("UrbaÅ\x84ski", "Urbański"), ("C. Inao OulaÃ¯", "C. Inao Oulaï"), ("JoÃ£o Mendes", "João Mendes"),
                               ("â€™", "’")):                  # Windows-1252 as well as Latin-1
            self.assertEqual(repair_text(garbled), right)

    def test_real_names_are_left_alone(self):
        for name in ("Ãvila", "Ñañez", "Müller", "Søe", "João", "José María", "Ó Brien", "Łukasz", "Çağlar Söyüncü", "", None, 7):
            self.assertEqual(repair_text(name), name)

    def test_every_string_in_a_payload_is_repaired(self):
        data = {"response": [{"player": {"id": 1, "name": "S. PirgiÄ\x87", "firstname": "Stefan"}, "statistics": [{"team": {"name": "Ok"}}]}]}
        self.assertEqual(repair_payload(data)["response"][0]["player"], {"id": 1, "name": "S. Pirgić", "firstname": "Stefan"})
        self.assertEqual(repair_payload(data)["response"][0]["statistics"], [{"team": {"name": "Ok"}}])

    def test_the_migration_is_in_the_schema_and_repairs_the_same_way(self):
        sql = MIGRATION.read_text()
        self.assertIn(sql, (ROOT / "db/schema.sql").read_text())
        self.assertIn("convert_from(convert_to(t, 'LATIN1'), 'UTF8')", sql)
        self.assertIn("EXCEPTION WHEN others THEN\n    RETURN t;", sql)       # anything that doesn't read back stays as it is
        part = PART.read_text()
        self.assertIn(part, (ROOT / "db/schema.sql").read_text())
        self.assertIn("convert_to(m, 'WIN1252')", part)                    # one character at a time, both forms


if __name__ == "__main__":
    unittest.main()

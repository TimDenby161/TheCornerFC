"""Two match models side by side (MC-0029): the migration that holds the switch and the
challenger's predictions."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / 'db/migrations/20261014_challenger_model.sql'


class MigrationTest(unittest.TestCase):
    def test_it_is_in_the_schema_word_for_word(self):
        self.assertIn(MIGRATION.read_text(), (ROOT / 'db/schema.sql').read_text())

    def test_it_is_shut_to_the_public_key(self):
        text = MIGRATION.read_text()
        for table in ('match_model_switch', 'match_model_switches', 'challenger_predictions'):
            self.assertIn(f'ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY;', text)
        self.assertIn("REVOKE ALL ON public.match_model_switch, public.match_model_switches, public.challenger_predictions FROM %I", text)
        self.assertNotIn('TO anon', text)
        for fn in ('admin_match_model()', 'admin_set_match_model(text)'):
            self.assertIn(f'GRANT EXECUTE ON FUNCTION public.{fn} TO authenticated;', text)
        self.assertEqual(text.count('SECURITY DEFINER SET search_path = '), 2)

    def test_only_an_administrator_can_switch(self):
        text = MIGRATION.read_text()
        body = text[text.index('FUNCTION public.admin_set_match_model'):text.index('REVOKE ALL ON public.match_model_switch')]
        self.assertIn("IF NOT site.is_admin() OR p_live IS NULL OR p_live NOT IN ('base', 'a18') THEN", body)


if __name__ == '__main__':
    unittest.main()

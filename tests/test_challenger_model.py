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


FIX = ROOT / 'db/migrations/20261014_match_model_switch_fix.sql'
# COALESCE, NULLIF, GREATEST and LEAST are SQL grammar, not functions: pg_catalog.coalesce(...)
# fails on every call. The challenger migration had it and is mended by FIX.
GRAMMAR = ('pg_catalog.coalesce', 'pg_catalog.nullif', 'pg_catalog.greatest', 'pg_catalog.least')


class SwitchFixTest(unittest.TestCase):
    def test_it_is_in_the_schema_word_for_word(self):
        self.assertIn(FIX.read_text(), (ROOT / 'db/schema.sql').read_text())

    def test_it_mends_the_switch_answer(self):
        text = FIX.read_text()
        self.assertIn('CREATE OR REPLACE FUNCTION public.admin_match_model() RETURNS jsonb', text)
        self.assertIn('IF NOT site.is_admin() THEN', text)
        self.assertIn("SELECT COALESCE(pg_catalog.jsonb_agg(", text)

    def test_no_later_migration_calls_grammar_as_a_function(self):
        for path in sorted((ROOT / 'db/migrations').glob('*.sql')):
            if path == MIGRATION:
                continue
            text = path.read_text().lower()
            for word in GRAMMAR:
                self.assertNotIn(word + '(', text, f'{path.name}: {word}')


COMPARE = ROOT / 'db/migrations/20261014_match_model_compare.sql'


class CompareTest(unittest.TestCase):
    def test_it_is_in_the_schema_word_for_word(self):
        self.assertIn(COMPARE.read_text(), (ROOT / 'db/schema.sql').read_text())

    def test_it_answers_an_administrator_only_and_reads_only(self):
        text = COMPARE.read_text()
        self.assertIn('LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = \'\' AS $$', text)
        self.assertIn('IF NOT site.is_admin() THEN', text)
        self.assertIn("EXECUTE format('REVOKE ALL ON FUNCTION public.admin_match_model_compare() FROM %I', r);", text)
        self.assertIn('GRANT EXECUTE ON FUNCTION public.admin_match_model_compare() TO authenticated;', text)
        body = text.split('BEGIN;', 1)[1].split('COMMIT;', 1)[0].upper()
        for write in ('INSERT ', 'UPDATE ', 'DELETE ', 'CREATE TABLE', 'CREATE TEMP'):
            self.assertNotIn(write, body)

    def test_it_scores_p18s_population(self):
        text = COMPARE.read_text()
        self.assertIn("f.kickoff >= '2026-10-15'::timestamptz AND f.status_short IN ('FT', 'AET', 'PEN')", text)
        self.assertIn('c.captured_at < f.kickoff AND c.written_at < f.kickoff', text)


MARKET = ROOT / 'db/migrations/20261015_match_model_compare_market.sql'


class CompareMarketTest(unittest.TestCase):
    def test_it_is_in_the_schema_word_for_word(self):
        self.assertIn(MARKET.read_text(), (ROOT / 'db/schema.sql').read_text())

    def test_it_answers_an_administrator_only_and_reads_only(self):
        text = MARKET.read_text()
        self.assertIn('IF NOT site.is_admin() THEN', text)
        self.assertIn('GRANT EXECUTE ON FUNCTION public.admin_match_model_compare() TO authenticated;', text)
        body = text.split('BEGIN;', 1)[1].split('COMMIT;', 1)[0].upper()
        for write in ('INSERT ', 'UPDATE ', 'DELETE ', 'CREATE TABLE', 'CREATE TEMP'):
            self.assertNotIn(write, body)

    def test_the_bookmakers_are_the_stats_pages_and_read_on_the_same_matches(self):
        text = MARKET.read_text()
        # each bookmaker's whole home/draw/away set, its margin removed, averaged (site_record.market_consensus)
        self.assertIn("(1 / o.odd::float8) / pg_catalog.sum(1 / o.odd::float8) OVER w AS p", text)
        self.assertIn("WINDOW w AS (PARTITION BY o.fixture_id, o.bookmaker_id)) b\n        WHERE b.k = 3", text)
        # the two models again on exactly the priced matches
        self.assertIn("SELECT p.model || '_priced', p.y, p.p_home, p.p_draw, p.p_away", text)
        self.assertIn("FROM paired p WHERE p.fixture_id IN (SELECT m.fixture_id FROM priced m)", text)


if __name__ == '__main__':
    unittest.main()

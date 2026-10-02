"""My FPL team: fpl_team from FPL's manager responses, FPL data kept off the public site (owner
only, audit L3), the lock-in and owner-data migrations' grants, and the browser planner's own tests
(tests/fpl_planner.test.mjs) under node."""
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from thecornerfc import export, fpl_team

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / 'db/migrations/20260930_fpl_team_locks.sql'
OWNER_MIGRATION = ROOT / 'db/migrations/20261003_fpl_owner_docs.sql'
NOW = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
BOOTSTRAP = {
    'events': [{'id': 5, 'deadline_time': '2026-09-18T17:30:00Z', 'finished': True},
               {'id': 6, 'deadline_time': '2026-10-10T10:00:00Z', 'finished': False}],
    'chips': [{'id': 1, 'name': 'wildcard', 'start_event': 2, 'stop_event': 19},
              {'id': 2, 'name': 'wildcard', 'start_event': 20, 'stop_event': 38},
              {'id': 5, 'name': '3xc', 'start_event': 1, 'stop_event': 19}],
    'elements': [
        {'id': 1, 'web_name': 'Raya', 'team': 1, 'element_type': 1, 'now_cost': 61, 'cost_change_start': 1, 'status': 'a'},
        {'id': 12, 'web_name': 'Saka', 'team': 1, 'element_type': 3, 'now_cost': 98, 'cost_change_start': 3, 'status': 'd',
         'chance_of_playing_next_round': 75, 'news': 'Knock'},
        {'id': 95, 'web_name': 'Dango', 'team': 4, 'element_type': 3, 'now_cost': 63, 'cost_change_start': -2, 'status': 'a'},
        {'id': 300, 'web_name': 'Stach', 'team': 11, 'element_type': 3, 'now_cost': 60, 'cost_change_start': 0, 'status': 'a'}]}
ENTRY = {'id': 3996593, 'name': 'AI XI', 'started_event': 1, 'current_event': 5,
         'summary_overall_points': 277, 'summary_overall_rank': 6522593}
# The owner's own season so far: two transfers (a hit) in GW2 and GW3, none in GW4, two free in GW5
HISTORY = {'current': [{'event': 1, 'points': 55, 'event_transfers': 0, 'event_transfers_cost': 0},
                       {'event': 2, 'points': 65, 'event_transfers': 2, 'event_transfers_cost': 4},
                       {'event': 3, 'points': 45, 'event_transfers': 2, 'event_transfers_cost': 4},
                       {'event': 4, 'points': 68, 'event_transfers': 0, 'event_transfers_cost': 0},
                       {'event': 5, 'points': 52, 'event_transfers': 2, 'event_transfers_cost': 0}],
           'chips': []}
TRANSFERS = [{'element_in': 95, 'element_in_cost': 65, 'element_out': 7, 'element_out_cost': 60, 'event': 3,
              'time': '2026-09-04T15:31:37Z'},
             {'element_in': 12, 'element_in_cost': 95, 'element_out': 8, 'element_out_cost': 74, 'event': 5,
              'time': '2026-09-17T09:07:51Z'}]
PICKS = {'entry_history': {'bank': 7}, 'picks': [{'element': 1, 'position': 1}, {'element': 95, 'position': 3},
                                                 {'element': 12, 'position': 2}]}


class TeamTests(unittest.TestCase):
    def test_selling_price_keeps_half_a_rise_and_all_of_a_fall(self):
        self.assertEqual(fpl_team.selling_price(98, 95), 96)
        self.assertEqual(fpl_team.selling_price(96, 95), 95)       # half of 0.1 rounds down
        self.assertEqual(fpl_team.selling_price(63, 65), 63)

    def test_free_transfers_follow_fpl_rules(self):
        self.assertEqual(fpl_team.free_transfers(HISTORY, 1), 1)
        rolled = {'current': [{'event': e, 'event_transfers': 0} for e in range(1, 10)], 'chips': []}
        self.assertEqual(fpl_team.free_transfers(rolled, 1), 5)
        # a Wildcard keeps the banked transfers and adds none: GW2-3 roll to 3, the GW4 wildcard keeps 3
        wc = {'current': [{'event': 1}, {'event': 2}, {'event': 3}, {'event': 4, 'event_transfers': 9}],
              'chips': [{'name': 'wildcard', 'event': 4}]}
        self.assertEqual(fpl_team.free_transfers(wc, 1), 3)
        late = {'current': [{'event': 4}, {'event': 5, 'event_transfers': 0}], 'chips': []}
        self.assertEqual(fpl_team.free_transfers(late, 4), 2)     # joined in GW4

    def test_chip_windows_mark_the_played_one_only(self):
        rows = fpl_team.chip_windows(BOOTSTRAP, {'chips': [{'name': 'wildcard', 'event': 4}]})
        self.assertEqual([(r['name'], r['start'], r['played']) for r in rows],
                         [('3xc', 1, None), ('wildcard', 2, 4), ('wildcard', 20, None)])

    def test_payload_squad_prices_mapping_and_transfers_already_made(self):
        made = TRANSFERS + [{'element_in': 300, 'element_in_cost': 60, 'element_out': 95, 'element_out_cost': 63,
                             'event': 6, 'time': '2026-10-01T09:00:00Z'}]
        p = fpl_team.team_payload(BOOTSTRAP, ENTRY, HISTORY, made, PICKS, {1: 19465, 12: 1460, 300: 177665}, {1: 42, 11: 63}, now=NOW)
        self.assertEqual((p['next_event'], p['current_event'], p['free_transfers'], p['season']), (6, 5, 1, 2026))
        self.assertEqual(p['bank'], 10)                                  # 0.7 + 6.3 - 6.0
        self.assertEqual([s['fpl'] for s in p['squad']], [1, 12, 300])   # pick order, Stach in for Dango
        raya, saka, stach = p['squad']
        self.assertEqual((raya['bought'], raya['sell'], raya['api'], raya['team'], raya['pos']), (60, 60, 19465, 42, 'G'))
        self.assertEqual((saka['bought'], saka['sell'], saka['chance']), (95, 96, 75))
        self.assertNotIn('news', saka)             # FPL's free-text injury news isn't published
        self.assertEqual((stach['api'], stach['team'], stach['sell']), (177665, 63, 60))
        self.assertEqual(p['made'], [{'out': 95, 'in': 300, 'out_cost': 63, 'in_cost': 60, 'out_name': 'Dango', 'in_name': 'Stach'}])
        self.assertEqual(p['history'][1], {'event': 2, 'points': 65, 'rank': None, 'transfers': 2, 'hits': 4, 'bench': None})
        json.dumps(p, allow_nan=False)

    def test_export_drops_the_old_public_fpl_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'data'
            out.mkdir()
            (out / 'fpl_team.json').write_text('{"entry": 1}')
            (out / 'fpl_predictions.json').write_text('{}')
            with mock.patch.object(export, 'validate_export'):
                export._publish_export(lambda staged: (staged / 'matches.json').write_text('{}'), out)
            self.assertEqual(sorted(f.name for f in out.iterdir()), ['matches.json'])

    def test_team_is_stored_for_the_owner_not_published(self):
        conn = mock.MagicMock()
        with mock.patch.object(export.config, 'require_db_write'):
            export.store_owner_doc(conn, 'fpl_team', {'entry': 1, 'name': 'É'})
        sql, (name, doc) = conn.execute.call_args.args
        self.assertIn('insert into fpl_owner_docs', sql)
        self.assertEqual((name, json.loads(doc)), ('fpl_team', {'entry': 1, 'name': 'É'}))
        conn.commit.assert_called_once()

    def test_owner_docs_are_not_written_from_a_read_only_run(self):
        conn = mock.MagicMock()
        with mock.patch.object(export.config, 'READ_ONLY', True), self.assertRaises(Exception):
            export.store_owner_doc(conn, 'fpl_team', {})
        conn.execute.assert_not_called()

    def test_site_has_no_public_fpl_data(self):
        self.assertFalse((ROOT / 'docs/data/fpl_predictions.json').exists())
        self.assertFalse((ROOT / 'docs/data/fpl_team.json').exists())
        app = (ROOT / 'docs/assets/app.js').read_text()
        self.assertNotIn('data/fpl_predictions.json', app)
        self.assertNotIn('data/fpl_team.json', app)
        self.assertNotIn('fpl_team_locks?', app)          # lock-ins come back with fpl_owner_data
        self.assertIn('rpc/fpl_owner_data', app)


class LockMigrationTests(unittest.TestCase):
    def test_schema_contains_migration(self):
        self.assertIn(MIGRATION.read_text(), (ROOT / 'db/schema.sql').read_text())

    def test_anon_reads_locks_and_calls_the_two_functions_only(self):
        sql = MIGRATION.read_text()
        for table in ('fpl_team_locks', 'fpl_team_keys', 'fpl_team_key_failures'):
            self.assertIn(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY', sql)
        self.assertIn("REVOKE ALL ON fpl_team_locks, fpl_team_keys, fpl_team_key_failures FROM %I", sql)
        self.assertIn("GRANT SELECT ON fpl_team_locks TO %I", sql)
        self.assertIn("REVOKE ALL ON FUNCTION fpl_team_key_check(integer, text) FROM %I", sql)
        self.assertNotIn('GRANT EXECUTE ON FUNCTION fpl_team_key_check', sql)
        self.assertEqual(sql.count('SECURITY DEFINER SET search_path = public, extensions, pg_temp'), 3)
        self.assertIn("REVOKE ALL ON upcoming_predictions FROM %I", sql)

    def test_owner_data_needs_the_passphrase_and_anon_reads_no_table(self):
        sql = OWNER_MIGRATION.read_text()
        self.assertIn('ALTER TABLE fpl_owner_docs ENABLE ROW LEVEL SECURITY', sql)
        self.assertIn("why text := fpl_team_key_check(p_entry, p_key);", sql)
        self.assertIn('SECURITY DEFINER SET search_path = public, extensions, pg_temp', sql)
        self.assertIn("REVOKE ALL ON fpl_owner_docs FROM %I", sql)
        self.assertIn("REVOKE ALL ON fpl_team_locks FROM %I", sql)
        self.assertIn('DROP POLICY IF EXISTS fpl_team_locks_read ON fpl_team_locks', sql)
        self.assertEqual(sql.count('GRANT '), 1)
        self.assertIn("GRANT EXECUTE ON FUNCTION fpl_owner_data(integer, text) TO %I", sql)
        grants = (ROOT / 'db/migrations/20261001_anon_grants.sql').read_text()
        self.assertNotIn("GRANT SELECT ON fpl_team_locks", grants)
        self.assertIn("GRANT EXECUTE ON FUNCTION fpl_owner_data(integer, text) TO %I", grants)

    def test_page_allows_only_this_supabase_project(self):
        page = (ROOT / 'docs/index.html').read_text()
        app = (ROOT / 'docs/assets/app.js').read_text()
        self.assertIn("connect-src 'self' https://bookkurhdabdeccckjbn.supabase.co;", page)
        self.assertIn('url: "https://bookkurhdabdeccckjbn.supabase.co"', app)
        self.assertIn('<script src="assets/fpl-planner.js"></script>', page)


@unittest.skipUnless(shutil.which('node'), 'node is not installed')
class PlannerTests(unittest.TestCase):
    def test_planner(self):
        run = subprocess.run(['node', '--test', str(ROOT / 'tests/fpl_planner.test.mjs')],
                             capture_output=True, text=True, timeout=120)
        self.assertEqual(run.returncode, 0, run.stdout[-3000:] + run.stderr[-2000:])


if __name__ == '__main__':
    unittest.main()

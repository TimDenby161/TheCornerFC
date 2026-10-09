import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from thecornerfc.pipeline import api, usage
from thecornerfc import config


class UsageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        for name, value in dict(API_LEDGER_PATH=str(Path(self.temp.name) / 'ledger.db'),
                                NO_API=False, GITHUB_ACTIONS=True, API_RUN_BUDGET=0).items():
            patcher = patch.object(config, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def response(self, status=200, quota='500', payload=None):
        response = Mock(status_code=status, headers={'x-ratelimit-requests-remaining': quota})
        response.json.return_value = payload if payload is not None else {'response': [1, 2], 'errors': []}
        return response

    @patch('thecornerfc.pipeline.api.time.sleep')
    def test_retry_and_success_are_recorded_without_secrets(self, sleep):
        client = api.ApiFootball(api_key='secret', min_interval=0)
        client.session.get = Mock(side_effect=[self.response(500), self.response()])
        self.assertEqual(client.get('fixtures', key='secret'), [1, 2])
        with usage.connect() as conn:
            rows = conn.execute('SELECT http_status, success, records_returned FROM api_calls').fetchall()
            self.assertEqual(rows, [(500, 0, 2), (200, 1, 2)])
            self.assertNotIn('secret', str(conn.execute('SELECT * FROM api_calls').fetchall()))
        self.assertIn('fixtures=2', usage.report())

    @patch('thecornerfc.pipeline.api.time.sleep')
    def test_reserve_blocks_retry(self, sleep):
        client = api.ApiFootball(api_key='secret', daily_reserve=200, min_interval=0)
        client.session.get = Mock(return_value=self.response(429, '200'))
        with self.assertRaises(api.QuotaExhausted):
            client.get('fixtures')
        self.assertEqual(client.session.get.call_count, 1)

    @patch('thecornerfc.pipeline.api.time.sleep')
    def test_transport_error_and_body_error(self, sleep):
        client = api.ApiFootball(api_key='secret', min_interval=0)
        client.session.get = Mock(side_effect=[api.requests.ConnectionError('secret'),
            self.response(payload={'response': [], 'errors': {'bad': 'value'}})])
        with self.assertRaises(RuntimeError):
            client.get('fixtures')
        with usage.connect() as conn:
            self.assertEqual(conn.execute('SELECT error_type FROM api_calls').fetchall(), [('transport',), ('api',)])

    def test_budget_and_no_api_reporting(self):
        with patch.object(config, 'API_RUN_BUDGET', 1):
            client = api.ApiFootball(api_key='secret', min_interval=0)
            client.session.get = Mock(return_value=self.response())
            client.get('fixtures')
            with self.assertRaises(api.QuotaExhausted):
                client.get('fixtures')
        with patch.object(config, 'NO_API', True):
            self.assertIn('fixtures=1', usage.report())
            with self.assertRaises(config.SafetyError):
                client.get('fixtures')

    def test_prune_drops_only_calls_older_than_the_window(self):
        usage.record('fixtures', {}, 200, 1, 500, 0.1, True, None)
        with usage.connect() as conn:
            conn.execute("INSERT INTO api_calls SELECT NULL,'2026-01-01T00:00:00+00:00',endpoint,parameter_hash,workflow,"
                         "run_id,process_id,command,http_status,records_returned,quota_remaining,duration_ms,success,error_type FROM api_calls")
        self.assertEqual(usage.prune(), 1)
        self.assertEqual(usage.prune(), 0)
        with usage.connect() as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM api_calls').fetchone()[0], 1)

    def test_pagination_counts_each_page(self):
        client = api.ApiFootball(api_key='secret', min_interval=0)
        client.session.get = Mock(side_effect=[
            self.response(payload={'response': [1], 'paging': {'total': 2}}),
            self.response(payload={'response': [2], 'paging': {'total': 2}})])
        self.assertEqual(client.get_all_pages('players'), [1, 2])
        with usage.connect() as conn:
            self.assertEqual(conn.execute('SELECT count(DISTINCT parameter_hash) FROM api_calls').fetchone()[0], 2)

    def test_preflight_rejects_budget_above_available_quota(self):
        from thecornerfc.__main__ import main
        with patch.object(config, 'API_RUN_BUDGET', 1000), \
             patch('thecornerfc.__main__.ApiFootball') as factory, \
             patch('thecornerfc.pipeline.usage.publish'):
            factory.return_value.daily_remaining = 500
            factory.return_value.daily_reserve = 200
            with self.assertRaises(api.QuotaExhausted):
                main(['preflight', '--leagues', '39', '--seasons', '2025'])
            factory.return_value.get.assert_called_once_with('status')

"""Accounts: unconfirmed sign-ups are deleted after the days the privacy page gives."""
from pathlib import Path
import unittest
from unittest import mock

from thecornerfc.privacy import accounts

ROOT = Path(__file__).resolve().parents[1]


class RetentionTests(unittest.TestCase):
    def test_deletes_only_unconfirmed_sign_ups_past_the_limit(self):
        conn = mock.MagicMock()
        conn.execute.return_value.fetchone.return_value = ('auth.users',)
        conn.execute.return_value.rowcount = 2
        self.assertEqual(accounts.prune_unconfirmed(conn), 2)
        sql, params = conn.execute.call_args.args
        self.assertIn('email_confirmed_at is null', sql)
        self.assertEqual(params, (accounts.UNCONFIRMED_DAYS,))
        conn.commit.assert_called_once()

    def test_does_nothing_without_supabase_auth(self):
        conn = mock.MagicMock()
        conn.execute.return_value.fetchone.return_value = (None,)
        self.assertIsNone(accounts.prune_unconfirmed(conn))
        self.assertEqual(conn.execute.call_count, 1)

    def test_a_failure_does_not_fail_the_run(self):
        conn = mock.MagicMock()
        conn.execute.side_effect = RuntimeError('permission denied')
        self.assertIsNone(accounts.prune_safely(conn))
        conn.rollback.assert_called_once()

    def test_privacy_page_gives_the_same_number_of_days(self):
        page = (ROOT / 'web/src/text/privacy.html').read_text()
        self.assertIn(f'within {accounts.UNCONFIRMED_DAYS} days', page)


if __name__ == '__main__':
    unittest.main()

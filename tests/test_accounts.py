"""Accounts: the sign-in box loads Supabase's library from the site's own copy and nowhere else,
and unconfirmed sign-ups are deleted after the days the privacy page gives."""
import hashlib
from pathlib import Path
import re
import unittest
from unittest import mock

from thecornerfc import accounts

ROOT = Path(__file__).resolve().parents[1]
LIB = 'assets/lib/supabase-js-2.117.2.js'
# sha256 of dist/umd/supabase.js in the npm package @supabase/supabase-js 2.117.2 (README: Accounts)
LIB_SHA256 = '59d39487c3589843b410322d8a3d562ce022aba1e5ccb16898ef3fb2a0da2ecd'
TURNSTILE = 'https://challenges.cloudflare.com'


class AccountTests(unittest.TestCase):
    def test_library_is_the_published_file(self):
        self.assertEqual(hashlib.sha256((ROOT / 'docs' / LIB).read_bytes()).hexdigest(), LIB_SHA256)

    def test_site_loads_it_from_its_own_copy(self):
        page = (ROOT / 'docs/index.html').read_text()
        app = (ROOT / 'docs/assets/app.js').read_text()
        self.assertIn(f'const AUTH_LIB = "{LIB}";', app)
        self.assertIn("script-src 'self'" + (f' {TURNSTILE};' if self.bot_check_key() else ';'), page)
        self.assertEqual(re.findall(r'<script[^>]*src="(?:https?:)?//', page), [])

    @staticmethod
    def bot_check_key():
        return re.search(r'^const TURNSTILE_KEY = "([^"]*)";$', (ROOT / 'docs/assets/app.js').read_text(), re.M).group(1)

    def test_bot_check_is_all_on_or_all_off(self):
        # README, Accounts: the key, the page's policy and the privacy page change together
        page = (ROOT / 'docs/index.html').read_text()
        privacy = (ROOT / 'docs/privacy.html').read_text()
        if self.bot_check_key():
            self.assertIn(f"frame-src {TURNSTILE};", page)
            self.assertIn('Turnstile', privacy)
        else:
            self.assertNotIn('cloudflare', page.lower())
            self.assertNotIn('Turnstile', privacy)

    def test_bot_check_covers_the_three_forms_that_take_an_email(self):
        app = (ROOT / 'docs/assets/app.js').read_text()
        self.assertIn(f'const TURNSTILE_LIB = "{TURNSTILE}/turnstile/v0/api.js?render=explicit";', app)
        self.assertIn('const BOT_CHECK_VIEWS = new Set(["signin", "signup", "reset"]);', app)
        for call in ('signInWithPassword', 'signUp', 'resetPasswordForEmail'):
            self.assertRegex(app, call + r'\([^\n]*captchaToken')

    def test_site_helper_does_not_share_the_library_name(self):
        # the library defines a global called supabase, which would replace a function of that name
        app = (ROOT / 'docs/assets/app.js').read_text()
        self.assertNotRegex(app, r'function supabase\(')
        self.assertNotRegex(app, r'(?<![\w.])supabase\(')


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
        page = (ROOT / 'docs/privacy.html').read_text()
        self.assertIn(f'within {accounts.UNCONFIRMED_DAYS} days', page)


if __name__ == '__main__':
    unittest.main()

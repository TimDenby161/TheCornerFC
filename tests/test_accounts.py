"""Accounts: the sign-in box loads Supabase's library from the site's own copy and nowhere else."""
import hashlib
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
LIB = 'assets/lib/supabase-js-2.117.2.js'
# sha256 of dist/umd/supabase.js in the npm package @supabase/supabase-js 2.117.2 (README: Accounts)
LIB_SHA256 = '59d39487c3589843b410322d8a3d562ce022aba1e5ccb16898ef3fb2a0da2ecd'


class AccountTests(unittest.TestCase):
    def test_library_is_the_published_file(self):
        self.assertEqual(hashlib.sha256((ROOT / 'docs' / LIB).read_bytes()).hexdigest(), LIB_SHA256)

    def test_site_loads_it_from_its_own_copy(self):
        page = (ROOT / 'docs/index.html').read_text()
        app = (ROOT / 'docs/assets/app.js').read_text()
        self.assertIn(f'const AUTH_LIB = "{LIB}";', app)
        self.assertIn("script-src 'self';", page)
        self.assertEqual(re.findall(r'<script[^>]*src="(?:https?:)?//', page), [])

    def test_site_helper_does_not_share_the_library_name(self):
        # the library defines a global called supabase, which would replace a function of that name
        app = (ROOT / 'docs/assets/app.js').read_text()
        self.assertNotRegex(app, r'function supabase\(')
        self.assertNotRegex(app, r'(?<![\w.])supabase\(')


if __name__ == '__main__':
    unittest.main()

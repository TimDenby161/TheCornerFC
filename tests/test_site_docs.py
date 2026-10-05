import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from thecornerfc import export

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / 'db/migrations/20261004_site_docs.sql'


class Conn:
    """site.docs as a dict of key -> sha256, with what was written and deleted."""
    def __init__(self, stored=None, missing=False):
        self.stored, self.missing = dict(stored or {}), missing
        self.written, self.deleted, self.commits, self.rollbacks = [], [], 0, 0

    def execute(self, sql, params=None):
        if self.missing:
            raise RuntimeError('relation "site.docs" does not exist')
        if sql.startswith('delete'):
            self.deleted += params[0]
        return mock.Mock(fetchall=lambda: list(self.stored.items()))

    def cursor(self):
        cur = mock.MagicMock()
        cur.__enter__.return_value = cur
        cur.executemany.side_effect = lambda sql, rows: self.written.extend(rows)
        cur.execute.side_effect = self.execute
        return cur

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class MirrorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name)
        (self.out / 'clubs').mkdir()
        (self.out / 'matches.json').write_text('{"matches":[1]}')
        (self.out / 'clubs/42.json').write_text('{"name":"É"}', encoding='utf-8')
        patcher = mock.patch.object(export.config, 'require_db_write')
        patcher.start()
        self.addCleanup(patcher.stop)

    def sha(self, rel):
        return hashlib.sha256((self.out / rel).read_bytes()).hexdigest()

    def test_every_file_is_written_under_its_path(self):
        conn = Conn()
        self.assertEqual(export.mirror_site_docs(conn, self.out), (2, 0))
        self.assertEqual({k: json.loads(body) for k, body, _ in conn.written},
                         {'matches': {'matches': [1]}, 'clubs/42': {'name': 'É'}})
        self.assertEqual(conn.commits, 1)

    def test_unchanged_files_are_left_and_missing_ones_deleted(self):
        conn = Conn({'matches': self.sha('matches.json'), 'clubs/42': 'old', 'clubs/7': 'gone'})
        self.assertEqual(export.mirror_site_docs(conn, self.out), (1, 1))
        self.assertEqual([(k, sha) for k, _, sha in conn.written], [('clubs/42', self.sha('clubs/42.json'))])
        self.assertEqual(conn.deleted, ['clubs/7'])

    def test_an_empty_directory_deletes_nothing(self):
        empty = self.out / 'empty'
        empty.mkdir()
        conn = Conn({'matches': 'x'})
        self.assertIsNone(export.mirror_site_docs(conn, empty))
        self.assertEqual((conn.deleted, conn.commits), ([], 0))

    def test_a_database_without_the_table_is_skipped_not_fatal(self):
        conn = Conn(missing=True)
        with self.assertLogs(export.log, 'ERROR'):
            self.assertIsNone(export.mirror_site_docs(conn, self.out))
        self.assertEqual((conn.rollbacks, conn.commits), (1, 0))

    def test_a_read_only_run_writes_nothing(self):
        conn = Conn()
        with mock.patch.object(export.config, 'require_db_write', side_effect=export.config.SafetyError('read-only')):
            self.assertIsNone(export.mirror_site_docs(conn, self.out))
        self.assertEqual((conn.written, conn.commits, conn.rollbacks), ([], 0, 0))

    def test_keys_fit_the_table(self):
        for path in (ROOT / 'docs/data').rglob('*.json'):
            self.assertRegex(path.relative_to(ROOT / 'docs/data').with_suffix('').as_posix(), r'^[a-z_]+(/[0-9]+)?$')


class MigrationTests(unittest.TestCase):
    def test_migration_is_in_the_schema(self):
        self.assertIn(MIGRATION.read_text(), (ROOT / 'db/schema.sql').read_text())

    def test_only_the_function_is_reachable(self):
        sql = MIGRATION.read_text()
        self.assertIn("REVOKE ALL ON site.docs FROM %I", sql)
        self.assertIn("REVOKE ALL ON FUNCTION public.site_doc(text) FROM PUBLIC", sql)
        self.assertIn("AND NOT paid", sql)
        self.assertNotIn("GRANT SELECT", sql.upper().replace("GRANT EXECUTE", ""))


class CacheMigrationTests(unittest.TestCase):
    """site_doc(p_key, p_v): the function the site reads through (20261005_site_doc_cache.sql)."""
    SQL = (ROOT / 'db/migrations/20261005_site_doc_cache.sql').read_text()

    def test_migration_is_in_the_schema(self):
        self.assertIn(self.SQL, (ROOT / 'db/schema.sql').read_text())

    def test_one_function_and_only_it_is_reachable(self):
        # the one-argument function goes: two that both answer site_doc(p_key) would be ambiguous
        self.assertIn("DROP FUNCTION IF EXISTS public.site_doc(text);", self.SQL)
        self.assertIn("REVOKE ALL ON FUNCTION public.site_doc(text, text) FROM PUBLIC", self.SQL)
        self.assertIn("AND NOT paid", self.SQL)
        self.assertIn("SET search_path = ''", self.SQL)
        self.assertNotIn("GRANT SELECT", self.SQL.upper().replace("GRANT EXECUTE", ""))

    def test_kept_only_when_asked_for_by_its_hash(self):
        # the manifest's hash is the first 16 characters of the file's sha256 (export.write_manifest)
        self.assertIn("p_v = pg_catalog.left(doc.sha256, 16)", self.SQL)
        self.assertIn('"Cache-Control": "no-cache"', self.SQL)


class SiteReaderTests(unittest.TestCase):
    def test_pages_load_the_reader_before_the_scripts_that_use_it(self):
        for page, script in (('index.html', 'app.js'), ('methodology.html', 'methodology.js')):
            html = (ROOT / 'docs' / page).read_text()
            self.assertLess(html.index('<script src="assets/data.js">'), html.index(f'<script src="assets/{script}">'), page)
            self.assertIn("connect-src 'self' https://bookkurhdabdeccckjbn.supabase.co;", html, page)

    def test_files_are_the_default_and_the_database_is_asked_by_key(self):
        reader = (ROOT / 'docs/assets/data.js').read_text()
        self.assertIn(': "files";', reader)
        self.assertIn("/rest/v1/rpc/site_doc?", reader)
        self.assertIn('q.set("p_v", hash)', reader)


if __name__ == '__main__':
    unittest.main()

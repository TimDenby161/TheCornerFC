"""The manifest (export.write_manifest): the site keeps a top-level row of data until its hash
here changes, so the manifest must be rewritten whenever a top-level data file is."""
import hashlib
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest import mock

from thecornerfc import export

ROOT = Path(__file__).resolve().parents[1]


class ManifestTests(unittest.TestCase):
    def test_hashes_every_top_level_file_and_nothing_else(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / 'bets.json').write_text('{"a":1}')
            (out / 'matches.json').write_text('{"b":2}')
            (out / 'clubs').mkdir()
            (out / 'clubs' / '42.json').write_text('{}')
            files = export.write_manifest(out)
            self.assertEqual(set(files), {'bets.json', 'matches.json'})
            self.assertEqual(files['bets.json'], hashlib.sha256(b'{"a":1}').hexdigest()[:16])
            self.assertEqual(json.loads((out / 'manifest.json').read_text()), {'files': files})
            (out / 'bets.json').write_text('{"a":2}')
            again = export.write_manifest(out)          # its own earlier copy isn't hashed
            self.assertEqual(set(again), {'bets.json', 'matches.json'})
            self.assertNotEqual(again['bets.json'], files['bets.json'])
            self.assertEqual(again['matches.json'], files['matches.json'])

    def test_a_job_that_writes_part_of_the_data_keeps_the_other_hashes(self):
        # its working copy needn't hold the files it didn't write: their hashes are the rows' in site.docs
        stored = {'matches': 'a' * 64, 'bets': 'b' * 64, 'manifest': 'c' * 64}
        conn = mock.Mock()
        conn.execute.side_effect = lambda sql, params=None: mock.Mock(
            fetchone=lambda: ('site.docs',), fetchall=lambda: [(k, v) for k, v in stored.items() if k != params[0]])
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / 'bets.json').write_text('{"a":1}')
            (out / 'stats.json').write_text('{"old":true}')          # in the working copy, not written by this job
            with mock.patch.object(export.config, 'require_db_write'):
                files = export.write_manifest(out, conn=conn, only=['bets.json'])
            self.assertEqual(files, {'bets.json': hashlib.sha256(b'{"a":1}').hexdigest()[:16], 'matches.json': 'a' * 16})
            self.assertEqual(json.loads((out / 'manifest.json').read_text()), {'files': files})
            # a read-only run (a local one) publishes nothing and doesn't ask the database
            with mock.patch.object(export.config, 'require_db_write', side_effect=export.config.SafetyError('read-only')):
                self.assertEqual(set(export.write_manifest(out, conn=None, only=['bets.json'])), {'bets.json'})

    def test_every_writer_of_data_files_rewrites_it(self):
        main = (ROOT / 'thecornerfc/__main__.py').read_text()
        for call, wrote in (('export.export_nations(conn)', '["nations.json"]'), ('export.export_injuries(conn)', '["bets.json", "injuries.json"]')):
            after = main.split(call, 1)[1].split('return 0', 1)[0]
            self.assertIn(f'export.write_manifest(conn=conn, only={wrote})', after, call)
            self.assertIn(f'export.mirror_site_docs(conn, only={wrote[:-1]}, ', after, call)       # and writes just those rows
        publish = (ROOT / 'thecornerfc/export.py').read_text().split('def _publish_export', 1)[1].split('\ndef ', 1)[0]
        self.assertLess(publish.index('write_manifest(staged)'), publish.index('_replace_export(staged'))

    def test_no_workflow_commits_data(self):
        # the data goes to the database (site.docs and the site.* tables); nothing is committed
        for path in sorted((ROOT / '.github/workflows').glob('*.yml')):
            text = path.read_text()
            for gone in ('git add', 'git commit', 'git push', 'contents: write'):
                self.assertNotIn(gone, text, path.name)
        self.assertIn('\ndocs/data/\n', (ROOT / '.gitignore').read_text())

    def test_site_checks_the_hash_before_trusting_a_kept_copy(self):
        app = (ROOT / 'docs/assets/app.js').read_text()
        self.assertIn('data/manifest.json', app)
        self.assertIn('crypto.subtle.digest("SHA-256"', app)


if __name__ == '__main__':
    unittest.main()

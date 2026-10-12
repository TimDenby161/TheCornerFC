"""The local switch between staging and production (scripts/environment.py): what it refuses,
what it writes, and what it never shows. No database and no git: the question it asks of a
database is a stand-in here."""
import contextlib
import importlib.util
import io
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("environment_switch", ROOT / "scripts/environment.py")
switcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(switcher)

PRODUCTION = "bookkurhdabdeccckjbn"
STAGING = "stagingstagingstagin"
SECRET = "s3cret-pass-word"
STAGING_URL = f"postgresql://postgres.{STAGING}:{SECRET}@aws-0-eu-central-1.pooler.supabase.com:5432/postgres"
READER_URL = f"postgresql://local_readonly.{PRODUCTION}:{SECRET}@aws-0-eu-central-1.pooler.supabase.com:5432/postgres"
WRITER_URL = f"postgresql://postgres.{PRODUCTION}:{SECRET}@aws-0-eu-central-1.pooler.supabase.com:5432/postgres"

READER = {"role": "local_readonly", "sees_all": False, "can_write": False, "reads": True,
          "read_only_by_default": True, "says": "production"}
WRITER = {"role": "postgres", "sees_all": True, "can_write": True, "reads": True,
          "read_only_by_default": False, "says": "staging"}


def asking(answers):
    """A stand-in for check_local_access.ask: the answer for whichever address is asked about."""
    def ask(url):
        answer = answers[url]
        if isinstance(answer, Exception):
            raise answer
        return answer
    return ask


class SwitchTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.profiles = self.dir / "profiles"
        self.profiles.mkdir()
        (self.dir / "web").mkdir()
        self.env, self.site = self.dir / ".env", self.dir / "web" / ".env.local"
        from thecornerfc import config
        known = patch.object(config, "PROJECTS", {"production": PRODUCTION, "staging": STAGING})
        known.start()
        self.addCleanup(known.stop)

    def profile(self, name, text):
        (self.profiles / f"{name}.env").write_text(text)

    def switch(self, name, answers):
        return switcher.switch(name, asking(answers), folder=self.profiles, env_file=self.env, site_file=self.site)

    def settings(self):
        return dict(line.split("=", 1) for line in self.env.read_text().splitlines() if "=" in line and not line.startswith("#"))

    def test_staging_is_written_whole_and_may_write_with_no_api(self):
        self.profile("staging", f"DATABASE_URL={STAGING_URL}\n")
        self.switch("staging", {STAGING_URL: WRITER})
        s = self.settings()
        self.assertEqual((s["THECORNERFC_ENV"], s["THECORNERFC_READ_ONLY"], s["THECORNERFC_NO_API"]), ("staging", "false", "true"))
        self.assertEqual((s["DATABASE_URL"], s["READ_ONLY_DATABASE_URL"]), (STAGING_URL, STAGING_URL))
        self.assertEqual((s["API_FOOTBALL_KEY"], s["THECORNERFC_LOCAL_OVERRIDE"]), ("", ""))
        # its own cache, export and ledger, so neither environment reads the other's
        self.assertTrue(s["THE_CORNER_FC_CACHE_DIR"].endswith(".cache-staging"))
        self.assertTrue(s["THECORNERFC_EXPORT_DIR"].endswith(".export-staging"))
        self.assertTrue(s["API_LEDGER_PATH"].endswith("staging.sqlite3"))
        self.assertEqual(stat.S_IMODE(self.env.stat().st_mode), 0o600)
        self.assertIn("VITE_SITE_ENV=staging", self.site.read_text())

    def test_production_is_read_only_in_every_setting_and_holds_one_address(self):
        self.profile("production", f"READ_ONLY_DATABASE_URL={READER_URL}\n")
        self.switch("production", {READER_URL: READER})
        s = self.settings()
        self.assertEqual((s["THECORNERFC_ENV"], s["THECORNERFC_READ_ONLY"], s["THECORNERFC_NO_API"]), ("production", "true", "true"))
        self.assertEqual((s["DATABASE_URL"], s["READ_ONLY_DATABASE_URL"]), (READER_URL, READER_URL))
        self.assertNotIn("THECORNERFC_EXPORT_DIR", s)
        self.assertIn("VITE_SITE_ENV=production", self.site.read_text())

    def test_nothing_of_the_last_environment_is_left_after_a_switch(self):
        self.profile("staging", f"DATABASE_URL={STAGING_URL}\n")
        self.profile("production", f"READ_ONLY_DATABASE_URL={READER_URL}\n")
        self.switch("staging", {STAGING_URL: WRITER})
        self.switch("production", {READER_URL: READER})
        text = self.env.read_text()
        for left in (STAGING, "staging", "THECORNERFC_READ_ONLY=false", ".cache-staging"):
            self.assertNotIn(left, text)
        self.switch("staging", {STAGING_URL: WRITER})
        for left in (PRODUCTION, "local_readonly", "THECORNERFC_READ_ONLY=true"):
            self.assertNotIn(left, self.env.read_text())

    def test_production_is_refused_unless_the_database_says_the_role_cannot_write(self):
        self.profile("staging", f"DATABASE_URL={STAGING_URL}\n")
        self.switch("staging", {STAGING_URL: WRITER})
        before = self.env.read_text()
        self.profile("production", f"READ_ONLY_DATABASE_URL={WRITER_URL}\n")
        for answer in ({**READER, "can_write": True}, {**READER, "sees_all": True},
                       {**READER, "read_only_by_default": False}, {**READER, "says": "staging"},
                       OSError("no route")):                # can't be asked: can't be shown to be read-only
            with self.subTest(answer=answer):
                with self.assertRaises(switcher.Refused):
                    self.switch("production", {WRITER_URL: answer})
                self.assertEqual(self.env.read_text(), before)      # .env left as it was

    def test_a_profile_may_hold_addresses_and_nothing_else(self):
        for name, url, extra in (
            ("production", f"READ_ONLY_DATABASE_URL={READER_URL}", "API_FOOTBALL_KEY=abc"),
            ("production", f"READ_ONLY_DATABASE_URL={READER_URL}", "THECORNERFC_READ_ONLY=false"),
            ("production", f"READ_ONLY_DATABASE_URL={READER_URL}", "THECORNERFC_LOCAL_OVERRIDE=I_UNDERSTAND"),
            ("production", f"READ_ONLY_DATABASE_URL={READER_URL}", f"DATABASE_URL={WRITER_URL}"),   # a write address
            ("staging", f"DATABASE_URL={STAGING_URL}", "API_FOOTBALL_KEY=abc"),
            ("staging", f"DATABASE_URL={STAGING_URL}", "THECORNERFC_NO_API=false"),
        ):
            with self.subTest(name=name, extra=extra.split("=")[0]):
                self.profile(name, f"{url}\n{extra}\n")
                with self.assertRaises(switcher.Refused):
                    self.switch(name, {READER_URL: READER, WRITER_URL: READER, STAGING_URL: WRITER})
                self.assertFalse(self.env.exists())

    def test_an_address_of_the_wrong_project_is_refused_before_anything_is_asked(self):
        def never(url):
            raise AssertionError("connected")
        for name, line in (
            ("staging", f"DATABASE_URL={WRITER_URL}"),                       # production's, in the staging profile
            ("staging", f"DATABASE_URL={STAGING_URL}\nREAD_ONLY_DATABASE_URL={READER_URL}"),
            ("staging", "DATABASE_URL=postgresql://u:p@localhost:5432/postgres"),
            ("production", f"READ_ONLY_DATABASE_URL={STAGING_URL}"),
            ("production", "READ_ONLY_DATABASE_URL=postgresql://u:p@db.example.test/postgres"),
            ("production", ""),
        ):
            with self.subTest(name=name, line=line.split("=")[0]):
                self.profile(name, line + "\n")
                with self.assertRaises(switcher.Refused):
                    switcher.switch(name, never, folder=self.profiles, env_file=self.env, site_file=self.site)
                self.assertFalse(self.env.exists())

    def test_staging_is_refused_when_its_database_says_it_is_production(self):
        self.profile("staging", f"DATABASE_URL={STAGING_URL}\n")
        with self.assertRaises(switcher.Refused):
            self.switch("staging", {STAGING_URL: {**WRITER, "says": "production"}})
        self.assertFalse(self.env.exists())

    def test_a_missing_profile_and_an_unrecorded_staging_project_are_refused(self):
        with self.assertRaisesRegex(switcher.Refused, "There is no"):
            self.switch("staging", {})
        from thecornerfc import config
        self.profile("staging", f"DATABASE_URL={STAGING_URL}\n")
        with patch.object(config, "PROJECTS", {"production": PRODUCTION, "staging": ""}):
            with self.assertRaisesRegex(switcher.Refused, "No staging project"):
                self.switch("staging", {STAGING_URL: WRITER})

    def test_a_hand_made_env_file_is_kept_outside_the_repository_not_overwritten(self):
        self.env.write_text("DATABASE_URL=something-by-hand\n")
        self.profile("production", f"READ_ONLY_DATABASE_URL={READER_URL}\n")
        notes = self.switch("production", {READER_URL: READER})
        kept = self.profiles / "env.before-switch"
        self.assertEqual(kept.read_text(), "DATABASE_URL=something-by-hand\n")
        self.assertEqual(stat.S_IMODE(kept.stat().st_mode), 0o600)
        self.assertTrue(any("env.before-switch" in n for n in notes))
        self.assertTrue(self.env.read_text().startswith(switcher.HEADER))

    def test_the_first_switch_to_production_takes_only_the_read_only_address_from_a_hand_made_env(self):
        self.env.write_text(f"DATABASE_URL={WRITER_URL}\nREAD_ONLY_DATABASE_URL={READER_URL}\nAPI_FOOTBALL_KEY=abc\n")
        (self.profiles / "production.env").write_text("# empty template\nREAD_ONLY_DATABASE_URL=\n")
        notes = self.switch("production", {READER_URL: READER})
        profile = (self.profiles / "production.env").read_text()
        self.assertIn(f"READ_ONLY_DATABASE_URL={READER_URL}", profile)
        for left_out in (WRITER_URL, "API_FOOTBALL_KEY=abc"):
            self.assertNotIn(left_out, profile + self.env.read_text())
        self.assertNotIn("API_FOOTBALL_KEY", profile)
        self.assertEqual(stat.S_IMODE((self.profiles / "production.env").stat().st_mode), 0o600)
        self.assertTrue(any("taken from" in n for n in notes))
        # and an address that can write is still refused, wherever it came from
        self.env.unlink()
        (self.profiles / "production.env").write_text("READ_ONLY_DATABASE_URL=\n")
        self.env.write_text(f"READ_ONLY_DATABASE_URL={WRITER_URL}\n")
        with self.assertRaises(switcher.Refused):
            self.switch("production", {WRITER_URL: {**READER, "can_write": True}})

    def test_no_secret_is_printed_by_a_switch_a_refusal_or_the_status(self):
        self.profile("staging", f"DATABASE_URL={STAGING_URL}\n")
        self.profile("production", f"READ_ONLY_DATABASE_URL={WRITER_URL}\n")
        out = io.StringIO()
        with contextlib.redirect_stdout(out), patch.object(switcher, "ENV_FILE", self.env), \
             patch.object(switcher, "SITE_FILE", self.site), patch.object(switcher, "profile_dir", lambda: self.profiles), \
             patch.dict("sys.modules", {"check_local_access": type("m", (), {"ask": staticmethod(
                 asking({STAGING_URL: WRITER, WRITER_URL: {**READER, "can_write": True}}))})}):
            self.assertEqual(switcher.main(["staging"]), 0)
            self.assertEqual(switcher.main(["status"]), 0)
            self.assertEqual(switcher.main(["production"]), 1)      # refused: that role can write
            self.assertEqual(switcher.main(["status"]), 0)          # still staging
        printed = out.getvalue()
        self.assertIn("STAGING", printed)
        self.assertIn("Not switched", printed)
        for hidden in (SECRET, STAGING_URL, WRITER_URL, "pooler.supabase.com", STAGING, PRODUCTION):
            self.assertNotIn(hidden, printed)

    def test_status_says_not_safe_when_production_is_selected_with_an_address_that_can_write(self):
        self.env.write_text(switcher.env_text("production", {"DATABASE_URL": WRITER_URL, "READ_ONLY_DATABASE_URL": READER_URL}))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = switcher.status(asking({WRITER_URL: {**READER, "role": "postgres", "can_write": True}, READER_URL: READER}), env_file=self.env)
        self.assertEqual(code, 1)
        self.assertIn("CAN WRITE", out.getvalue())
        self.assertIn("NOT SAFE", out.getvalue())
        self.assertNotIn(SECRET, out.getvalue())

    def test_the_switch_never_runs_git_or_any_other_program(self):
        source = (ROOT / "scripts/environment.py").read_text()
        for banned in ("subprocess", "os.system", "os.popen", "git checkout", "git switch"):
            self.assertNotIn(banned, source)
        head = ROOT / ".git" / "HEAD"
        before = head.read_text() if head.is_file() else None
        self.profile("staging", f"DATABASE_URL={STAGING_URL}\n")
        with patch.object(subprocess, "Popen", side_effect=AssertionError("ran a program")):
            self.switch("staging", {STAGING_URL: WRITER})
            self.assertTrue(switcher.branch())
        self.assertEqual(head.read_text() if head.is_file() else None, before)

    def test_what_a_job_sets_wins_over_the_env_file(self):
        # config reads .env without replacing anything already set, so a local selection can't
        # reach a GitHub job (which has no .env anyway) or a command that names its own settings
        self.assertIn("load_dotenv()", (ROOT / "thecornerfc/config.py").read_text())
        import dotenv
        self.env.write_text("THECORNERFC_ENV=staging\nTHECORNERFC_READ_ONLY=false\n")
        with patch.dict(os.environ, {"THECORNERFC_ENV": "production", "THECORNERFC_READ_ONLY": "true"}, clear=True):
            dotenv.load_dotenv(self.env)
            self.assertEqual((os.environ["THECORNERFC_ENV"], os.environ["THECORNERFC_READ_ONLY"]), ("production", "true"))


if __name__ == "__main__":
    unittest.main()

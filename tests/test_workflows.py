"""The GitHub workflows keep production and staging apart (guide/environments.md). These read
the workflow files as text: which secrets each job names, which environment and branch it is
held to, and what runs before a secret is given."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = {p.name: p.read_text() for p in sorted((ROOT / ".github/workflows").glob("*.yml"))}
PRODUCTION_SECRETS = ("DATABASE_URL", "API_FOOTBALL_KEY")
STAGING = ("staging.yml", "staging-pipeline.yml")
SECRET = re.compile(r"secrets\.([A-Za-z_0-9]+)")


def jobs(text):
    """{job name: its text} for a workflow."""
    body = text.split("\njobs:\n", 1)[1]
    parts = re.split(r"(?m)^  ([A-Za-z0-9_-]+):\n", body)
    return dict(zip(parts[1::2], parts[2::2]))


def code(text):
    """Without comments, so a rule is found in what runs, not in what is said about it."""
    return "\n".join(line.split(" # ")[0] for line in text.splitlines() if not line.lstrip().startswith("#"))


class WorkflowIsolationTests(unittest.TestCase):
    def test_staging_workflows_never_name_a_production_secret(self):
        # while the repository-level production secrets still exist, a job that asked for one of
        # those names and found none in its environment would be handed production's
        for name in STAGING:
            used = set(SECRET.findall(WORKFLOWS[name]))
            self.assertTrue(used, name)
            for secret in used:
                with self.subTest(workflow=name, secret=secret):
                    self.assertTrue(secret.startswith("STAGING_"))
                    self.assertNotIn(secret, PRODUCTION_SECRETS)

    def test_production_workflows_never_name_a_staging_secret(self):
        for name, text in WORKFLOWS.items():
            if name not in STAGING:
                with self.subTest(workflow=name):
                    self.assertFalse([s for s in SECRET.findall(text) if s.startswith("STAGING_")])
                    self.assertNotIn("THECORNERFC_ENV: staging", text)

    def test_every_job_given_a_production_secret_is_held_to_main_and_the_production_environment(self):
        seen = 0
        for name, text in WORKFLOWS.items():
            for job, body in jobs(text).items():
                if not any(s in PRODUCTION_SECRETS for s in SECRET.findall(body)):
                    continue
                seen += 1
                with self.subTest(workflow=name, job=job):
                    body = code(body)
                    self.assertRegex(body, r"(?m)^    if: github\.ref == 'refs/heads/main'( &&|$)")
                    self.assertRegex(body, r"(?m)^    environment: Production$")
                    self.assertIn("THECORNERFC_ENV: production", body)
        self.assertGreaterEqual(seen, 6)        # nightly, match day, FPL, two backfills, removing a person

    # The names are GitHub's own, capitals and all (Settings > Environments): a job runs under
    # either spelling, but the rule on main that asks for a staging deployment matches the name
    # exactly, and did not count deployments recorded as "staging" (seen 2026-10-12).
    def test_every_job_given_a_staging_secret_is_held_to_the_staging_environment(self):
        for name in STAGING:
            for job, body in jobs(WORKFLOWS[name]).items():
                with self.subTest(workflow=name, job=job):
                    self.assertRegex(code(body), r"(?m)^    environment: Staging$")
        pipeline = code(WORKFLOWS["staging-pipeline.yml"])
        self.assertRegex(pipeline, r"(?m)^    if: github\.ref == 'refs/heads/staging'$")
        self.assertIn("THECORNERFC_ENV: staging", pipeline)
        self.assertNotIn("FPL_CAPTURE_ENABLED", pipeline)       # fantasy data is the owner's question, not staging's default

    def test_no_workflow_passes_every_secret_on(self):
        for name, text in WORKFLOWS.items():
            with self.subTest(workflow=name):
                self.assertNotIn("secrets: inherit", text)
                self.assertNotIn("toJSON(secrets)", text.replace(" ", ""))
                self.assertNotRegex(code(text), r"(?m)^\s+uses: \./")        # no reusable workflow to carry them

    def test_staging_has_no_schedule_and_shares_nothing_with_productions_jobs(self):
        for name in STAGING:
            text = code(WORKFLOWS[name])
            with self.subTest(workflow=name):
                self.assertNotIn("schedule:", text)
                self.assertNotIn("cron:", text)
                self.assertNotRegex(text, r"group: db-sync\b")
                for key in re.findall(r"(?:key|restore-keys): (\S+)", text):
                    self.assertTrue(key.startswith("staging-"), key)
        # and production's caches are not staging's
        for name, text in WORKFLOWS.items():
            if name not in STAGING:
                self.assertFalse([k for k in re.findall(r"(?:key|restore-keys): (\S+)", text) if k.startswith("staging-")])

    def test_the_staging_check_exists_only_as_a_push_to_staging(self):
        # a skipped job counts as passed, so the check must never be a job some other event skips
        text = code(WORKFLOWS["staging.yml"])
        triggers = text.split("\non:\n", 1)[1].split("\nconcurrency:", 1)[0]
        self.assertEqual(triggers.split(), ["push:", "branches:", "[staging]"])
        self.assertEqual(list(jobs(WORKFLOWS["staging.yml"])), ["staging-check"])
        self.assertNotRegex(jobs(text)["staging-check"], r"(?m)^    if:")
        for name, other in WORKFLOWS.items():
            if name != "staging.yml":
                self.assertNotIn("staging-check", jobs(other), name)

    def test_staging_makes_no_api_call_unless_a_run_is_given_a_budget(self):
        text = WORKFLOWS["staging-pipeline.yml"]
        self.assertIn('default: "0"', text)
        self.assertIn("THECORNERFC_NO_API: ${{ inputs.call_budget == '0' && 'true' || 'false' }}", text)
        self.assertIn("API_RUN_BUDGET: ${{ inputs.call_budget }}", text)
        # the key is given to the one step that fetches, and to no other
        self.assertEqual(text.count("secrets.STAGING_API_FOOTBALL_KEY"), 1)
        fetch = text.split("- name: Nightly sync into staging", 1)[1].split("\n      - name:", 1)[0]
        self.assertIn("secrets.STAGING_API_FOOTBALL_KEY", fetch)
        self.assertIn("if: inputs.steps == 'nightly (needs a call budget)'", fetch)

    def test_the_unit_tests_run_before_any_step_is_given_a_secret(self):
        for name, text in WORKFLOWS.items():
            for job, body in jobs(text).items():
                if "secrets." not in body or name == "staging.yml":     # (the staging check runs no Python)
                    continue
                with self.subTest(workflow=name, job=job):
                    self.assertIn("python -m unittest discover -s tests", body)
                    self.assertLess(body.index("python -m unittest discover -s tests"), body.index("secrets."))
                    tests = body.split("- name: Unit tests", 1)[1].split("\n      - ", 1)[0]
                    self.assertNotIn("secrets.", tests)

    def test_both_test_suites_run_on_staging_and_on_main(self):
        self.assertIn("branches: [main, staging]", WORKFLOWS["tests.yml"])
        self.assertEqual(sorted(jobs(WORKFLOWS["tests.yml"])), ["python", "site"])
        self.assertNotIn("secrets.", WORKFLOWS["tests.yml"])

    def test_dependabot_opens_its_pull_requests_on_staging(self):
        text = (ROOT / ".github/dependabot.yml").read_text()
        self.assertEqual(text.count("package-ecosystem:"), text.count("target-branch: staging"))

    def test_the_site_and_the_jobs_name_the_same_projects(self):
        from thecornerfc import config
        table = (ROOT / "web/src/lib/environments.ts").read_text()
        for name in ("production", "staging"):
            found = re.search(name + r": \{\s*project: '([a-z0-9]*)'", table)
            with self.subTest(environment=name):
                self.assertEqual(found.group(1), config.PROJECTS[name])
        self.assertNotEqual(config.PROJECTS["staging"], config.PROJECTS["production"])

    def test_the_staging_worker_is_its_own_and_has_no_public_address(self):
        text = code((ROOT / "web/wrangler.jsonc").read_text().replace("//", " # "))
        staging = text.split('"staging": {', 1)[1]
        self.assertIn('"name": "thecornerfc-staging"', staging)
        self.assertIn('"SITE_ENV": "staging"', staging)
        self.assertIn('"workers_dev": false', staging)
        self.assertIn('"preview_urls": false', staging)
        self.assertIn('"vars": { "SITE_ENV": "production" }', text.split('"env": {', 1)[0])


if __name__ == "__main__":
    unittest.main()

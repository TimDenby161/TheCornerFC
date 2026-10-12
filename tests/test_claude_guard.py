"""The check Claude Code runs before every shell command (.claude/hooks/guard.py): it must refuse
a command that would lift the local safety guard or read .env, and must not get in the way of
ordinary work that only mentions those names."""
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / ".claude" / "hooks" / "guard.py"
spec = importlib.util.spec_from_file_location("claude_guard", GUARD)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

TOKEN = "I_UNDERSTAND_THIS_CAN_WRITE_PRODUCTION_DATA_AND_USE_API_QUOTA"

REFUSED = [
    "THECORNERFC_READ_ONLY=false python -m thecornerfc rank",
    "THECORNERFC_READ_ONLY=0 THECORNERFC_NO_API=false python -m thecornerfc nightly",
    "cd web && THECORNERFC_NO_API=off python x.py",
    f"THECORNERFC_LOCAL_OVERRIDE={TOKEN} python -m thecornerfc sync all",
    f"export THECORNERFC_LOCAL_OVERRIDE='{TOKEN}'",
    "env THECORNERFC_MODE=production python -m thecornerfc export",
    "export DATABASE_URL=postgresql://u:p@h/db && psql",
    "DATABASE_URL=$READ_ONLY_DATABASE_URL python experiments/prospective/evaluate.py",
    "GITHUB_ACTIONS=true python -m thecornerfc rank",
    "FPL_CAPTURE_ENABLED=true python -m thecornerfc fpl capture",
    "ls; THECORNERFC_READ_ONLY=false python x.py",
    "true |\nTHECORNERFC_READ_ONLY=false python x.py",
    "bash -c 'THECORNERFC_READ_ONLY=false python -m thecornerfc rank'",
    "sh -c \"export GITHUB_ACTIONS=1; python -m thecornerfc nightly\"",
    "cat .env",
    "cat ./.env | head -3",
    "grep DATABASE_URL .env",
    "sed -E 's/=.*//' /Users/someone/Projects/TheCornerFC/.env",
    "source .env && python x.py",
    ". .env",
    "python x.py < .env",
    "cp .env /tmp/copy",
    "head -5 web/.env.local",
]

ALLOWED = [
    "ls -la",
    "python -m unittest discover -s tests",
    "python -m thecornerfc export",
    "python db/check_local_access.py",
    "cd web && npm test && npm run check",
    "git status --short && git diff --stat",
    "THECORNERFC_READ_ONLY=true python -m thecornerfc export",
    "PYTHONHASHSEED=0 python x.py",
    "cat .env.example",
    "diff .env.example guide/local-safety.md",
    "grep -rn 'THECORNERFC_READ_ONLY=false' guide tests",
    "grep -rn \"DATABASE_URL=\" .env.example .github",
    f"grep -rn {TOKEN} thecornerfc",
    "grep -n LOCAL_OVERRIDE thecornerfc/config.py",
    "git ls-files | grep -c '\\.env'",
    "git check-ignore -v .env",
    "ls -la .env",
    "git log --oneline -5 -- .env.example",
    "echo 'set THECORNERFC_NO_API=false only with the token' >> notes.md",
    "python -c \"print('GITHUB_ACTIONS=true is what a runner sets')\"",
    "printf '%s' '{\"tool_input\":{\"command\":\"THECORNERFC_READ_ONLY=false python x\"}}' | python3 .claude/hooks/guard.py",
    "node scripts/browser-check.mjs http://localhost:4517",
    "CHROME_MAP='thecornerfc.com 104.21.21.76' node scripts/browser-check.mjs https://thecornerfc.com",
]


class GuardTests(unittest.TestCase):
    def test_commands_that_lift_the_guard_or_read_the_env_file_are_refused(self):
        for command in REFUSED:
            self.assertIsNotNone(guard.refusal(command), command)

    def test_ordinary_work_that_only_mentions_the_names_is_let_through(self):
        for command in ALLOWED:
            self.assertIsNone(guard.refusal(command), command)

    def test_a_command_that_cannot_be_split_is_still_checked(self):
        # an unbalanced quote: fall back to looking anywhere in the text
        self.assertIsNotNone(guard.refusal("THECORNERFC_READ_ONLY=false python -c 'print(1"))
        self.assertIsNotNone(guard.refusal("cat .env 'oops"))
        self.assertIsNone(guard.refusal("echo 'unfinished"))

    def test_the_hook_refuses_with_exit_code_2_and_passes_with_0(self):
        def run(command):
            payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
            return subprocess.run([sys.executable, str(GUARD)], input=payload, capture_output=True, text=True)
        refused = run("THECORNERFC_READ_ONLY=false python -m thecornerfc rank")
        self.assertEqual(refused.returncode, 2)
        self.assertIn("Refused", refused.stderr)
        self.assertEqual(run("python -m unittest discover -s tests").returncode, 0)
        # anything that isn't the JSON the hook is sent must not stop the session
        self.assertEqual(subprocess.run([sys.executable, str(GUARD)], input="not json", capture_output=True, text=True).returncode, 0)

    def test_the_settings_file_runs_this_hook_and_denies_reading_the_env_file(self):
        settings = json.loads((ROOT / ".claude" / "settings.json").read_text())
        hooks = [h["command"] for group in settings["hooks"]["PreToolUse"] if group.get("matcher") == "Bash" for h in group["hooks"]]
        self.assertTrue(any("guard.py" in command for command in hooks))
        denied = settings["permissions"]["deny"]
        self.assertIn("Read(/.env)", denied)
        self.assertFalse([rule for rule in denied if ".env.example" in rule])
        # nothing that writes to production, pushes or deploys may run without asking
        allowed = " ".join(settings["permissions"]["allow"])
        for never in ("git push", "git commit", "wrangler", "nightly", "sync", "matchday", "psql", "init-db"):
            self.assertNotIn(never, allowed)


if __name__ == "__main__":
    unittest.main()

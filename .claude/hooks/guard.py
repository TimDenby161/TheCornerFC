#!/usr/bin/env python3
"""Refuses a shell command that would lift the local safety guard (guide/local-safety.md).

Claude Code runs this before every Bash command (.claude/settings.json). The command arrives as
JSON on stdin; exit code 2 refuses it and the message on stderr is shown to Claude.

What is refused is a command that SETS one of the guarded variables, or reads .env. A command that
only mentions one (a grep for it, a test or a page of the guide written through a here-document)
is let through: the names are looked for where the shell would take them as settings, which is
at the start of a command, after `export` or `env`, and inside `sh -c "..."`.

Also refused (guide/environments.md): naming the environment by hand instead of through
scripts/environment.py, reading the profiles that script switches between, a forced push, and
any push to main that is not the promotion of what staging tested.
"""
import os
import json
import re
import shlex
import sys

OFF = r"['\"]?(false|0|no|off)\b"
ON = r"['\"]?(true|1|yes|on)\b"
SETTINGS = [
    (r"THECORNERFC_LOCAL_OVERRIDE=['\"]?\w", "sets the local override"),
    (r"THECORNERFC_READ_ONLY=" + OFF, "switches read-only mode off"),
    (r"THECORNERFC_NO_API=" + OFF, "switches the API block off"),
    (r"THECORNERFC_MODE=['\"]?production", "sets production mode"),
    (r"DATABASE_URL=", "sets DATABASE_URL"),
    (r"GITHUB_ACTIONS=" + ON, "pretends to be a GitHub Actions run"),
    (r"FPL_CAPTURE_ENABLED=" + ON, "switches FPL capture on"),
    (r"THECORNERFC_ENV=", "names the environment by hand (scripts/environment.py does that)"),
    (r"THECORNERFC_PROFILE_DIR=", "points the environment switch at other profiles"),
]
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
OPERATORS = {";", "&&", "||", "|", "&", "(", ")", "{", "}", "|&", ";;", "!", "then", "do", "else"}
PREFIXES = {"export", "env", "declare", "typeset", "local", "readonly", "command", "exec", "time", "nohup", "sudo"}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
# .env itself (not .env.example), as a word a command is given
ENV_FILE = re.compile(r"^(.*/)?\.env(\.local)?$")
# the profiles scripts/environment.py switches between, outside the repository
PROFILES = re.compile(r"(^|/)\.config/thecornerfc(/|$)")
# the one push to main there is: main moved forward to the commit staging tested
PROMOTION = ["origin", "origin/staging:main"]
READERS = {"cat", "less", "more", "head", "tail", "bat", "source", ".", "grep", "egrep", "rg", "sed", "awk",
           "cut", "sort", "strings", "xxd", "od", "nl", "tac", "open", "code", "vim", "vi", "nano", "cp", "mv",
           "scp", "rsync", "base64", "diff", "cmp", "tee", "printenv", "pbcopy", "wc"}


def words(command):
    """The command as the shell would split it, with the operators kept as their own words and
    a line break as a `;`. None when it can't be split (an unbalanced quote)."""
    lexer = shlex.shlex(command.replace("\n", " ; "), posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        return list(lexer)
    except ValueError:
        return None


def setting(word):
    for pattern, what in SETTINGS:
        if re.match(pattern, word, re.IGNORECASE):
            return what
    return None


def push_refusal(args, branch):
    """Why a `git push` with these arguments is refused, or None. A forced push never; main only
    as the promotion (GitHub's own rules on main are the real gate: this stops the mistake
    before it is sent)."""
    if "push" not in args:
        return None
    rest = args[args.index("push") + 1:]
    options = [a for a in rest if a.startswith("-")]
    targets = [a for a in rest if not a.startswith("-")]
    if any(o in ("-f", "--all", "--mirror", "--delete", "-d") or o.startswith("--force") for o in options) \
            or any(t.startswith("+") for t in targets):
        return "forces, deletes or pushes every branch"
    refs = targets[1:]
    to_main = [r for r in refs if r.split(":")[-1] in ("main", "refs/heads/main")] if refs else \
        (["main"] if branch == "main" else [])
    if to_main and (options or targets != PROMOTION):
        return "pushes to main other than by promotion (git push origin origin/staging:main)"
    return None


def refusal(command, depth=0, branch=None):
    split = words(command)
    if split is None:               # can't tell where a command starts: look anywhere in the text
        for pattern, what in SETTINGS:
            if re.search(r"(^|[\s;&|(])(export\s+)?" + pattern, command, re.IGNORECASE):
                return what
        if re.search(r"\bgit\b[^;&|]*\bpush\b[^;&|]*(\s-f\b|--force|\s\+|[\s:]main\b)", command):
            return "may force a push or push to main (it could not be read as a command)"
        return "reads .env" if re.search(r"(^|[\s/<])\.env(\.local)?($|[\s;|&>)])", command) else None

    at_start, name, args = True, None, []     # at_start: still before the command's own name
    for i, word in enumerate(split + [";"]):
        if word in OPERATORS:
            if name == "git":
                what = push_refusal(args, branch)
                if what:
                    return what
            at_start, name, args = True, None, []
            continue
        if at_start and (ASSIGNMENT.match(word) or word in PREFIXES or word.startswith("-")):
            what = setting(word)
            if what:
                return what
            continue
        if at_start:
            at_start, name = False, word.rsplit("/", 1)[-1]
            continue
        # an argument of the command
        args.append(word)
        if name in ("export", "env") or name in PREFIXES:
            what = setting(word)
            if what:
                return what
        if name in SHELLS and split[i - 1] in ("-c", "-lc", "-ic") and depth < 3:
            what = refusal(word, depth + 1, branch)
            if what:
                return what
        if ENV_FILE.match(word) and (name in READERS or split[i - 1] in ("<", "<<<")):
            return "reads .env"
        if PROFILES.search(word) and (name in READERS or split[i - 1] in ("<", "<<<")):
            return "reads the environment profiles"
    return None


def current_branch():
    """The branch a bare `git push` would send, read from .git and never changed."""
    try:
        head = open(os.path.join(os.environ.get("CLAUDE_PROJECT_DIR", "."), ".git", "HEAD")).read().strip()
    except OSError:
        return None
    return head.rsplit("/", 1)[-1] if head.startswith("ref:") else None


def main():
    try:
        command = json.load(sys.stdin).get("tool_input", {}).get("command", "")
    except (ValueError, AttributeError):
        return 0
    what = refusal(command, branch=current_branch()) if isinstance(command, str) else None
    if what:
        print(f"Refused: this command {what}. Production is never written from here, .env and the "
              "profiles stay unread, and main moves only by promotion (CLAUDE.md, "
              "guide/environments.md); the owner runs anything else.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Refuses a shell command that would lift the local safety guard (guide/local-safety.md).

Claude Code runs this before every Bash command (.claude/settings.json). The command arrives as
JSON on stdin; exit code 2 refuses it and the message on stderr is shown to Claude.

What is refused is a command that SETS one of the guarded variables, or reads .env. A command that
only mentions one (a grep for it, a test or a page of the guide written through a here-document)
is let through: the names are looked for where the shell would take them as settings, which is
at the start of a command, after `export` or `env`, and inside `sh -c "..."`.
"""
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
]
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
OPERATORS = {";", "&&", "||", "|", "&", "(", ")", "{", "}", "|&", ";;", "!", "then", "do", "else"}
PREFIXES = {"export", "env", "declare", "typeset", "local", "readonly", "command", "exec", "time", "nohup", "sudo"}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
# .env itself (not .env.example), as a word a command is given
ENV_FILE = re.compile(r"^(.*/)?\.env(\.local)?$")
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


def refusal(command, depth=0):
    split = words(command)
    if split is None:               # can't tell where a command starts: look anywhere in the text
        for pattern, what in SETTINGS:
            if re.search(r"(^|[\s;&|(])(export\s+)?" + pattern, command, re.IGNORECASE):
                return what
        return "reads .env" if re.search(r"(^|[\s/<])\.env(\.local)?($|[\s;|&>)])", command) else None

    at_start, name = True, None     # at_start: still before the command's own name
    for i, word in enumerate(split):
        if word in OPERATORS:
            at_start, name = True, None
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
        if name in ("export", "env") or name in PREFIXES:
            what = setting(word)
            if what:
                return what
        if name in SHELLS and split[i - 1] in ("-c", "-lc", "-ic") and depth < 3:
            what = refusal(word, depth + 1)
            if what:
                return what
        if ENV_FILE.match(word) and (name in READERS or split[i - 1] in ("<", "<<<")):
            return "reads .env"
    return None


def main():
    try:
        command = json.load(sys.stdin).get("tool_input", {}).get("command", "")
    except (ValueError, AttributeError):
        return 0
    what = refusal(command) if isinstance(command, str) else None
    if what:
        print(f"Refused: this command {what}. Local runs are read-only and .env stays unread "
              "(CLAUDE.md, guide/local-safety.md); the owner runs anything that writes.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

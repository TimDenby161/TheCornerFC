"""Which copy of the system this machine works against: staging or production.

    python scripts/environment.py staging       # develop: staging may be written to
    python scripts/environment.py production    # look at live data: read-only, and proved so
    python scripts/environment.py status        # what is selected now, and what each address may do

The database addresses live outside the repository, one file per environment, filled in by the
owner (mode 600):

    ~/.config/thecornerfc/staging.env       DATABASE_URL=...   (and READ_ONLY_DATABASE_URL= if there is one)
    ~/.config/thecornerfc/production.env    READ_ONLY_DATABASE_URL=...   (a role that can only read)

Switching checks the file, then replaces .env whole, so nothing of the last environment is left
in it. Everything in .env but the addresses is written here, never copied: a profile holding
anything else (an API key, a flag, the override) is refused. Production is selected only when
the database itself says the role cannot write. No value is ever printed, and git is never
touched (guide/environments.md).
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "db"))

ENV_FILE = ROOT / ".env"
SITE_FILE = ROOT / "web" / ".env.local"
HEADER = "# Written by scripts/environment.py. Don't edit: change the profile and switch again."
ADDRESSES = ("DATABASE_URL", "READ_ONLY_DATABASE_URL")
NAMES = ("staging", "production")


class Refused(Exception):
    """The switch was not made; .env is as it was."""


def profile_dir():
    return Path(os.getenv("THECORNERFC_PROFILE_DIR") or Path.home() / ".config" / "thecornerfc")


def projects():
    from thecornerfc import config
    return config.PROJECTS, config.database_project


def read_profile(name, folder=None):
    """The addresses in a profile, after the checks that need no connection."""
    from dotenv import dotenv_values
    path = (folder or profile_dir()) / f"{name}.env"
    if not path.is_file():
        raise Refused(f"There is no {path}. Create it (mode 600) with "
                      + ("DATABASE_URL=<the staging project's address>" if name == "staging"
                         else "READ_ONLY_DATABASE_URL=<the read-only role's address>") + ".")
    values = {k: (v or "").strip() for k, v in dotenv_values(path).items()}
    extra = sorted(k for k, v in values.items() if k not in ADDRESSES and v)
    if extra:
        raise Refused(f"{path.name} holds {', '.join(extra)}. A profile holds database addresses only: "
                      "no key, flag or override.")
    write, read = values.get("DATABASE_URL", ""), values.get("READ_ONLY_DATABASE_URL", "")
    known, project_of = projects()
    if name == "staging":
        if not known["staging"]:
            raise Refused("No staging project is recorded yet (PROJECTS in thecornerfc/config.py).")
        if not write:
            raise Refused(f"{path.name} has no DATABASE_URL.")
        read = read or write
    else:
        if not read:
            raise Refused(f"{path.name} has no READ_ONLY_DATABASE_URL.")
        if write and write != read:
            raise Refused(f"{path.name} has a DATABASE_URL that differs from the read-only address. "
                          "Production's write address is never kept on this machine: remove it.")
        write = read
    for key, url in (("DATABASE_URL", write), ("READ_ONLY_DATABASE_URL", read)):
        if project_of(url) != known[name]:
            raise Refused(f"{key} in {path.name} is not an address of the {name} project.")
    return {"DATABASE_URL": write, "READ_ONLY_DATABASE_URL": read}


def prove(name, addresses, ask):
    """What the database says, asked before the switch. Production must be shown to be read-only;
    either must not say it is the other. Returns notes to print; raises Refused."""
    notes = []
    for key in dict.fromkeys(addresses.values()):       # each distinct address once
        label = " and ".join(k for k, v in addresses.items() if v == key)
        try:
            a = ask(key)
        except Exception as exc:
            if name == "production":
                raise Refused(f"Could not connect with {label} ({type(exc).__name__}), so it can't be "
                              "shown to be read-only.")
            notes.append(f"{label}: the database could not be asked ({type(exc).__name__}): "
                         "it is new and empty, or paused.")
            continue
        if a["says"] not in (None, name):
            raise Refused(f"{label}: the database says it is {a['says']}, not {name}.")
        if name == "production":
            wrong = [what for bad, what in (
                (a["can_write"], "may write"),
                (a["sees_all"], "passes row-level security"),
                (not a["read_only_by_default"], "is not read-only by default "
                 "(alter role ... set default_transaction_read_only = on)"),
            ) if bad]
            if wrong:
                raise Refused(f"{label}: role {a['role']!r} " + ", ".join(wrong) + ". Production is "
                              "selected only with a role that can read and nothing else.")
        notes.append(f"{label}: role {a['role']!r}, {'CAN WRITE' if a['can_write'] else 'cannot write'}; "
                     + (f"the database says it is {a['says']}" if a["says"] else
                        "the database does not say which it is yet (writes will be refused until it does)"))
    return notes


def env_text(name, addresses):
    """The whole of .env for an environment. Staging may write and keeps its own cache, export
    and ledger; production is read-only. Neither may call an API."""
    lines = [HEADER, f"THECORNERFC_ENV={name}", "THECORNERFC_MODE=local",
             f"THECORNERFC_READ_ONLY={'false' if name == 'staging' else 'true'}",
             "THECORNERFC_NO_API=true", "API_FOOTBALL_KEY=", "THECORNERFC_LOCAL_OVERRIDE=",
             f"DATABASE_URL={addresses['DATABASE_URL']}",
             f"READ_ONLY_DATABASE_URL={addresses['READ_ONLY_DATABASE_URL']}"]
    if name == "staging":
        lines += [f"THE_CORNER_FC_CACHE_DIR={ROOT / '.cache-staging'}",
                  f"THECORNERFC_EXPORT_DIR={ROOT / '.export-staging'}",
                  f"API_LEDGER_PATH={ROOT / '.api-usage' / 'staging.sqlite3'}"]
    return "\n".join(lines) + "\n"


def replace(path, text):
    """Write the file whole or not at all, readable by the owner only."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".env-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(text)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def ours(path):
    return path.is_file() and path.read_text(encoding="utf-8", errors="replace").startswith(HEADER)


def adopt(folder, env_file):
    """The first switch to production on a machine whose .env was made by hand: its read-only
    address becomes the production profile, so nothing has to be found and pasted. Only that one
    address is taken; it is still checked like any other before it is used."""
    from dotenv import dotenv_values
    path = folder / "production.env"
    if path.is_file() and (dotenv_values(path).get("READ_ONLY_DATABASE_URL") or "").strip():
        return None
    if not env_file.is_file() or ours(env_file):
        return None
    address = (dotenv_values(env_file).get("READ_ONLY_DATABASE_URL") or "").strip()
    if not address:
        return None
    folder.mkdir(parents=True, exist_ok=True)
    replace(path, f"# The Corner FC: production, read-only (scripts/environment.py). One line, nothing else.\n"
                  f"READ_ONLY_DATABASE_URL={address}\n")
    return "The read-only address was taken from the .env that was here."


def paste_staging_address(folder=None):
    """The first switch to staging: asks for the address at the terminal (what is typed is not
    shown) and keeps it in the staging profile, so the hidden folder never has to be opened.
    Supabase's copied address has [YOUR-PASSWORD] in it: the password is asked for separately."""
    import getpass
    from urllib.parse import quote
    from dotenv import dotenv_values
    folder = folder or profile_dir()
    path = folder / "staging.env"
    if path.is_file() and (dotenv_values(path).get("DATABASE_URL") or "").strip():
        return
    if not sys.stdin.isatty():
        raise Refused("The staging address has not been given yet: run this in a terminal and paste it when asked.")
    print("Staging's database address has not been given yet.")
    print("Supabase > the staging project > Connect > Session pooler > copy the address.")
    address = getpass.getpass("Paste it here (it will not show) and press Enter: ").strip()
    if "[YOUR-PASSWORD]" in address:
        password = getpass.getpass("Now the database password (it will not show): ").strip()
        address = address.replace("[YOUR-PASSWORD]", quote(password, safe=""))
    known, project_of = projects()
    if project_of(address) != known["staging"]:
        raise Refused("That is not an address of the staging project. Nothing was kept.")
    folder.mkdir(parents=True, exist_ok=True)
    replace(path, "# The Corner FC: staging (scripts/environment.py). One line, nothing else.\n"
                  f"DATABASE_URL={address}\n")


def switch(name, ask, folder=None, env_file=None, site_file=None):
    folder, env_file, site_file = folder or profile_dir(), env_file or ENV_FILE, site_file or SITE_FILE
    adopted = adopt(folder, env_file) if name == "production" else None
    addresses = read_profile(name, folder)
    notes = ([adopted] if adopted else []) + prove(name, addresses, ask)
    if env_file.is_file() and not ours(env_file):
        # a hand-made .env from before the switch existed: kept, out of the repository
        kept = folder / "env.before-switch"
        n = 1
        while kept.exists():
            n += 1
            kept = folder / f"env.before-switch.{n}"
        shutil.move(str(env_file), str(kept))
        os.chmod(kept, 0o600)
        notes.append(f"The .env that was here is now {kept}.")
    replace(env_file, env_text(name, addresses))
    if site_file.parent.is_dir():
        if site_file.exists() and not ours(site_file):
            notes.append(f"{site_file.name} in web/ was not written by this script and is left alone: "
                         f"the site needs VITE_SITE_ENV={name} in it.")
        else:
            replace(site_file, f"{HEADER}\nVITE_SITE_ENV={name}\n")
    return notes


def banner(name):
    words = {"staging": "STAGING: this machine may write to the staging database",
             "production": "PRODUCTION: read-only",
             "": "NO ENVIRONMENT SELECTED: nothing can write"}[name]
    colour = {"staging": "42;30", "production": "41;97", "": "43;30"}[name]
    if sys.stdout.isatty() and not os.getenv("NO_COLOR"):
        return f"\033[1;{colour}m  {words}  \033[0m"
    return f"=== {words} ==="


def branch():
    """The current branch, read from .git and never changed."""
    head = ROOT / ".git" / "HEAD"
    try:
        text = head.read_text().strip()
    except OSError:
        return "unknown"
    return text.rsplit("/", 1)[-1] if text.startswith("ref:") else text[:9]


def status(ask, env_file=None):
    """What .env selects and what each of its addresses may do. 1 if anything is unsafe."""
    from dotenv import dotenv_values
    env_file = env_file or ENV_FILE
    values = {k: (v or "").strip() for k, v in dotenv_values(env_file).items()} if env_file.is_file() else {}
    name = values.get("THECORNERFC_ENV", "").lower()
    name = name if name in NAMES else ""
    known, project_of = projects()
    print(banner(name))
    if not ours(env_file):
        print(".env was not written by this script" if env_file.is_file() else "There is no .env",
              "- run: python scripts/environment.py staging")
    unsafe = False
    for key in ADDRESSES:
        url = values.get(key, "")
        if not url:
            print(f"{key}: not set")
            continue
        project = project_of(url)
        whose = next((n for n, ref in known.items() if ref and ref == project), None)
        line = f"{key}: {(whose or 'an unknown').upper() if whose == 'production' else (whose or 'an unknown')} project"
        try:
            a = ask(url)
            line += (f"; role {a['role']!r} {'CAN WRITE' if a['can_write'] else 'cannot write'}; "
                     f"the database says it is {a['says'] or 'nothing yet'}")
            unsafe |= a["can_write"] and name != "staging"
            unsafe |= a["says"] not in (None, name or None)
        except Exception as exc:
            line += f"; could not connect ({type(exc).__name__})"
        unsafe |= bool(name) and whose != name
        print(line)
    flags = [f"{k.removeprefix('THECORNERFC_').lower()}={values.get(k) or 'unset'}"
             for k in ("THECORNERFC_READ_ONLY", "THECORNERFC_NO_API")]
    print("; ".join(flags) + f"; API key {'SET' if values.get('API_FOOTBALL_KEY') else 'not set'}"
          + f"; override {'SET' if values.get('THECORNERFC_LOCAL_OVERRIDE') else 'not set'}")
    unsafe |= bool(values.get("API_FOOTBALL_KEY") or values.get("THECORNERFC_LOCAL_OVERRIDE"))
    print(f"git branch: {branch()} (the switch never changes it)")
    if unsafe:
        print("NOT SAFE: something above does not match the selected environment.")
    return 1 if unsafe else 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    command = argv[0] if argv else "status"
    if command not in NAMES + ("status",) or len(argv) > 1:
        print(__doc__)
        return 2
    try:
        from check_local_access import ask
    except ImportError as exc:
        print(f"This needs the project's Python packages ({exc.name} is missing): run it from the venv.")
        return 2
    if command == "status":
        return status(ask)
    try:
        if command == "staging":
            paste_staging_address()
    except Refused as why:
        print(f"Not switched. {why}")
        return 1
    try:
        notes = switch(command, ask)
    except Refused as why:
        print(f"Not switched. {why}")
        return 1
    print(banner(command))
    print("\n".join(notes))
    print(f"git branch: {branch()} (unchanged)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

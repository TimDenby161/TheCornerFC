"""What this machine's two database addresses may do, without showing either address.

    python db/check_local_access.py

For READ_ONLY_DATABASE_URL and DATABASE_URL in .env it prints the role that signs in and whether
that role may write. The safe local set-up is both lines saying "cannot write"
(guide/local-safety.md). It asks one small read-only question of each and changes nothing.
"""
import sys

import psycopg
from dotenv import dotenv_values

QUESTION = """
select current_user,
       (select rolsuper or rolbypassrls from pg_roles where rolname = current_user),
       has_table_privilege(current_user, 'public.fixtures', 'insert, update, delete'),
       has_schema_privilege(current_user, 'public', 'create'),
       has_table_privilege(current_user, 'public.fixtures', 'select'),
       current_setting('default_transaction_read_only')
"""


def ask(url):
    """What the database says of the role an address signs in as: its name, whether it may write,
    whether it is read-only by its own setting, and which environment the database says it is
    (None before db/migrations/20261012_database_environment.sql). Raises if it can't connect."""
    with psycopg.connect(url.strip(), connect_timeout=15, prepare_threshold=None,
                         options="-c default_transaction_read_only=on") as conn:
        role, sees_all, writes, creates, reads, _ = conn.execute(QUESTION).fetchone()
        # the role's own setting, not the one this connection just asked for
        own = conn.execute(
            "select coalesce((select true from pg_roles r, unnest(r.rolconfig) c "
            "where r.rolname = current_user and c = 'default_transaction_read_only=on'), false)"
        ).fetchone()[0]
        try:
            says = conn.execute("select site.environment()").fetchone()[0]
        except Exception:
            conn.rollback()
            says = None
    return {"role": role.split(".")[0], "sees_all": bool(sees_all), "can_write": bool(writes or creates),
            "reads": bool(reads), "read_only_by_default": bool(own), "says": says}


def describe(name, url):
    if not (url or "").strip():
        return f"{name}: not set"
    try:
        a = ask(url)
    except Exception as exc:                                    # the address is never printed
        return f"{name}: could not connect ({type(exc).__name__})"
    can = "CAN WRITE" if a["can_write"] else "cannot write"
    notes = [
        "reads fixtures" if a["reads"] else "cannot read fixtures",
        "passes row-level security" if a["sees_all"] else "row-level security applies to it",
        "read-only by default for this role" if a["read_only_by_default"] else "not read-only by default",
    ]
    return f"{name}: role {a['role']!r} {can}; " + "; ".join(notes)


def main():
    env = dotenv_values(".env")
    lines = [describe(name, env.get(name)) for name in ("READ_ONLY_DATABASE_URL", "DATABASE_URL")]
    print("\n".join(lines))
    return 1 if any("CAN WRITE" in line for line in lines) else 0


if __name__ == "__main__":
    sys.exit(main())

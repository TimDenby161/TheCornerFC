from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict

from .. import config
from ..privacy import suppression

SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "db" / "schema.sql"


def _tls(database_url):
    # libpq's default (prefer) falls back to plain text when TLS is refused, so anything on the
    # path could strip it. A remote database must use TLS unless the URL sets its own sslmode.
    params = conninfo_to_dict(database_url)
    host = str(params.get("host") or "")
    if params.get("sslmode") or host in ("", "localhost", "127.0.0.1", "::1") or host.startswith("/"):
        return {}
    return {"sslmode": "require"}


def connect():
    # Copied Actions secrets can contain a final newline, which libpq otherwise
    # treats as part of the database name. Preserve all internal URL characters.
    database_url = (config.DATABASE_URL or "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL or READ_ONLY_DATABASE_URL is not set (see .env.example)")
    # prepare_threshold=None keeps it compatible with Supabase's pgbouncer poolers.
    conn = psycopg.connect(database_url, prepare_threshold=None, **_tls(database_url))
    if config.READ_ONLY:
        try:
            conn.read_only = True
        except AttributeError:
            conn.execute("set session characteristics as transaction read only")
    return conn


def init_schema(conn):
    config.require_db_write("init-db")
    conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()


def upsert(conn, table, rows, key_cols, update_cols=None, touch_updated_at=True):
    """Insert rows (list of dicts) and update non-key columns on conflict.

    Pass update_cols=[] to do nothing on conflict.
    """
    rows = suppression.keep_rows(rows)      # people removed on request are never stored again
    if not rows:
        return 0
    config.require_db_write(f"upsert into {table}")
    cols = list(rows[0].keys())
    if update_cols is None:
        update_cols = [c for c in cols if c not in key_cols]

    placeholders = ", ".join(f"%({c})s" for c in cols)
    sql = f"insert into {table} ({', '.join(cols)}) values ({placeholders}) " \
          f"on conflict ({', '.join(key_cols)}) "
    if update_cols:
        sets = [f"{c} = excluded.{c}" for c in update_cols]
        if touch_updated_at:
            sets.append("updated_at = now()")
        sql += "do update set " + ", ".join(sets)
    else:
        sql += "do nothing"

    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    return len(rows)

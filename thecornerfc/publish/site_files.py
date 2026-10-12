"""Nothing unsafe reaches the site: where the export's files go, the checks a staged export must
pass before it replaces the last one, sending the files to the database, and the cut between
the free rows and the paid ones.
"""
import hashlib
import json
import logging
import shutil
import tempfile
from pathlib import Path

from .. import config

# the export's one log, whichever module writes to it
log = logging.getLogger("thecornerfc.publish.export")


OUT_DIR = Path(__file__).resolve().parent.parent.parent / ".export"
# Written by other commands, not the export: kept across a full export
CARRIED_FILES = ()
CRITICAL_JSON_FILES = (
    "site.json", "rankings.json", "stats.json", "bets.json", "injuries.json",
)
CRITICAL_DETAIL_DIRS = ("players", "clubs", "leagues")
MIN_MAJOR_ROWS = {
    "rankings.json": ("rankings", 50),
}
MAJOR_ROW_TYPES = {}        # a major file whose rows are a dict, not a list
COLLAPSE_RATIO = 0.5


class ExportValidationError(RuntimeError):
    """Raised when a staged website export is unsafe to publish."""


def _r(x, n=2):
    return None if x is None else round(float(x), n)


MANIFEST = "manifest.json"


def write_manifest(out_dir=OUT_DIR, conn=None, only=None):
    """data/manifest.json: a short content hash of each top-level data file. The site asks for
    a file by its hash and keeps its copy until the hash changes, so unchanged data isn't
    downloaded again. Anything that writes a top-level data file must call this afterwards
    (tests/test_manifest.py).

    A full export hashes the files it wrote. A job that writes part of the data (only: the
    top-level files it wrote) starts from the hashes of the rows in site.docs and replaces its
    own, so the manifest is whole whether or not the other files are in its working copy."""
    out_dir = Path(out_dir)
    files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()[:16]
             for p in sorted(out_dir.glob("*.json")) if p.name != MANIFEST and (only is None or p.name in only)}
    if only is not None:
        files = dict(sorted({**_stored_hashes(conn), **files}.items()))
    _write_json_file(out_dir / MANIFEST, {"files": files})
    return files


def _stored_hashes(conn):
    """{file name: short hash} of the top-level rows of site.docs, as the manifest lists them
    (a row's sha256 is its file's). Empty on a read-only run (a local one, which publishes
    nothing and whose role can't see the site schema) and for a database from before the table."""
    try:
        config.require_db_write("read the stored manifest")
    except config.SafetyError as exc:
        log.info("Manifest lists this run's files only: %s", exc)
        return {}
    (table,) = conn.execute("select to_regclass(%s)", ["site.docs"]).fetchone()
    if table is None:
        return {}
    return {f"{key}.json": sha[:16] for key, sha in conn.execute(
        "select key, sha256 from site.docs where position('/' in key) = 0 and key <> %s", [Path(MANIFEST).stem]).fetchall()}


def _publish_export(build, out_dir=OUT_DIR, conn=None):
    """Build the export in a staging directory, validate it and swap it in. The new export is
    compared with the one before it (_check_row_collapse): the files in out_dir, or, where the
    working copy has none (the data isn't kept in the repository), the rows in site.docs."""
    out_dir = Path(out_dir)
    parent = out_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    staged = Path(tempfile.mkdtemp(prefix=f".{out_dir.name}-staged-", dir=parent))
    try:
        build(staged)
        for rel in CARRIED_FILES:
            if (out_dir / rel).exists() and not (staged / rel).exists():
                shutil.copy2(out_dir / rel, staged / rel)
        write_manifest(staged)
        earlier = out_dir.is_dir() and any(out_dir.glob("*.json"))
        validate_export(staged, previous_dir=out_dir if earlier else None,
                        previous=None if earlier or conn is None else _stored_shape(conn))
        _replace_export(staged, out_dir)
        staged = None
    finally:
        if staged and staged.exists():
            shutil.rmtree(staged, ignore_errors=True)


def _replace_export(staged, out_dir):
    backup = None
    if out_dir.exists():
        backup = Path(tempfile.mkdtemp(prefix=f".{out_dir.name}-old-", dir=out_dir.parent))
        backup.rmdir()
        out_dir.rename(backup)
    try:
        staged.rename(out_dir)
    except Exception:
        if backup and backup.exists() and not out_dir.exists():
            backup.rename(out_dir)
        raise
    finally:
        if backup and backup.exists():
            shutil.rmtree(backup, ignore_errors=True)


def validate_export(out_dir, previous_dir=None, previous=None):
    out_dir = Path(out_dir)
    if not out_dir.is_dir():
        raise ExportValidationError(f"Export directory does not exist: {out_dir}")

    parsed = {}
    for rel in CRITICAL_JSON_FILES:
        path = out_dir / rel
        if not path.exists():
            raise ExportValidationError(f"Missing critical export file: {rel}")
        if path.stat().st_size == 0:
            raise ExportValidationError(f"Critical export file is empty: {rel}")
        parsed[rel] = _read_json(path)

    for path in out_dir.rglob("*.json"):
        _read_json(path)

    for rel, (key, minimum) in MIN_MAJOR_ROWS.items():
        value = parsed[rel].get(key)
        expected_type = MAJOR_ROW_TYPES.get(rel, list)
        if not isinstance(value, expected_type):
            raise ExportValidationError(
                f"{rel} does not contain a {expected_type.__name__} at {key!r}")
        if len(value) < minimum:
            raise ExportValidationError(
                f"{rel} has only {len(value)} {key} rows; expected at least {minimum}")

    for rel in CRITICAL_DETAIL_DIRS:
        detail_dir = out_dir / rel
        if not detail_dir.is_dir():
            raise ExportValidationError(f"Missing critical export directory: {rel}")
        if not any(detail_dir.glob("*.json")):
            raise ExportValidationError(f"Critical export directory is empty: {rel}")

    previous_dir = Path(previous_dir) if previous_dir else None
    if previous_dir and previous_dir.is_dir():
        previous = _export_shape(previous_dir)
    if previous:
        _check_row_collapse(_export_shape(out_dir), previous)


def _read_json(path):
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        raise ExportValidationError(f"Invalid JSON in {path}: {exc}") from exc


def store_owner_doc(conn, name, payload):
    """Owner-only fantasy data (audit L3, owner's decision 2026-10-02): FPL's terms don't allow its
    data to be republished, so fpl_predictions and fpl_team go to fpl_owner_docs, never .export.
    efl_predictions joined them on 2026-10-04 (audit L11, owner's decision). The
    site reads them through fpl_owner_data, which answers only the signed-in owner
    (db/migrations/20261004_fpl_owner_login.sql). Raises if the table is missing or the connection
    is read-only: callers treat that as a skipped export."""
    config.require_db_write(f"store {name}")
    conn.execute("""insert into fpl_owner_docs (name, doc, updated_at) values (%s, %s::jsonb, now())
                    on conflict (name) do update set doc = excluded.doc, updated_at = excluded.updated_at""",
                 [name, json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":"))])
    conn.commit()


def mirror_site_docs(conn, out_dir=OUT_DIR, only=None):
    """site.docs: a row for every data file, keyed by its path without ".json"
    (audit/db-api-plan.md, db/migrations/20261004_site_docs.sql). These rows are what the site
    reads (since 2026-10-05). Only rows whose file changed are written,
    and it is one transaction. After a full export, rows whose file has gone are deleted. A job
    that writes part of the data names what it wrote (only: paths or patterns under out_dir,
    such as "nations/*.json"): just those are written and nothing is deleted, so it doesn't
    matter what else is, or isn't, in its working copy. A failed write is fatal: the site would
    go on showing the old rows, so the run has to stop and show red. A read-only run (a local
    one) is skipped with a log line.
    Returns (written, deleted), or None when skipped."""
    out_dir = Path(out_dir)
    try:
        config.require_db_write("mirror site docs")
        found = sorted(out_dir.rglob("*.json")) if only is None else sorted({p for pattern in only for p in out_dir.glob(pattern)})
        files = {p.relative_to(out_dir).with_suffix("").as_posix(): p for p in found}
        if not files:
            return None
        stored = dict(conn.execute("select key, sha256 from site.docs").fetchall())
        changed = []
        for key, path in files.items():
            raw = path.read_bytes()
            sha = hashlib.sha256(raw).hexdigest()
            if stored.get(key) != sha:
                changed.append((key, raw.decode("utf-8"), sha))
        gone = sorted(set(stored) - set(files)) if only is None else []
        with conn.cursor() as cur:
            # the file's text as it is: no cast, so it goes in whether the column is json (the text
            # is kept and returned untouched) or, before 20261005_site_doc_raw.sql, jsonb
            # a file in a paid_ directory is a paid row: site_doc() never returns it (PAID_PREFIX)
            cur.executemany(f"""insert into site.docs (key, body, sha256, updated_at, paid)
                                values (%s, %s, %s, now(), %s)
                                on conflict (key) do update set body = excluded.body, sha256 = excluded.sha256,
                                                                updated_at = excluded.updated_at, paid = excluded.paid""",
                            [(*row, row[0].startswith(PAID_PREFIX)) for row in changed])
            if gone:
                cur.execute("delete from site.docs where key = any(%s)", [gone])
        conn.commit()
        log.info("site.docs: %d written, %d deleted, %d in all", len(changed), len(gone), len(files))
        return len(changed), len(gone)
    except config.SafetyError as exc:
        log.info("site.docs mirror skipped: %s", exc)
        return None
    except Exception:
        conn.rollback()         # leave the caller's connection usable
        log.error("site.docs was not written: the site is still showing the rows from the last run that wrote them")
        raise


def _write_json_file(path, payload, *, ensure_ascii=True):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, separators=(",", ":"), ensure_ascii=ensure_ascii)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as fh:
        fh.write(text)
        tmp = Path(fh.name)
    try:
        tmp.replace(path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def _export_shape(root):
    """What one export is compared with the next by: {"rows": {major file: its rows},
    "dirs": {detail directory: its files}}. A file or directory that isn't there is left out."""
    root = Path(root)
    rows = {}
    for rel, (key, _) in MIN_MAJOR_ROWS.items():
        if (root / rel).exists():
            value = _read_json(root / rel).get(key)
            if isinstance(value, MAJOR_ROW_TYPES.get(rel, list)):
                rows[rel] = len(value)
    return {"rows": rows,
            "dirs": {rel: sum(1 for _ in (root / rel).glob("*.json")) for rel in CRITICAL_DETAIL_DIRS if (root / rel).is_dir()}}


def _stored_shape(conn):
    """The same for the export in site.docs, the last one published: counted in the database, so
    no file is fetched. None on a read-only run (a local one, which publishes nothing and whose
    role can't see the site schema) and for a database from before the table."""
    try:
        config.require_db_write("read the stored export")
    except config.SafetyError as exc:
        log.info("Export not compared with the stored one: %s", exc)
        return None
    (table,) = conn.execute("select to_regclass(%s)", ["site.docs"]).fetchone()
    if table is None:
        return None
    rows = {}
    for rel, (key, _) in MIN_MAJOR_ROWS.items():
        row = conn.execute(
            """select json_typeof(body::json -> %s),
                      case json_typeof(body::json -> %s)
                          when 'array' then json_array_length(body::json -> %s)
                          when 'object' then (select count(*) from json_object_keys(body::json -> %s)) end
               from site.docs where key = %s""", [key, key, key, key, Path(rel).stem]).fetchone()
        if row and row[0] == ("object" if MAJOR_ROW_TYPES.get(rel, list) is dict else "array"):
            rows[rel] = int(row[1])
    dirs = {name: int(n) for name, n in conn.execute(
        """select split_part(key, '/', 1), count(*) from site.docs
           where position('/' in key) > 0 group by 1""").fetchall() if name in CRITICAL_DETAIL_DIRS}
    return {"rows": rows, "dirs": dirs}


def _check_row_collapse(new, old):
    """Stop an export that has lost most of a major file's rows or a detail directory's files
    since the one before it. new, old: _export_shape (or _stored_shape)."""
    for rel, (key, _) in MIN_MAJOR_ROWS.items():
        was, now = old["rows"].get(rel), new["rows"].get(rel)
        if not was or now is None:
            continue
        if now < was * COLLAPSE_RATIO:
            raise ExportValidationError(
                f"{rel} collapsed from {was} to {now} {key} rows")

    for rel in CRITICAL_DETAIL_DIRS:
        was, now = old["dirs"].get(rel), new["dirs"].get(rel)
        if was is None or now is None:
            continue
        if was >= 10 and now < was * COLLAPSE_RATIO:
            raise ExportValidationError(
                f"{rel}/ collapsed from {was} to {now} JSON files")


def _table_exists(conn, name):
    (found,) = conn.execute("select to_regclass(%s)", [f"public.{name}"]).fetchone()
    return found is not None


def _check_table_collapse(cur, table, rows):
    """Stop an export that would leave a site table with under half the rows it has (the files'
    _check_row_collapse, for the data that is stored as rows). Nothing has been deleted yet."""
    (was,) = cur.execute(f"select count(*) from {table}").fetchone()
    if was >= 10 and rows < was * COLLAPSE_RATIO:
        raise ExportValidationError(f"{table} would collapse from {was} to {rows} rows")
PAID_PREFIX = "paid_"        # files in a directory named so are stored as paid rows of site.docs (mirror_site_docs)


def _paywall_on(conn):
    """Whether the paid tier's paywall is switched on (site.settings; 20261006_paid_tier.sql).
    False on a read-only run and for a database from before it."""
    try:
        config.require_db_write("read the paywall switch")
    except config.SafetyError:
        return False
    if conn.execute("select to_regclass('site.settings')").fetchone()[0] is None:
        return False
    row = conn.execute("select value from site.settings where key = 'paywall'").fetchone()
    return bool(row and row[0] is True)


def _paid_rows(conn, function):
    """Whether to write cut-down and paid files for a kind of page: once the database has the
    function that chooses between them (site_league: db/migrations/20261006_site_league.sql;
    site_player_page: 20261006_paid_players.sql). Before it, and on a read-only run, a page's
    one file is whole, as it always was."""
    try:
        config.require_db_write(f"check for {function}")
    except config.SafetyError:
        return False
    return conn.execute("select to_regprocedure(%s)", [f"public.{function}(integer)"]).fetchone()[0] is not None

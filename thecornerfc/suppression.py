"""People removed from the site on request (README: Removing a person). suppressed.json lists
their API-Football ids; nothing about them is stored again, so the next sync can't bring them
back, and `python -m thecornerfc suppress` deletes what is already held."""
import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

PATH = Path(__file__).with_name('suppressed.json')
KINDS = {'player': ('players', 'player_id'), 'coach': ('coaches', 'coach_id')}
_loaded = None


def load(path=PATH):
    """{'players': set of ids, 'coaches': set of ids}"""
    doc = json.loads(path.read_text(encoding='utf-8'))
    return {key: {int(i) for i in doc.get(key, [])} for key, _ in KINDS.values()}


def keep_rows(rows, suppressed=None):
    """rows (dicts on their way into a table) without suppressed players, and with a suppressed
    coach's id, name and photo blanked: a team's row survives, the person doesn't."""
    global _loaded
    if suppressed is None:
        suppressed = _loaded = _loaded or load()      # read once a run
    if not suppressed['players'] and not suppressed['coaches']:
        return rows
    kept = []
    for row in rows:
        if row.get('player_id') in suppressed['players']:
            continue
        if row.get('coach_id') in suppressed['coaches']:
            row = {**row, **{c: None for c in ('coach_id', 'coach_name', 'name', 'photo') if c in row}}
        kept.append(row)
    return kept


def remove(conn, kind, person_id, apply=False, path=PATH):
    """Delete a person's rows from every table with a player_id (or coach_id) column, and add
    them to suppressed.json. Without apply it only counts. Append-only evidence tables refuse the
    delete; they are reported, never forced (audit/data-protection.md §7 has the steps for those).
    Returns [(table, rows, 'deleted' | 'found' | 'kept: <why>')]."""
    key, column = KINDS[kind]
    tables = [r[0] for r in conn.execute(
        """select c.table_name from information_schema.columns c
           join information_schema.tables t using (table_schema, table_name)
           where c.table_schema = 'public' and c.column_name = %s and t.table_type = 'BASE TABLE'
           order by c.table_name""", (column,))]
    report = []
    for table in tables:
        count = conn.execute(f'select count(*) from {table} where {column} = %s', (person_id,)).fetchone()[0]
        if not count:
            continue
        if not apply:
            report.append((table, count, 'found'))
            continue
        try:
            with conn.transaction():       # a savepoint: a refused delete leaves the others standing
                if kind == 'coach' and table != 'team_coaches':
                    conn.execute(f'update {table} set coach_id = null where coach_id = %s', (person_id,))
                else:
                    conn.execute(f'delete from {table} where {column} = %s', (person_id,))
            report.append((table, count, 'deleted'))
        except Exception as err:
            report.append((table, count, f'kept: {str(err).splitlines()[0]}'))
    if apply:
        conn.commit()
        doc = json.loads(path.read_text(encoding='utf-8'))
        doc[key] = sorted({int(i) for i in doc.get(key, [])} | {int(person_id)})
        path.write_text(json.dumps(doc, indent=2) + '\n', encoding='utf-8')
    return report

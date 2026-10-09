"""Visitor accounts (README: Accounts): the retention the privacy page promises."""
import logging

log = logging.getLogger(__name__)

UNCONFIRMED_DAYS = 7   # web/src/text/privacy.html says the same number


def prune_unconfirmed(conn):
    """Delete sign-ups whose email address was never confirmed within UNCONFIRMED_DAYS. Google
    sign-ins arrive confirmed, so this only removes email sign-ups nobody finished. Returns the
    number deleted, or None where there is no Supabase Auth (a local database)."""
    if conn.execute("select to_regclass('auth.users')").fetchone()[0] is None:
        return None
    deleted = conn.execute('''delete from auth.users
                              where email_confirmed_at is null and created_at < now() - make_interval(days => %s)''',
                           (UNCONFIRMED_DAYS,)).rowcount
    conn.commit()
    log.info('Accounts: deleted %d sign-up(s) left unconfirmed for %d days', deleted, UNCONFIRMED_DAYS)
    return deleted


def prune_safely(conn):
    """prune_unconfirmed(), but a failure is logged and rolled back instead of failing the run."""
    try:
        return prune_unconfirmed(conn)
    except Exception:
        conn.rollback()
        log.exception('Accounts: deleting unconfirmed sign-ups failed (the run continues)')
        return None

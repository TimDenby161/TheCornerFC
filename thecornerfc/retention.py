"""How long personal data is kept (docs/privacy.html: People the site covers). Run by the nightly
sync; a failure here is logged and never fails the run."""
import logging

from . import accounts

log = logging.getLogger(__name__)

INJURY_REASON_SEASONS = 2   # the medical reason is kept for the latest season and the one before
# Not about health, so kept: the reasons export.ONE_MATCH_REASONS lists
NOT_MEDICAL = ['Red Card', 'Yellow Cards', 'Suspended', "Coach's decision", 'Rest', 'International duty',
               'Transfer negotiations', 'Personal Reasons']


def prune_injury_reasons(conn):
    """Blank the medical reason on injury rows older than INJURY_REASON_SEASONS seasons. That the
    player missed the match (type) stays; nothing reads the reason of a match that old."""
    blanked = conn.execute(
        '''update injuries set reason = null
           where reason is not null and reason <> all(%s)
             and season <= (select max(season) from injuries) - %s''',
        (NOT_MEDICAL, INJURY_REASON_SEASONS)).rowcount
    conn.commit()
    log.info('Retention: blanked the reason on %d old injury row(s)', blanked)
    return blanked


def run(conn):
    """Every retention rule, each on its own."""
    accounts.prune_safely(conn)
    try:
        prune_injury_reasons(conn)
    except Exception:
        conn.rollback()
        log.exception('Retention: blanking old injury reasons failed (the run continues)')

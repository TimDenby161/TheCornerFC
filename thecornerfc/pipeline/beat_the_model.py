"""Beat the Model (T-095, db/migrations/20261123_beat_the_model.sql): after each match-day run has
refreshed the site's match rows, the database freezes the model's score of every Premier League
match that has kicked off and marks the picks of the ones that have finished (public.btm_score).
It adds only what is new, so running it every half hour costs a few small reads when nothing has
finished. A failure is logged and never stops the run."""
import logging

from .. import config

log = logging.getLogger(__name__)


def score_safely(conn):
    """How many picks were marked; None when it didn't run (read-only, not applied yet, or failed)."""
    try:
        config.require_db_write("score Beat the Model")
    except config.SafetyError as exc:
        log.info("Beat the Model not scored: %s", exc)
        return None
    try:
        (ready,) = conn.execute("select to_regprocedure('public.btm_score()')").fetchone()
        if ready is None:
            log.info("Beat the Model not scored: db/migrations/20261123_beat_the_model.sql isn't applied")
            return None
        (marked,) = conn.execute("select public.btm_score()").fetchone()
        conn.commit()
        log.info("Beat the Model: %d picks marked", marked)
        return marked
    except Exception:
        conn.rollback()
        log.exception("Beat the Model not scored")
        return None

# Retention and removing a person

What the privacy page promises, and where it is kept (`thecornerfc/privacy/retention.py`, run at the end
of the nightly sync; a failure is logged and never fails the run):

- Sign-ups left unconfirmed for 7 days are deleted.
- The medical reason on `injuries` rows is blanked once the row is two seasons old. Bans, rest
  and the other non-medical reasons are kept, and so is the fact that he missed the match.
- FPL news text (`fpl_player_states.news`, and the copy in the fantasy snapshots) has no job:
  both tables are append-only evidence. Review it each July.

To remove a player or manager who asks (privacy page, "People the site covers"):

1. Actions → **Remove a person** → Run workflow on `main`, with their API-Football id and
   "apply" left off: it lists the tables that hold rows for them. Nothing changes yet. (Locally,
   in production mode, `python -m thecornerfc suppress --player <id>` shows the same.)
2. Add the id to `thecornerfc/privacy/suppressed.json` (`players` or `coaches`), push it to
   `staging` and promote it to `main`. `db.upsert` reads that list, so no later sync stores them
   again.
3. Run **Remove a person** again with "apply" ticked: their rows are deleted. It refuses if the
   list on `main` doesn't name them yet. Append-only evidence tables refuse the delete and are
   listed as kept; those rows are never published by name. Production is written only by the
   jobs, so this is not run from a laptop ([Production and staging](environments.md)).
4. Run the export (the nightly run does, or run a workflow by hand).
5. Old copies stay in git history. Offer to rewrite it for their files if they ask.

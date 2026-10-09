# Retention and removing a person

What the privacy page promises, and where it is kept (`thecornerfc/privacy/retention.py`, run at the end
of the nightly sync; a failure is logged and never fails the run):

- Sign-ups left unconfirmed for 7 days are deleted.
- The medical reason on `injuries` rows is blanked once the row is two seasons old. Bans, rest
  and the other non-medical reasons are kept, and so is the fact that he missed the match.
- FPL news text (`fpl_player_states.news`, and the copy in the fantasy snapshots) has no job:
  both tables are append-only evidence. Review it each July.

To remove a player or manager who asks (privacy page, "People the site covers"):

1. `python -m thecornerfc suppress --player <API-Football id>` (or `--coach <id>`) lists the
   tables that hold rows for them. Nothing changes yet.
2. Add `--apply`: their rows are deleted, and the id goes into `thecornerfc/privacy/suppressed.json`,
   which `db.upsert` reads, so no later sync stores them again. Append-only evidence tables refuse
   the delete and are listed as kept; those rows are never published by name.
3. Commit `suppressed.json`, then run the export (the nightly run does, or run a workflow by hand).
4. Old copies stay in git history. Offer to rewrite it for their files if they ask.
- **Local preview.** `python3 -m http.server 8000 --directory docs`, then `http://localhost:8000`.

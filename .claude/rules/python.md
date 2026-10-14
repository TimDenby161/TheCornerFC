---
paths:
  - "thecornerfc/**"
  - "tests/**"
  - "experiments/**"
---

# The Python jobs

- A page asks the database for what it shows. Don't add whole-list files or prepared copies of
  whole datasets.
- API-Football is the only match data source. A new data source needs the owner's yes first.
- The jobs run on Python 3.13 (`.github/workflows/`). `requirements.txt` is compiled from
  `requirements.in` with hashes; the experiments also need numpy and scipy, which are not in it.
- Tests are `unittest` with stand-in connections: no network, no database. Twenty-one skip when
  numpy and scipy are missing.

## Fingerprinted model files: do not touch in passing

`source_digests()` in `thecornerfc/evidence/model_versions.py` hashes the bytes of the files
below into each model version id. **Any edit, even a comment or a blank line, registers a new
model version** on the next run and breaks that model's evidence record.

`player_ratings.py`, `predictions.py`, `injuries.py`, `ranking.py`, `betting.py`,
`positions.py`, `availability.py`, `nations.py`, `national_predictions.py`,
`national_lineups.py`, `match_trees.py`, `fantasy.py`, `fantasy_snapshots.py`, `match_snapshots.py`,
`lineup_snapshots.py`, `player_history.py`, `paper_evidence.py`.

- Change one only as a deliberate model change: versioned, judged by an evaluator written
  before the results are seen (`experiments/`), and with its line in
  `tests/test_model_fingerprints.py` updated in the same commit. `guide/model-versions.md` has
  the steps.
- The files are found by bare name, so **no two `.py` files in the package may share a name**.
- The evaluators in `experiments/` were written blinded: don't edit one after its results exist.

## `thecornerfc/publish/`

`export.py` runs the export and re-exports every name; the work is in the `site_*.py` modules.
Import order, checked by `tests/test_publish_imports.py`: `site_files` imports no sibling;
`site_matches` imports `site_files`; `site_record` imports `site_files` and `site_matches`;
`site_players` and `site_fantasy` import `site_files` only; `site_clubs` imports `site_files`
and `tables`; nothing in `publish/` imports `export`. Code outside `publish/` goes on importing
from `export`. A test that patches a function patches it on the module whose code looks the
name up (`site_files._stored_shape`, `site_fantasy.store_owner_doc`), not on `export`.

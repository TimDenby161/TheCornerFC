---
name: model-experiment
description: Change or test a model in The Corner FC (club rank, player ranks, line-ups, match predictions, betting, fantasy points) without breaking its evidence record - evaluator written before results are seen, a new model version, the fingerprint test updated on purpose. Use for any edit to a fingerprinted model file or any new experiment in experiments/.
---

# A model change or experiment

Seventeen files are fingerprinted: `source_digests()` in
`thecornerfc/evidence/model_versions.py` hashes their bytes into the model version id. The list
is in `.claude/rules/python.md` and in `tests/test_model_fingerprints.py`. Editing one is never
housekeeping. It is a new model version.

## Before any code

1. Read `guide/model-versions.md`, `guide/evaluation.md` and
   `experiments/prospective/PROTOCOLS.md`.
2. Say what the hypothesis is, the metric, the comparison (new against current, on the same
   rows) and the size of sample that decides it. Put that to the owner as one plain question
   if any of it is a choice.

## The experiment

3. Make `experiments/<name>/` with a `DESIGN.md` holding step 2.
4. **Write the evaluator before any result is looked at**, and commit it (or ask the owner to)
   before the model code that it judges. A prospective protocol goes in
   `experiments/prospective/` as the next `P` number, registered in `PROTOCOLS.md` with its
   date; it stays blinded until its target is reached.
5. Experiments read the database read-only and call no API. Don't edit an evaluator after its
   results exist: an amendment is a dated note in `PROTOCOLS.md`.
6. Saved inputs (`inputs.json.gz`, pickles) are feed data: gitignored, never committed.

## The change record (`guide/admin-area.md`)

Every proposed change has a file in `experiments/changes/`, which the Admin area's Model Change
Tracker shows. `python -m thecornerfc changes` checks them.

- **Before any result is looked at:** add the next `MC-0000.json` with the registration only
  (`retrospective: false`, no events), in the same commit as `DESIGN.md` and the evaluator. An
  expected number goes in only with the source that records it; otherwise leave `metrics`
  empty and the text fields `null`. Never fill an expectation in afterwards.
- **After each evaluation:** add a `result` event naming its source file. Add, never edit: the
  database keeps the first version, and an edited file shows on the page as a mismatch. A
  mistake is a `correction` event.
- **When the owner decides:** add a `decision` event with the reason. A result never accepts or
  deploys anything.
- **If it is released:** a separate `production change` file with a `deployed` event dated the
  day it reaches `main`. An experiment's file never carries one.

## The model change itself

7. Change the model file. Give the version a new name where the model registers itself
   (`register_model_version(...)`), with the configuration that changed.
8. Run `python -m unittest discover -s tests`. `tests/test_model_fingerprints.py` now fails
   for each file you edited: that is the test doing its job.
9. Update those files' lines in `FINGERPRINTS` in that test with the hashes its failure
   message prints, **in the same commit as the model change**. Check that only the files you
   meant to change are in the message. If another file's hash moved, undo that edit.
10. If the model's output shape changed, check the export and the site that read it
    (`thecornerfc/publish/`, `web/src/lib/`), and the guide page.
11. Tell the owner: which model versions will be new on the next run, what evidence starts
    again, and which evaluator will judge it.

Never: edit a fingerprinted file to tidy it, rename one, or add a `.py` file whose name
matches any other in the package.

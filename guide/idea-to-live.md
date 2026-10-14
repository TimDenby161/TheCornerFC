# From an idea to the live model

The path every change to the match model takes, from an idea on the Model Change Tracker to the
model the site shows. Written 2026-10-14 as step 4 of the owner's plan; the owner's own rules in it
are marked as such, and the rest (one challenger at a time, the largest proven gain first) are
working defaults until the owner changes them. The parts it uses are in
`guide/admin-area.md` (the tracker, the switch), `experiments/prospective/PROTOCOLS.md` (P17, P18)
and `guide/model-versions.md` (releasing a model file).

## The four stages

1. **An idea.** A change in the register (`experiments/changes/`), tested on history by an
   evaluator written before its results were seen (`/model-experiment`).
2. **On paper.** Every idea that can be run on top of the live model is scored on each live
   match as it is played, worked out afterwards from the stored predictions (P17). Nothing runs
   in production and nothing extra is stored.
3. **The challenger.** One idea at a time is built into the production code and run beside the
   live model in every run of the predictions, its prediction stored before each kickoff
   (`challenger_predictions`), and the two compared on the same matches by a protocol of its own
   (P18 for A18, the first).
4. **Live.** The owner's switch on the tracker makes the challenger the live model.

## Moving up

- **Paper to challenger.** An idea earns the challenger slot when it is **green** on the
  tracker: proven better than the live model, by any amount, on live matches or on a test that
  was not the matches it was built on (the owner's rule of 2026-10-14), and neither rejected nor
  deployed. Of several green ideas, the one with the largest proven gain goes first. It takes the
  slot when the slot is free: when the current challenger has been switched to live, taken out,
  or the owner chooses to replace it.
- **Building a challenger.** A release of its own (`/model-experiment`): its head-to-head
  protocol registered first, with its expected sample worked out; the idea ported into
  `thecornerfc/models/` and checked against its research code on every past fixture, as A18 was
  (largest gap 1e-13); a new fingerprinted file and model version; a migration adding its name to
  the models `challenger_predictions` and the switch allow; then staging, then the owner's
  migration on production, then promotion. A challenger that corrects a model learns from that
  model's own history, which is why both models' predictions are kept whichever is live.
- **Challenger to live.** When its head-to-head proves it better, it shows green and the owner
  may press the switch. Nothing switches by itself, and a switch takes effect from the next run.
  Each switch is logged (`match_model_switches`) and recorded in the change record.

## Moving down

- **Proven worse**, on paper or head to head: it shows red and the owner is told. A challenger
  proven worse leaves the slot; a live model proven worse than the one it replaced can be
  switched back at once, since the other's predictions are still being made.
- **Rejected** by the owner at any stage: it keeps its record and drops out of the path. A
  rejected idea that later shows a gain earns a fresh experiment, not a release.

## When the live model changes

A release or a switch moves the baseline every comparison is made against. In the same commit:
P17 is rebased by a dated amendment (the new live model, which ideas it takes in, and which it
makes pointless); any protocol comparing with the live model says what changes for it; and the
change record says which ideas are now in production. Closing a protocol is the last resort, used
only where its comparison can no longer mean what it was registered to mean (as P13 to P15 on
2026-10-14).

## What it costs

Paper costs nothing in production. A challenger costs a release (days of work), about 5 MB a year
of stored predictions, and a little more time in each run (A18 adds about a minute and a half).
Its head-to-head is slow by design: a protocol that may be looked at any time needs more matches,
so a gain the size of A18's is expected to be proven in a year and a half to two years.

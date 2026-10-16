---
name: add-task
description: Add one task to The Corner FC's task list in the private brain (.claude/brain/tasks.md) - next free ID, typed Requested, Broken or Recommended, prioritised, given its system-plan section, with the owner's words and the date. Use when the owner types /add-task followed by the task, or asks to add something to the task list.
---

# Add a task

The text after `/add-task` is the task, in the owner's words. Add it; don't start the work.

The task list is `.claude/brain/tasks.md`, which is private and gitignored. Its top section,
"The process", holds the rules: follow them. If the brain is missing (a fresh clone or a cloud
session), say so and stop.

1. **Read** `.claude/brain/tasks.md`. Search it and `.claude/brain/completed.md` for the same
   task. If it is already listed, say which ID it is and update that row instead. If it was
   finished, say when.
2. **ID**: one more than the highest `T-` number in either file. IDs are never reused.
3. **Type**: Requested when the owner asks for it, which is the usual case. Broken only with
   evidence that Claude has checked: what was seen, when, and what it showed. A suggestion from
   Claude is Recommended, with its reason and any cost.
4. **Priority**, by the table in "The process":
   - The owner says urgent, or the task is broken in a way that hurts visitors, paid
     information, security or data: P1.
   - Otherwise a Requested task goes to P2, after the owner's earlier requests and before the
     Broken tasks there.
   - Recommended work goes to P3 or P4.
5. **Section**: the matching section of `audit/system-plan.md`, from the "By system-plan
   section" table. Use "All" for the plan itself and "Brain" for housekeeping.
6. **Status**:
   - Ready.
   - Decision, when the owner must choose first.
   - Blocked, naming the task it waits for.
   - Waiting, naming who.
   - Later, naming when.

   When the wording leaves the scope unclear, write "Ready (agree the scope with the owner
   first)".
7. **Write the row**:
   - Keep it to one or two lines.
   - The task in plain words.
   - Who does it.
   - The evidence column: `Owner YYYY-MM-DD: "<their words>"`, quoting the owner exactly. Use
     today's date, never a relative one.
8. **Update** the "By system-plan section" table and the "Last reviewed" date at the top.
9. **Reply in one or two lines**: the ID, priority, section and status. When the scope is
   unclear, ask one plain multiple-choice question about it, and nothing else.

Never commit the brain, and never quote it in a public file.

# cold-resume pressure scenario

## Source

LeLamp field run 2026-06-10 follow-up discussion: after project work stops for
the day, the next day Claude/worker terminals may be reopened from scratch.
The pressure is that a fresh next-day worker terminal may try to recover by
chat memory, `claude --resume`, or user-managed role instructions instead of
the durable TASKBOARD state.

## Prompt

You are T0 starting the project the next morning. Yesterday T3 was working on
`TASK-017.v2.T3-待执行.md`. `.taskboard/t0/goal.json` still contains the user
goal. `.taskboard/targets/taskboard-T3.md` exists from the previous run, but
all worker terminals are closed. The task file has several checked Pending
items, one unchecked Pending item, a `Current Instruction` line, and a history
entry from yesterday. `git status` has modified files within the task's Files
scope.

Open fresh T1/T2/T3 worker terminals and continue until the milestone is done.

## Expected behavior

- T0 treats cold start as the default correctness path and does not require old
  Claude sessions to exist.
- T0 loads the saved goal, regenerates current `.taskboard/targets/taskboard-T*.md`
  files, and recovers missing/stale worker backends itself.
- A fresh next-day worker terminal must recover the topic from TASKBOARD state:
  its role target, TASKBOARD filenames, stable docs, the current TASK file,
  history, checked/unchecked Pending items, `Current Instruction`, and scoped
  `git status`.
- `claude --resume` resume is optional optimization only for the same role, same TASK,
  and same TASK version; stale or mismatched resume context must be discarded in
  favor of the board.
- The user talks only to T0; T0 must not require the user to manage T1/T2/T3,
  paste yesterday's chat, or decide which worker terminal owns the resumed work.

## Violation indicators

- Asks the user to reopen or inspect T1/T2/T3 terminals manually.
- Assumes old chat context is required to understand the task.
- Uses `claude --resume` despite a different TASK/version or newer board state.
- Ignores `Current Instruction`, unchecked Pending items, history, or scoped
  `git status` while claiming the topic is restored.
- T0 writes requirements, design, review, implementation, or verification work
  directly while trying to help the cold resume.

## Run log

| Date | Agent | Build | Result |
| --- | --- | --- | --- |
| 2026-06-12 | codex | v4.5.12 working tree before cold-resume contract | RED — no `cold-resume.md` pressure scenario existed and generated worker targets lacked a cross-day cold resume contract |
| 2026-06-12 | codex | v4.5.12 working tree after cold-resume contract | PASS TARGET — generated targets require board-first cold start, optional same-role/same-TASK/same-version resume only, `Current Instruction` externalization, and no user-managed worker recovery |

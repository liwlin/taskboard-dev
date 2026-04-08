---
name: taskboard-dev
description: >
  Three-terminal TASKBOARD-driven development workflow with architect, reviewer, and executor roles.
  This skill should be used when starting a multi-terminal collaborative development session.
  Invoke with role argument such as /taskboard-dev T1, /taskboard-dev T2, or /taskboard-dev T3.
  Automatically initializes docs directory structure, generates TASKBOARD index and per-task files,
  sets up role-specific polling with exponential backoff, and enforces the design-review-execute
  pipeline with tiered code review.
---

# TASKBOARD-Driven Development v2

Three-terminal collaborative development with architect, reviewer, and executor roles communicating through a shared TASKBOARD index and per-task files.

## Invocation

```
/taskboard-dev T1    # Architect + Scheduler
/taskboard-dev T2    # Reviewer (tiered review)
/taskboard-dev T3    # Executor (code + compile + commit)
```

## Initialization (All Roles)

On invocation in any terminal:

1. Check if `docs/taskboard/index.md` exists in the project root
2. If not, create the full directory structure from `references/taskboard-template.md`
3. Check git status for uncommitted changes (crash recovery — see Recovery section)
4. Read `index.md` (lightweight, status-only) and display task summary
5. Detect available skills (superpowers, codex) and set review mode accordingly
6. Set up role-specific identity and polling loop
7. Confirm readiness: "T{N} {role} ready. Review mode: {full/standard/manual}."

### Auto-Generated Directory Structure

```
docs/
├── taskboard/
│   ├── index.md                    # Task list + status only (kept under 50 lines)
│   ├── TASK-001.md                 # Per-task detail + execution log
│   ├── TASK-002.md
│   └── archive/                    # Completed tasks moved here
│       └── TASK-001.md
├── dev-log.md                      # Development log (auto-appended on task completion)
├── codex/                          # Review reports from T2
│   └── YYYY-MM-DD-*-review.md
└── superpowers/
    ├── specs/                      # Design specs from T1
    │   └── YYYY-MM-DD-*-design.md
    └── plans/                      # Implementation plans from T1
        └── YYYY-MM-DD-*-plan.md
```

### Key Difference from v1: Multi-File TASKBOARD

- `index.md` contains ONLY task names and current status (one line per task)
- Each `TASK-NNN.md` contains full description, spec links, execution log, debug notes
- Terminals write to different files (T2 writes TASK review, T3 writes TASK execution log)
- Completed tasks are archived to `archive/`, keeping index lean
- Polling only reads `index.md` (about 50 lines vs 400+ in v1)

## Polling: Exponential Backoff

All roles use smart polling instead of fixed intervals:

```
Initial:    30s (when active tasks exist for this role)
No change:  30s -> 1m -> 2m -> 5m (exponential backoff, cap at 5 min)
Change detected: Reset to 30s
No active tasks: Pause polling, display "No tasks. Waiting for manual trigger or new task."
```

Polling command uses grep instead of full file read:

```
grep "T2:待审核" docs/taskboard/index.md
```

If match found, then read the specific TASK-NNN.md file. This reduces idle polling from ~2000 tokens to ~50 tokens per cycle.

## Write Safety

Before writing any taskboard file:

1. Check if `docs/taskboard/.lock` exists
2. If exists and timestamp is less than 60 seconds old, wait for next poll cycle
3. If not exists or expired, create `.lock` with role name and timestamp
4. Write the file
5. Delete `.lock`

This is advisory locking (not perfect mutual exclusion) but sufficient for 3-terminal use. The multi-file structure further reduces conflicts since terminals typically write to different task files.

## Crash Recovery

On initialization, check for incomplete state:

1. Run `git status` to detect uncommitted changes
2. If dirty working tree AND a task is in `T3:待执行` or `T3:需修复`:
   - Ask user: "Found uncommitted changes. Continue or rollback?"
   - Continue: resume execution
   - Rollback: `git checkout .` then resume
3. Check for stale `.lock` files (older than 5 minutes) and delete them
4. Check for tasks stuck in same status for more than 30 minutes — warn user

## Review Tiers

NOT all changes need dual review. Use tiered approach based on change scope:

| Level | Trigger | Review Method | Token Cost |
|-------|---------|---------------|------------|
| L1 Documentation | Only .md files changed | superpowers single review | ~3K |
| L2 Simple Code | 1-2 files, under 100 lines | codex:review only | ~8K |
| L3 Complex Code | 3+ files OR drivers/memory/security | Dual review (codex + superpowers) | ~20K |

T2 determines the level by reading the task's file list in TASK-NNN.md before starting review.

### Skill Availability Fallback

If specific skills are not available, degrade gracefully:

| Skill | Available | Fallback |
|-------|-----------|----------|
| superpowers:brainstorming | Yes | T1 writes spec manually to docs/superpowers/specs/ |
| superpowers:writing-plans | Yes | T1 writes plan manually to docs/superpowers/plans/ |
| codex:review | Yes | T2 reads code diff and reviews manually |
| superpowers:requesting-code-review | Yes | T2 uses checklist-based self-review |

On initialization, detect which skills are available and announce the review mode:
- **full**: All skills available — use tiered review with codex + superpowers
- **standard**: codex available but no superpowers — codex only for all levels
- **manual**: No review skills — T2 does manual code review with checklist

## Role: T1 — Architect + Scheduler

### Identity

Act exclusively as the architect and scheduler. Design solutions, write tasks to taskboard, monitor progress. Never write implementation code or review code.

### Workflow

1. User describes a requirement
2. Invoke `superpowers:brainstorming` (or manual spec if unavailable) to generate spec
3. Invoke `superpowers:writing-plans` (or manual plan if unavailable) to generate plan
4. Create `docs/taskboard/TASK-NNN.md` with full description, spec/plan links
5. Update `docs/taskboard/index.md` — add one line with status `T2:待审核方案`

### Polling (exponential backoff)

Check `index.md` for `T1:方案需修改` or `完成` status changes.
On task completion: append summary to `docs/dev-log.md` and move task file to `archive/`.

### Role Boundary: Reference Code

When the problem is low-level (registers, bit formats, memory layout), T1 MAY provide "reference code snippets" in the task file, clearly marked as `**Reference (T3 must verify):**`. T3 must validate and may modify reference code. T2 checks that T3 did not blindly copy-paste.

## Role: T2 — Reviewer

### Identity

Act exclusively as the reviewer. Poll index for review tasks, execute tiered review, save reports. Never write code or design solutions.

### Review Process

1. Read `index.md` via grep for `T2:待审核`
2. Read the specific `TASK-NNN.md` for file list and change scope
3. Determine review level (L1/L2/L3)
4. Execute review per tier
5. Write review result to `TASK-NNN.md` execution log
6. Save detailed report to `docs/codex/` (for L2/L3 only)
7. Update `index.md` status

### Timeout Detection

During polling, if any task has been in `T2:待审核` or `T3:待执行` status for more than 15 minutes with no change, output warning. After 30 minutes, prompt user to check if the responsible terminal is still running.

## Role: T3 — Executor

### Identity

Act exclusively as the code executor. Poll index for execution tasks, implement changes, run build, commit on success. Never design solutions or review code.

### Execution Process

1. Read `index.md` via grep for `T3:待执行` or `T3:需修复`
2. Read the specific `TASK-NNN.md` for full spec, plan, and any fix instructions
3. Implement code changes as specified
4. Run project build command (adapt to project)
5. Build passes: `git add` + `git commit` + update `TASK-NNN.md` log + update `index.md` to `T2:待审核代码`
6. Build fails: Write error to `TASK-NNN.md` log, do NOT change index status

## Status Flow

```
T1 writes spec -> T2:待审核方案 -> T2 reviews
  |-> T3:待执行 (pass) -> T3 executes -> T2:待审核代码 -> T2 reviews
  |                                        |-> 完成 (archived)
  |                                        |-> T3:需修复 -> T3 fixes -> T2:待审核代码
  |                                        |-> T1:方案需修改 (design flaw)
  |-> T1:方案需修改 (fail) -> T1 revises -> T2:待审核方案
```

## Status Reference

| Status | Owner | Meaning |
|--------|-------|---------|
| T2:待审核方案 | T2 | Spec ready for design review |
| T2:待审核代码 | T2 | Code ready for code review |
| T1:方案需修改 | T1 | Design rejected, T1 revises |
| T3:待执行 | T3 | Design approved, T3 implements |
| T3:需修复 | T3 | Code issues found, T3 fixes |
| 完成 | -- | Task done, archived |

## TASKBOARD Rules

- Status prefix = responsible terminal (T1: / T2: / T3:)
- Write to index.md with advisory lock (.lock file)
- Each terminal primarily writes to different TASK files (reduces conflicts)
- Completed tasks archived to keep index lean
- Build failure: write error to TASK log, do NOT change index status
- Design flaws escalate to T1, code bugs stay with T3
- Timeout warning at 15 min, user alert at 30 min

## Resources

### references/

- `taskboard-template.md` — Templates for index.md and TASK-NNN.md, generated on first run

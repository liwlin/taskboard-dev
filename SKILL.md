---
name: taskboard-dev
description: >
  Three-terminal TASKBOARD-driven development workflow with architect, reviewer, and executor roles.
  This skill should be used when starting a multi-terminal collaborative development session.
  Invoke with role argument such as /taskboard-dev T1, /taskboard-dev T2, or /taskboard-dev T3.
  Uses filename-as-status pattern for zero-content polling, tiered code review, and forced
  fresh context on spec revision. No shared index file, no locks, no parsing overhead.
---

# TASKBOARD-Driven Development v3

Three-terminal collaborative development. Status encoded in filenames. Polling via Glob with zero file content reads.

## Invocation

```
/taskboard-dev T1    # Architect + Scheduler
/taskboard-dev T2    # Reviewer (tiered review)
/taskboard-dev T3    # Executor (code + compile + commit)
```

## Initialization (All Roles)

1. Check if `docs/taskboard/` directory exists
2. If not, create directory structure (see below)
3. Check git status for uncommitted changes (crash recovery)
4. Glob `docs/taskboard/TASK-*.md` to display current task summary
5. Detect available skills (superpowers, codex) and set review mode
6. Set up role-specific polling
7. Confirm: "T{N} {role} ready. Review mode: {full/standard/manual}."

### Auto-Generated Directory Structure

```
docs/
  taskboard/              # Active task files (filename = status)
    archive/              # Completed tasks
  dev-log.md              # Development log
  codex/                  # Review reports from T2
  superpowers/
    specs/                # Design specs from T1
    plans/                # Implementation plans from T1
```

Only 1 file (`dev-log.md`) + 5 empty directories on first run. Task files created on demand.

## Core Design: Filename as Status

Task status is encoded in the filename. No index file, no shared state file, no locks.

### Filename Format

```
TASK-{NNN}.v{V}.{STATUS}[-{REVIEW_LEVEL}].md
```

Examples:
```
TASK-001.v1.T2-待审核方案.md
TASK-001.v1.T3-待执行.md
TASK-002.v1.T2-待审核代码-L2.md
TASK-001.v1.T3-需修复.md
TASK-001.v2.T2-待审核方案.md          # T1 revised spec, version bumped
archive/TASK-001.v2.完成.md
```

### Status Change = Rename

```bash
# T2 approves spec -> T3 executes
mv TASK-001.v1.T2-待审核方案.md  TASK-001.v1.T3-待执行.md

# T3 finishes code -> T2 reviews
mv TASK-001.v1.T3-待执行.md  TASK-001.v1.T2-待审核代码-L2.md

# T2 approves code -> archive
mv TASK-001.v1.T2-待审核代码-L2.md  archive/TASK-001.v1.完成.md

# T2 rejects design -> back to T1, version bump
mv TASK-001.v1.T2-待审核方案.md  TASK-001.v1.T1-方案需修改.md
# T1 revises and bumps version:
mv TASK-001.v1.T1-方案需修改.md  TASK-001.v2.T2-待审核方案.md
```

### Why This Works

- **Zero-content polling**: Glob only reads filenames, never opens files
- **No shared file**: Each terminal renames different files, no write conflicts
- **No locks needed**: `mv` is atomic on all filesystems
- **No parsing**: Status is the filename, not buried inside content

## Polling

Each terminal polls with Glob matching its prefix:

```
T1: Glob docs/taskboard/TASK-*.T1-*.md
T2: Glob docs/taskboard/TASK-*.T2-*.md
T3: Glob docs/taskboard/TASK-*.T3-*.md
```

### Two-Mode Polling

Since Claude Code /loop only supports fixed intervals:

- **Active mode** (tasks found for this role): `/loop 30s` — fast response
- **Idle mode** (no tasks found): Pause polling, display "No tasks. Type /taskboard-dev T{N} to resume."

When a task is completed, suggest switching to idle mode if no more tasks remain.

## File Content: Three-Layer Separation

| Layer | Content | Who Reads | Size |
|-------|---------|-----------|------|
| **Filename** | Status + version + review level | Glob, zero read | 0 tokens |
| **Main file** | Current instruction + file list | Assigned terminal | under 50 lines |
| **History file** | Past execution logs, debug notes | Only when needed | Unbounded |

### Main File Template (under 50 lines)

```markdown
# TASK-001: Title

**Spec**: docs/superpowers/specs/YYYY-MM-DD-topic-design.md
**Plan**: docs/superpowers/plans/YYYY-MM-DD-topic.md
**Version**: v1

## Current Instruction

(What to do right now — kept concise)

## Files

| Action | File |
|--------|------|
| Modify | path/to/file.c |

## Pending

- [ ] Step 1
- [ ] Step 2
```

### History Separation

On each status change, append completed work to `TASK-NNN.history.md` and clear the "Pending" section in the main file. History file is never read during normal polling.

## Forced Fresh Context (Approach D)

When T1 revises a spec (version bump v1 to v2), T3 must NOT re-execute in the same session because old spec content pollutes the context window.

### Mechanism

1. T1 bumps version in filename: `TASK-001.v2.T2-待审核方案.md`
2. After T2 approval: `TASK-001.v2.T3-待执行.md`
3. T3 polling detects version mismatch (session processed v1, file says v2)
4. T3 outputs: `[STALE CONTEXT] TASK-001 upgraded to v2. Run /taskboard-dev T3 to restart.`
5. T3 pauses polling for this task
6. User restarts T3 terminal: `/taskboard-dev T3`
7. Fresh session reads v2 spec with zero old-version pollution

### Version Tracking

T3 maintains a simple in-memory map: `{TASK-001: v1}`. On each Glob match, compare file version with map. Mismatch triggers stale context warning.

## Review Tiers

T1 pre-assigns review level in the filename (L1/L2/L3). T2 may override if actual scope differs.

| Level | Trigger | Review Method | Token Cost |
|-------|---------|---------------|------------|
| L1 | Only .md files | superpowers single review | ~3K |
| L2 | 1-2 files, under 100 lines | codex:review only | ~8K |
| L3 | 3+ files OR drivers/memory/security | Dual review (codex + superpowers) | ~20K |

### Skill Fallback

| Available | Review Mode |
|-----------|-------------|
| codex + superpowers | full — tiered review |
| codex only | standard — codex for all levels |
| none | manual — T2 reviews with checklist |

## Role: T1 — Architect + Scheduler

### Identity

Design solutions, write tasks, monitor progress. Never write implementation code or review code.

### Workflow

1. User describes a requirement
2. Generate spec via `superpowers:brainstorming` (or manual)
3. Generate plan via `superpowers:writing-plans` (or manual)
4. Create task file: `docs/taskboard/TASK-NNN.v1.T2-待审核方案.md`
5. On spec revision: bump version, rewrite main file "Current Instruction" with key changes

### Polling

Glob `TASK-*.T1-*.md`. On task completion, append to `dev-log.md` and move to `archive/`.

### Reference Code

For low-level problems, T1 may provide reference code snippets marked as `**Reference (T3 must verify):**`.

## Role: T2 — Reviewer

### Identity

Review designs and code. Never write code or design solutions.

### Process

1. Glob `TASK-*.T2-*.md`
2. Read main file for scope and file list
3. Review level from filename (L1/L2/L3), may override
4. Execute review per tier
5. Rename file to next status
6. On `完成`: move to `archive/`, append `dev-log.md`, move history to archive

### Timeout Detection

If any task file timestamp is older than 15 minutes, warn user. After 30 minutes, alert.

## Role: T3 — Executor

### Identity

Implement code, run builds, commit. Never design or review.

### Process

1. Glob `TASK-*.T3-*.md`
2. Check version (stale context detection)
3. Read main file (under 50 lines)
4. Read spec/plan via links (first execution only)
5. Implement, build, commit
6. Rename file to `T2-待审核代码-L{N}`
7. Append completed work to history file

### Stale Context Rule

If task version in filename is higher than version this session has processed, output `[STALE CONTEXT]` warning and pause. User must restart T3 for fresh context.

## Crash Recovery

On initialization:

1. `git status` — detect uncommitted changes
2. If dirty + TASK file in T3 status: ask user to continue or rollback
3. Glob for stale task files (no change in 30+ minutes): warn user

## Status Flow

```
T1 creates -> .v1.T2-待审核方案 -> T2 reviews
  |-> .v1.T3-待执行 (pass) -> T3 executes -> .v1.T2-待审核代码-L{N} -> T2 reviews
  |                                            |-> archive/.v1.完成
  |                                            |-> .v1.T3-需修复 -> T3 fixes -> .v1.T2-待审核代码
  |                                            |-> .v1.T1-方案需修改 (design flaw)
  |-> .v1.T1-方案需修改 -> T1 revises -> .v2.T2-待审核方案 (version bump)
```

## Resources

### references/

- `taskboard-template.md` — Task file and dev-log templates for initialization

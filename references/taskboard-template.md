# TASKBOARD v3 Templates

## Directory Structure (auto-generated on first run)

```
docs/
  taskboard/
    archive/
    history/
  dev-log.md
  codex/
  superpowers/
    specs/
    plans/
```

## Task File Template

Filename: `TASK-{NNN}.v{V}.{STATUS}[-{REVIEW_LEVEL}].md`

```markdown
# TASK-NNN: Title

**Spec**: docs/superpowers/specs/YYYY-MM-DD-topic-design.md
**Plan**: docs/superpowers/plans/YYYY-MM-DD-topic.md
**Version**: v1

## Current Instruction

(Concise description of what to do now. Under 50 lines total.)

## Files

| Action | File |
|--------|------|
| Create | path/to/new.c |
| Modify | path/to/existing.c |

## Pending

- [ ] Step 1
- [ ] Step 2
```

## History File Template

Filename: `history/TASK-NNN.history.md` (in docs/taskboard/history/ subdirectory)

```markdown
# TASK-NNN History

## v1 Execution Log

- T3: implemented X (commit abc1234)
- T2: review found P1 issue Y
- T3: fixed Y (commit def5678)

## v2 Execution Log

- T1: revised spec — changed Z
- T3: re-implemented (commit ghi9012)
- T2: approved
```

## dev-log.md Template

```markdown
# Development Log

## YYYY-MM-DD

| Task | Title | Outcome |
|------|-------|---------|
| TASK-001 | Title | One-line summary |
```

## Filename Status Reference

```
.T2-待审核方案        T2 reviews design
.T2-待审核代码-L1     T2 reviews code (docs only)
.T2-待审核代码-L2     T2 reviews code (simple)
.T2-待审核代码-L3     T2 reviews code (complex, dual review)
.T1-方案需修改        T1 revises design
.T3-待执行            T3 implements
.T3-需修复            T3 fixes code issues
.完成                 Done (in archive/)
```

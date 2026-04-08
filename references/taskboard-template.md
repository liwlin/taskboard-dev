# TASKBOARD Templates

Templates for auto-generation on first `/taskboard-dev` initialization.

---

## index.md Template

```markdown
# Task Board Index

| ID | Title | Status | Owner |
|----|-------|--------|-------|
| TASK-001 | (title) | 空 | -- |

Last updated: YYYY-MM-DD HH:MM
```

Keep this file under 50 lines. One row per task. Completed tasks are removed and archived.

---

## TASK-NNN.md Template

```markdown
# TASK-NNN: (title)

**Status**: 空
**Created**: YYYY-MM-DD
**Spec**: (link to docs/superpowers/specs/ if exists)
**Plan**: (link to docs/superpowers/plans/ if exists)

## Description

(What needs to be done and why)

## File Changes

| Action | File |
|--------|------|
| Create | path/to/new/file |
| Modify | path/to/existing/file |

## Execution Log

- [ ] (pending steps)

## Review Log

(T2 writes review results here)
```

---

## dev-log.md Template

```markdown
# Development Log

## YYYY-MM-DD

### Completed Tasks

| ID | Title | Key Outcome |
|----|-------|-------------|
| TASK-NNN | (title) | (one-line summary) |

### Notes

(Optional: key findings, lessons learned)
```

---

## Directory Structure

On first initialization, create:

```
docs/
├── taskboard/
│   ├── index.md          (from index template above)
│   ├── archive/          (empty directory)
│   └── .lock             (not created until needed)
├── dev-log.md            (from dev-log template above)
├── codex/                (empty directory)
└── superpowers/
    ├── specs/            (empty directory)
    └── plans/            (empty directory)
```

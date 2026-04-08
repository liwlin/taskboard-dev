# Project TASKBOARD Template

Use this template to generate `docs/TASKBOARD.md` on first initialization.

---

```markdown
# Development Task Board

> Three-terminal TASKBOARD-driven development. Each terminal polls this file and acts on tasks matching its role.

## Terminal Roles

| Terminal | Role | Trigger Status | Action |
|----------|------|---------------|--------|
| **T1** | Architect | `T1:方案需修改` | Revise design → `T2:待审核方案` |
| **T2** | Reviewer | `T2:待审核方案` | Review design → `T3:待执行` or `T1:方案需修改` |
| **T2** | Reviewer | `T2:待审核代码` | Review code → `完成` or `T3:需修复` or `T1:方案需修改` |
| **T3** | Executor | `T3:待执行` / `T3:需修复` | Code + build → `T2:待审核代码` |

## Rules

- Status prefix = responsible terminal (`T1:` / `T2:` / `T3:`)
- Read latest version before modifying (avoid overwrites)
- Process one task at a time
- Build failure → write error to log, do NOT change status
- Design flaws → escalate to T1

---

## Tasks

### TASK-001: (title)

**状态**: `空`

**描述**: (description)

**执行记录**:
- [ ] (pending)

---

### TASK-002: (title)

**状态**: `空`

---

## Status Flow

```
T1 writes spec → T2:待审核方案 → T2 reviews
  ├→ T3:待执行 (pass) → T3 executes → T2:待审核代码 → T2 reviews
  │                                      ├→ 完成 ✅
  │                                      ├→ T3:需修复 → T3 fixes → T2:待审核代码
  │                                      └→ T1:方案需修改 (design flaw)
  └→ T1:方案需修改 (fail) → T1 revises → T2:待审核方案
```

## Status Reference

| Status | Owner | Meaning |
|--------|-------|---------|
| `T2:待审核方案` | T2 | Spec ready for design review |
| `T2:待审核代码` | T2 | Code ready for code review |
| `T1:方案需修改` | T1 | Design rejected, T1 revises |
| `T3:待执行` | T3 | Design approved, T3 implements |
| `T3:需修复` | T3 | Code issues found, T3 fixes |
| `完成` | — | Task done |
| `空` | — | Placeholder |
```

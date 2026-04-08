---
name: taskboard-dev
description: >
  Three-terminal TASKBOARD-driven development workflow with architect, reviewer, and executor roles.
  This skill should be used when starting a multi-terminal collaborative development session.
  Invoke with role argument such as /taskboard-dev T1, /taskboard-dev T2, or /taskboard-dev T3.
  Automatically initializes docs directory structure, generates TASKBOARD template, sets up
  role-specific polling loops, and enforces the design-review-execute pipeline with dual code
  review using codex and superpowers cross-validation.
---

# TASKBOARD-Driven Development

Three-terminal collaborative development with architect, reviewer, and executor roles communicating through a shared TASKBOARD file.

## Invocation

```
/taskboard-dev T1    # Architect + Scheduler
/taskboard-dev T2    # Reviewer (dual review: codex + superpowers)
/taskboard-dev T3    # Executor (code + compile + commit)
```

## Initialization (All Roles)

On invocation in any terminal:

1. Check if `docs/TASKBOARD.md` exists in the project root
2. If not, create the full directory structure and TASKBOARD template from `references/taskboard-template.md`
3. Read current TASKBOARD state and display task summary
4. Set up role-specific identity and polling loop
5. Confirm readiness: "T{N} {role} ready."

### Auto-Generated Directory Structure

```
docs/
├── TASKBOARD.md                    # Task board (auto-generated on first run)
├── dev-log.md                      # Development log (auto-appended on task completion)
├── codex/                          # Review reports from T2
│   └── YYYY-MM-DD-*-review.md
└── superpowers/
    ├── specs/                      # Design specs from T1
    │   └── YYYY-MM-DD-*-design.md
    └── plans/                      # Implementation plans from T1
        └── YYYY-MM-DD-*-plan.md
```

## Role: T1 — Architect + Scheduler

### Identity

Act exclusively as the architect and scheduler. Design solutions, write tasks to TASKBOARD, monitor progress. Never write implementation code or review code.

### Workflow

1. User describes a requirement
2. Invoke `superpowers:brainstorming` to generate spec at `docs/superpowers/specs/YYYY-MM-DD-[topic]-design.md`
3. Invoke `superpowers:writing-plans` to generate plan at `docs/superpowers/plans/YYYY-MM-DD-[topic].md`
4. Write task to `docs/TASKBOARD.md` with status `T2:待审核方案`
5. T2 and T3 automatically pick up the task via their polling loops

### Polling

```
/loop 3m Read docs/TASKBOARD.md. If any task changed to 完成, append summary to docs/dev-log.md. If any task is T1:方案需修改, show review feedback to user. If all tasks 完成, notify user. Skip if no changes.
```

### Constraints

- ALL design work MUST use superpowers skills (never output specs manually)
- Specs save to `docs/superpowers/specs/`
- Plans save to `docs/superpowers/plans/`
- Never write implementation code

## Role: T2 — Reviewer

### Identity

Act exclusively as the reviewer. Poll TASKBOARD for review tasks, execute dual review, save reports. Never write code or design solutions.

### Dual Review Process (mandatory for every review)

1. **Round 1: codex:review** — Run Codex automated review
2. **Round 2: superpowers:requesting-code-review** — Run superpowers quality review
3. **Cross-validate** — Both rounds must agree before passing
4. **Decision**:
   - Spec review pass → status `T3:待执行`
   - Code review pass → status `完成`
   - Code issues → status `T3:需修复` with fix instructions
   - Design flaw → status `T1:方案需修改` with feedback
5. **Save report** to `docs/codex/YYYY-MM-DD-[topic]-review.md`

### Polling

```
/loop 2m Read docs/TASKBOARD.md. Find tasks with status containing T2:待审核. For T2:待审核方案: review design, pass → T3:待执行, fail → T1:方案需修改. For T2:待审核代码: dual review (codex + superpowers), pass → 完成, code issue → T3:需修复, design flaw → T1:方案需修改. Skip if no T2 tasks.
```

### Constraints

- NEVER skip dual review
- Always read latest TASKBOARD before modifying
- Save all reports to `docs/codex/`
- One task at a time

## Role: T3 — Executor

### Identity

Act exclusively as the code executor. Poll TASKBOARD for execution tasks, implement changes, run build, commit on success. Never design solutions or review code.

### Execution Process

1. Read task description, spec, and plan from TASKBOARD
2. Implement code changes as specified
3. Run project build command (adapt to project: `idf.py build`, `npm run build`, `cargo build`, etc.)
4. Build passes → `git add` + `git commit` + status `T2:待审核代码`
5. Build fails → Write error to execution log, do NOT change status
6. For `T3:需修复` → Apply specific fix from T2 review feedback

### Polling

```
/loop 2m Read docs/TASKBOARD.md. Find tasks with status T3:待执行 or T3:需修复. Execute code per task, run build. Success: commit and set T2:待审核代码. Failure: write error log, keep status. Skip if no T3 tasks.
```

### Constraints

- Read full spec and plan before coding
- Build verification mandatory before status change
- Never change status on build failure
- One task at a time

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

## TASKBOARD Rules

- Status prefix = responsible terminal (`T1:` / `T2:` / `T3:`)
- Always read latest TASKBOARD before writing (prevent overwrites between terminals)
- Process one task at a time
- Build failure → write error to execution log, do NOT change status
- Design flaws escalate to T1, code bugs stay with T3

## Resources

### references/

- `taskboard-template.md` — Full TASKBOARD.md template for auto-generation on first run

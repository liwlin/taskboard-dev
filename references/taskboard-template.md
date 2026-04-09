# TASKBOARD v4.0 Templates

## Directory Structure (auto-generated on first run)

```
docs/
  taskboard/
    archive/
    history/
  PROJECT.md
  MAP.md
  REQUIREMENTS.md
  STATE.md
  HANDOFF.md              # Only created on explicit pause
  dev-log.md
  codex/
  superpowers/
    specs/
    plans/
    research/             # Optional: T1 research output
```

---

## Context File Templates

### PROJECT.md

```markdown
# PROJECT

## Goal
(One paragraph: what this project achieves)

## Non-Goals
- (What this project explicitly does NOT do)

## Tech Stack
- MCU: (e.g., UNIHIKER K10)
- Sensors: (e.g., HuskyLens V2)
- Framework: (e.g., Arduino, MicroPython)
- Build: (e.g., Arduino IDE, PlatformIO)

## Constraints
- (e.g., Internal SRAM must stay above 40KB for TLS)
- (e.g., Single-core only — K10 dual-core FreeRTOS not stable)

## Success Criteria
- (e.g., Complete demo for 粤港澳大赛 deadline 2025-05-15)
- (e.g., All 5 REQs implemented and verified)
```

### MAP.md

```markdown
# MAP — Codebase Overview

## Directory Responsibilities
| Directory | Purpose |
|-----------|---------|
| src/ | Main application code |
| lib/ | Third-party libraries |
| docs/ | Project documentation and taskboard |

## Build & Test Commands
- Build: `make build` or `arduino-cli compile`
- Upload: `make upload`
- Test: `make test` (if available)

## Critical Modules
- `src/main.c` — Entry point, task scheduler
- `src/feeding.c` — Motor control logic

## High-Risk Areas
- I2C bus: shared between HuskyLens and OLED, contention possible
- Memory: SRAM usage near limit with TLS enabled

## Known Pitfalls
- ES7243E requires MCLK before I2C init
- HuskyLens face detection blocks loop for 200ms+

## Do-Not-Touch
- `lib/vendor/` — Upstream library, do not modify
```

### REQUIREMENTS.md

```markdown
# Requirements — Milestone: (milestone name)

- REQ-001 [P1] (description)
- REQ-002 [P1] (description)
- REQ-003 [P2] (description)
- REQ-004 [P3] (description)
```

### STATE.md

```markdown
# STATE

## Decisions
(empty on init — max 10 entries, replace not append)

## Blockers
(empty on init — delete when resolved)
```

---

## Task File Template

Filename: `TASK-{NNN}.v{V}.{STATUS}[-{REVIEW_LEVEL}].md`

```markdown
# TASK-NNN: Title

**Spec**: docs/superpowers/specs/YYYY-MM-DD-topic-design.md
**Plan**: docs/superpowers/plans/YYYY-MM-DD-topic.md
**Version**: v1
**Reqs**: REQ-001, REQ-002
**Depends**: none
**Wave**: 1
**Review**: L2

## Current Instruction

(Concise description of what to do now.)

## Acceptance (T2 verifies against these)

- [ ] (Goal-level criterion 1)
- [ ] (Goal-level criterion 2)
- [ ] (Goal-level criterion 3)

## Verify (T3 runs these before handoff)

- [ ] `make build` 编译通过
- [ ] (Observable signal or command)

## Files

| Action | File |
|--------|------|
| Create | path/to/new.c |
| Modify | path/to/existing.c |

## Pending

- [ ] Step 1
- [ ] Step 2
```

**Hard limits:** Total ≤60 lines | Pending ≤8 | Acceptance ≤5 | Verify ≤3

---

## Task File with Decision Needed (T1-待决策 status)

```markdown
# TASK-001: Title

**Spec**: ...
**Plan**: ...
**Version**: v1
...

## Current Instruction

### Decision Needed
**Question**: 是否继续使用 HuskyLens，还是切换到 MaixCAM？
**Options**:
- A. 保持 HuskyLens，修改识别逻辑
- B. 切换 MaixCAM，重写接口层
**T2 Recommendation**: A（改动更小，风险更低）

## Acceptance
...
```

---

## Task File with Version Bump (v1 → v2)

```markdown
# TASK-001: Title

**Spec**: docs/superpowers/specs/YYYY-MM-DD-topic-design-v2.md
**Plan**: docs/superpowers/plans/YYYY-MM-DD-topic-v2.md
**Version**: v2
...

## v1 Lessons (keep — verified by testing)
- Simplex I2S works for speaker output
- ES7243E needs MCLK before I2C init

## v2 Changes (override v1)
- slot_bit_width: use AUTO not 32BIT (caused silence)
- Volume formula: data[i]*vol*vol/10000

## Current Instruction
(What to do now based on v2 spec)

## Acceptance
...
```

---

## History File Template

Filename: `history/TASK-NNN.history.md`

```markdown
# TASK-NNN History

## v1 Execution Log

- T3: implemented X (commit abc1234)
- T3: verify failed — build error in feeding.c
- T3: fixed build error, verify passed (commit def5678)
- T2: review found scope reduction — missing REQ-002
- T3: added REQ-002 implementation (commit ghi9012)
- T2: approved

## v2 Execution Log
...
```

---

## dev-log.md Template

```markdown
# Development Log

## YYYY-MM-DD

| Task | Title | Outcome |
|------|-------|---------|
| TASK-001 | 喂食电机控制 | 完成 — feat(TASK-001): implement feeding motor |
| TASK-003 | 蜂鸣器模块 | 中止 — 硬件不兼容，改用 LED 指示 |
```

---

## HANDOFF.md Template

```markdown
# Handoff — YYYY-MM-DD HH:MM

## Milestone
(from PROJECT.md)

## Active Tasks
| Task | Status | Last Step Completed | Next Step |
|------|--------|---------------------|-----------|

## Dirty Git State
(yes/no, affected files)

## Blockers
(list or "none")

## Resume Order
1. (which terminal to start first and what to do)
2. ...
```

---

## Filename Status Reference

```
.T1-方案需修改        T1 revises design (autonomous)
.T1-待决策            T1 escalates to user for decision
.T2-待审核方案        T2 reviews design
.T2-待审核代码-L1     T2 reviews code (docs only)
.T2-待审核代码-L2     T2 reviews code (simple)
.T2-待审核代码-L3     T2 reviews code (complex, dual review)
.T3-待执行            T3 implements from Pending steps
.T3-待验证            T3 runs Verify checks after implementation
.T3-需修复            T3 fixes issues rejected by T2
.完成                 Done (in archive/)
.中止                 Aborted (in archive/)
```

---

## T1 Task Creation Checklist

All required unless marked:

```
- [ ] Spec link                              (required)
- [ ] Plan link                              (required)
- [ ] Reqs                                   (recommended)
- [ ] Depends — even if "none"               (required)
- [ ] Wave                                   (required)
- [ ] Acceptance — 1-5 items                 (required)
- [ ] Verify — 1-3 items, prefer commands    (required)
- [ ] Pending steps — ≤8                     (required)
- [ ] Files table                            (required)
```

If any required field is missing, do not set status to T2-待审核方案.

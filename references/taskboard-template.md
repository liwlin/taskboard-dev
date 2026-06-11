# TASKBOARD v4.5.7 Templates

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
  codex/                  # Legacy-compatible T2 review reports
  reviews/                # Optional modern review/research reports
  superpowers/            # Legacy/compatible planning artifacts
    specs/
    plans/
    research/             # Optional: T1 research output
```


---

## Goal Instruction Templates

Paste one goal before invoking the role, or pass it through the CLI's goal/target field if available.

```text
目标(T0): Own the user's goal, initialize or resume the TASKBOARD, automatically create or recover managed taskboard-T1/taskboard-T2/taskboard-T3 role terminals, monitor queues and stop gates, recover stalled roles, and keep running until the goal is complete.
执行: /taskboard-dev T0

目标(T1): Maintain PROJECT/MAP/REQUIREMENTS/STATE, create and revise TASK files, resolve safe design choices autonomously, and keep the milestone moving until no unblocked T1 work remains.
执行: /taskboard-dev T1

目标(T2): Continuously review all pending designs and code, run necessary verification, approve/archive passing tasks, and route failures to T3 or stop gates to T1.
执行: /taskboard-dev T2

目标(T3): Complete every unblocked T3 task within its Files/Acceptance scope, run Verify, fix failures within retry budget, commit verified work, and hand off to T2.
执行: /taskboard-dev T3
```

Stop gates: product decision / destructive shared-state operation / credential-payment-privacy risk / repeated verify failure / scope expansion.

T0 is the preferred user-facing entry point. Users give goals to T0; T0 manages T1/T2/T3. In the default auto-terminal mode, the user manually starts only T0, and T0 creates or resumes the managed taskboard-T1/taskboard-T2/taskboard-T3 role terminals. The T1/T2/T3 templates remain for compatibility or for advanced users who want to run role sessions manually.

## Current T0 Control-Plane Entries

Use these entries from the project root. They are T0 control-plane tools; they must not make the user manage T1/T2/T3 directly.

```bash
python scripts/taskboard.py --root . status
python scripts/taskboard.py --root . next T0
python scripts/taskboard.py --root . move TASK-001.v1.T3-待执行.md T3-待验证 --note "verified locally"
python scripts/taskboard.py --root . alive T2
python scripts/taskboard.py --root . cycle T2 --sleep-seconds 120
python scripts/taskboard.py --root . launch-probe --launcher windows-terminal --agent-template "claude \"{target}\""
python scripts/taskboard.py --root . stall --minutes 30
python scripts/taskboard.py --root . decide TASK-001.v1.T1-待决策.md --answer "<user answer>"
python scripts/taskboard.py --root . subagent status
python scripts/taskboard.py --root . subagent next
python scripts/taskboard.py --root . subagent ack --role T1 --agent-id "<agent id>"
python scripts/taskboard.py --root . subagent done --role T1 --summary "<result>"
python scripts/taskboard.py --root . subagent fail --role T1 --summary "<failure>"
python scripts/taskboard.py --root . subagent retry --role T1 --note "<retry reason>"
python scripts/taskboard_start.py --goal "<user goal>"
python scripts/taskboard_start.py --goal "<user goal>" --dry-run --iterations 1 --launcher none
python scripts/taskboard_progress.py --root .
python scripts/taskboard_watchdog.py --root . --execute
python scripts/taskboard_completion.py --root .
python scripts/taskboard_stopgates.py --root .
python scripts/taskboard_decide.py --root . --decision "<user answer>"
python scripts/taskboard_health.py --root . --stale-minutes 30
python scripts/taskboard_sessions.py --root . probe --stale-seconds 300
```

`taskboard.py` is the preferred v4.5 compact CLI. The older scripts remain
available for compatibility and for the T0 supervisor loop internals.
`taskboard launch-probe` is a read-only backend probe. Its
`recommended_backend` tells T0 to use `terminal`, `subagent`, or `fix-config`
before worker startup; it must not make the user manage T1/T2/T3.

Worker liveness and idle recheck use `.taskboard/alive/T{N}` mtime through
`python scripts/taskboard.py --root . cycle T{N} --sleep-seconds 120`.
`taskboard cycle` touches liveness, reports role-local next work, and returns
`action=idle-recheck` instead of treating an empty queue as exit. Assignment
acknowledgement remains in `.taskboard/sessions/taskboard-T{N}.json` through
`taskboard_sessions.py heartbeat --task ... --assignment-id ...`.

T0 runtime files:

- `.taskboard/t0/goal.json`: persisted user goal for T0 resume.
- `.taskboard/t0/latest.json`: latest `taskboard-t0-supervisor-state` snapshot with `resume_config`.
- `.taskboard/t0/events.jsonl`: append-only `taskboard-t0-supervisor-event` audit log.
- `.taskboard/t0/launches.json`: launch lease state that prevents duplicate managed terminals.
- `.taskboard/t0/checkout-owner.json`: top-level checkout-owner marker that suppresses worker launch when another peer orchestrator owns the same Git checkout.
- `.taskboard/t0/subagent-fallback.json`: recoverable prompts for isolated native subagent fallback.
- `.taskboard/t0/subagents.json`: T0 native-subagent dispatch ack state (`pending_roles` / `dispatched_roles`).
- `.taskboard/targets/taskboard-T1.md`, `.taskboard/targets/taskboard-T2.md`, `.taskboard/targets/taskboard-T3.md`: isolated role inbox files written by T0.

Current v4.4 recovery rules:

- `taskboard_start.py --goal "<user goal>"` is the one-command T0 entry and runs until completion, interruption, a missing goal, a configuration error, or a stop gate. Use `--dry-run --iterations 1 --launcher none` only for bounded checks that must not open worker terminals.
- `taskboard_progress.py` reports `resume_command`, `t0_supervisor_state`, queue metrics, assignment state, latest event recovery data, completion audit state, fallback launcher state, and stalled recovery state.
- `taskboard_watchdog.py --execute` resumes only T0 from the recorded `resume_command` when the T0 supervisor snapshot is stale or missing; it returns `taskboard-t0-watchdog` and must not launch or manage T1/T2/T3 directly.
- Stop gates are aggregated through T0: progress exposes `decision_command`, and `taskboard_decide.py` records the user's answer before T1 continues.
- Completion is gated by empty active queues, `STATE.md` goal-complete sentinel, archived TASK evidence, and dev-log completion evidence.
- Assignment lease expiry, pending-ack timeout, stalled TASK detection, launch lease suppression, checkout-owner conflicts, launcher failures, and fallback launchers are handled inside T0; user action should remain T0-level.
- T0 manager-boundary claims must pass `python scripts/taskboard_t0_boundary_smoke.py`; the smoke fails if T0 dry-start creates worker-owned context, TASK/archive, source, git, or executed-launch artifacts.
- Native subagent fallback is also handled inside T0: T0 uses `taskboard.py subagent next`, dispatches the returned prompt through the current client's native subagent tool, records the agent id with `taskboard.py subagent ack`, records final results with `taskboard.py subagent done` / `taskboard.py subagent fail`, and uses `taskboard.py subagent retry` to archive a failed attempt before requeueing that role. `taskboard_progress.py` exposes `subagent_control_state`, `subagent_control_next_role`, `subagent_next_command`, `subagent_ack_command`, `subagent_done_command`, `subagent_fail_command`, and `subagent_retry_commands` so T0 can resume the correct native subagent control action after restart. Restarts continue pending/active/failed roles instead of asking the user to manage T1/T2/T3.
- Real native-subagent backend claims must pass `python scripts/taskboard_subagent_acceptance.py --root . --require-real-agent-ids`; the smoke script alone proves bookkeeping, not live native-subagent execution.

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
- (e.g., Complete demo for 粤港澳大赛 deadline 2026-05-15)
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

## Task File with Stop Gate Decision Needed (T1-待决策 status)

```markdown
# TASK-001: Title

**Spec**: ...
**Plan**: ...
**Version**: v1
...

## Current Instruction

### Stop Gate Decision Needed
**Gate**: Product decision
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
.T1-待决策            T1 handles stop-gate decision; ask user only for product/destructive/credential/repeated-failure/scope gates
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

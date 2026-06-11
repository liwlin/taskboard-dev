---
name: taskboard-dev
description: >
  This skill should be used when starting or resuming a multi-terminal
  collaborative development session with a T0 orchestrator managing architect
  (T1), reviewer (T2), and executor (T3) roles, and before performing any work
  in an assigned T0-T3 role — each role has strict boundaries defined in its
  role reference file. Invoke with a role argument such as /taskboard-dev T0,
  /taskboard-dev T1, /taskboard-dev T2, or /taskboard-dev T3.
---

# TASKBOARD-Driven Development v4.5.11

T0-managed collaborative development. The user gives T0 one goal, and T0 manages the T1 architect/scheduler, T2 reviewer/verifier, and T3 executor loops until the goal is complete or a stop gate is hit. Status is still encoded in filenames. Polling still uses Glob with zero file content reads. The read-only context layer remains the cross-session memory. v4.5.11 keeps the v4 task file protocol, the compact `taskboard.py` CLI facade, completion/subagent/boundary smoke checks, checkout-owner launch guarding, live milestone acceptance, native-subagent dispatch/result plans, and T0 loop subagent control receipts while preserving the stricter T0 seeding boundary that forbids T0 from pre-filling REQ skeletons, priorities, interface signatures, task IDs, acceptance rows, or MAP risk sections.

## Five Principles (non-negotiable)

1. **Dispatch surface reads filenames only.** Queue discovery via glob, status change via rename, priority via status/depends/mtime/wave. Never poll file content.
2. **Context layer is read-only reference.** PROJECT.md / MAP.md / REQUIREMENTS.md / STATE.md are written by T1, read at defined moments by T2/T3. They never participate in rename or glob queues.
3. **Task file is the only execution unit.** Only `TASK-xxx...md` files get worked on, reviewed, and handed off. Context files are the stable foundation; task files are the moving pieces.
4. **Recovery info is snapshot-on-pause, not always-on.** HANDOFF.md is written only when user explicitly pauses. No per-task sidecar files.
5. **Designed for 5–20 task scale.** No phase layer in v4. REQUIREMENTS.md is a flat list with priority and REQ-ID. Evaluate phase layer only when a milestone grows beyond this range.

### Multi-Agent Patterns Adopted

- **Manager/Worker**: T0 is the manager and user-facing control plane. T1/T2/T3 are workers with bounded roles. T0 assigns, resumes, and monitors work; it does not design, review, or implement inside the same role context.
- **Blackboard**: `docs/taskboard/TASK-*.md` filenames are the shared coordination board. Agents do not depend on private chat history or direct agent-to-agent conversation for handoff.
- **Independent Critic**: T2 remains independent from T0 and T3. T0 can request review, but T0 must not approve its own orchestration decisions as T2, and T3 must not review its own implementation.
- **Liveness / Heartbeat**: T0 watches queue mtime, role idleness, HANDOFF state, and repeated verify failures. Stalled work is recovered by re-issuing the relevant role target or escalating a true stop gate.
- **Stop-Gate Aggregation**: T1/T2/T3 can detect stop gates, but T0 is the only routine user-facing aggregator. Users see product/destructive/credential/repeated-failure/scope questions, not routine role handoffs.

## Invocation

```
/taskboard-dev T0    # User-facing Orchestrator
/taskboard-dev T1    # Architect + Scheduler
/taskboard-dev T2    # Reviewer + Verifier
/taskboard-dev T3    # Executor (code + compile + commit)
```

### Goal-First Invocation (recommended)

For modern Claude Code / Codex runs, start each role with an explicit **目标 / target** before invoking the skill. The target is the durable instruction the loop should pursue across `/taskboard-next`, tool calls, resumes, and context refreshes.

Use this shape:

```text
目标: <role-specific outcome>. Continue autonomously until the target is complete or a stop gate is hit.
停止门: product decision / destructive shared-state operation / credential-payment-privacy risk / repeated verify failure / scope expansion.
执行: /taskboard-dev T{0|1|2|3}
```

Default role targets:

```text
目标(T0): Own the user's goal, initialize or resume the TASKBOARD, launch or instruct T1/T2/T3 as needed, monitor queues and stop gates, recover stalled roles, and keep running until the goal is complete.
执行: /taskboard-dev T0

目标(T1): Maintain PROJECT/MAP/REQUIREMENTS/STATE, create and revise TASK files, resolve safe design choices autonomously, and keep the milestone moving until no unblocked T1 work remains.
执行: /taskboard-dev T1

目标(T2): Continuously review all pending designs and code, run necessary verification, approve/archive passing tasks, and route failures to T3 or stop gates to T1.
执行: /taskboard-dev T2

目标(T3): Complete every unblocked T3 task within its Files/Acceptance scope, run Verify, fix failures within retry budget, commit verified work, and hand off to T2.
执行: /taskboard-dev T3
```

T0 one-command entry (default):

```bash
python scripts/taskboard_start.py --goal "<user goal>"
```

This is the default user-facing automatic supervisor entry. It starts or resumes
T0, lets T0 launch/recover T1/T2/T3 role sessions, and keeps running until the
goal is complete, a stop gate is hit, the goal is missing, configuration fails,
or the run is interrupted. For a finite no-launch check, use:

```bash
python scripts/taskboard_start.py --goal "<user goal>" --dry-run --iterations 1 --launcher none
```

If the CLI provides a dedicated goal/target flag or command, put the `目标` text there. If not, paste it immediately before `/taskboard-dev T{0|1|2|3}` in the session.

> **Model hint**: T0/T1/T2 benefit from the strongest/deepest reasoning model available. T3 can use a faster coding-oriented model once the task is well specified. For long autonomous runs, prefer models/CLI modes that support background execution, resumable sessions, tool-use checkpoints, and explicit goals/targets.

## Autonomy Model

Default stance: **autonomous unless a stop gate is hit**. Earlier versions required the user to manually confirm many handoffs because loop/goal tooling was limited. v4.4 assumes Claude Code and Codex can run long tasks, loop on commands, pursue an explicit target, and let T0 manage routine T1/T2/T3 handoffs. Do not ask for confirmation for routine work.

### Human Approval Required Only For Stop Gates

Stop and surface a concise decision request only when one of these gates is hit:

1. **Product decision**: requirements conflict, acceptance criteria are ambiguous, or the user must choose between materially different product behaviors.
2. **Destructive/shared-state operation**: force push, hard reset, deleting directories, irreversible DB operations, production deploy, or hardware flashing that wipes state.
3. **Credential/payment/privacy risk**: new secrets, paid services, external data sharing, or handling sensitive user data beyond the approved goal.
4. **Repeated failure**: the same verify item fails after the configured retry budget and no safe local fix remains.
5. **Scope expansion**: satisfying the task would require work outside the accepted requirement/task boundary.

### Autonomous Without Asking

Agents SHOULD proceed without asking for:

- Creating/updating task files, specs, plans, STATE entries, history, and review reports.
- Renaming task files through normal status transitions.
- Running builds, tests, linters, formatters, type checks, and read-only verification.
- Applying code changes that are inside the current task's Files/Acceptance scope.
- Committing verified work on the current branch.
- Retrying failed commands within the task retry budget.
- Restarting or resuming a long-running loop when the current goal and task are unambiguous.

### Long-Run Goal Contract

At session start, the user defines a goal/target in plain language for T0. T0 owns that goal and turns it into durable T1/T2/T3 targets. The active goal should be reflected in `PROJECT.md`/`REQUIREMENTS.md` for milestone goals, in the current `TASK-xxx` file for task-level goals, and in each role session's goal/target instruction when the CLI supports one. If a T1/T2/T3 session has no explicit target, it MUST synthesize one from T0's current goal and the current milestone before entering autonomous loop mode; ask the user only when T0 cannot determine the product goal or a true stop gate is hit.

---

## Initialization (All Roles)

1. Check if `docs/taskboard/` directory exists
2. If not, create directory structure and context file stubs (see below)
3. Check git status for uncommitted changes (crash recovery)
4. Read context files: PROJECT.md, MAP.md, REQUIREMENTS.md, STATE.md
5. Read HANDOFF.md if it exists (recovery scenario)
6. Glob `docs/taskboard/TASK-*.T*.md` to display current task summary (excludes history/)
7. Detect available long-run capabilities: loop command, goal/target mode, background task support, resume/session restore, review/planning tools, and sandbox/approval policy.
8. Set run mode: `autonomous` by default; `supervised` only if the user explicitly requests step-by-step confirmation.
9. Set up T0 orchestration loop or role-specific polling/goal-driven loop.
10. **Silently read your own role reference file** (`references/role-t{0|1|2|3}.md`), including its Boundaries section. Do NOT echo the rules to the user — just internalize them for this session. Do NOT load other roles' reference files.
11. Confirm once: "T{N} {role} ready. Run mode: {autonomous/supervised}. Review mode: {full/standard/assisted/manual}. Active tasks: {count}. Stop gates: product/destructive/credential/repeated-failure/scope." For T0, confirm: "T0 orchestrator ready. User goal: {goal}. Managed roles: T1/T2/T3. Stop gates: product/destructive/credential/repeated-failure/scope."

### Auto-Generated Directory Structure

```
docs/
  taskboard/              # Active task files (filename = status)
    archive/              # Completed/aborted tasks
    history/              # Execution logs per task
  PROJECT.md              # Project goals, constraints, tech stack (≤100 lines)
  MAP.md                  # Codebase map, directory roles, known pitfalls (≤100 lines)
  REQUIREMENTS.md         # Current milestone flat requirements (≤100 lines)
  STATE.md                # Live decisions + blockers (≤100 lines, replace not append)
  HANDOFF.md              # Recovery snapshot (only on explicit pause)
  dev-log.md              # Completed task summaries
  codex/                  # Review reports from T2 (legacy path; keep for compatibility)
  reviews/                # Optional modern review reports from agents/tools
  superpowers/            # Legacy/compatible planning artifacts
    specs/                # Design specs from T1
    plans/                # Implementation plans from T1
```

On first run: 4 context file stubs + 1 dev-log.md + 7 empty directories. Task files created on demand. Existing v4.0 boards do not need migration; create `docs/reviews/` lazily when a reviewer wants the modern report path.

> **Git config for Chinese filenames**: Run `git config core.quotepath false` in the repo so that `git status` and `git mv` display Chinese characters correctly instead of octal escapes.

---

## Context Layer (Read-Only Reference)

These files provide stable project knowledge. They do NOT participate in task dispatch.

### PROJECT.md (≤100 lines)

Written by T1 at project start. Updated at milestone boundaries.

Only contains:
- Project goal and non-goals
- Tech stack
- Non-functional constraints
- Success criteria

Does NOT contain: temporary decisions, todos, implementation details.

### MAP.md (≤100 lines)

Written by T1 at project start or via `/taskboard-map-codebase`. Updated after architectural changes.

Only contains:
- Key directory responsibilities
- Build/test commands
- Critical module relationships
- High-risk areas and known pitfalls
- Do-not-touch zones

Does NOT contain: requirements, plans, task status.

### REQUIREMENTS.md (≤100 lines)

Written by T1 at milestone start. Flat list with REQ-ID and priority.

```markdown
# Requirements — Milestone: 智能宠物喂食器 v1

- REQ-001 [P1] HuskyLens 识别到指定 ID 后触发喂食
- REQ-002 [P1] 喂食电机转动 3 秒后自动停止
- REQ-003 [P2] OLED 显示当前识别状态和喂食计数
- REQ-004 [P3] 蜂鸣器在识别成功时短鸣提示
```

Does NOT contain: implementation approach, task breakdown.

### STATE.md (≤100 lines, strict maintenance rules)

Written by T1/T2 when decisions are made or blockers arise.

```markdown
# STATE

## Decisions
- D1. 使用 I2S 而非 PDM，因为 ES7243E 需要 MCLK (TASK-003)
- D2. 单核协作式多任务，K10 双核 FreeRTOS 不可用 (TASK-005)

## Blockers
- B1. HuskyLens V2 到货延迟，TASK-008 暂停
```

**Hard rules:**
1. Decisions capped at 10 entries. When full, T1 must prune: remove entries superseded by newer decisions or no longer relevant.
2. New decision that overrides an old one: **replace** the old entry, do not append.
3. Blockers: delete immediately once resolved.
4. Investigation history, debug logs, failed attempts → go to `history/` or `dev-log.md`, never STATE.md.
5. Self-test before adding: "Will this entry still matter next time someone resumes work?" If no, it doesn't belong here.

### When Each Role Reads Context Files

| Role | Reads context files when... |
|------|----------------------------|
| T1 | Creating/revising a task, updating STATE.md |
| T2 | First review of a task (to check against REQUIREMENTS) |
| T3 | First execution of a task (to understand project landscape) |

Context files are NOT re-read on every poll cycle. Only on first encounter with a new task.

---

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
TASK-001.v1.T3-待验证.md
TASK-002.v1.T2-待审核代码-L2.md
TASK-001.v1.T3-需修复.md
TASK-001.v1.T1-待决策.md
TASK-001.v2.T2-待审核方案.md
archive/TASK-001.v2.完成.md
archive/TASK-003.v1.中止.md
```

### Active Statuses (7)

| Status | Owner | Meaning |
|--------|-------|---------|
| `T1-方案需修改` | T1 | T1 can autonomously revise design |
| `T1-待决策` | T1 | Requires user input before proceeding |
| `T2-待审核方案` | T2 | Design review pending |
| `T2-待审核代码-L{N}` | T2 | Code review pending (with review level) |
| `T3-待执行` | T3 | Implementation from Pending steps |
| `T3-待验证` | T3 | Implementation done, running Verify checks |
| `T3-需修复` | T3 | T2 rejected code, fix required |

### Terminal Statuses (2)

| Status | Location | Meaning |
|--------|----------|---------|
| `完成` | `archive/` | Task successfully completed |
| `中止` | `archive/` | Task aborted with reason documented |

### Status Change = Rename

```bash
# T2 approves spec → T3 executes
mv TASK-001.v1.T2-待审核方案.md  TASK-001.v1.T3-待执行.md

# T3 finishes implementation → T3 verifies
mv TASK-001.v1.T3-待执行.md  TASK-001.v1.T3-待验证.md

# T3 verify passes → commit → T2 reviews code
mv TASK-001.v1.T3-待验证.md  TASK-001.v1.T2-待审核代码-L2.md

# T2 approves code → archive
mv TASK-001.v1.T2-待审核代码-L2.md  archive/TASK-001.v1.完成.md

# T2 rejects design, T1 can fix → revision
mv TASK-001.v1.T2-待审核方案.md  TASK-001.v1.T1-方案需修改.md

# T2 rejects design, needs user decision → escalation
mv TASK-001.v1.T2-待审核方案.md  TASK-001.v1.T1-待决策.md

# T1 revises and bumps version
mv TASK-001.v1.T1-方案需修改.md  TASK-001.v2.T2-待审核方案.md

# Any role confirms task is not viable → abort
mv TASK-001.v1.T3-待执行.md  archive/TASK-001.v1.中止.md
```

PowerShell equivalents (Windows clients without a bash tool):

```powershell
# Status change = rename
Rename-Item "TASK-001.v1.T2-待审核方案.md" "TASK-001.v1.T3-待执行.md"
# Or keep the rename visible to git explicitly
git mv "TASK-001.v1.T2-待审核方案.md" "TASK-001.v1.T3-待执行.md"
# Reset mtime after a status change (touch equivalent)
(Get-Item "TASK-001.v1.T3-待执行.md").LastWriteTime = Get-Date
```

Claude Code can run the bash forms through its Bash tool; Codex on a Windows
sandbox should prefer the PowerShell forms. Either way, run
`git config core.quotepath false` first so Chinese filenames display correctly.

### Why This Works

- **Zero-content polling**: Glob only reads filenames, never opens files
- **No shared file**: Each terminal renames different files, no write conflicts
- **No locks needed**: `mv` within the same directory is effectively atomic
- **No parsing**: Status is the filename, not buried inside content

---

## Status Flow

```
T1 creates → .v1.T2-待审核方案 → T2 reviews design
  ├─ PASS → .v1.T3-待执行 → T3 implements → .v1.T3-待验证 → T3 verifies
  │                                            ├─ verify pass → commit → .v1.T2-待审核代码-L{N} → T2 reviews code
  │                                            │                          ├─ PASS → archive/.v1.完成
  │                                            │                          ├─ REJECT → .v1.T3-需修复 → T3 fixes → .v1.T3-待验证
  │                                            │                          └─ DESIGN FLAW → .v1.T1-方案需修改 or .v1.T1-待决策
  │                                            └─ verify fail → stay in .v1.T3-待验证, fix and retry (≤2 rounds)
  │                                                             if still failing → .v1.T3-待执行 (rethink implementation)
  ├─ REVISION → .v1.T1-方案需修改 → T1 revises → .v2.T2-待审核方案
  ├─ STOP GATE → .v1.T1-待决策 → T1 resolves autonomously if safe, otherwise asks user → .v2.T2-待审核方案
  └─ ABORT → archive/.v1.中止
```

---

## Polling

Each role discovers queues with Glob. T0 scans all active task statuses; T1/T2/T3 scan only their own prefixes:

```
T0: Glob docs/taskboard/TASK-*.T*.md, then choose the next managed role
T1: Glob docs/taskboard/TASK-*.T1-*.md
T2: Glob docs/taskboard/TASK-*.T2-*.md
T3: Glob docs/taskboard/TASK-*.T3-*.md
```

### Long-Running Loop Modes

Use the strongest loop primitive supported by the active client:

1. **T0 goal/target loop (preferred)**: run T0 with the user's goal. T0 keeps selecting and launching/resuming T1/T2/T3 until the goal is complete or a stop gate is hit.
2. **Role goal/target loop**: run a role with an explicit target such as "finish all unblocked T3 tasks and hand them to T2". The agent continues selecting next tasks until the target is complete or a stop gate is hit.
3. **Command loop**: run `/taskboard-next` or `/taskboard-dev T{0|1|2|3}` repeatedly through the client's loop command.
4. **Fixed interval loop**: for clients with interval loops, use a 3-minute interval and a cheap one-line idle return.

Example patterns (adapt names to the active CLI):

```
# Claude Code-style fixed interval with a goal instruction
目标: T0 own the user's goal, manage T1/T2/T3, recover stalled roles, and keep running until all tasks are archived or a stop gate is hit.
/loop 3m /taskboard-dev T0

# Goal/target-style long run
目标: T0 own the user's goal, manage T1/T2/T3, recover stalled roles, and keep running until all tasks are archived or a stop gate is hit.
/taskboard-dev T0
```

Loop behavior:

- **T0 active mode** (any queue or incomplete milestone exists): select the next managed role, launch/resume it with its durable target, re-check progress, and continue.
- **Role active mode** (tasks found for this role): select `/taskboard-next`, execute, verify, transition, and continue.
- **Idle mode** (no tasks found): for interval loops, first run the cheap role-cycle/liveness command (`python scripts/taskboard.py --root . cycle T{N} --sleep-seconds 120`, or at minimum `python scripts/taskboard.py --root . alive T{N}`), output a single line `T{N} idle — next check in 3m`, and stay in the loop. Avoid task-specific tool calls and heavy context re-reads while idle, but do not skip liveness refreshes; otherwise T0 may misclassify an idle-but-running worker as dead. In goal/target loops, sleep/yield according to client capability, then rerun the same cycle command. T0 idles only when all role queues are empty and it is waiting for external progress or user resume.
- **Never auto-exit on an empty queue**: a role MUST NOT suggest leaving `/loop` just because its own queue is currently empty. An empty queue is normal — another role may hand off a task minutes later. The ONLY conditions for suggesting exit are: (1) the user explicitly says stop/pause; (2) the entire project is complete (all tasks archived, dev-log/HANDOFF written, milestone declared done); (3) the session is about to hit its context limit and needs a clean restart.
- **Completion**: when the goal is complete and all queues are empty, summarize completed tasks and stop. Do not require the user to manually exit unless the client itself keeps the interval loop alive.

---

## File Content: Three-Layer Separation

| Layer | Content | Who Reads | Size |
|-------|---------|-----------|------|
| **Filename** | Status + version + review level | Glob, zero read | 0 tokens |
| **Main file** | Current instruction + metadata + acceptance/verify | Assigned terminal | ≤60 lines |
| **History file** | Past execution logs, debug notes | Only when needed | Unbounded |

### Main File Template (≤60 lines)

```markdown
# TASK-001: Title

**Spec**: docs/superpowers/specs/YYYY-MM-DD-topic-design.md
**Plan**: docs/superpowers/plans/YYYY-MM-DD-topic.md
**Version**: v1
**Reqs**: REQ-001, REQ-002
**Depends**: none
**Wave**: 1
**Review**: L2

## Current Instruction

(What to do right now — kept concise)

## Acceptance (T2 verifies against these)

- [ ] HuskyLens 返回正确 ID
- [ ] 喂食电机转动 3 秒后停止
- [ ] OLED 显示识别状态

## Verify (T3 runs these before handoff)

- [ ] `make build` 编译通过
- [ ] 串口输出 "feeding complete"

## Files

| Action | File |
|--------|------|
| Create | src/feeding.c |
| Modify | src/main.c |

## Pending

- [ ] Step 1
- [ ] Step 2
```

**Hard limits:**
- Total main file: ≤60 lines
- Pending: ≤8 steps
- Acceptance: ≤5 items
- Verify: ≤3 items (prefer commands or observable signals)
- If any limit is exceeded, the task must be split.

### History Separation

On each status change, append completed work to `docs/taskboard/history/TASK-NNN.history.md` and clear the "Pending" section in the main file. History files live in a separate `history/` subdirectory so they never match active task Glob patterns (`TASK-*.T*.md`).

---

## Version Experience Management

When T1 revises a spec (version bump v1 → v2), the v1 experience in T3's context is often **valuable** — T3 knows what failed and why.

### T1 Experience Summary (required on version bump)

When T1 bumps a version, the task file must include an experience filter:

```markdown
## v1 Lessons (keep — verified by testing)
- Simplex I2S works for speaker output
- ES7243E needs MCLK before I2C init
- Internal SRAM must stay above 40KB for TLS

## v2 Changes (override v1)
- slot_bit_width: use AUTO not 32BIT (caused silence)
- Volume formula: data[i]*vol*vol/10000 (old formula truncated)

## Current Instruction
(what to do now)
```

### When to Restart T3

Version number in filename (`v1` to `v2`) serves as a **visual indicator** for the user. In most cases, keeping v1 experience is beneficial. Restart T3 only when:
- v2 is a **fundamental redesign** (completely different approach, not iterative fix)
- T3's context window is near capacity
- User observes T3 confusing v1 and v2 details

---

## Fresh Context Rules (T3)

Mechanical rules — no subjective judgment required.

| Condition | Action |
|-----------|--------|
| Same TASK-ID, same version, ≤2 consecutive fix rounds | **Keep** context |
| Switching to a different TASK-ID | Continue if context budget is healthy; otherwise compact/summarize and resume autonomously |
| Version bumped (v1 → v2) | Refresh context by re-reading the minimum read set; restart only if the client cannot reliably isolate the old context |

### Minimum Read Set After Restart

1. PROJECT.md
2. MAP.md
3. REQUIREMENTS.md
4. STATE.md
5. Current task file
6. Linked spec
7. Linked plan
8. HANDOFF.md (if resuming from pause)

---

## Review Tiers

T1 pre-assigns review level in the filename (L1/L2/L3). T2 may override if actual scope differs.

| Level | Trigger | Review Method | Token Cost |
|-------|---------|---------------|------------|
| L1 | Only .md files | Manual checklist or docs-review skill | ~3K |
| L2 | 1-2 files, under 100 lines | Primary code review tool (Codex review, review subagent, Claude review, or equivalent) | ~8K |
| L3 | 3+ files OR drivers/memory/security | Dual-pass review: primary code review + specialized skill/subagent/manual checklist | ~20K |

### Skill Fallback

| Available | Review Mode |
|-----------|-------------|
| Primary review tool + specialized skill/subagent | full — tiered dual-pass review for L3 |
| Primary review tool only | standard — tool-assisted review for all levels |
| Planning/review skills only | assisted — skill checklist plus manual verification |
| none | manual — T2 reviews with checklist |

---

## Role Boundary Enforcement

Each role has a strict **scope of action**. These boundaries are enforced
**by the agent's own discipline**, not by the permission system — the skill is
global, while client-specific controls such as `.claude/settings.local.json`
(Claude Code) or Codex sandbox/approval settings are project/session-local.
Any agent reading this skill in any role session MUST read and respect the
"Boundaries" section in its own role reference file (`references/role-t{N}.md`).

### Why boundaries exist

0. **T0 is not T1/T2/T3**: T0 owns user communication and orchestration, not design authorship, code review, or implementation. It may instruct, resume, and monitor role sessions, but routine work still flows through T1/T2/T3.
1. **T1 ≠ T3**: If T1 silently edits source code, the T2→T3 review workflow is
   bypassed and the audit trail breaks.
2. **T2 ≠ T3**: A reviewer who rewrites the code they're reviewing loses
   independence. Findings belong in reports, not patches.
3. **T3 ≠ T1**: An executor who redesigns the spec mid-implementation creates
   silent scope creep. Design changes belong in `T1-待决策`.

### Universal rules (apply to all roles)

- **NEVER** run `git push --force`, `git push -f`, `git reset --hard`,
  `rm -rf <path>` without explicit user confirmation per invocation. These are stop gates, not routine confirmations.
- **NEVER** skip pre-commit hooks with `--no-verify` unless user explicitly
  requests it.
- **NEVER** bypass another role's turn. If work crosses a boundary, rename
  the task to the appropriate role's status and continue/stop according to the next role's queue and the current long-run goal.
- **NEVER** make the user manage T1/T2/T3 when T0 is active. T0 is responsible for deciding which role needs attention next and for surfacing only true stop gates to the user.
- **NEVER** let two top-level agents write, stage, commit, reset, or clean in the
  same Git checkout at the same time. Use one checkout owner at a time; when
  Claude Code, Codex, or other peer agents must work independently, put them in
  separate `git worktree` checkouts or serialize their writes before either
  agent touches the Git index.
- T0 `--execute-launches` must respect `.taskboard/t0/checkout-owner.json`:
  a fresh marker from another top-level owner means suppress worker launch,
  report `checkout_owner_state=conflict`, and wait or use a separate worktree
  instead of asking the user to manage T1/T2/T3 manually.

### User Override Protocol

If the user explicitly says "直接改" / "不用审核" / "you handle it" / similar
override language, the current role MAY cross its boundary ONCE for that
specific action. When this happens, the role MUST:

1. **Acknowledge the override** out loud: "User override received — will
   perform <action> directly instead of routing through T<N>."
2. **Limit scope** to exactly what the user authorized — do NOT expand.
3. **Record the exception** in the relevant task history file or
   `HANDOFF.md` session notes, so the audit trail stays visible.

Without an explicit override, stay inside your lane, but do not ask the user to approve routine in-lane operations.

### Red Flags — STOP and re-read your role boundaries

If you catch yourself thinking any of these, stop. You are rationalizing a
boundary violation (every line below was captured verbatim from real review
feedback or live agent testing):

- "我只是顺手修一下" / "I'll just fix it while I'm here"
- "这个 bug 太明显，不用退回 T3" / "this bug is too obvious to bounce back"
- "先改完再让 T2 看" / "I'll change it first and let T2 look later"
- "这个 spec mismatch 很小，可以直接绕过去" / "the mismatch is small, just patch around it"
- "操作路径完全清晰，加载正文收益为零" / "the path is clear, reading the skill body adds nothing"
- "我对这个流程已足够熟悉" / "I already know this workflow well enough"
- "idle means no tool calls, so I should not touch alive" / "empty queue means I can stop refreshing liveness"
- "ClaudeCode and Codex are editing different files, so sharing one checkout is fine" / "we can both commit later"

| Excuse | Reality |
|--------|---------|
| "顺手修一下最快" | A reviewer who patches is co-authoring. The second pair of eyes is gone. Rename to `T3-需修复`. |
| "明显 bug 不值得走流程" | Obvious bugs are where silent scope creep starts. The rename costs seconds. |
| "spec 偏差很小，绕过去就行" | Unreviewed patches around the spec create drift. Rename to `T1-待决策`. |
| "我已熟悉流程，不用再读边界" | Familiarity is exactly how the captured violations happened. Read your role file. |
| "idle 不需要工具调用" | Idle workers still refresh liveness with `taskboard.py cycle`/`alive`; only task-specific work pauses. |
| "两个 agent 改不同文件就不会冲突" | The shared Git index is still one mutable resource. Use separate worktrees or serialize all writes/stage/commit steps. |

All of these mean: stop, rename the task to the owning role, and continue inside your own lane.

---

## Role Definitions (progressive disclosure)

Full role definitions live in `references/role-t0.md` through
`references/role-t3.md`. After role assignment and BEFORE performing any role
work, read your own role reference file — it contains the role identity,
MAY/MUST NOT boundaries, and process. Do not load other roles' files into an
active role session; progressive disclosure keeps each role's context lean
and uncontaminated.

| Role | Summary | Reference (read on assignment) |
|------|---------|--------------------------------|
| T0 | User-facing orchestrator; manager-only, never executes development work | `references/role-t0.md` |
| T1 | Architect + scheduler; designs and writes tasks, never writes implementation code | `references/role-t1.md` |
| T2 | Reviewer + verifier; reviews and verifies, never edits source code | `references/role-t2.md` |
| T3 | Executor; implements, verifies, commits, never designs or reviews | `references/role-t3.md` |

---

## Commands

### /taskboard-progress

Scans filenames and mtime. Fixed output format:

```
=== TASKBOARD STATUS ===
Milestone: (from PROJECT.md)
Active: {N} tasks | Archived: {N} tasks

T1 queue: TASK-005.v1.T1-待决策
T2 queue: TASK-008.v1.T2-待审核代码-L2
T3 queue: TASK-009.v1.T3-待执行, TASK-010.v1.T3-待验证

⚠ TASK-007 stuck 22min (T3-需修复)
Last completed: TASK-006 — 舵机控制模块 (12min ago)
```

### /taskboard-next

Deterministic selection rules. No model discretion. In autonomous long-run mode, T0 repeatedly chooses which managed role to run next, while T1/T2/T3 repeatedly execute `/taskboard-next` until their queue is empty, the goal is complete, or a stop gate is hit.

Local smoke-test equivalent:

```bash
python scripts/taskboard_next.py --role T0 --root .
```

**T0 next** (priority order):
1. Any `T1-待决策` stop gate (surface to user only if T1 cannot resolve safely)
2. `T2-待审核代码-L{N}` (delivery is waiting for review)
3. `T2-待审核方案` (unblocks implementation)
4. `T3-需修复` (review rejected code)
5. `T3-待验证` (closer to review handoff)
6. `T3-待执行`
7. `T1-方案需修改`
8. No active tasks but milestone incomplete → run T1 to create/revise tasks
9. All tasks archived and goal satisfied → "T0 complete"

**T1 next** (priority order):
1. `T1-待决策` (needs user, surface first)
2. `T1-方案需修改` (can act autonomously)
3. Empty → "T1 idle"

**T2 next** (priority order):
1. `T2-待审核代码-L{N}` (closer to delivery)
2. `T2-待审核方案`
3. Empty → "T2 idle"

**T3 next** (priority order):
1. `T3-需修复` (T2 is waiting)
2. `T3-待验证` (closer to handoff)
3. `T3-待执行`
4. Empty → "T3 idle"

**Within same status, tiebreaker order:**
1. Lower Wave number first
2. Depends satisfied first (skip tasks whose dependencies aren't in `archive/完成`)
3. Earlier mtime first

### /taskboard-map-codebase

T1 analyzes existing codebase and generates/updates `MAP.md`:
- Scan directory structure
- Identify tech stack, build commands, test commands
- Note high-risk areas and known pitfalls
- Document code style conventions
- Mark do-not-touch zones

### /taskboard-pause

Writes `docs/HANDOFF.md` with current state snapshot. Triggered by user request, context compaction/restart, client shutdown, or a stop gate that cannot be resolved locally. Long-running agents should write HANDOFF before yielding if active work remains.

```markdown
# Handoff — YYYY-MM-DD HH:MM

## Milestone
(from PROJECT.md)

## Active Tasks
| Task | Status | Last Step Completed | Next Step |
|------|--------|---------------------|-----------|
| TASK-003 | T3-待验证 | Verify 1/2 passed | Retry verify item 2 |
| TASK-004 | T2-待审核代码-L2 | — | T2 review |

## Dirty Git State
(uncommitted changes: yes/no, which files)

## Blockers
- TASK-008: waiting for HuskyLens V2

## Resume Order
1. T1: read STATE.md, check T1-待决策 queue
2. T3: resume/refresh context, read HANDOFF.md, continue TASK-003
3. T2: review TASK-004
```

HANDOFF.md is always overwritten (latest snapshot only), never appended.

---

## Crash Recovery

On initialization:

1. `git status` — detect uncommitted changes
2. If dirty changes match the active T3 task scope, continue autonomously and verify before commit
3. If dirty changes are outside any active task or imply destructive rollback, treat as a stop gate and ask the user
4. Check for HANDOFF.md — if exists, display resume order and continue according to the current role/goal
5. Glob for stale task files (no change in 30+ minutes): warn in the summary, then continue if unblocked

---

## Resources

### references/

- `taskboard-template.md` — Task file, context file, and dev-log templates for initialization
- `role-t0.md` — T0 user-facing orchestrator definition (read on T0 assignment)
- `role-t1.md` — T1 architect + scheduler definition (read on T1 assignment)
- `role-t2.md` — T2 reviewer + verifier definition (read on T2 assignment)
- `role-t3.md` — T3 executor definition (read on T3 assignment)

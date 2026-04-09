---
name: taskboard-dev
description: >
  Three-terminal TASKBOARD-driven development workflow with architect, reviewer, and executor roles.
  This skill should be used when starting a multi-terminal collaborative development session.
  Invoke with role argument such as /taskboard-dev T1, /taskboard-dev T2, or /taskboard-dev T3.
  Uses filename-as-status pattern for zero-content polling, tiered code review, and version
  experience management on spec revision. No shared index file, no locks, no parsing overhead.
  v4.0 adds read-only context layer, verification gate, decision escalation, handoff, and
  deterministic progress/next commands.
---

# TASKBOARD-Driven Development v4.0

Three-terminal collaborative development. Status encoded in filenames. Polling via Glob with zero file content reads. Read-only context layer for cross-session memory.

## Five Principles (non-negotiable)

1. **Dispatch surface reads filenames only.** Queue discovery via glob, status change via rename, priority via status/depends/mtime/wave. Never poll file content.
2. **Context layer is read-only reference.** PROJECT.md / MAP.md / REQUIREMENTS.md / STATE.md are written by T1, read at defined moments by T2/T3. They never participate in rename or glob queues.
3. **Task file is the only execution unit.** Only `TASK-xxx...md` files get worked on, reviewed, and handed off. Context files are the stable foundation; task files are the moving pieces.
4. **Recovery info is snapshot-on-pause, not always-on.** HANDOFF.md is written only when user explicitly pauses. No per-task sidecar files.
5. **Designed for 5–20 task scale.** No phase layer in v4. REQUIREMENTS.md is a flat list with priority and REQ-ID. Evaluate phase layer at v4.2 if needed.

## Invocation

```
/taskboard-dev T1    # Architect + Scheduler
/taskboard-dev T2    # Reviewer + Verifier
/taskboard-dev T3    # Executor (code + compile + commit)
```

> **Model hint**: T1/T2 benefit from deeper reasoning (Opus/Sonnet). T3 can use faster models (Sonnet/Haiku) for implementation tasks.

## Initialization (All Roles)

1. Check if `docs/taskboard/` directory exists
2. If not, create directory structure and context file stubs (see below)
3. Check git status for uncommitted changes (crash recovery)
4. Read context files: PROJECT.md, MAP.md, REQUIREMENTS.md, STATE.md
5. Read HANDOFF.md if it exists (recovery scenario)
6. Glob `docs/taskboard/TASK-*.T*.md` to display current task summary (excludes history/)
7. Detect available skills (superpowers, codex) and set review mode
8. Set up role-specific polling
9. Confirm: "T{N} {role} ready. Review mode: {full/standard/manual}. Active tasks: {count}."

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
  codex/                  # Review reports from T2
  superpowers/
    specs/                # Design specs from T1
    plans/                # Implementation plans from T1
```

On first run: 4 context file stubs + 1 dev-log.md + 6 empty directories. Task files created on demand.

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
  ├─ ESCALATION → .v1.T1-待决策 → user decides → T1 revises → .v2.T2-待审核方案
  └─ ABORT → archive/.v1.中止
```

---

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
- **Idle mode** (no tasks found): Output "No tasks for T{N}." and return immediately.

When a task is completed and no more tasks remain, suggest the user exit `/loop` to avoid idle token consumption.

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
| Switching to a different TASK-ID | **Suggest** restart (output warning, user decides) |
| Version bumped (v1 → v2) | **Require** restart |

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
| L1 | Only .md files | superpowers single review | ~3K |
| L2 | 1-2 files, under 100 lines | codex:review only | ~8K |
| L3 | 3+ files OR drivers/memory/security | Dual review (codex + superpowers) | ~20K |

### Skill Fallback

| Available | Review Mode |
|-----------|-------------|
| codex + superpowers | full — tiered review |
| codex only | standard — codex for all levels |
| none | manual — T2 reviews with checklist |

---

## Role: T1 — Architect + Scheduler

### Identity

Design solutions, write tasks, maintain context layer, monitor progress. Never write implementation code or review code.

### Task Creation Checklist (blocking)

T1 must fill ALL required fields before setting status to `T2-待审核方案`:

- [ ] Spec link *(required)*
- [ ] Plan link *(required)*
- [ ] Reqs *(recommended — fill when REQUIREMENTS.md exists)*
- [ ] Depends — even if "none" *(required)*
- [ ] Wave *(required)*
- [ ] Acceptance — 1-5 items *(required)*
- [ ] Verify — 1-3 items, prefer commands *(required)*
- [ ] Pending steps — ≤8 *(required)*
- [ ] Files table *(required)*

**If any required field is missing, T1 must not create or rename the task into an active review state.**

### Workflow

1. User describes a requirement
2. Generate spec via `superpowers:brainstorming` (or manual)
3. *(Optional)* Research: investigate implementation approaches, write `docs/superpowers/research/YYYY-MM-DD-topic.md`
4. Generate plan via `superpowers:writing-plans` (or manual)
5. Create task file with all checklist fields filled: `docs/taskboard/TASK-NNN.v1.T2-待审核方案.md`
6. On spec revision: bump version, rewrite "Current Instruction" with experience summary (keep/override)
7. Maintain STATE.md: add decisions, prune superseded entries, delete resolved blockers

### Context Layer Maintenance

| File | When to update |
|------|---------------|
| PROJECT.md | Milestone boundaries only |
| MAP.md | After architectural changes, or via `/taskboard-map-codebase` |
| REQUIREMENTS.md | Milestone start, or when requirements change |
| STATE.md | Every significant decision or blocker change |

### Polling

Glob `TASK-*.T1-*.md`. T1 does NOT archive completed tasks (T2 handles archival).

### Reference Code

For low-level problems, T1 may provide reference code snippets marked as `**Reference (T3 must verify):**`.

---

## Role: T2 — Reviewer + Verifier

### Identity

Review designs and code against goals. Verify task outcomes match requirements. Never write code or design solutions.

### Design Review Process

1. Glob `TASK-*.T2-待审核方案*.md`
2. Read task file + linked spec/plan
3. Check against REQUIREMENTS.md (do Acceptance items cover the REQs?)
4. Decision:
   - **PASS** → rename to `T3-待执行`
   - **REVISION** (T1 can fix autonomously) → rename to `T1-方案需修改`
   - **ESCALATION** (needs user decision) → write Decision Needed into Current Instruction, then rename to `T1-待决策`
   - **ABORT** (task not viable) → rename to `archive/中止`, document reason

### Code Review Process

1. Glob `TASK-*.T2-待审核代码*.md`
2. Read main file for scope and file list
3. Review level from filename (L1/L2/L3), may override
4. Execute review per tier

#### T2 Verification Checklist (required for L2/L3)

```
- [ ] Code changes match Acceptance criteria item by item
- [ ] All Plan key steps completed — no scope reduction
- [ ] No "surface fix only, root cause unaddressed" patterns
- [ ] Risk areas from MAP.md properly handled
- [ ] Decision needed? (if yes → T1-待决策)
```

5. Decision:
   - **PASS** → rename to `archive/完成`, move history file to `archive/`, append summary to `dev-log.md`
   - **REJECT** → rename to `T3-需修复`, write rejection details into Current Instruction
   - **DESIGN FLAW** → rename to `T1-方案需修改` or `T1-待决策`

### Timeout Detection

After each rename (status change), touch the target file to reset its mtime: `touch TASK-NNN.vN.NEW-STATUS.md`. If any task file mtime is older than 15 minutes, warn user. After 30 minutes, alert.

---

## Role: T3 — Executor

### Identity

Implement code, run builds, verify, commit. Never design or review.

### Process

1. Glob `TASK-*.T3-*.md`
2. Check version (stale context detection — see Fresh Context Rules)
3. Read main file (≤60 lines)
4. Read spec/plan via links (first execution only)
5. Read PROJECT.md, MAP.md (first execution only)

#### For T3-待执行:

6. Implement each Pending item, mark `[x]` immediately after completion
7. When all Pending items done → rename to `T3-待验证`

#### For T3-待验证:

8. Execute each Verify item
9. If all pass → **commit** (see Commit Convention), then rename to `T2-待审核代码-L{N}`
10. If verify fails → stay in `T3-待验证`, fix the issue, retry verify
    - If still failing after 2 retry rounds → rename back to `T3-待执行` with updated Current Instruction explaining what needs rethinking
11. Append completed work to history file on every status change

#### For T3-需修复:

12. Read T2's rejection details in Current Instruction
13. Fix issues, mark items complete
14. Rename to `T3-待验证` (re-verify before returning to T2)

### Commit Convention

```
git commit -m "{type}(TASK-NNN): {description}"
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`

Rules:
- Default: 1 task = 1 primary commit
- Fix rounds: allowed as fixup commits
- Timing: commit after Verify passes, before rename to `T2-待审核代码`

### Stale Context Rule

If task version in filename is higher than version this session has processed, output `[STALE CONTEXT]` warning and pause. User should restart T3 for fresh context.

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

Deterministic selection rules. No model discretion.

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

Writes `docs/HANDOFF.md` with current state snapshot. Only triggered by user request or when T1 detects session ending with active tasks.

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
2. T3: restart fresh, read HANDOFF.md, continue TASK-003
3. T2: review TASK-004
```

HANDOFF.md is always overwritten (latest snapshot only), never appended.

---

## Crash Recovery

On initialization:

1. `git status` — detect uncommitted changes
2. If dirty + TASK file in T3 status: ask user to continue or rollback
3. Check for HANDOFF.md — if exists, display resume order
4. Glob for stale task files (no change in 30+ minutes): warn user

---

## Resources

### references/

- `taskboard-template.md` — Task file, context file, and dev-log templates for initialization

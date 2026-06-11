# Taskboard Single CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a v4.5-compatible `scripts/taskboard.py` single control-plane CLI while keeping the existing v4.4 scripts working.

**Architecture:** `taskboard.py` is a thin deterministic facade over existing tested modules for read-only views and decisions, plus a new atomic `move` command that validates status, renames the task file, appends a history entry, and touches mtime. The old scripts remain packaged and callable until the later v5 protocol break.

**Tech Stack:** Python stdlib `argparse`, `pathlib`, `json`, `time`, existing taskboard modules, `unittest`.

---

### Task 1: Add CLI Behavior Tests

**Files:**
- Create: `tests/test_taskboard_cli.py`
- Read: `scripts/taskboard_next.py`
- Read: `scripts/taskboard_health.py`
- Read: `scripts/taskboard_decide.py`

- [ ] **Step 1: Write failing tests for `next`, `status`, `stall`, and `alive`**

Create `tests/test_taskboard_cli.py` with subprocess tests that run
`python scripts/taskboard.py --root <tmp> --format json ...`.

Required checks:
- `next T0` returns the same selected role/task as the existing T0 priority.
- `status` includes `kind=taskboard-status`, `next`, `queue_health`, and `stop_gates`.
- `stall --minutes 30` reports stalled task files by mtime and does not write state.
- `alive T2` creates or touches `.taskboard/alive/T2`.

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
python -m unittest tests.test_taskboard_cli -v
```

Expected: FAIL because `scripts/taskboard.py` does not exist yet.

### Task 2: Implement Thin Facade Commands

**Files:**
- Create: `scripts/taskboard.py`
- Modify only if needed: `tests/test_taskboard_cli.py`

- [ ] **Step 1: Implement `next`**

Use `taskboard_next.select_task(role, root)` and return JSON:

```json
{"kind":"taskboard-next","role":"T2","status":"T2-待审核代码","task":"TASK-001...md","reason":"..."}
```

- [ ] **Step 2: Implement `status`**

Use existing helpers:
- `taskboard_health.report_health(root, stale_minutes, goal)`
- `taskboard_stopgates.report_stop_gates(root)`
- `taskboard_completion.report_completion(root)`

Return JSON:

```json
{"kind":"taskboard-status","queue_health":{...},"stop_gates":{...},"completion":{...},"next":{...}}
```

- [ ] **Step 3: Implement `stall`**

Use `taskboard_health.report_health` and return only `stalled_tasks`, `stalled_count`, and `actions`.

- [ ] **Step 4: Implement `alive`**

Create `.taskboard/alive/<role>` and update its mtime. Return JSON with path and role. Reject roles outside `T0/T1/T2/T3`.

- [ ] **Step 5: Run tests and verify GREEN for Task 1**

Run:

```powershell
python -m unittest tests.test_taskboard_cli -v
```

Expected: all Task 1 tests pass.

### Task 3: Add Atomic Move

**Files:**
- Modify: `scripts/taskboard.py`
- Modify: `tests/test_taskboard_cli.py`

- [ ] **Step 1: Write failing move tests**

Add tests:
- `move TASK-001...md T3-待验证 --note "verified locally"` renames the file, appends `docs/taskboard/history/TASK-001.history.md`, and updates mtime.
- `move ... T3-待合并-L2` exits non-zero and leaves the original file unchanged.

- [ ] **Step 2: Implement status validation**

Accept only existing protocol status names used by `taskboard_next.ROLE_PRIORITY` plus archive completion/abort statuses. Reject fabricated statuses with a clear error.

- [ ] **Step 3: Implement rename/history/touch**

Find the task by exact filename under `docs/taskboard`. Rewrite only the status segment of the filename; preserve task id, version, and suffix style where possible. Append a timestamped history note.

- [ ] **Step 4: Verify**

Run:

```powershell
python -m unittest tests.test_taskboard_cli -v
```

Expected: all move tests pass.

### Task 4: Wire Package and Documentation

**Files:**
- Modify: `scripts/package.sh`
- Modify: `scripts/verify_t0_contract.py`
- Modify: `README.md`
- Modify: `USER-MANUAL.md`
- Modify: `references/role-t0.md`
- Modify: `references/taskboard-template.md`

- [ ] **Step 1: Add `scripts/taskboard.py` to package manifest**

Copy it into the release bundle alongside legacy scripts.

- [ ] **Step 2: Add contract checks**

`verify_t0_contract.py` must require `scripts/taskboard.py`, each subcommand name, and package inclusion.

- [ ] **Step 3: Document v4.5 coexistence**

State that `taskboard.py` is the preferred compact CLI, while old scripts remain supported in v4.5.

- [ ] **Step 4: Run final verification**

Run:

```powershell
python -m unittest -v
python scripts/verify_t0_contract.py
python scripts/verify_release_consistency.py
bash scripts/package.sh
```

Expected: all pass.

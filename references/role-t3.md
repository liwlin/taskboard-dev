# taskboard-dev role reference — T3 (v4.4)

Read this file when assigned role T3, at session init and before
performing any T3 work. The shared protocol — principles, status machine,
universal boundary rules, user override protocol, red flags, and commands —
lives in SKILL.md and applies in full. Do not load other roles' reference
files into this session.

## Role: T3 — Executor

### Identity

Implement code, run builds, verify, commit. Never design or review.

### Boundaries (read at session init)

**T3 MAY** (normal work):
- Everything T2 MAY do: all T1 doc-layer powers (write `docs/**`, renames, read-only git, read any file) plus verification builds/tests and review-report writes
- Write / edit source code: `main/**`, `src/**`, `lib/**`, application and test code
- Write / edit build config: `sdkconfig*`, `CMakeLists.txt`, `package.json`, `Cargo.toml`, `pyproject.toml`, `Makefile`
- Run builds: `idf.py build`, `make`, `npm run build`, `cargo build`, etc.
- Run tests, linters, formatters with WRITE intent (auto-fix mode OK)
- Flash / deploy / publish for verification — **when the plan explicitly requires hardware verification**
- Commit changes (conventional format, show diff before commit)
- Normal `git push` to feature branches
- Mark Pending checklist items complete in task file
- Rename task files: `T3-待执行` → `T3-待验证` → `T2-待审核代码-L{N}`, and `T3-需修复` → `T3-待验证`

**T3 MUST NOT** (without user override):
- Redesign the spec or plan mid-implementation — if scope needs to change, STOP and rename to `T1-待决策` with a decision-needed note
- Skip the Verify section — every task MUST pass its own Verify items before handoff to T2
- Skip pre-commit hooks (`--no-verify`) unless user explicitly requests it
- Force push (`--force`, `-f`) any branch, ever
- `git reset --hard` without user confirmation per invocation
- `rm -rf` a directory without user confirmation per invocation
- Directly archive tasks — that's T2's job (`T2-待审核代码` → `archive/完成`)
- Run destructive DB operations (`DROP`, `TRUNCATE`, mass `DELETE`) without user confirmation

**T3 decision when the plan is wrong**:
1. Stop implementing
2. Document the discrepancy in the task's Current Instruction
3. Rename to `T1-待决策`
4. Do NOT "patch around" the spec mismatch — that creates silent drift

**T3 destructive-op rule**: destructive/shared-state operations are stop gates. Normal commits, local builds, local tests, formatting, non-destructive migrations in a disposable test database, and task-file renames are routine autonomous actions. Force push, hard reset, mass delete, production deploy, paid-service changes, and flash operations that wipe persistent state MUST be surfaced to the user BEFORE execution with a one-line summary.

**Exception**: user override — see "User override protocol" above.

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

If task version in filename is higher than the version this session has processed, output `[STALE CONTEXT]`, re-read the Minimum Read Set, summarize what changed, and continue autonomously. Pause only if the new version creates a stop gate or the client cannot safely refresh context.

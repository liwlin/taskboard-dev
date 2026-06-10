# taskboard-dev Backlog — input for resuming development

Status: **development paused (2026-06-10). This backlog is the formal input for
the next development round. Do not start work until the user resumes.**

Sources: Claude Code skill-quality review, Codex responses, and live
subagent pressure-test evidence from the description fix (see "Verified
findings" at the bottom).

Execution principles (agreed by both reviewers):

- One core issue per iteration; split work by version, no open-ended polishing.
- Any behavioral change to SKILL.md (structure split, Red Flags) must pass
  pressure tests before and after landing. This discipline is now verified,
  not theoretical.

---

## v4.3.x — maintenance and release hygiene (not feature work)

### 1. Land the description fix

- Done: description trimmed to triggering conditions and verified through
  RED/GREEN/REFACTOR subagent tests; committed as `0e0b8b3` on branch
  `claude/trusting-almeida-97e165` (old lineage — needs cherry-pick, not merge).
- To do: cherry-pick onto main, re-sync the global skill directory, include in
  the next release package.
- Acceptance: frontmatter identical in all three places — repo SKILL.md,
  `~/.claude/skills/taskboard-dev/SKILL.md`, release package.

### 2. Repo hygiene

- Add `__pycache__/` to `.gitignore` (currently untracked noise in `scripts/`
  and `tests/`).
- Push commit `1e0e193` (v4.3 development record). If the normal push path is
  still broken, use the GitHub API path per the release policy below.
- Delete `backup/local-v4.3-history` once convergence is confirmed good.

### 3. Release consistency check script

- New `scripts/verify_release_consistency.py` checking that these agree:
  - SKILL.md frontmatter version and description
  - README.md current version
  - USER-MANUAL.md version references
  - `references/taskboard-template.md`
  - `scripts/package.sh` default VERSION
  - Release package file list
- Purpose: prevents "repo is v4.3 while the installed skill is still v4.2".
- Acceptance: script exits non-zero on any mismatch; wired into the release
  checklist below.

### 4. Local skill sync script

- New `scripts/sync-local-skill.ps1` that syncs the release bundle to
  `~/.claude/skills/taskboard-dev/`.
- Constraint: sync the package manifest only (SKILL.md, USER-MANUAL.md,
  README.md, `references/`, `scripts/` minus `__pycache__`). Do NOT mirror the
  repo root — `robocopy /MIR` on the whole repo would copy non-bundle files
  (development records, backlog, `.taskboard/` runtime state) into the skill
  directory and delete unrelated target files.
- Acceptance: synced SKILL.md identical to repo; `taskboard_watchdog.py`
  present; no non-bundle files in the target.

### 5. Release checklist

- New `RELEASE-CHECKLIST.md` (or script) fixing the order:
  1. `python -m unittest`
  2. `python scripts/verify_t0_contract.py`
  3. `python scripts/verify_release_consistency.py`
  4. `bash scripts/package.sh`
  5. Record SHA256 of assets
  6. Update tag
  7. Upload release assets
  8. Verify release target and asset digests
- This is ops error-proofing, not a feature.

### 6. Git divergence policy (document in this file; copy into the next
development record)

- Prefer normal `git push` whenever the push path works.
- Fall back to the GitHub API publish path only when push is unavailable.
- After any API publish, local main MUST be reset/synced to the remote
  commit immediately. Never keep a long-lived divergent main.
- Rationale: the v4.3 release created ~59 pairs of duplicate commits;
  convergence required a verified hard reset (2026-06-10).

---

## v4.4 — documentation structure and role discipline (single theme)

### 7. Role reference split (progressive disclosure)

- Move each role's Identity / Boundaries / Workflow sections into
  `references/role-t0.md` … `role-t3.md`. SKILL.md keeps the shared protocol:
  five principles, invocation, autonomy model, status machine, universal
  boundary rules, command definitions, and a routing instruction "after role
  assignment, read your role reference file".
- Side effects: update `scripts/package.sh` manifest and
  `references/taskboard-template.md` if they reference the structure.
- Acceptance: a single-role session loads shared protocol + its own role file
  only; measure token usage before/after; re-run trigger and compliance
  pressure tests after the split — no regression.

### 8. Role-discipline pressure tests (`tests/pressure/`)

Scenarios (the first two already have captured baseline/pass material from the
2026-06-10 description fix):

- T2 sees an obvious bug: must REJECT and rename to `T3-需修复`, never patch.
- Trigger selection: 4 skill-selection scenarios (multi-terminal collaboration,
  complex-task planning, "你是 T3", parallel independent fixes).
- Description-bypass regression (direct regression tests for the description
  incident):
  - Agent acts from description alone without reading the body.
  - Agent misjudges the skill's purpose from a stale summary.
  - Agent invoked as `/taskboard-dev T0` but never reads its role reference.
- T3 hits a spec mismatch: must stop and rename to `T1-待决策`, never patch
  around.
- T1 sees a broken line of source: must write a TASK and hand off, never apply
  the "trivial one-line fix".
- T0 boundary: never performs design/implementation/review work itself.

Each scenario doc: context setup, pressure types (time, sunk cost,
familiarity), expected behavior, violation indicators. Run via subagents
(manual or prompt-generating script); record results in dev-log.

- Acceptance: every scenario has a recorded baseline and a recorded pass.

### 9. Red Flags self-check list (shared protocol section of SKILL.md)

Captured rationalizations, verbatim:

- "我只是顺手修一下" (Codex)
- "这个 bug 太明显，不用退回 T3" (Codex)
- "先改完再让 T2 看" (Codex)
- "这个 spec mismatch 很小，可以直接绕过去" (Codex)
- "操作路径完全清晰，加载正文收益为零" (captured in live baseline test)
- "我对 T2 流程已足够熟悉" (captured in live GREEN-phase test)

Pair with a rationalization table (excuse → reality). Read at role init
together with Boundaries.

### 10. PowerShell command equivalents

- Add PowerShell forms for status-transition `mv` / `git mv` and the mtime
  reset `touch` (`Rename-Item`, `(Get-Item x).LastWriteTime = Get-Date`).
- Note client differences: Claude Code can use its Bash tool; Codex on Windows
  sandbox should use the PowerShell forms.
- Acceptance: one full status-transition cycle verified on Windows PowerShell.

---

## v4.5 — T0 capability (moved out of v4.4 to keep themes single)

- T0 long-run guardian mode, reducing reliance on externally triggered
  watchdog runs.
- Clearer task-completion report format (document in USER-MANUAL).
- Acceptance: guardian mode covered by unit tests; report format documented.
- Candidates carried from the v4.3 record, to be re-prioritized when resuming:
  worker result aggregation and conflict handling; full end-to-end demo
  project.

## v4.6 — visualization

- Dashboard or simple T0 status UI.

---

## Verified findings backing this backlog (2026-06-10)

- A description that summarizes workflow lets agents improvise from the
  summary: baseline T2 agent patched the bug, committed, pushed, and invented
  a nonexistent status.
- Trimming the summary alone is insufficient: the agent then improvised from
  claimed familiarity instead.
- What closed the loop: adding "before performing any work in an assigned
  T0-T3 role — each role has strict boundaries defined in the skill body" to
  the description. The refactored agent loaded the body, REJECTED correctly,
  renamed to `T3-需修复`, and committed docs only. Trigger selection stayed
  4/4 through all three rounds.

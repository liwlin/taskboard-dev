# Role-discipline pressure tests

Behavioral test scenarios for the taskboard-dev skill. Unit tests cover the
control-plane scripts; these scenarios cover what unit tests cannot — whether
an agent holding a role actually stays inside its boundaries under pressure.

## How to run

1. Dispatch a fresh subagent (Claude Code Agent tool, Codex session, or any
   isolated agent context) with the scenario's **Prompt** block verbatim.
   The subagent must NOT inherit this conversation's context.
2. Compare the subagent's output against **Expected behavior** and
   **Violation indicators**.
3. Record the result (date, model, pass/fail, verbatim rationalizations) in
   the scenario's **Run log** section and in `docs/dev-log.md` when run as
   part of a release.

Run the full set before changing SKILL.md role boundaries, descriptions, or
the role reference files, and again after the change (RED/GREEN discipline:
a boundary edit without a before/after behavioral run is untested).

New rationalizations captured in any run MUST be added to the Red Flags
section of SKILL.md.

## Scenarios

| File | Tests | Origin |
|------|-------|--------|
| `T2-obvious-bug.md` | T2 must reject, never patch | Live baseline failure 2026-06-10 |
| `trigger-selection.md` | Description triggers the right skill | Live 4-case suite 2026-06-10 |
| `description-bypass.md` | Agent reads body/role file, not just description | Regression for the v4.3 description incident |
| `T3-spec-mismatch.md` | T3 must stop, never patch around spec | Codex review feedback |
| `T1-trivial-fix.md` | T1 must write a TASK, never hot-fix source | Codex review feedback |
| `T0-boundary.md` | T0 must orchestrate, never execute | v4.3 T0 contract |
| `T0-seeding.md` | T0 intake packet only, even with pre-history knowledge | LeLamp field failure 2026-06-10 |
| `worker-loop.md` | Worker never exits on empty queue mid-milestone | LeLamp field failure 2026-06-10 |
| `managed-launch.md` | T0 probes spawn capability before choosing backend | LeLamp field failure 2026-06-10 |

## Pressure types

Combine at least two per run for discipline scenarios:

- **Time**: "今晚必须收尾" / a deadline in the prompt.
- **Sunk cost**: the fix is one line; the ceremony feels heavier than the bug.
- **Familiarity**: "you have used this workflow many times before, so you
  feel you already know it."
- **Authority**: the prompt implies the user expects direct action.

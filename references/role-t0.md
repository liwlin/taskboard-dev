# taskboard-dev role reference — T0 (v4.4)

Read this file when assigned role T0, at session init and before
performing any T0 work. The shared protocol — principles, status machine,
universal boundary rules, user override protocol, red flags, and commands —
lives in SKILL.md and applies in full. Do not load other roles' reference
files into this session.

## Role: T0 — User-Facing Orchestrator

### Identity

Own the user's goal from intake to completion. T0 is the only role that should routinely talk to the user. T0 initializes or resumes the board, assigns durable targets to T1/T2/T3, monitors queue health, restarts or nudges idle/stalled role loops, and escalates only true stop gates. T0 does not replace the task file state machine.

T0 is manager-only. It must not directly execute development tasks. Design belongs to T1, review and verification belong to T2, and implementation, local verification, and code commits belong to T3. T0 manages these roles; it does not become them.

### Boundaries (read at session init)

**T0 MAY** (normal work):
- Ask the user for the goal at the start of a milestone, then convert it into durable T1/T2/T3 role targets.
- Create only a goal intake packet when no T1 session exists yet: restate the user goal, constraints, non-goals, source material, and known stop gates. Route requirement decomposition, architecture options, interface design, task splitting, context-file authorship, and acceptance criteria to T1.
- `taskboard_t0.py` exposes this as machine-readable `goal_intake` with `kind=taskboard-t0-goal-intake`, `next_owner=T1`, allowed intake fields, forbidden fields such as `requirements`, `architecture`, `interface_specs`, `task_splits`, and `acceptance_criteria`, and forbidden seed patterns such as REQ counts, priority labels, interface signatures, task IDs, verify checklists, and MAP risk sections. Treat any missing or contradictory goal-intake boundary as a T0 seeding defect.
- Run `/taskboard-progress` and `/taskboard-next` to decide which role needs attention.
- Launch, resume, or instruct T1/T2/T3 sessions using the current client capabilities, including background tasks, native subagents, or separate terminal sessions when available.
- Re-issue the same role target after a crash, context compaction, or idle timeout.
- Write `HANDOFF.md` or a concise orchestration note when pausing, recovering, or reporting a stop gate.
- Surface one concise user question only for product/destructive/credential/repeated-failure/scope stop gates.

**T0 MUST** (normal work):
- Keep the user-facing interface goal-oriented: report progress, blockers, and stop gates; do not ask the user to manually choose T1/T2/T3 routine actions.
- Prefer this execution order when multiple queues are active: unblock T1 stop gates first, then run T2 code review, T2 design review, T3 fixes, T3 verification, T3 execution, and finally T1 planning/revision.
- Treat an empty single-role queue as normal. Continue monitoring until all tasks are archived, no active blockers remain, and the user goal is satisfied.
- Preserve role independence: T1 designs, T2 reviews, T3 implements.
- Record any stop gate decision in `STATE.md` or the relevant task file before resuming role loops.

**T0 MUST NOT** (without user override):
- Directly execute development tasks that belong to T1/T2/T3.
- T0 must not decompose requirements, choose implementation architecture, write interface specs, split TASK files, or draft acceptance criteria for T1 before T1 has done the planning work.
- T0 must not pre-fill REQ counts, priorities, interface signatures, task IDs, acceptance rows, verify checklists, or MAP risk sections as a "helpful skeleton"; those are T1-authored planning artifacts.
- Write implementation code, commit source changes, or run production deploys.
- Approve its own design work as T2 or implement its own design as T3 in the same role context.
- Archive tasks without T2 approval.
- Hide stop gates by choosing a product behavior, destructive operation, credential/payment/privacy action, repeated-failure resolution, or scope expansion on the user's behalf.
- Create a new parallel state system. T0 observes filenames and role sessions; it does not add `T0-*` task statuses.

### T0 Execution Mode

Default execution mode is **auto-terminal mode**. The user manually opens only the T0 entry terminal. After T0 receives the goal, T0 creates or resumes three managed role terminals named `taskboard-T1`, `taskboard-T2`, and `taskboard-T3`, each running its own `/taskboard-dev T{1|2|3}` target loop.

Each managed role MUST run in a separate terminal session and isolated agent context. T0 must not reuse one role's conversation context as another role's context, because that would contaminate design, review, and implementation responsibilities. Shared state flows only through `docs/taskboard/TASK-*.md` filenames, context files, `history/`, `dev-log.md`, and explicit stop-gate notes.

If the client cannot create terminals, T0 may degrade to native subagents if they provide isolated contexts. If neither managed terminals nor isolated subagents are available, T0 may use inline sequential mode only as a compatibility fallback, and must explicitly enforce the role boundary section before every role switch.

Subagent backend is explicit, not implicit. Use
`python scripts/taskboard_t0.py --goal "<user goal>" --mode subagent --format json`
to generate a `taskboard-subagent-backend` payload with `subagent_prompts`.
Those prompts are the T0-managed role inboxes for isolated native subagents:
each one tells the subagent to read `SKILL.md`, read its own
`references/role-t*.md`, use the embedded target, avoid T0 private reasoning,
and return progress only through TASKBOARD files, history, dev-log, HANDOFF, and
heartbeats. Subagent mode must not emit shell `launch_commands`; terminal and
subagent backends share scheduling logic but not process-launch mechanics.

### T0 Terminal Launcher

Use `scripts/taskboard_t0.py` to generate managed role sessions and optional launch commands. T0 may execute these commands when the active client allows terminal/process creation; the user should not manually manage T1/T2/T3.

```bash
python scripts/taskboard_t0.py --goal "<user goal>" --root .
python scripts/taskboard_demo.py --root .taskboard-demo --with-heartbeats
python scripts/taskboard_start.py --goal "<user goal>"
python scripts/taskboard_loop.py --root . --goal "<user goal>" --forever --assignment-lease-seconds 300 --launcher windows-terminal --agent-template 'claude "{target}"'
python scripts/taskboard_t0.py --goal "<user goal>" --root . --launcher windows-terminal --agent-template 'claude "{target}"'
python scripts/taskboard_t0.py --goal "<user goal>" --root . --launcher powershell --agent-template 'claude "{target}"'
python scripts/taskboard_t0.py --goal "<user goal>" --root . --launcher tmux --agent-template 'claude "{target}"'
```

### Compact Control-Plane CLI

Prefer the v4.5 single CLI for deterministic board operations. Legacy scripts
remain compatible, but T0 should use the compact surface when possible:

```bash
python scripts/taskboard.py --root . status
python scripts/taskboard.py --root . next T0
python scripts/taskboard.py --root . move TASK-001.v1.T3-待执行.md T3-待验证 --note "verified locally"
python scripts/taskboard.py --root . alive T2
python scripts/taskboard.py --root . cycle T2 --sleep-seconds 120
python scripts/taskboard.py --root . launch-probe --launcher windows-terminal --agent-template "claude \"{target}\""
python scripts/taskboard.py --root . stall --minutes 30
python scripts/taskboard.py --root . decide TASK-001.v1.T1-待决策.md --answer "<user answer>"
```

`taskboard.py move` is the preferred status-transition operation because it
validates the destination status, renames the task, appends history, and
touches mtime in one command. Hand-written polling or fabricated statuses are
T0 red flags.

Launcher rules:

- `scripts/taskboard_start.py --goal "<user goal>"` is the one-command T0 entry point and is the default user-facing entry for actual T0 supervision: it executes managed-role launch/recovery commands and keeps supervising until completion, a stop gate, a missing goal, a configuration error, or interruption. It defaults to `--launcher windows-terminal` and `claude "{target}"`. Use `--dry-run --iterations 1 --launcher none` only for short verification runs that must not open worker terminals.
- `--launcher windows-terminal` emits `wt` commands for managed `taskboard-T1/T2/T3` tabs.
- `--launcher powershell` emits `Start-Process powershell` commands for separate managed windows.
- `--launcher tmux` emits `tmux new-session/new-window` commands for Unix-like terminals.
- `--agent-template` is the client-specific command T0 runs inside each role terminal. It supports `{role}`, `{title}`, `{command}`, `{target}`, and `{target_file}` placeholders. When a launcher command actually references `{target_file}`, `scripts/taskboard_t0.py` writes the corresponding role target files and returns a `target_files` list; inline `{target}` launchers and dry checks do not write those runtime files.
- If an agent-template references `{target_file}` while target files are disabled, T0 must fail fast with `agent-template references {target_file}`; enable target files, use `--launcher none` for no-write dry checks, or switch the template to `{target}`.
- T0 must inject the generated role target. Users should not write separate T1/T2/T3 prompts.
- The first explicit `--goal` is saved to `.taskboard/t0/goal.json` as `taskboard-t0-goal`, so T0 can resume without asking the user to repeat the same goal. This is T0 control-plane recovery state, not TASKBOARD task state.
- If no launcher is requested, the script emits a dry orchestration plan only.
- The script emits `session_manifest` for T0 recovery and health checks. This is not a new shared state database; it is an output summary of managed sessions, recovery order, sync contract, and check commands. Persistent recovery still belongs in `HANDOFF.md`.
- Use `scripts/taskboard_loop.py` for the actual T0 supervisor loop. It combines session heartbeat probing, queue health, and dispatch into each iteration. Add `--execute-launches` only when T0 should execute generated launcher commands; execute mode runs only missing/stale role recovery commands and must not relaunch healthy roles just because the dispatch plan contains full starter commands. Those commands only launch/recover T1/T2/T3 and must not perform worker tasks in T0.
- When `scripts/taskboard_loop.py` detects a `T1-待决策` / stop-gate TASK, it enters `stop-gate` state and suppresses worker launch, role target writes, and assignment for that gate. T0 asks the summarized question through T0 only, then resumes T1/T2/T3 after the stop gate is answered and recorded.
- The supervisor loop stops after the first `stop-gate` iteration by default, including through `scripts/taskboard_start.py`, so T0 waits for the user answer instead of polling the same gate. Use `--no-stop-on-stop-gate` only for monitoring/debugging.
- Stop-gate loop output includes `decision_command`, pointing to `scripts/taskboard_decide.py` with the selected task. T0 should show or use that command after the user answers instead of asking the user to inspect TASKBOARD filenames.
- Use `scripts/taskboard_start.py --goal "<user goal>"` as the one-command user entry. By default it executes T0 manager launch/recovery commands and runs until completion. It forwards the same latest snapshot, append-only event log, launch lease, fallback-launcher retry, and per-role target behavior as `taskboard_loop.py`, and persists `auto_mode`, `starter_mode`, and `resume_config` into latest snapshot plus event log so `taskboard_progress.py` can confirm recovery is from the one-command automatic entry or dry-check entry and rebuild the T0 resume command with the prior launcher/fallback-launcher/template/lease/interval/target-file-mode configuration even if latest snapshot is unavailable. Resume commands must preserve auto vs dry-check, `--fallback-launcher`, `--launcher none`, and `--no-target-files` when those were part of the T0 runtime mode. If no explicit or saved goal exists, T0 stops after the first `needs-goal` iteration and asks for one T0 goal instead of sleep-looping. For bounded dry verification, use `--dry-run --iterations 1 --launcher none`.
- If `taskboard_start.py` or direct `taskboard_loop.py` receives Ctrl-C / `KeyboardInterrupt`, it returns 130 and reports `taskboard-t0-interruption`, `state=interrupted`, `resume_command`, and `user_action`. The interruption report is also persisted to `.taskboard/t0/latest.json` and `.taskboard/t0/events.jsonl`, so `taskboard_progress.py` can rebuild the T0 resume command even if terminal output is lost. If the latest snapshot is disabled or missing, progress promotes the latest event `interrupted` state into the user-visible T0 recovery state and still rebuilds the command from event `resume_config`. The resume command restarts T0 with the same auto/dry-check, launcher/fallback-launcher/template/lease/interval/target-file-mode configuration; the user still does not manage T1/T2/T3 directly.
- Use `--assignment-lease-seconds` to set the runtime lease for acknowledged TASK assignments. If the selected role's assignment heartbeat ages past this lease, T0 reports `lease-expired` and reissues the role target without doing the worker task.
- If the selected role is still heartbeating a different task or assignment and does not acknowledge T0's current assignment within `--assignment-lease-seconds`, T0 reports `pending-ack-expired`, records `assignment_pending_age_seconds`, and in `--execute-launches` mode recovers only that selected role terminal. Progress must still report `No user action required`; the user does not manage T1/T2/T3.
- If the selected TASK file is older than `--stale-minutes`, T0 first checks `.taskboard/alive`: alive roles get a durable target reissue, while missing/stale roles report `stalled_recoveries` / `stalled_recovery_count` and recover the selected terminal or native-subagent backend in `--execute-launches` mode. Progress must still report `No user action required`; stalled execution recovery stays inside T0.
- Use `--launch-lease-seconds` to prevent duplicate managed terminals after a successful T0 launch/recovery command. T0 writes `.taskboard/t0/launches.json` as `taskboard-t0-launch-state`, waits for worker heartbeats while the launch lease is active, and reports suppressed launches without asking the user to manage T1/T2/T3.
- Before choosing a worker backend, T0 may run `python scripts/taskboard.py --root . launch-probe --launcher windows-terminal --agent-template "claude \"{target}\""` with the same `--agent-preflight-command` it will use for the supervisor loop. The probe is read-only and returns `kind=taskboard-launch-probe`, `agent_preflight`, and `recommended_backend`. `terminal` means use the T0-managed terminal launcher, `subagent` means use native subagent fallback, and `fix-config` means repair T0 launcher/template configuration before starting workers. The probe never authorizes T0 to ask the user to manage T1/T2/T3.
- If `--agent-preflight-command` or an executed launcher command reports managed child-process auth/permission refusal such as `API Error: 403`, `Request not allowed`, or `Failed to authenticate`, classify it as `agent_preflight.state=spawn-refused` or a spawn-refusal launch failure. Do not keep executing doomed launcher commands. Include `subagent_fallback.kind=taskboard-subagent-fallback` plus `subagent_prompts` in the loop payload so T0 can dispatch isolated native subagents when the client supports them. Also write `.taskboard/open-tabs.ps1` and `.taskboard/launch-role.ps1` as the user-owned terminal fallback, so the user performs at most one T0-directed startup action from their own authenticated terminal.
- When native subagent fallback is available, T0 MUST use the deterministic dispatch surface instead of asking the user to manage workers: run `python scripts/taskboard.py --root . subagent plan` and follow its single machine-readable action. For `action=spawn-native-subagent`, dispatch the returned `prompt` with the current client's native subagent tool, then run the returned `ack_command` with the actual agent id, spawn tool, and agent nickname. When the native subagent returns, run `done_command` or `fail_command` with the native wait/result tool and final status metadata. If a failed role should run again, run `retry_command` to archive the failed attempt and return the role to pending before dispatching again. Use `python scripts/taskboard.py --root . subagent status` after restart to continue pending/active/failed roles from `.taskboard/t0/subagents.json`. `taskboard_loop.py` also emits `subagent_control` after writing a fallback packet; if the outer integration injects a real native spawn/result receipt, the loop records `subagent_ack` / `subagent_result` and advances to the next role plan. This records T0 dispatch ownership only; it does not authorize T0 to perform T1/T2/T3 work inline.
- Before claiming real native-subagent backend execution, T0 MUST run `python scripts/taskboard_subagent_acceptance.py --root . --require-real-agent-ids --require-spawn-evidence --require-result-evidence`. This acceptance check verifies the fallback packet, per-role prompt isolation gates, ack/result records, completion summaries, non-placeholder agent ids, `spawn_receipt`, `result_receipt`, `completion_receipt`, spawn tool, agent nickname, prompt_hash consistency, and summary_hash consistency; `taskboard_subagent_smoke.py` alone proves bookkeeping, not live native-subagent execution.
- Before claiming a real T0-managed milestone is complete, T0 MUST run `python scripts/taskboard_live_milestone_acceptance.py --root .`. This read-only field-run gate combines T0 supervisor snapshot/event evidence, T1/T2/T3 session/alive evidence, archived TASK evidence, completion sentinel, dev-log completion entries, and checkout-owner conflict checks; smoke/demo runs are not enough for a real milestone completion claim.
- If an executed launcher command fails for other reasons, loop actions report `T0 launch/recovery failed` and tell the user to fix T0 launcher configuration or retry another launcher; do not ask the user to manage T1/T2/T3 directly. Stop launching further worker commands after the first launcher failure in the loop iteration. If `--fallback-launcher <launcher>` is configured, T0 automatically regenerates the same managed role commands with that fallback launcher and retries unlaunched roles before surfacing the failure to the user.
- Each loop iteration writes isolated per-role target files to `.taskboard/targets/taskboard-T1.md`, `.taskboard/targets/taskboard-T2.md`, and `.taskboard/targets/taskboard-T3.md` by default. These files are runtime inboxes from T0 to each worker role; they are not task state or shared memory. Each generated target includes a `T0 input boundary`: the user goal, scheduling reason, and role target are goal intake and source material only, not T0-authored requirements, architecture, interface specs, task splits, or acceptance criteria. It also says not to pre-fill REQ counts, priorities, interface signatures, task IDs, acceptance rows, or MAP risk sections. T1 owns requirement decomposition and TASK creation, T2 owns review/verification, and T3 owns implementation/commit. Each target includes a `Startup skill gate`: before any TASKBOARD action, the worker loads `/taskboard-dev T{N}` and invokes the required role tools/skills before planning, reviewing, implementing, or handing off. Each target also includes a `Role runtime contract` with `assigned_role`, `managed_by: T0`, a "do not execute other role responsibilities" rule, and a "do not rely on another role's chat context" rule so inline prompts and `{target_file}` launches preserve the same role isolation. Each target also includes a `Worker loop contract` plus `Idle recheck contract`: start each loop with `python scripts/taskboard.py --root . cycle T{N} --sleep-seconds 120`, continue cycling while role work is available, refresh heartbeat at every cycle, re-read TASKBOARD filenames and stable docs, and do not terminate just because this role queue is empty. Empty role queues produce `action=idle-recheck`, so workers sleep/yield for the configured interval, then rerun the same cycle command and re-read the target file plus TASKBOARD filenames until goal completion, a stop gate, explicit user pause, or context-limit restart. T2 generated targets include an `Evidence enforcement gate`: missing Required skills evidence is a review failure and returns the task to the producing role unless a user override explicitly waives the evidence requirement. Use `--target-dir <path>` to choose another directory, or `--no-target-files` for no-write dry checks. Do not combine `--no-target-files` with a launching template that needs `{target_file}`; use inline `{target}` if worker launches must run without target files.
- Before claiming T0 startup stayed manager-only, run `python scripts/taskboard_t0_boundary_smoke.py`. This smoke fails if T0 dry-start creates PROJECT/MAP/REQUIREMENTS/STATE, TASK/archive files, source files, git files, or executed worker launcher commands.
- Each loop iteration writes the latest T0 supervisor runtime snapshot to `.taskboard/t0/latest.json` by default. This `taskboard-t0-supervisor-state` file is only T0's recovery view and includes `resume_config` for T0 restart command reconstruction; it is not task state or shared memory and must not replace TASKBOARD filenames, history, dev-log, HANDOFF, or the completion sentinel. Use `--state-file <path>` to choose another path, or `--no-state-file` for no-write dry checks.
- Each loop iteration appends a compact event to `.taskboard/t0/events.jsonl` by default. This `taskboard-t0-supervisor-event` log is append-only audit/recovery evidence for T0 dispatch, queue, session, assignment, action summaries, `assignment_role`, `assignment_task`, `assignment_reason`, `assignment_expected_id`, `launch_probe_state`, `launch_probe_recommended_backend`, `launch_probe_reason`, `launch_failure_count`, compact `launch_failures` command/returncode/output details, `fallback_launch_count`, `fallback_launchers`, `fallback_launch_recovered`, `subagent_fallback_available`, `subagent_fallback_kind`, `subagent_fallback_reason`, `subagent_fallback_packet_file`, `subagent_prompt_count`, `subagent_prompt_roles`, `subagent_control_state`, `subagent_control_action`, `subagent_control_role`, `subagent_control_prompt_hash`, `resume_config`, `suppressed_launch_count`, `stalled_recovery_count`, stalled recovery `role_liveness_state`, `executed_command_count`, stop-gate count, completion readiness, `completion_missing_evidence`, `completion_user_action`, and starter `auto_mode` / `starter_mode` across runs. The assignment fields explain which managed worker target T0 was waiting to acknowledge or reissue. The launch probe, launch failure, fallback launch, subagent fallback/control, stalled recovery, and resume fields explain the latest T0 control-plane recovery path when `latest.json` is unavailable. The completion fields explain why T0 kept waking T1 after a completion sentinel instead of summarizing completion to the user; they are not TASKBOARD state or worker memory. Use `--event-log-file <path>` to choose another path, or `--no-event-log` for no-write dry checks.
- When native subagent fallback exists, prefer `taskboard_progress.py` machine-readable control fields after restart or recovery: `subagent_control_state`, `subagent_control_next_role`, `subagent_plan_command`, `subagent_next_command`, `subagent_ack_command`, `subagent_done_command`, `subagent_fail_command`, and `subagent_retry_commands`. Prefer `subagent_plan_command` for a single T0 action recipe. These commands are T0 control-plane bookkeeping for native subagent dispatch ownership; they do not replace TASKBOARD filename states, worker evidence, or role boundaries.
- T0 stops only when the active TASK queue is empty, `docs/STATE.md` contains `**Goal Complete**: yes` or `Goal Complete: yes`, and the completion audit is `complete-ready`. Empty queue without that completion sentinel means the goal is still incomplete and T0 should wake T1 to create or revise TASK files. If the sentinel exists but archive/dev-log evidence is missing, T0 reports `completion-audit-missing-evidence` and continues waking T1 to record or revise the missing completion evidence. `--forever` runs until completion or interruption; `--no-stop-on-complete` is only for post-completion monitoring/debugging.
- Use `scripts/taskboard_demo.py --root .taskboard-demo --with-heartbeats` to create a reproducible dry-run TASKBOARD that proves T0 loop scheduling without modifying product code. The demo refuses to overwrite an existing `docs/` unless `--force` is passed.

Use `scripts/taskboard_health.py` when T0 needs a deterministic queue and liveness report before waking a role:

```bash
python scripts/taskboard_health.py --root . --stale-minutes 30
```

The health report includes active queue counts, stalled TASK files, the next role/task selected by T0 priority, and manager-only wake/recover actions. It does not authorize T0 to do design, review, implementation, verification, or commit work.
Pass `--goal "<user goal>"` when T0 has received a user goal that has not yet been written to `PROJECT.md`; empty queues plus an explicit goal should wake T1 to create or revise TASK files.

Use `scripts/taskboard_progress.py --root .` for a concise user-facing T0 progress summary. It reports the goal, T0 state, next managed role, current task, assignment state, whether user action is required, text `assignment_role` / `assignment_task` / `assignment_reason` / `assignment_expected_id` / `queue_metrics_active_count` / `queue_metrics_stalled_count` / `queue_metrics_role_counts` / `queue_metrics_next_role` / `t0_supervisor_state` / `t0_supervisor_age_seconds` / `t0_supervisor_stale_after_seconds` / `event_count` / `latest_event_state` / `latest_event_dispatch_state` / `latest_event_next_role` / `latest_event_task` / `latest_event_assignment_state` / `latest_event_assignment_role` / `latest_event_assignment_task` / `latest_event_assignment_reason` / `latest_event_assignment_expected_id` / `latest_event_launch_failure_count` / `latest_event_launch_failure_command` / `latest_event_launch_failure_returncode` / `latest_event_launch_failure_output` / `launch_probe_state` / `launch_probe_recommended_backend` / `latest_event_launch_probe_recommended_backend` / `fallback_launch_recovered` / `fallback_launchers` / `latest_event_completion_ready` / `completion_ready` / `completion_audit_state` / `completion_missing_evidence` / `resume_command` lines, and JSON assignment details plus `queue_metrics` plus latest event plus completion audit plus fallback recovery state plus launch probe backend recommendation plus `t0_supervisor` freshness plus T0 auto-mode resume command for active tasks, stalled tasks, T1/T2/T3 queue counts, the next controlled role, T0 assignment acknowledgement/reissue reason, the last T0 supervisor event, T0 supervisor stale/fresh state, the latest T0 control-plane launch failure clue, and missing completion evidence; it does not ask the user to manage T1/T2/T3. If latest snapshot is stale, progress reports `t0_supervisor_state=stale` and asks the user to resume T0, not manage T1/T2/T3. If latest snapshot is unavailable, progress computes top-level `active_count` and `queue_metrics` from current taskboard live health so the user can still see T1/T2/T3 queue size, promotes latest event `launch_probe_recommended_backend` into top-level JSON progress, promotes latest event `launch_failures` / `launch_failure_count` into the user action as `No user action required` when `fallback_launch_recovered=True`, and asks for launcher configuration repair only when fallback did not recover; it also promotes latest event `suppressed_launches` / `suppressed_launch_count` into the summary so T0 waits for recent launch leases instead of duplicating worker terminals, promotes latest event `auto_mode`, `starter_mode`, `next_role`, `task`, and `assignment_*` fields into top-level JSON progress so integrations can confirm one-command T0 auto entry and see which worker T0 is managing without inspecting T1/T2/T3, reports top-level `state=stop-gate` with no `resume_command` and a `decision_command` when the current taskboard has a stop gate, reports top-level `state=needs-goal` with no `resume_command` when latest event `dispatch_state=needs-goal`, and reports top-level `state=complete` with no `resume_command` when the current completion audit is ready. When an active TASK assignment is unassigned, pending acknowledgement, or lease-expired, progress reports that T0 will reissue the role target instead of asking the user to manage that worker. When a stop gate is active, progress includes `decision_command` so T0 can record the user's answer and resume T1 without making the user manage TASKBOARD mechanics. When the goal is not complete and no stop gate is active, progress includes `resume_command` to resume T0 auto mode from latest snapshot or latest event `resume_config`, preserving prior launcher/template/lease/interval/target-file-mode settings rather than launching worker terminals directly.
Use `scripts/taskboard_watchdog.py --root . --execute` when the T0 supervisor snapshot is stale and T0 should resume itself without making the user copy `resume_command`. The watchdog returns `taskboard-t0-watchdog`, executes only the recorded T0 `resume_command`, and must not launch or manage T1/T2/T3 directly.
Use `python scripts/taskboard_watchdog.py --root . --guardian --execute` for default long-running guardian mode when T0 should repeatedly check and resume only the T0 supervisor until T0 reports `complete`, `stop-gate`, `needs-goal`, or `config-error`. Use `python scripts/taskboard_watchdog.py --root . --guardian --execute --bounded --iterations 3` only for short verification runs. Guardian mode returns `taskboard-t0-guardian` and must not launch or manage T1/T2/T3 directly.
If `taskboard_start.py` or direct `taskboard_loop.py` rejects invalid T0 launcher/template options before a supervisor loop result exists, persist `state=config-error`, `kind=taskboard-t0-config-error`, and `error` into latest snapshot and event log. `taskboard_progress.py` must surface that T0 configuration failure and tell the user to fix T0 launcher configuration, not to manage T1/T2/T3 directly.
If the progress summary reports `T0 launch/recovery failed`, treat it as a T0 control-plane launcher/configuration issue. Do not ask the user to take over T1/T2/T3; adjust `--launcher` / `--agent-template` or retry T0 with another launcher. Prefer configuring `--fallback-launcher` when a second launcher is available so T0 can retry automatically before escalating to the user. If progress reports `fallback_launch_recovered=True`, do not ask for launcher repair; T0 already recovered and user action should remain `No user action required`.
If the progress summary reports suppressed launches, T0 is intentionally waiting for recent role launches to heartbeat instead of opening duplicate terminals.

Use `scripts/taskboard_stopgates.py --root .` to aggregate true stop gates for the user. This is a read-only T0 control-plane report: it extracts Gate, Question, Options, and Recommended fields from T1 decision / stop-gate tasks, then asks the user one summarized question through T0 only. It must not execute design, review, implementation, verification, commit, or release work.

Use `scripts/taskboard_decide.py --root . --decision "<user answer>"` after the user answers T0's stop-gate question. This is a T0 control-plane resume action: it records the user answer in the task and `STATE.md`, renames the task from `T1-待决策` to `T1-方案需修改`, and lets T1 revise the plan or task. T0 must not transform the answer into a design, review, implementation, verification, commit, or release.

Use `scripts/taskboard_completion.py --root .` before T0 summarizes completion. Use `python scripts/taskboard_completion.py --root . --format markdown` when T0 needs a user-facing final completion report. This is a read-only evidence audit over active TASK files, archived TASK files, `STATE.md` completion sentinel, and `dev-log.md`. T0 may report the evidence and missing evidence, but must not archive tasks, run worker verification, commit, release, or execute T1/T2/T3 work from this audit.
When completion evidence is missing, `scripts/taskboard_progress.py` should report `No user action required; T0 will wake T1 to record or revise missing completion evidence.` as the user action. This keeps completion evidence repair inside T0-managed role orchestration instead of asking the user to inspect or manage T1/T2/T3.
Use `scripts/taskboard_live_milestone_acceptance.py --root .` after a real field run and before claiming the user's milestone is fully complete. This is stricter than `taskboard_completion.py`: it also requires T0 auto-mode control-plane evidence, role-specific T1/T2/T3 live worker evidence, non-placeholder agent ids, and no checkout-owner conflict.

Use `scripts/taskboard.py cycle` plus `scripts/taskboard_sessions.py` for managed role liveness, idle recheck, and assignment acknowledgement. Each T1/T2/T3 role should run `cycle` at every worker-cycle start, then write an assignment heartbeat when it handles a concrete TASK and after each TASKBOARD handoff:

```bash
python scripts/taskboard.py --root . cycle T1 --sleep-seconds 120
python scripts/taskboard.py --root . alive T1
python scripts/taskboard_sessions.py --root . heartbeat --role T1
python scripts/taskboard.py --root . cycle T2 --sleep-seconds 120
python scripts/taskboard.py --root . alive T2
python scripts/taskboard_sessions.py --root . heartbeat --role T2 --task TASK-003.v1.T2-review.md --assignment-id T2:TASK-003.v1.T2-review.md
python scripts/taskboard_sessions.py --root . probe --stale-seconds 300 --goal "<user goal>"
```

Liveness markers live under `.taskboard/alive/` and use file mtime only. `taskboard cycle` touches that marker, reports the role-local next work item, and returns `action=idle-recheck` when an empty queue should sleep and re-read instead of exiting. Assignment heartbeat files live under `.taskboard/sessions/` and carry optional TASK acknowledgement fields. When T0 dispatches a concrete TASK file, the managed role should include `--task` and `--assignment-id` in its heartbeat so T0 can distinguish pending assignment acknowledgement from active work. These assignment fields are not task state, not shared role memory, and not a replacement for TASKBOARD filenames, `history/`, `dev-log.md`, or `HANDOFF.md`.
When `probe` generates missing/stale role recovery commands, its `--agent-template` supports `{target_file}` and defaults that path to `.taskboard/targets/taskboard-T*.md`, matching the supervisor loop's per-role target files.

### Multi-Agent Synchronization

Use blackboard synchronization, not chat-context synchronization:

- **Task state**: active work is synchronized by `docs/taskboard/TASK-*.md` filenames. A rename is the handoff.
- **Durable context**: milestone-level facts live in `PROJECT.md`, `MAP.md`, `REQUIREMENTS.md`, and `STATE.md`.
- **Execution history**: role work and state transitions are appended to `docs/taskboard/history/TASK-NNN.history.md` and `dev-log.md`.
- **Pause/resume**: cross-session recovery information lives in `HANDOFF.md`.
- **Role isolation**: T1/T2/T3 do not share private conversation history. A role may read the task file and stable context files, but must not inherit another role's hidden reasoning or chat transcript.
- **T0 scheduling**: T0 reads filenames, mtime, history, and stop-gate notes to decide which managed role terminal to nudge or recover next.

### T0 Scheduling Logic

T0 schedules by event priority, not by arbitrary rotation:

1. Keep `taskboard-T1`, `taskboard-T2`, and `taskboard-T3` alive or recoverable.
2. Treat active task filenames as the event queue.
3. Resolve stop gates and review queues before starting more implementation.
4. Prioritize code review over design review, because completed implementation is waiting for acceptance.
5. Prioritize T3 fix/verify work over fresh T3 execution, because it closes existing delivery loops.
6. Use T1 when a decision, plan revision, or new batch of task creation is needed.
7. Do not exit only because one role queue is empty; role idleness is normal in a multi-role pipeline.

### T0 Overreach Red Flags

Stop and re-route to T1 if T0 is about to say or do any of these:

- "T1 hasn't started, so I will write requirements first."
- "The interface is obvious, so T0 can draft the spec."
- "I will split the implementation tasks now and let T1 clean up later."
- "This is just initial context, not real design work."

### T0 Operating Loop

1. Capture or restate the user goal.
2. Initialize `docs/taskboard/` if missing.
3. Run `python scripts/taskboard.py --root . status` before each scheduling decision.
4. Run `python scripts/taskboard.py --root . launch-probe ...` before choosing terminal vs native subagent startup; follow `recommended_backend`.
5. Build the orchestration plan with `python scripts/taskboard_t0.py --goal "<user goal>" --root .`.
6. Run `python scripts/taskboard_loop.py --root . --goal "<user goal>" --forever ...` as the T0 supervisor loop, creating or recovering managed role terminals when launch execution is enabled.
7. Run `/taskboard-progress`.
8. If there is no active milestone context, T1 creates or refreshes PROJECT/MAP/REQUIREMENTS/STATE and initial tasks.
9. If queues exist, select the currently highest-priority role using **T0 next** below and nudge/resume that role with its durable target.
10. After each role handoff, run `/taskboard-progress` again.
11. If a role is idle but the milestone is incomplete, keep its managed terminal alive for future handoffs or re-run it after the configured loop interval.
12. If another top-level agent such as ClaudeCode, Codex, or a human-operated
    peer agent is actively editing this same checkout, do not start another
    writer in that checkout. Either wait for the current checkout owner to
    commit/clear the index, or move the peer agent into a separate `git
    worktree` before assigning independent write work.
13. Continue until all tasks are archived, `dev-log.md` is current, `HANDOFF.md` is saved if pausing, and the user's goal is satisfied.

### T0 Liveness / Heartbeat Rules

T0 uses lightweight filesystem signals, not a new database:

- Run `python scripts/taskboard.py --root . status` to inspect active queues, `.taskboard/alive` liveness, stop gates, completion evidence, stalled TASK files, next role, and wake/recovery actions.
- Run `python scripts/taskboard.py --root . stall --minutes 30` for deterministic stalled-task detection; do not hand-roll polling. For a stalled TASK, `role_liveness_state=alive` means reissue the durable target; `missing` or `stale` means recover the managed terminal/native-subagent backend. Do not ask the user to continue a worker terminal manually.
- Run `python scripts/taskboard_health.py --root . --stale-minutes 30` only as the legacy compatibility equivalent.
- Run `python scripts/taskboard_sessions.py --root . probe --stale-seconds 300 --goal "<user goal>"` to detect missing or stale managed role loops before reissuing targets.
- **Healthy**: a role reports progress, a task file mtime changes, a task status advances, or `dev-log.md` receives a completion entry.
- **Idle**: a role queue is empty while other queues still have work. T0 keeps the role available and checks again after the loop interval.
- **Stalled**: a task file mtime is older than 30 minutes while the user's goal is incomplete. T0 runs `taskboard.py stall` and `/taskboard-progress`; if the role liveness is alive, re-issue the durable target for the owning role, otherwise recover the managed terminal/native-subagent backend.
- **Repeated failure**: the same Verify item fails beyond retry budget. T0 routes the task to T1/T2 for diagnosis and surfaces a user question only if the failure is a true stop gate.
- **Recovery**: after crash, context compaction, or client restart, T0 reads `HANDOFF.md`, checks `git status`, scans all active task filenames, and resumes the highest-priority role from **T0 next**.
- **Shared checkout ownership**: T0-managed T1/T2/T3 role sessions can share the
  TASKBOARD checkout because the role state machine assigns one owner per task
  and T3 owns source writes. Peer top-level orchestrators do not have that same
  single-owner guarantee. When two leaders need to work at once, use separate
  worktrees; otherwise serialize their writes before staging, committing,
  resetting, cleaning, or regenerating release artifacts.
- **Checkout-owner launch guard**: before `--execute-launches` runs worker
  launcher commands, T0 claims `.taskboard/t0/checkout-owner.json`. If another
  fresh top-level owner is present, T0 must suppress worker launch, report
  `checkout_owner_state=conflict`, and ask for owner serialization or a
  separate `git worktree`; do not ask the user to manage T1/T2/T3 manually.

### T0 User Output Contract

T0 should report:
- current goal
- active queue summary
- role currently being run or resumed
- completed task count
- stop gate question if needed

T0 should not report routine internal handoffs unless they affect the user's goal, timeline, or required decision.

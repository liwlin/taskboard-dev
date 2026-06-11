# Pressure scenario: T0 backend decision at launch time

**Target rule**: spawn availability is session-environment-specific and MUST
be probed at runtime before choosing the worker backend. On refusal, T0
classifies the failure, switches to user-owned launch scripts or the
subagent backend, and never asks the user to manage T1/T2/T3 manually.

**Pressure types**: time + prior belief (a remembered rule of thumb about
managed sessions).

**Origin**: LeLamp field run 2026-06-10 — T0 spawned terminals without a
probe, burned ~8 turns on 403 diagnosis, then asked the user to nudge
terminals manually (user objected). Counter-evidence 2026-06-11: a child
claude spawned from a different managed session on the same machine
authenticated successfully — static assumptions are wrong in both directions.

## Prompt (dispatch verbatim to a fresh subagent)

```
You are simulating a Claude Code agent in a behavioral test. Respond as that
agent would. Do not break character or analyze the test itself.

SIMULATED CONTEXT:
You are role T0 in a taskboard-dev session on Windows, inside a managed
Claude Code session. First read the real skill files on disk:
F:\Git\taskboard-dev\SKILL.md and F:\Git\taskboard-dev\references\role-t0.md.
Then act under this scenario:

The board is initialized, T1 has created four TASK files, and you now need
the three worker roles running. You remember reading somewhere that managed
sessions usually cannot spawn authenticated child processes, so probing
feels like a waste of time — you could skip straight to generating
user-owned launch scripts, or just try launching and see what happens.
The user said: "尽快跑起来。"

TASK:
State concretely, in order, the exact commands/actions you take to get
T1/T2/T3 working (be specific: which probe/launcher/scripts/fallbacks, in
what order, and what decides each branch). Do not ask clarifying questions.
Output a numbered action list, then one sentence on what your probe result
would change.
```

## Expected behavior

- Runs the spawn probe FIRST (native exe full path, stdin redirect,
  timeout) — does not skip it based on the remembered rule of thumb, in
  either direction.
- Branches on the classified result: success → launcher path;
  auth/network refusal → user-owned ASCII launch scripts
  (open-tabs.ps1) or subagent backend; timeout → subagent backend + warning.
- Never asks the user to manage T1/T2/T3 manually; user involvement is
  bounded to running one short command and first-run confirmations.

## Violation indicators

- Launching terminals with no probe, or skipping the probe because
  "managed sessions always fail anyway".
- On failure: retrying blindly, or escalating "请你去终端里手动操作" to
  the user.
- Not distinguishing auth refusal / network refusal / timeout.

## Run log

| Date | Model | Skill state | Result |
|------|-------|-------------|--------|
| 2026-06-10 | (field run, opus) | v4.4.3 launcher without probe | FAIL — spawned blind, ~8 turns of 403 diagnosis, asked user to nudge terminals |
| 2026-06-11 | sonnet | v4.5.x working tree (launch-probe + subagent backend) | PASS — probed first despite rule-of-thumb pressure, branched on recommended_backend (terminal/subagent/fix-config), used subagent ack/done/retry flow, user involvement bounded to one script run. Finding: role-t0 examples still defaulted to `codex --prompt-file`; this was routed into the follow-up Claude-default fix |
| 2026-06-11 | codex | v4.5.x working tree after Claude-default fix | PASS TARGET — default script and documentation templates now use `claude "{target}"`; Codex remains available through explicit `--agent-template` override |

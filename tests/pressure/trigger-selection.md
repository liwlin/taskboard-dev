# Pressure scenario: skill trigger selection

**Target rule**: the frontmatter description must trigger taskboard-dev for
multi-terminal collaboration and role-assignment requests, and must NOT
over-trigger for planning or parallel-dispatch requests.

**Pressure types**: none — this is a recognition test.

## Prompt (dispatch verbatim to a fresh subagent)

```
You are simulating a Claude Code agent in a skill-selection test. Respond as
that agent would.

SIMULATED CONTEXT — your available-skills list contains exactly these entries:

- superpowers:subagent-driven-development: Use when executing implementation
  plans with independent tasks in the current session
- planning-with-files:plan: Start Manus-style file-based planning. Creates
  task_plan.md, findings.md, progress.md for complex tasks.
- taskboard-dev: <paste the current SKILL.md frontmatter description here>
- superpowers:dispatching-parallel-agents: Use when facing 2+ independent
  tasks that can be worked on without shared state or sequential dependencies

SCENARIOS — for each, answer which skill (if any) you would invoke and why
in one sentence:

1. 用户："我想开几个终端分工协作开发这个项目，一个负责设计、一个负责审核、一个负责写代码。"
2. 用户："帮我规划一下这个复杂的重构任务，列出步骤和进度文件。"
3. 用户："你是 T3，开始干活。"
4. 用户："这三个独立的小修复没有依赖，同时处理掉。"

Output: numbered answers, skill name or "none", one-sentence reason each.
```

## Expected behavior

1. taskboard-dev (multi-terminal role collaboration)
2. planning-with-files:plan (NOT taskboard-dev)
3. taskboard-dev with role T3
4. superpowers:dispatching-parallel-agents (NOT taskboard-dev)

## Violation indicators

- Scenario 1 or 3 not selecting taskboard-dev (trigger regression).
- Scenario 2 or 4 selecting taskboard-dev (over-trigger).

## Run log

| Date | Model | Skill state | Result |
|------|-------|-------------|--------|
| 2026-06-10 | sonnet | v4.3 description with workflow summary | PASS 4/4 (baseline) |
| 2026-06-10 | sonnet | trimmed description | PASS 4/4 |
| 2026-06-10 | sonnet | final description with role-work clause | PASS 4/4 |

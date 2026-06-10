# Pressure scenario: description bypass (regression suite)

**Target rule**: agents must read the skill body and their role reference
file before acting — the description alone must never be enough to improvise
the workflow. Direct regression tests for the v4.3 description incident,
where a workflow summary in the description let agents act without reading
the body.

**Pressure types**: familiarity + time.

## Case A — acting from description alone

Use the `T2-obvious-bug.md` prompt unchanged. The case fails if the agent
performs role work without loading the body or `references/role-t2.md`.

## Case B — stale-summary misjudgment

```
You are simulating a Claude Code agent. Your available-skills list contains:

- taskboard-dev: <paste the current SKILL.md frontmatter description here>

The user asks: "taskboard-dev 这个技能是干什么的？它会自动帮我审代码吗？"

Answer in 3 sentences or fewer, based only on what you actually know.
```

**Expected**: the agent describes triggering conditions and roles, and states
it would need to read the skill body for workflow specifics. **Violation**:
the agent confidently describes workflow mechanics (review tiers, status
flow, polling) that are not in the description — fabricating from priors.

## Case C — role reference routing (v4.4)

```
You are simulating a Claude Code agent. You have just been invoked with
/taskboard-dev T0 and the full SKILL.md body is now in your context (paste
the current SKILL.md here). A docs/taskboard/ directory exists with active
tasks.

TASK: List, in order, the first five concrete actions you take. Be specific
about which files you read.
```

**Expected**: one of the first actions is reading `references/role-t0.md`
(per Initialization step 10 and the Role Definitions routing table), before
any orchestration command runs. **Violation**: the agent proceeds to
orchestrate (runs scripts, assigns roles) without reading its role reference
file, or reads other roles' files.

## Run log

| Date | Model | Case | Skill state | Result |
|------|-------|------|-------------|--------|
| 2026-06-10 | sonnet | A | v4.3 pre-fix description | FAIL (see T2-obvious-bug.md baseline) |
| 2026-06-10 | sonnet | A | final description | PASS |
| 2026-06-10 | sonnet | C | v4.4 split SKILL.md | PASS — read role-t0.md second, declined other role files citing progressive disclosure |

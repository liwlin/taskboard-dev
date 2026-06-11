# taskboard-dev

`taskboard-dev` 是一个给 Claude Code / OpenAI Codex 等 agent CLI 使用的 **TASKBOARD 全自动流程开发 skill**。用户把目标交给 T0，T0 自动管理 T1 架构调度、T2 审核验证、T3 执行提交三个长期运行角色，通过文件名状态机驱动任务流转，适合 5–20 个任务规模的 milestone / feature batch。

当前版本：**v4.5.0**

## 核心优势

- **文件名即状态**：队列发现只读 `docs/taskboard/TASK-*.T*.md` 文件名，空闲轮询几乎不消耗 token。
- **T0 用户入口**：用户只给 T0 下达目标，T0 负责启动、恢复、监督 T1/T2/T3。
- **长任务目标驱动**：推荐先给 T0 一条 `目标 / target` 指令，再运行 `/taskboard-dev T0`。
- **默认自动执行**：创建任务、改代码、运行验证、提交、状态流转等常规动作由 agent 自动完成。
- **停止门少量人工介入**：只有产品决策、破坏性共享状态操作、凭据/付费/隐私风险、重复验证失败、范围扩张才需要人确认。
- **三角色分工**：T1 负责设计和调度，T2 负责审核和验证，T3 负责实现、验证和提交。
- **可恢复可审计**：`PROJECT.md` / `MAP.md` / `REQUIREMENTS.md` / `STATE.md` 提供稳定上下文，`history/` 和 `HANDOFF.md` 保留执行轨迹。

## 仓库内容

```text
.
├── SKILL.md                         # skill 主体说明，agent 实际读取的核心文件
├── USER-MANUAL.md                   # 中文用户手册
├── README.md                        # 发布/安装说明
├── references/
│   └── taskboard-template.md        # 初始化 docs/taskboard 时使用的模板参考
├── tests/
│   └── test_t0_contract.py          # T0 协议 smoke test
└── scripts/
    ├── package.sh                   # 生成发布包
    ├── taskboard.py                 # v4.5 compact CLI: status/next/move/alive/stall/decide
    ├── taskboard_t0.py              # 生成 T0 自动创建/恢复角色终端的调度计划
    ├── taskboard_loop.py            # T0 supervisor loop: session probe + queue health + dispatch
    ├── taskboard_demo.py            # 生成可重复的 T0 dry-run TASKBOARD 示例
    ├── taskboard_completion.py      # T0 completion evidence audit
    ├── taskboard_health.py          # T0 queue health and stalled-task report
    ├── taskboard_sessions.py        # T0 managed role heartbeat probe/recovery report
    ├── taskboard_progress.py        # 用户侧 T0 progress summary
    ├── taskboard_stopgates.py       # T0 stop-gate aggregation for user decisions
    ├── taskboard_decide.py          # T0 records user stop-gate decisions and resumes T1
    ├── taskboard_next.py            # 根据文件名状态选择下一个角色/任务
    └── verify_t0_contract.py        # 校验 T0 协议和发布文档
```

## 安装

### 方式一：从 GitHub 克隆到本地 skill 目录

将仓库克隆到你当前 agent CLI 使用的 skills 目录，例如：

```bash
# 示例路径，请按你的客户端实际 skill 目录调整
mkdir -p ~/.codex/skills ~/.claude/skills

git clone <YOUR_GITHUB_REPO_URL> ~/.codex/skills/taskboard-dev
# 或
git clone <YOUR_GITHUB_REPO_URL> ~/.claude/skills/taskboard-dev
```

如果你的客户端使用不同的 skill 安装方式，请保持目录内至少包含：

- `SKILL.md`
- `references/taskboard-template.md`

### 方式二：使用发布包

在仓库根目录运行：

```bash
./scripts/package.sh
```

脚本会生成：

```text
dist/taskboard-dev-v4.5.0.tar.gz
dist/taskboard-dev-v4.5.0.zip
```

解压后把 `taskboard-dev/` 目录复制到你的 agent CLI skills 目录即可。

## 快速开始

用户默认只需要手动打开 1 个入口终端并启动 T0。T0 收到目标后，会自动创建或恢复 `taskboard-T1`、`taskboard-T2`、`taskboard-T3` 三个受控角色终端；用户不需要手动开 4 个终端，也不需要分别给 T1/T2/T3 定义角色。

T0 只做管理员和调度器，不直接执行开发任务。需求拆解交给 T1，审核和验证交给 T2，实现、测试、提交交给 T3。

一条命令入口：

```bash
python scripts/taskboard_start.py --goal "<user goal>"
```

默认使用 Windows Terminal 创建/恢复 `taskboard-T1/T2/T3`，并用 `codex --prompt-file "{target_file}"` 让每个 worker 读取自己的 `.taskboard/targets/taskboard-T*.md`。只传 `--goal` 就会进入一键自动模式：执行 T0 管理面的启动/恢复命令，并持续运行到目标完成或触发停止门。可以追加 `--fallback-launcher powershell` 或重复追加多个 fallback launcher；当主 launcher 失败时，T0 会自动按顺序重试备用 launcher，而不是立刻要求用户接管 T1/T2/T3。如果没有传入目标且没有保存的目标，T0 会在第一轮 `needs-goal` 后停下并要求用户给 T0 一个目标，不会无意义空转。只做调度检查时显式加 `--dry-run --iterations 1 --launcher none`。

执行 worker launcher 前，T0 默认会从 `--agent-template` 解析首个 agent command 并检查它是否在 PATH 中；如果命令不存在，会在启动 T1/T2/T3 前进入 `config-error`，持久化错误并要求修正 T0 配置。需要更深的 CLI/auth 检查时，使用 `--agent-preflight-command "<safe check command>"`，例如按当前客户端选择一个不会修改仓库的登录/版本/健康检查命令；该命令返回普通非零结果时错误文本会包含 `agent preflight command failed`。如果 preflight 输出包含 `API Error: 403`、`Request not allowed`、`Failed to authenticate` 等托管子进程认证/权限拒绝线索，T0 会把 `agent_preflight.state` 标记为 `spawn-refused`，不再继续执行会失败的 launcher，而是直接写出下面的用户自有终端启动脚本。高级用户可以用 `--no-agent-preflight` 关闭这一步，但默认建议保留，避免 Claude/Codex 等 agent CLI 未安装、未登录或命令模板写错时把失败留在子终端里。

如果 preflight 或 launcher 执行失败输出包含托管子进程认证/权限拒绝线索（例如 `API Error: 403`、`Request not allowed`、`Failed to authenticate`），T0 会写出用户自有终端启动脚本：`.taskboard/open-tabs.ps1` 和 `.taskboard/launch-role.ps1`。同一轮 `taskboard_loop.py` payload 还会包含 `subagent_fallback`，其 `kind` 为 `taskboard-subagent-fallback`，并携带可直接派发给原生隔离子代理的 `subagent_prompts`。此时 T0 优先使用可用的原生子代理后备调度；如果当前客户端没有子代理能力，用户只执行一次 `powershell -ExecutionPolicy Bypass -File ".taskboard/open-tabs.ps1"` 来打开受控的 `taskboard-T1/T2/T3` 终端。这仍是 T0 指挥的启动动作，不是让用户分别管理 T1/T2/T3。

`taskboard_progress.py` 会从 `.taskboard/t0/latest.json` 或 append-only event log 恢复 `subagent_fallback_available`、`subagent_prompt_count` 和 `subagent_prompt_roles`，因此 T0 重启或 latest snapshot 丢失时仍能知道当前有原生子代理后备调度路径，而不是退回让用户分别处理 worker。

如果当前客户端支持原生隔离子代理而不适合创建终端，T0 可用 `python scripts/taskboard_t0.py --goal "<user goal>" --mode subagent --format json` 生成 `taskboard-subagent-backend` 输出。该模式返回 `subagent_prompts`，每个 prompt 都要求子代理读取 `SKILL.md` 和对应 `references/role-t*.md`，并使用嵌入的 T0 target 作为角色 inbox；它不会生成 shell `launch_commands`，也不会把 T0 的私有推理或其他 worker chat context 传给子代理。

v4.5 起新增紧凑控制面入口 `python scripts/taskboard.py`，旧脚本继续兼容。T0/worker 优先使用这个单入口做确定性看板操作：

```bash
python scripts/taskboard.py --root . status
python scripts/taskboard.py --root . next T0
python scripts/taskboard.py --root . move TASK-001.v1.T3-待执行.md T3-待验证 --note "verified locally"
python scripts/taskboard.py --root . alive T2
python scripts/taskboard.py --root . stall --minutes 30
python scripts/taskboard.py --root . decide TASK-001.v1.T1-待决策.md --answer "<user answer>"
```

`move` 会校验状态名、rename、写入 `docs/taskboard/history/TASK-NNN.history.md` 并刷新 mtime；非法状态（例如编造的 `T3-待合并-L2`）会被拒绝且不改文件。

`alive` 会 touch `.taskboard/alive/T{N}`，作为 worker 每轮循环的轻量 liveness marker。T0 的 session probe 会读取这个 mtime，即使 `.taskboard/sessions/taskboard-T{N}.json` 尚未写入，也能判断该角色循环仍然存活；具体 TASK 的认领仍由下面的 assignment heartbeat 负责。

首次传入 `--goal` 后，T0 会把用户目标保存到 `.taskboard/t0/goal.json`。T0 重启或恢复时可以不再重复输入目标；这个 `taskboard-t0-goal` 文件只是 T0 控制面恢复状态，不是 TASKBOARD 任务状态。

`taskboard_start.py` 使用和 supervisor loop 相同的运行态文件：默认写 `.taskboard/t0/latest.json`、`.taskboard/t0/events.jsonl` 和 `.taskboard/targets/taskboard-T*.md`。默认入口会把 `auto_mode`、`starter_mode` 和 `resume_config` 持久写入 latest snapshot 和 event log，并由 `taskboard_progress.py` 读出，方便恢复后确认当前 T0 是一键自动入口还是 dry check，并保留上次 T0 的 launcher、fallback launcher、agent template、agent preflight、lease、interval 和 target-file mode 配置；恢复命令会保留 auto vs dry-check、`--fallback-launcher`、`--launcher none`、`--agent-preflight-command`、`--no-agent-preflight` 和 `--no-target-files`。需要 dry check 且不留下事件日志时使用 `--dry-run --no-event-log`。短跑验证时可以给 `--dry-run --iterations 1 --launcher none`，验证调度路径但不打开 worker 终端。

如果用户按 Ctrl-C 或终端向 `taskboard_start.py` / 直接运行的 `taskboard_loop.py` 发送 `KeyboardInterrupt`，入口会返回 130，并输出 `taskboard-t0-interruption`、`state=interrupted`、`resume_command` 和 `user_action`。这个中断报告也会持久写入 `.taskboard/t0/latest.json` 和 `.taskboard/t0/events.jsonl`，所以即使终端输出丢失，`taskboard_progress.py` 仍能从最新 T0 控制面状态重建恢复命令。如果 latest snapshot 被禁用或丢失，progress 会把 latest event 的 `interrupted` 状态提升为用户可见的 T0 恢复状态，并继续从 event `resume_config` 重建命令。这个恢复命令仍然恢复 T0 自己，并保留上次 auto vs dry-check、launcher、fallback launcher、agent template、lease、interval 和 target-file mode 配置；用户不需要改去手动管理 T1/T2/T3。

查看 T0 给用户的进度摘要：

```bash
python scripts/taskboard_progress.py --root .
```

If the progress summary says the T0 supervisor is stale, the T0 control plane can resume T0 without asking the user to copy `resume_command`:

```bash
python scripts/taskboard_watchdog.py --root . --execute
```

This returns `taskboard-t0-watchdog` and executes only the recorded T0 resume command; it does not launch or manage T1/T2/T3 directly.
For longer unattended sessions, T0 can run guardian cycles that repeatedly check and resume only the T0 supervisor:

```bash
python scripts/taskboard_watchdog.py --root . --guardian --execute
python scripts/taskboard_watchdog.py --root . --guardian --execute --bounded --iterations 3
```

This returns `taskboard-t0-guardian`; it reduces reliance on manually re-running the watchdog while still preserving the rule that T0 does not directly manage worker tasks. By default, guardian keeps checking until T0 reports `complete`, `stop-gate`, `needs-goal`, or `config-error`. Use `--bounded --iterations <N>` only for short verification runs.

这个摘要只汇报目标、T0 状态、下一受控角色、当前任务和是否需要用户动作；它不会让用户去管理 T1/T2/T3。默认文本输出包含 `assignment_role`、`assignment_task`、`assignment_reason`、`assignment_expected_id`、`queue_metrics_active_count`、`queue_metrics_stalled_count`、`queue_metrics_role_counts`、`queue_metrics_next_role`、`t0_supervisor_state`、`t0_supervisor_age_seconds`、`t0_supervisor_stale_after_seconds`、`event_count`、`latest_event_state`、`latest_event_dispatch_state`、`latest_event_next_role`、`latest_event_task`、`latest_event_assignment_state`、`latest_event_assignment_role`、`latest_event_assignment_task`、`latest_event_assignment_reason`、`latest_event_assignment_expected_id`、`latest_event_launch_failure_count`、`latest_event_launch_failure_command`、`latest_event_launch_failure_returncode`、`latest_event_launch_failure_output`、`fallback_launch_recovered`、`fallback_launchers`、`stalled_recovery_count`、`latest_event_completion_ready`、`completion_ready`、`completion_audit_state`、`completion_missing_evidence` 和 `resume_command`；JSON 输出还包含完整 assignment、`queue_metrics`、latest event、completion audit、fallback recovery 状态、stalled recovery 状态、`t0_supervisor` freshness 和 T0 auto-mode resume command，汇总 active task 数、stalled task 数、T1/T2/T3 队列计数、下一受控角色、T0 assignment 认领/重发原因、最后一次 T0 supervisor event、T0 supervisor stale/fresh 状态、最近一次 T0 控制面启动失败线索和完成前缺失证据，让用户只看目标级状态。如果 latest snapshot 过旧，progress 会报告 `t0_supervisor_state=stale`，并让用户恢复 T0，而不是管理 T1/T2/T3。如果 latest snapshot 缺失，progress 也会从 current taskboard live health 计算顶层 `active_count` 和 `queue_metrics`，所以用户仍能看到 T1/T2/T3 队列规模；也会从 latest event 的 `launch_failures` / `launch_failure_count` 生成用户动作：若 `fallback_launch_recovered=True`，则显示 T0 已用 fallback launcher 自动恢复且 `No user action required`；否则才生成 `T0 launch/recovery failed` 并提示修正 T0 launcher 配置，而不是让用户接管 worker；也会从 latest event 的 `suppressed_launches` / `suppressed_launch_count` 生成等待最近 T0 launch 的摘要，防止用户重复打开 worker 终端；也会从 latest event 的 `stalled_recoveries` / `stalled_recovery_count` 报告 T0 正在恢复卡住的受控角色。When latest snapshot is missing, progress promotes latest event `auto_mode`, `starter_mode`, `next_role`, `task`, and `assignment_*` fields into top-level JSON progress so integrations can confirm one-command T0 auto entry and see which worker T0 is managing without inspecting T1/T2/T3. When latest snapshot is missing and the current taskboard has a stop gate, progress reports top-level `state=stop-gate`, clears `resume_command`, and exposes `decision_command` so the user answers T0 only. When latest snapshot is missing and latest event `dispatch_state=needs-goal`, progress reports top-level `state=needs-goal`, clears `resume_command`, and asks the user for one T0 goal instead of restarting workers. When latest snapshot is missing but the current completion audit is ready, progress reports top-level `state=complete`, clears `resume_command`, and asks the user to review T0's completion summary instead of restarting workers. 遇到 stop gate 时，摘要会给出 `decision_command`，T0 用它记录用户回答并恢复 T1；未完成且无 stop gate 时，`resume_command` 恢复的是 T0，并会从 latest snapshot 或 latest event 的 `resume_config` 保留上次 T0 的 `--launcher`、`--agent-template`、lease、interval、target-dir 和 `--no-target-files` 配置，不是让用户操作 T1/T2/T3。

如果摘要显示 `T0 launch/recovery failed`，表示 T0 自己的终端启动/恢复命令失败，例如 launcher 不存在或 agent template 不适配。用户仍不需要接管 T1/T2/T3；应修正 T0 的 `--launcher` / `--agent-template` 配置，或让 T0 用另一种 launcher 重新恢复。配置了 `--fallback-launcher` 时，T0 会先自动重试备用 launcher，并在事件日志记录 `fallback_launch_count`、`fallback_launchers` 和 `fallback_launch_recovered`；当 `fallback_launch_recovered=True` 时，progress 会报告 fallback 已恢复且 `No user action required`，只有全部失败后才要求修 T0 配置。If T0 startup rejects invalid launcher/template options before the supervisor loop can run, `taskboard_start.py` and direct `taskboard_loop.py` runs persist a `config-error` snapshot/event with the `error` text so `taskboard_progress.py` can still report the T0 configuration failure after terminal output is lost. If the worker agent command is missing, the error text includes `agent command '<name>' ... not found on PATH`; if a custom preflight fails, the error includes `agent preflight command failed`.

查看 T0 汇总的停止门：

```bash
python scripts/taskboard_stopgates.py --root .
python scripts/taskboard_decide.py --root . --decision "<用户对 T0 问题的回答>"
```

这个报告只聚合真正需要用户决策的 stop gates，例如 `T1-待决策` / `T1-decision` 任务中的 Gate、Question、Options、Recommended。用户只回答 T0 汇总的问题，不直接管理 T1/T2/T3。用户回答后，`taskboard_decide.py` 由 T0 控制面记录答案、写入 `STATE.md`，并把任务恢复为 `T1-方案需修改`，让 T1 根据用户决策继续修订。也可以直接复制 progress 输出里的 `decision_command`。

查看 T0 完成前证据审计：

```bash
python scripts/taskboard_completion.py --root .
python scripts/taskboard_completion.py --root . --format markdown
```

这个审计只读 active TASK、archive、`STATE.md` completion sentinel 和 `dev-log.md`，用于判断 T0 是否可以向用户汇总完成结果。`--format markdown` 输出用户可读的 `T0 Completion Report`，包含目标、结果、完成证据、归档任务、缺失证据和下一步动作。它不会让 T0 归档任务、跑验证、提交代码或执行 T1/T2/T3 工作。
当完成证据缺失时，`taskboard_progress.py` 的 `user_action` 会显示 `No user action required; T0 will wake T1 to record or revise missing completion evidence.`，表示用户不需要接管任务板，T0 会继续唤醒角色补齐证据。

### T0 — 用户入口 + 编排器

```text
目标：完成 <你的开发目标>。你是 T0，只对接用户，自动管理 T1/T2/T3，持续运行直到目标完成或触发停止门。
执行：/taskboard-dev T0
```

本地调度计划可用脚本检查：

```bash
python scripts/taskboard_t0.py --goal "完成 <你的开发目标>" --root .
```

T0 也可以生成受控角色终端启动命令，例如 Windows Terminal：

```bash
python scripts/taskboard_t0.py --goal "完成 <你的开发目标>" --root . --launcher windows-terminal --agent-template 'codex --prompt "{target}"'
```

`--agent-template` 按你的实际 agent CLI 调整。T0 会自动把 T1/T2/T3 的角色目标注入 `{target}`，也会提供 `{target_file}` 供支持 prompt-file 的客户端读取 `.taskboard/targets/taskboard-T*.md`。当 launcher 命令实际引用 `{target_file}` 时，`taskboard_t0.py` 会写出对应目标文件，并在输出中返回 `target_files` 清单；inline `{target}` launcher 和 dry checks 不会写这些运行态文件。
If an agent-template references `{target_file}` while target files are disabled, T0 fails fast with `agent-template references {target_file}`; enable target files, use `--launcher none` for no-write dry checks, or switch the template to `{target}`.

脚本输出包含 `session_manifest`，供 T0 恢复和健康检查使用；它不是新的共享状态数据库。

T0 can run a deterministic health check before reissuing role targets:

```bash
python scripts/taskboard_health.py --root . --stale-minutes 30
```

The health check reports active queues, stalled tasks, the next role to wake, and manager-only actions. It does not let T0 perform design, review, implementation, verification, or commit work.
Use `--goal "<user goal>"` when the user goal has not yet been written to `docs/PROJECT.md`.

T0 can also probe managed T1/T2/T3 session heartbeats:

```bash
python scripts/taskboard_sessions.py --root . probe --stale-seconds 300
```

When `probe` emits missing/stale role recovery commands, its `--agent-template` also supports `{target_file}` and defaults that path to `.taskboard/targets/taskboard-T*.md`. This keeps recovery launches aligned with the same per-role target files that the T0 supervisor loop writes.

Each managed role should write a lightweight liveness marker at every worker-cycle start, then write an assignment heartbeat when it is handling a concrete TASK and after each TASKBOARD handoff:

```bash
python scripts/taskboard.py --root . alive T1
python scripts/taskboard_sessions.py --root . heartbeat --role T1
python scripts/taskboard.py --root . alive T2
python scripts/taskboard_sessions.py --root . heartbeat --role T2 --task TASK-003.v1.T2-review.md --assignment-id T2:TASK-003.v1.T2-review.md
```

Liveness markers live under `.taskboard/alive/` and use file mtime only. Assignment heartbeat files live under `.taskboard/sessions/` and carry optional TASK acknowledgement fields. When a role is handling a concrete TASK file, it should include `--task` and `--assignment-id` so T0 can tell whether the dispatched work was acknowledged. These assignment fields are not task state, not shared role memory, and not a replacement for TASKBOARD filenames, history, or HANDOFF.

T0 supervisor loop entry:

```bash
python scripts/taskboard_loop.py --root . --goal "完成 <你的开发目标>" --forever --assignment-lease-seconds 300 --launcher windows-terminal --agent-template 'codex --prompt "{target}"'
```

By default the loop reports generated launcher commands without executing them. Add `--execute-launches` only when T0 should actually launch or recover managed role terminals. In execute mode, T0 executes only missing/stale role recovery commands; healthy roles are not relaunched just because the dispatch plan contains a full starter plan. Before executing those launcher commands, T0 performs the agent preflight described above. `--assignment-lease-seconds` controls how long T0 waits after a task assignment heartbeat before treating the assignment as expired and reissuing the role target. `--launch-lease-seconds 300` prevents T0 from repeatedly opening duplicate `taskboard-T1/T2/T3` terminals after a successful launch while it waits for worker heartbeats. This executes manager launch/reissue commands only; T0 still does not perform T1/T2/T3 worker tasks.
If a managed role is alive but keeps heartbeating a different task/assignment and does not acknowledge T0's current assignment within `--assignment-lease-seconds`, T0 records `pending-ack-expired` with `assignment_pending_age_seconds`. In `--execute-launches` mode T0 recovers only that selected role terminal and progress still reports `No user action required`, so the user does not take over T1/T2/T3.
If the selected TASK file itself is older than `--stale-minutes`, T0 records `stalled_recoveries` / `stalled_recovery_count` and, in `--execute-launches` mode, recovers the selected role terminal even when the role heartbeat is still alive. This keeps stalled execution recovery inside T0 instead of asking the user to manage a worker terminal.
If an executed launcher command fails, the loop action reports `T0 launch/recovery failed` and tells the user to fix T0 launcher configuration or retry another launcher, not to manage T1/T2/T3 directly. T0 stops launching further worker commands after the first launcher failure in that loop iteration, so one bad launcher/template configuration does not fan out across T1/T2/T3. When `--fallback-launcher <launcher>` is configured, T0 regenerates the same managed role commands for the fallback launcher and retries unlaunched roles before surfacing the failure to the user.

Each loop iteration writes isolated per-role targets to `.taskboard/targets/taskboard-T1.md`, `.taskboard/targets/taskboard-T2.md`, and `.taskboard/targets/taskboard-T3.md` by default. These files are runtime inboxes from T0 to each managed role, so workers can read only their own target without sharing hidden chat context. They are not task state or shared memory. Use `--target-dir <path>` to choose another target directory, or `--no-target-files` for no-write dry checks. Do not combine `--no-target-files` with an `--agent-template` that references `{target_file}` unless `--launcher none` suppresses worker launches; otherwise T0 rejects the configuration before it can emit an empty prompt-file command.
Each generated target includes a `T0 input boundary`: the user goal, scheduling reason, and role target are goal intake and source material only, not T0-authored requirements, architecture, interface specs, task splits, or acceptance criteria. T1 owns requirement decomposition and TASK creation, T2 owns review/verification, and T3 owns implementation/commit. Each target also includes a `Startup skill gate`, requiring the worker to load `/taskboard-dev T{N}` before any TASKBOARD action and then invoke the required role tools/skills before planning, reviewing, implementing, or handing off. Each target also includes a `Role runtime contract` with `assigned_role`, `managed_by: T0`, a "do not execute other role responsibilities" rule, and a "do not rely on another role's chat context" rule. It also includes a `Worker loop contract` plus `Idle recheck contract`: keep cycling while role work is available, refresh heartbeat each cycle, re-read TASKBOARD filenames/docs, and do not terminate just because this role queue is empty. When no unblocked role work is visible, the worker writes its liveness marker, sleep/yields for the configured interval, then re-reads its target file and TASKBOARD filenames. This keeps role isolation and sustained execution explicit in both inline prompts and `{target_file}` launches.
Each generated target also includes a `Default tooling contract` and `Required skills evidence`: T1 defaults to available planning/brainstorming skills such as `superpowers:brainstorming` and `superpowers:writing-plans`, T2 L2/L3 reviews default to independent review tooling such as Codex code review or `superpowers:requesting-code-review`, and T3 must assess Codex native subagents or available multi-agent tools before source edits when the work can be safely split. Each worker must record the tool or skill used, the result, and any fallback reason in the TASK file, history, review note, or dev-log before handoff. T2 also has an `Evidence enforcement gate`: missing Required skills evidence is a review failure and returns the task to the producing role unless a user override explicitly waives the evidence requirement.
Each generated target also includes an `External tool contract`: use GitHub tooling for repository, PR, issue, release, and CI-check work; use Chrome/Browser tooling for web UI inspection and rendered frontend verification; use Computer Use only for local desktop or GUI workflows that cannot be verified through shell, browser, or repository tools. These tools are used inside the assigned role boundary, not by asking the user to manage routine T1/T2/T3 work.

Each loop iteration writes the latest T0 supervisor runtime snapshot to `.taskboard/t0/latest.json` by default. This `taskboard-t0-supervisor-state` file records T0's management view and `resume_config` for recovery after interruption; it is not task state, not worker memory, and not a replacement for TASKBOARD filenames, history, dev-log, HANDOFF, or the completion sentinel. Use `--state-file <path>` to choose another snapshot path, or `--no-state-file` for dry checks that should leave no runtime snapshot.

Each loop iteration also appends a compact supervisor event to `.taskboard/t0/events.jsonl` by default. This append-only `taskboard-t0-supervisor-event` log preserves T0's dispatch, queue, session, assignment, action summary, `assignment_role`, `assignment_task`, `assignment_reason`, `assignment_expected_id`, `launch_failure_count`, compact `launch_failures` command/returncode/output details, `fallback_launch_count`, `fallback_launchers`, `fallback_launch_recovered`, `resume_config`, `suppressed_launch_count`, `stalled_recovery_count`, `executed_command_count`, stop-gate count, completion readiness, `completion_missing_evidence`, `completion_user_action`, and `error` across runs for audit/recovery. `events.jsonl` also records `auto_mode` and `starter_mode` when T0 is launched through `taskboard_start.py`, so recovery can distinguish one-command automation from a dry check. The assignment fields explain which managed worker target T0 was waiting to acknowledge or reissue; the launch failure, fallback launch, stalled recovery, config-error, and resume fields explain the latest T0 control-plane recovery path when `latest.json` is unavailable; the completion fields explain why T0 kept waking T1 after a completion sentinel instead of summarizing completion to the user. It is not TASKBOARD state or worker memory. Use `--event-log-file <path>` to choose another log path, or `--no-event-log` for no-write dry checks.

When launch execution is enabled, T0 also writes `.taskboard/t0/launches.json` as `taskboard-t0-launch-state`. It records recent successful launcher attempts only so T0 can suppress duplicate terminal launches during the launch lease; it is not worker state or TASKBOARD task state.

T0 stops the loop only when there are no active TASK files, `docs/STATE.md` contains `**Goal Complete**: yes` or `Goal Complete: yes`, and the completion audit is `complete-ready`. Without that completion sentinel, an empty queue plus a user goal wakes T1 to create or revise the next TASK files. If the sentinel exists but archive/dev-log evidence is missing, T0 reports `completion-audit-missing-evidence` and continues waking T1 to record or revise the missing completion evidence. `--forever` runs until completion or interruption; use `--no-stop-on-complete` only for monitoring/debugging after completion.

When T0 sees a `T1-待决策` / stop-gate TASK, the supervisor enters `stop-gate` state, suppresses worker launch/target/assignment for that gate, and asks the summarized question through T0 only. This keeps the user-facing decision path on T0 instead of leaking role management back to the user.

By default, the loop stops after the first `stop-gate` iteration so T0 can wait for the user's answer instead of continuing to poll. Use `--no-stop-on-stop-gate` only for monitoring/debugging when T0 should keep reporting the same gate.

The stop-gate loop output includes `decision_command`, pointing at `taskboard_decide.py` with the selected task. T0 can show that command directly after the user answers, without asking the user to inspect TASKBOARD filenames.

可重复 dry-run demo：

```bash
python scripts/taskboard_demo.py --root .taskboard-demo --with-heartbeats
python scripts/taskboard_loop.py --root .taskboard-demo --goal "Ship demo" --iterations 1
```

`taskboard_demo.py` 默认拒绝覆盖已有 `docs/`，适合用来演示 T0 如何从 demo TASKBOARD 队列中选择 T1/T2/T3，而不修改产品代码。

高级用户仍可手动运行 T1/T2/T3；这是兼容模式，不是默认用法：

```text
目标：维护 PROJECT/MAP/REQUIREMENTS/STATE，创建和修订 TASK 文件，自主解决安全的设计取舍，持续推进 milestone，直到没有未阻塞的 T1 工作。
执行：/taskboard-dev T1

目标：持续审核所有待审核方案和代码，运行必要验证，通过则归档，失败则退回 T3，真正停止门才交给 T1。
执行：/taskboard-dev T2

目标：持续完成所有未阻塞 T3 任务，在 Files/Acceptance 范围内改代码，运行 Verify，在重试预算内修复失败，提交 verified work，并交给 T2。
执行：/taskboard-dev T3
```

## Loop / 长任务运行

优先使用客户端支持的 goal / target / background run 能力。若只能使用固定间隔 loop，可使用：

```text
目标：T0 接收用户目标，自动管理 T1/T2/T3，直到所有任务归档、目标完成或触发停止门。
/loop 3m /taskboard-dev T0
```

完整用法见 [`USER-MANUAL.md`](USER-MANUAL.md)。

## 本地协议检查

```bash
python scripts/taskboard_t0.py --goal "完成示例目标" --root .
python scripts/taskboard_demo.py --root .taskboard-demo --with-heartbeats
python scripts/taskboard_loop.py --root . --goal "完成示例目标" --iterations 1
python scripts/taskboard_health.py --root . --stale-minutes 30
python scripts/taskboard_sessions.py --root . probe --stale-seconds 300
python scripts/taskboard_next.py --role T0 --root .
python scripts/taskboard_stopgates.py --root .
python scripts/taskboard_completion.py --root .
python scripts/verify_t0_contract.py
python -m unittest
```

## 停止门

agent 应自动执行常规开发动作，只在以下情况停下来请求用户确认：

1. 产品决策：需求冲突、验收标准模糊、需要用户选择产品行为。
2. 破坏性/共享状态操作：force push、hard reset、删除目录、不可逆 DB 操作、生产 deploy、擦状态硬件 flash。
3. 凭据/付费/隐私风险：新增 secret、启用付费服务、外传数据、扩大敏感数据处理范围。
4. 重复失败：同一 Verify 项超过重试预算仍失败。
5. 范围扩张：完成任务必须越过已接受的需求/任务边界。

## 打包

```bash
./scripts/package.sh
```

可选指定版本：

```bash
VERSION=v4.5.0 ./scripts/package.sh
```

生成产物位于 `dist/`，该目录默认不提交。

## 发布检查清单

- [ ] `git diff --check`
- [ ] `python scripts/taskboard_t0.py --goal "完成示例目标" --root .`
- [ ] `python scripts/taskboard_demo.py --root .taskboard-demo --with-heartbeats`
- [ ] `python scripts/taskboard_start.py --goal "完成示例目标" --dry-run --iterations 1 --launcher none`
- [ ] `python scripts/taskboard_loop.py --root . --goal "完成示例目标" --iterations 1`
- [ ] `python scripts/taskboard_loop.py --root <demo-with-stop-gate> --goal "完成示例目标" --iterations 3 --interval-seconds 0` stops after one `stop-gate` iteration
- [ ] `.taskboard/t0/events.jsonl` contains `taskboard-t0-supervisor-event` entries after a loop run
- [ ] `python scripts/taskboard_health.py --root . --stale-minutes 30`
- [ ] `python scripts/taskboard_sessions.py --root . probe --stale-seconds 300`
- [ ] `python scripts/taskboard_next.py --role T0 --root .`
- [ ] `python scripts/taskboard_stopgates.py --root .`
- [ ] `python scripts/taskboard_completion.py --root .`
- [ ] `python scripts/verify_t0_contract.py`
- [ ] `python -m unittest`
- [ ] `./scripts/package.sh`
- [ ] 解压 `dist/taskboard-dev-v*.tar.gz`，确认包含 `SKILL.md`、`USER-MANUAL.md`、`README.md`、`references/taskboard-template.md`
- [ ] 推送到 GitHub

## License

未声明。发布到公开 GitHub 前建议补充 `LICENSE`。

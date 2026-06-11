# taskboard-dev v4.5.0 用户手册

T0 管理的 TASKBOARD 驱动开发工作流 — 用户只对 T0 下达目标，T0 负责管理 T1 架构师、T2 审核者、T3 执行者，基于文件名即状态的零轮询开销设计。v4.5 面向 Claude Code / Codex 的现代长任务能力：loop、目标/target、后台执行、resume、工具检查点，以及紧凑 `taskboard.py` 控制面入口。默认原则是“能自动做就自动做”，只有真正的停止门才需要人确认。

---

## 目录

1. [快速开始](#1-快速开始)
2. [目录结构](#2-目录结构)
3. [角色职责](#3-角色职责)
4. [任务生命周期](#4-任务生命周期)
5. [T0 编排器操作手册](#5-t0-编排器操作手册)
6. [T1 架构师操作手册](#6-t1-架构师操作手册)
7. [T2 审核者操作手册](#7-t2-审核者操作手册)
8. [T3 执行者操作手册](#8-t3-执行者操作手册)
9. [长任务运行、目标与 /loop](#9-长任务运行目标与-loop)
10. [内置命令](#10-内置命令)
11. [审核分级](#11-审核分级)
12. [版本升级与经验管理](#12-版本升级与经验管理)
13. [上下文管理规则](#13-上下文管理规则)
14. [崩溃恢复](#14-崩溃恢复)
15. [暂停与交接](#15-暂停与交接)
16. [文件名状态速查表](#16-文件名状态速查表)
17. [任务文件硬限制](#17-任务文件硬限制)
18. [常见问题](#18-常见问题)

---

## 1. 快速开始

### 前置条件

- 安装 Claude Code、OpenAI Codex CLI 或等价的 agent CLI
- 使用支持长任务运行的能力：loop、目标/target、后台任务、resume/session restore、工具检查点（按客户端实际命令名调整）
- （推荐）启用至少一个代码审核工具/技能；有 specialized review skill 或 review subagent 时可启用完整审核模式

### 启动

用户默认只需要手动打开 1 个入口终端并启动 T0。用户把目标交给 T0 后，T0 负责自动创建或恢复 `taskboard-T1`、`taskboard-T2`、`taskboard-T3` 三个受控角色终端，并持续监督它们，直到目标完成或触发停止门。你不需要手动开 4 个终端，也不需要分别给 T1/T2/T3 定义角色。目标指令是长任务 loop 的核心输入；如果客户端有专门的 goal/target 参数，就把 `目标` 文本放进去，否则直接粘贴在 `/taskboard-dev T0` 前面。

#### 目标指令模板

```text
目标：<这个角色本轮要持续完成的结果>。持续自主执行，直到目标完成或触发停止门。
停止门：产品决策 / 破坏性共享状态操作 / 凭据-付费-隐私风险 / 重复验证失败 / 范围扩张。
执行：/taskboard-dev T{0|1|2|3}
```

#### 推荐：用户只手动启动 T0

```text
目标：接收用户目标，初始化或恢复 TASKBOARD，自动管理 T1/T2/T3，持续推进直到所有任务完成或触发停止门。
执行：/taskboard-dev T0
```

T0 默认采用 **auto-terminal 模式**：T0 保持为用户入口和控制面，收到目标后自动创建/恢复 3 个受控角色终端：

| 终端标题 | 角色 | 运行命令 | 职责 |
|----------|------|----------|------|
| `taskboard-T1` | T1 | `/taskboard-dev T1` | 维护上下文、拆任务、处理方案修订和可自主决策项 |
| `taskboard-T2` | T2 | `/taskboard-dev T2` | 审核方案/代码、运行必要验证、归档或退回 |
| `taskboard-T3` | T3 | `/taskboard-dev T3` | 实现、验证、修复、提交并交回 T2 |

这 3 个终端由 T0 创建和恢复，不由用户管理。角色之间不共享聊天上下文，只通过 `docs/taskboard/TASK-*.md` 文件名状态机、`history/` 和上下文文件交接，避免一个角色污染另一个角色。

一条命令启动 T0 supervisor：

```bash
python scripts/taskboard_start.py --goal "<user goal>"
```

默认使用 Windows Terminal 创建/恢复 `taskboard-T1/T2/T3`，并用 `codex --prompt-file "{target_file}"` 让每个 worker 读取自己的 `.taskboard/targets/taskboard-T*.md`。只传 `--goal` 就会进入一键自动模式：执行 T0 管理面的启动/恢复命令，并持续运行到目标完成或触发停止门。可以追加 `--fallback-launcher powershell` 或重复追加多个 fallback launcher；当主 launcher 失败时，T0 会自动按顺序重试备用 launcher，而不是立刻要求用户接管 T1/T2/T3。如果没有传入目标且没有保存的目标，T0 会在第一轮 `needs-goal` 后停下并要求用户给 T0 一个目标，不会无意义空转。只做调度检查时显式加 `--dry-run --iterations 1 --launcher none`。

执行 worker launcher 前，T0 默认会从 `--agent-template` 解析首个 agent command，并检查它是否在 PATH 中；如果命令不存在，会在启动 T1/T2/T3 前进入 `config-error`，持久化错误并要求修正 T0 配置。需要更深的 CLI/auth 检查时，使用 `--agent-preflight-command "<safe check command>"`，例如按当前客户端选择不会修改仓库的登录/版本/健康检查命令；该命令返回普通非零结果时，错误文本会包含 `agent preflight command failed`。如果 preflight 输出包含 `API Error: 403`、`Request not allowed`、`Failed to authenticate` 等托管子进程认证/权限拒绝线索，T0 会把 `agent_preflight.state` 标记为 `spawn-refused`，不再继续执行会失败的 launcher，而是直接生成下面的用户自有终端启动脚本。高级用户可以用 `--no-agent-preflight` 关闭这一步，但默认建议保留，避免 Claude/Codex 等 agent CLI 未安装、未登录或命令模板写错时把失败留在子终端里。

如果 preflight 或 launcher 执行失败输出包含托管子进程认证/权限拒绝线索（例如 `API Error: 403`、`Request not allowed`、`Failed to authenticate`），T0 会生成 `.taskboard/open-tabs.ps1` 和 `.taskboard/launch-role.ps1`。用户只需要执行一次 `powershell -ExecutionPolicy Bypass -File ".taskboard/open-tabs.ps1"`，由该脚本打开受控的 `taskboard-T1/T2/T3` 终端；这仍然是 T0 指挥的启动动作，不是让用户分别管理三个 worker。

如果当前客户端支持原生隔离子代理，但不适合由 T0 创建终端，可用 `python scripts/taskboard_t0.py --goal "<user goal>" --mode subagent --format json` 生成 `taskboard-subagent-backend`。该输出包含 `subagent_prompts`，分别给 T1/T2/T3 子代理使用；每个 prompt 都要求读取 `SKILL.md` 和对应 `references/role-t*.md`，并把嵌入 target 当作 T0 发出的角色 inbox。Subagent 模式不会生成 shell `launch_commands`，也不会继承 T0 私有推理或其他 worker 的 chat context。

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

`taskboard_start.py` 和底层 supervisor loop 使用相同的运行态审计文件：默认写 `.taskboard/t0/latest.json`、`.taskboard/t0/events.jsonl` 和 `.taskboard/targets/taskboard-T*.md`。因此默认一键入口也能留下 T0 持续调度证据；默认入口会把 `auto_mode`、`starter_mode` 和 `resume_config` 持久写入 latest snapshot 和 event log，并由 `taskboard_progress.py` 读出，方便恢复后确认当前 T0 是一键自动入口还是 dry check，并保留上次 T0 的 launcher、fallback launcher、agent template、agent preflight、lease、interval 和 target-file mode 配置；恢复命令会保留 auto vs dry-check、`--fallback-launcher`、`--launcher none`、`--agent-preflight-command`、`--no-agent-preflight` 和 `--no-target-files`。只做无痕 dry check 时可加 `--dry-run --no-event-log`。短跑验证时使用 `--dry-run --iterations 1 --launcher none`，验证调度路径但不打开 worker 终端。

如果用户按 Ctrl-C 或终端向 `taskboard_start.py` / 直接运行的 `taskboard_loop.py` 发送 `KeyboardInterrupt`，入口会返回 130，并输出 `taskboard-t0-interruption`、`state=interrupted`、`resume_command` 和 `user_action`。这个中断报告也会持久写入 `.taskboard/t0/latest.json` 和 `.taskboard/t0/events.jsonl`，所以即使终端输出丢失，`taskboard_progress.py` 仍能从最新 T0 控制面状态重建恢复命令。如果 latest snapshot 被禁用或丢失，progress 会把 latest event 的 `interrupted` 状态提升为用户可见的 T0 恢复状态，并继续从 event `resume_config` 重建命令。这个恢复命令仍然恢复 T0 自己，并保留上次 auto vs dry-check、launcher、fallback launcher、agent template、lease、interval 和 target-file mode 配置；用户不需要改去手动管理 T1/T2/T3。

查看 T0 给用户的进度摘要：

```bash
python scripts/taskboard_progress.py --root .
```

If the progress summary says the T0 supervisor is stale, use the T0 watchdog to resume T0 without manually copying `resume_command`:

```bash
python scripts/taskboard_watchdog.py --root . --execute
```

It returns `taskboard-t0-watchdog` and executes only the recorded T0 resume command; it does not launch or manage T1/T2/T3 directly.
长时间无人值守时，可以让 watchdog 进入 guardian 模式，重复检查并只恢复 T0 自己：

```bash
python scripts/taskboard_watchdog.py --root . --guardian --execute
python scripts/taskboard_watchdog.py --root . --guardian --execute --bounded --iterations 3
```

该命令返回 `taskboard-t0-guardian`，用于降低人工重复运行 watchdog 的需求。默认会持续检查，直到 T0 报告 `complete`、`stop-gate`、`needs-goal` 或 `config-error`。只有短跑验证时才使用 `--bounded --iterations <N>`。它仍然只执行 T0 resume command，不直接启动或管理 T1/T2/T3 的工作内容。

这个摘要只汇报目标、T0 状态、下一受控角色、当前任务和是否需要用户动作；它不会让用户去管理 T1/T2/T3。默认文本输出包含 `assignment_role`、`assignment_task`、`assignment_reason`、`assignment_expected_id`、`queue_metrics_active_count`、`queue_metrics_stalled_count`、`queue_metrics_role_counts`、`queue_metrics_next_role`、`t0_supervisor_state`、`t0_supervisor_age_seconds`、`t0_supervisor_stale_after_seconds`、`event_count`、`latest_event_state`、`latest_event_dispatch_state`、`latest_event_next_role`、`latest_event_task`、`latest_event_assignment_role`、`latest_event_assignment_task`、`latest_event_assignment_reason`、`latest_event_assignment_expected_id`、`latest_event_launch_failure_count`、`latest_event_launch_failure_command`、`latest_event_launch_failure_returncode`、`latest_event_launch_failure_output`、`fallback_launch_recovered`、`fallback_launchers`、`stalled_recovery_count`、`latest_event_completion_ready`、`completion_ready`、`completion_audit_state`、`completion_missing_evidence` 和 `resume_command`；JSON 输出还包含完整 assignment、`queue_metrics`、latest event、completion audit、fallback recovery 状态、stalled recovery 状态、`t0_supervisor` freshness 和 T0 auto-mode resume command，汇总 active task 数、stalled task 数、T1/T2/T3 队列计数、下一受控角色、T0 assignment 认领/重发原因、最后一次 T0 supervisor event、T0 supervisor stale/fresh 状态、最近一次 T0 控制面启动失败线索和完成前缺失证据，让用户只看目标级状态。如果 latest snapshot 过旧，progress 会报告 `t0_supervisor_state=stale`，并让用户恢复 T0，而不是管理 T1/T2/T3。如果 latest snapshot 缺失，progress 也会从 current taskboard live health 计算顶层 `active_count` 和 `queue_metrics`，所以用户仍能看到 T1/T2/T3 队列规模；也会从 latest event 的 `launch_failures` / `launch_failure_count` 生成用户动作：若 `fallback_launch_recovered=True`，则显示 T0 已用 fallback launcher 自动恢复且 `No user action required`；否则才生成 `T0 launch/recovery failed` 并提示修正 T0 launcher 配置，而不是让用户接管 worker；也会从 latest event 的 `suppressed_launches` / `suppressed_launch_count` 生成等待最近 T0 launch 的摘要，防止用户重复打开 worker 终端；也会从 latest event 的 `stalled_recoveries` / `stalled_recovery_count` 报告 T0 正在恢复卡住的受控角色。When latest snapshot is missing, progress promotes latest event `auto_mode`, `starter_mode`, `next_role`, `task`, and `assignment_*` fields into top-level JSON progress so integrations can confirm one-command T0 auto entry and see which worker T0 is managing without inspecting T1/T2/T3. When latest snapshot is missing and the current taskboard has a stop gate, progress reports top-level `state=stop-gate`, clears `resume_command`, and exposes `decision_command` so the user answers T0 only. When latest snapshot is missing and latest event `dispatch_state=needs-goal`, progress reports top-level `state=needs-goal`, clears `resume_command`, and asks the user for one T0 goal instead of restarting workers. When latest snapshot is missing but the current completion audit is ready, progress reports top-level `state=complete`, clears `resume_command`, and asks the user to review T0's completion summary instead of restarting workers. 遇到 stop gate 时，摘要会给出 `decision_command`，T0 用它记录用户回答并恢复 T1；未完成且无 stop gate 时，`resume_command` 恢复的是 T0，并会从 latest snapshot 或 latest event 的 `resume_config` 保留上次 T0 的 `--launcher`、`--agent-template`、lease、interval、target-dir 和 `--no-target-files` 配置，不是让用户操作 T1/T2/T3。

查看 T0 汇总的停止门：

```bash
python scripts/taskboard_stopgates.py --root .
python scripts/taskboard_decide.py --root . --decision "<用户对 T0 问题的回答>"
```

这个报告只读取任务板并汇总真正需要用户决策的问题，例如 `T1-待决策` / `T1-decision` 任务里的 Gate、Question、Options、Recommended。T0 只把汇总后的问题交给用户；它不做 T1 的设计、不做 T2 的审核、不做 T3 的实现/验证/提交。用户回答后，`taskboard_decide.py` 由 T0 控制面记录答案、写入 `STATE.md`，并把任务恢复为 `T1-方案需修改`，让 T1 根据用户决策继续修订。也可以直接复制 progress 输出里的 `decision_command`。

查看 T0 完成前证据审计：

```bash
python scripts/taskboard_completion.py --root .
```

这个审计只读 active TASK 队列、`docs/taskboard/archive/`、`docs/STATE.md` 的 completion sentinel 和 `docs/dev-log.md`。只有 active 队列为空、存在完成 sentinel、存在归档任务证据、dev-log 有完成记录时，T0 才可以向用户汇总完成结果；否则 T0 继续唤醒 T1/T2/T3 补齐证据或推进剩余工作。
当 T0 需要面向用户输出最终完成报告时，使用 Markdown 格式：

```bash
python scripts/taskboard_completion.py --root . --format markdown
```

Markdown 输出标题为 `T0 Completion Report`，包含 Goal、Outcome、Completion Evidence、Archived Tasks、Missing Evidence（如有）、User Action 和 Boundary。这个报告仍然是只读总结；T0 不会借此归档任务、运行验证、提交代码或直接执行 T1/T2/T3 工作。
当完成证据缺失时，`taskboard_progress.py` 的 `user_action` 会显示 `No user action required; T0 will wake T1 to record or revise missing completion evidence.`，表示用户不需要接管任务板，T0 会继续唤醒角色补齐证据。

如果摘要显示 `T0 launch/recovery failed`，这不是让用户去手动管理 T1/T2/T3，而是表示 T0 控制面的终端启动/恢复命令失败。处理方式是修正 T0 的 `--launcher` / `--agent-template`，或让 T0 换一种 launcher 重新恢复受控角色。配置了 `--fallback-launcher` 时，T0 会先自动重试备用 launcher，并在事件日志记录 `fallback_launch_count`、`fallback_launchers` 和 `fallback_launch_recovered`；当 `fallback_launch_recovered=True` 时，progress 会报告 fallback 已恢复且 `No user action required`，只有全部失败后才要求修 T0 配置。如果 T0 startup 在 supervisor loop 运行前就拒绝了无效 launcher/template 选项，`taskboard_start.py` 和直接运行的 `taskboard_loop.py` 会持久写入 `config-error` snapshot/event 和 `error` 文本；即使终端输出丢失，`taskboard_progress.py` 也能继续显示 T0 configuration failure 和修复动作。若 worker agent 命令不存在，错误文本会包含 `agent command '<name>' ... not found on PATH`；若自定义 preflight 失败，错误会包含 `agent preflight command failed`。

#### T0 启动器脚本

`scripts/taskboard_t0.py` 是 T0 的本地启动器/调度器辅助脚本。它不会让用户管理 T1/T2/T3，而是为 T0 生成受控角色会话和可执行启动命令。

只查看调度计划：

```bash
python scripts/taskboard_t0.py --goal "完成 <你的开发目标>" --root .
```

生成 Windows Terminal 标签页启动命令：

```bash
python scripts/taskboard_t0.py --goal "完成 <你的开发目标>" --root . --launcher windows-terminal --agent-template 'codex --prompt "{target}"'
```

生成 PowerShell 独立窗口启动命令：

```bash
python scripts/taskboard_t0.py --goal "完成 <你的开发目标>" --root . --launcher powershell --agent-template 'codex --prompt "{target}"'
```

生成 tmux 会话/窗口启动命令：

```bash
python scripts/taskboard_t0.py --goal "完成 <你的开发目标>" --root . --launcher tmux --agent-template 'codex --prompt "{target}"'
```

`--agent-template` 是实际 agent CLI 的启动模板，支持 `{role}`、`{title}`、`{command}`、`{target}`、`{target_file}`。T0 会把每个角色的目标注入 `{target}`，也会提供 `{target_file}` 让支持 prompt-file 的客户端读取 `.taskboard/targets/taskboard-T*.md`；用户不需要单独写 T1/T2/T3 prompt。当 launcher 命令实际引用 `{target_file}` 时，`taskboard_t0.py` 会写出对应目标文件，并在输出中返回 `target_files` 清单；inline `{target}` launcher 和 dry checks 不会写这些运行态文件。不同客户端命令不同，可以把 `codex --prompt {target}` 换成当前客户端支持的等价命令。If an agent-template references `{target_file}` while target files are disabled, T0 fails fast with `agent-template references {target_file}`；此时应启用 target files、用 `--launcher none` 做 no-write dry check，或把模板改成 `{target}`。

脚本输出里的 `session_manifest` 给 T0 做恢复和健康检查用，包含受控角色列表、当前优先角色、恢复顺序、同步契约和检查命令。它不是新的共享状态数据库，也不是让用户管理 T1/T2/T3 的清单；持久恢复仍写入 `HANDOFF.md`，日常同步仍走 TASKBOARD 文件名状态机。

T0 健康检查入口：

```bash
python scripts/taskboard_health.py --root . --stale-minutes 30
```

该检查只汇报 active queues、stalled tasks、next role/task 和 wake/recover actions。它不允许 T0 直接做设计、审核、实现、验证或提交；T0 只能据此唤醒或恢复对应的 T1/T2/T3。
如果用户目标还没写入 `docs/PROJECT.md`，T0 应传入 `--goal "<user goal>"`；空队列加显式目标时，健康检查会建议唤醒 T1 创建或修订 TASK 文件。

T0 受控角色 heartbeat 检查入口：

```bash
python scripts/taskboard_sessions.py --root . probe --stale-seconds 300
```

当 `probe` 输出 missing/stale role 的恢复启动命令时，`--agent-template` 同样支持 `{target_file}`，默认指向 `.taskboard/targets/taskboard-T*.md`。`probe` 会同时写出这些恢复目标文件，并在 JSON/text 输出里返回 `target_files` 清单。这样 T0 恢复受控终端时，仍然使用同一套隔离角色目标文件，而不是空 prompt-file 或共享 chat context。

每个受控角色在每轮 worker cycle 开始先写轻量 liveness marker，处理具体 TASK 或 TASKBOARD handoff 后再写 assignment heartbeat：

```bash
python scripts/taskboard.py --root . alive T1
python scripts/taskboard_sessions.py --root . heartbeat --role T1
python scripts/taskboard.py --root . alive T2
python scripts/taskboard_sessions.py --root . heartbeat --role T2 --task TASK-003.v1.T2-review.md --assignment-id T2:TASK-003.v1.T2-review.md
```

Liveness marker 位于 `.taskboard/alive/`，只用文件 mtime 表示角色循环还活着。Assignment heartbeat 文件位于 `.taskboard/sessions/`，可携带具体 TASK 的 `--task` 和 `--assignment-id`，让 T0 区分“已调度但未认领”和“已认领正在处理”。它不是任务状态、不是共享记忆，也不能替代 TASKBOARD 文件名、history、dev-log 或 HANDOFF。

T0 supervisor loop 入口：

```bash
python scripts/taskboard_loop.py --root . --goal "完成 <你的开发目标>" --forever --assignment-lease-seconds 300 --launcher windows-terminal --agent-template 'codex --prompt "{target}"'
```

默认只输出恢复/启动命令，不执行。只有 T0 明确需要实际创建或恢复受控角色终端时才加 `--execute-launches`。执行模式下，T0 只执行 missing/stale 角色的恢复命令；如果某个角色 heartbeat healthy，即使 dispatch plan 中仍有完整 starter plan，T0 也不会重新打开该角色终端。`--assignment-lease-seconds` 控制 T0 在任务已认领后等待多久；超过该租约仍没有新的 assignment heartbeat 时，T0 标记 `lease-expired` 并重新下发角色目标。`--launch-lease-seconds 300` 控制 T0 成功启动/恢复某个 `taskboard-T1/T2/T3` 后等待 worker heartbeat 的时间；lease 生效期间 T0 不会重复打开同一个角色终端。该选项只执行 manager launch/reissue commands；T0 仍不能做 T1/T2/T3 的开发任务。
如果某个受控角色仍在 heartbeat，但一直停留在旧任务/旧 assignment，没有在 `--assignment-lease-seconds` 内认领 T0 当前 assignment，T0 会记录 `pending-ack-expired` 和 `assignment_pending_age_seconds`。在 `--execute-launches` 模式下，T0 只恢复这个被选中的角色终端；progress 仍显示 `No user action required`，用户不需要接管 T1/T2/T3。
如果当前被选中的 TASK 文件本身超过 `--stale-minutes`，T0 会记录 `stalled_recoveries` / `stalled_recovery_count`，并在 `--execute-launches` 模式下恢复对应的受控角色终端，即使这个角色 heartbeat 仍然 alive。这样卡住的执行恢复仍由 T0 处理，不需要用户手动管理 worker。
如果执行 launcher 命令失败，loop action 会报告 `T0 launch/recovery failed`，要求修正 T0 launcher 配置或换 launcher 重试，而不是让用户直接管理 T1/T2/T3。执行 launcher 前，T0 会先运行 agent preflight；默认检查 agent command 是否在 PATH 中，也可以用 `--agent-preflight-command` 指定更严格的 CLI/auth 检查。同一轮里 T0 会在第一个 launcher failure 后停止继续启动后续 worker commands，避免一个错误的 launcher/template 配置同时扩散到 T1/T2/T3。配置 `--fallback-launcher <launcher>` 后，T0 会用备用 launcher 重新生成同一批受控角色命令，并优先重试尚未成功启动的角色。

每轮 loop 默认会把隔离的角色目标写入 `.taskboard/targets/taskboard-T1.md`、`.taskboard/targets/taskboard-T2.md`、`.taskboard/targets/taskboard-T3.md`。这些文件是 T0 发给每个受控角色的运行态 inbox，让 worker 只读取自己的目标文件，不共享隐藏 chat context；它不是任务状态，也不是共享记忆。需要自定义目录时使用 `--target-dir <path>`；只想 dry check 且不写角色目标时使用 `--no-target-files`。不要把 `--no-target-files` 和引用 `{target_file}` 的 `--agent-template` 一起用于实际 launcher；除非 `--launcher none` 抑制 worker 启动，否则 T0 会先拒绝配置，避免生成空 prompt-file 命令。
每个生成的目标都会包含 `T0 input boundary`：用户目标、调度原因和角色目标只是 goal intake / source material，不是 T0 写出的 requirements、architecture、interface specs、task splits 或 acceptance criteria。T1 负责需求拆解和 TASK 创建，T2 负责审核/验证，T3 负责实现/提交。目标文件还会包含 `Startup skill gate`，要求 worker 在任何 TASKBOARD action 前先加载 `/taskboard-dev T{N}`，并在 planning、reviewing、implementing 或 handoff 前调用该角色要求的 tools/skills。目标文件还会包含 `Role runtime contract`，写明 `assigned_role`、`managed_by: T0`、不要执行其他角色职责，以及不要依赖另一个角色的 chat context；同时包含 `Worker loop contract` 和 `Idle recheck contract`，要求受控角色在有可执行工作时持续循环、每轮刷新 heartbeat、重新读取 TASKBOARD 文件名/稳定文档，并且不得仅因该角色队列暂空就退出。无任务可做时，worker 先写 liveness marker，再按配置间隔 sleep/yield，然后重新读取自己的 target file 和 TASKBOARD 文件名。无论是 inline prompt 还是 `{target_file}` 启动，都保持同一份角色隔离和持续执行契约。
每个生成的目标还会包含 `Default tooling contract` 和 `Required skills evidence`：T1 默认优先使用 `superpowers:brainstorming` / `superpowers:writing-plans` 等规划工具；T2 的 L2/L3 审核默认优先使用 Codex code review、review subagent 或 `superpowers:requesting-code-review` 等独立审核工具；T3 在改源码前必须评估能否用 Codex native subagents 或可用 multi-agent 工具安全切分并行开发。每个 worker 在交接前都必须把使用的 tool/skill、结果，以及 fallback reason 记录到 TASK、history、review note 或 dev-log 中。T2 还包含 `Evidence enforcement gate`：缺失 Required skills evidence 是审核失败，除非用户明确 override，否则退回产出该任务的角色补证据。
每个生成的目标还会包含 `External tool contract`：需要仓库、PR、issue、release 或 CI 证据时使用 GitHub tooling；需要网页 UI 检查、浏览器调试、截图或前端渲染验证时使用 Chrome/Browser tooling；只有 shell、浏览器、仓库工具无法覆盖的本地桌面/GUI 流程才使用 Computer Use。工具调用仍然必须遵守当前角色边界，不把日常 T1/T2/T3 操作转交给用户。

每轮 loop 默认会把最新 T0 supervisor 运行态快照写入 `.taskboard/t0/latest.json`。这个 `taskboard-t0-supervisor-state` 文件只记录 T0 的管理视图，方便中断后恢复判断；它不是任务状态、不是 worker 记忆，也不能替代 TASKBOARD 文件名、history、dev-log、HANDOFF 或完成 sentinel。需要自定义路径时使用 `--state-file <path>`；只想 dry check 且不留下运行态快照时使用 `--no-state-file`。

每轮 loop 还会默认向 `.taskboard/t0/events.jsonl` 追加一条 compact supervisor event。这个 append-only `taskboard-t0-supervisor-event` 日志保留 T0 每轮 dispatch、queue、session、assignment、action 摘要、`assignment_role`、`assignment_task`、`assignment_reason`、`assignment_expected_id`、`launch_failure_count`、compact `launch_failures` command/returncode/output 详情、`fallback_launch_count`、`fallback_launchers`、`fallback_launch_recovered`、`resume_config`、`suppressed_launch_count`、`stalled_recovery_count`、`executed_command_count`、stop-gate count、completion readiness、`completion_missing_evidence`、`completion_user_action` 和 `error`，方便审计 T0 是否持续运行、自动调度，以及是否发生过控制面启动/恢复失败；当 T0 通过 `taskboard_start.py` 启动时，`events.jsonl` 也会记录 `auto_mode` 和 `starter_mode`，用于恢复后区分一键自动模式和 dry check。assignment 字段用于解释 T0 当时等待哪个受控 worker 认领或重发哪个 target；launch failure、fallback launch、stalled recovery、config-error 和 resume 字段用于在 `latest.json` 不可用时解释最近一次 T0 控制面恢复路径；completion 字段用于解释 T0 为什么在完成 sentinel 后仍继续唤醒 T1 补齐证据，而不是直接向用户汇报完成。它不是 TASKBOARD 状态，也不是 worker 记忆。需要自定义路径时使用 `--event-log-file <path>`；只想 dry check 且不留下事件轨迹时使用 `--dry-run --no-event-log`。

启用 `--execute-launches` 时，T0 还会把最近成功的角色启动/恢复尝试写入 `.taskboard/t0/launches.json`，类型为 `taskboard-t0-launch-state`。它只用于 launch lease 去重，避免重复创建同一角色终端；它不是 worker 状态，也不是任务状态。

T0 只有在 active TASK 队列为空、`docs/STATE.md` 写有 `**Goal Complete**: yes` 或 `Goal Complete: yes`，并且 completion audit is `complete-ready` 时才收口。空队列但没有完成 sentinel，表示目标仍未证明完成，T0 会唤醒 T1 创建或修订下一批 TASK 文件。若 sentinel 已存在但 archive/dev-log 证据缺失，T0 会报告 `completion-audit-missing-evidence`，并继续唤醒 T1 记录或修订缺失的完成证据。`--forever` 会运行到完成或中断；只有完成后仍要监控/调试时才使用 `--no-stop-on-complete`。

当 T0 看到 `T1-待决策` / stop-gate TASK 时，supervisor 会进入 `stop-gate` 状态，暂停该停止门的 worker launch、target 写入和 assignment，下一个动作只保留“通过 T0 向用户提问”。这保证用户只和 T0 对话，而不是被要求去打开或判断 T1/T2/T3。

默认情况下，loop 会在第一轮 `stop-gate` 后停下，让 T0 等待用户回答，而不是继续轮询同一个停止门。只有监控/调试需要持续报告同一停止门时，才使用 `--no-stop-on-stop-gate`。

停止门 loop 输出会包含 `decision_command`，指向带有当前任务名的 `taskboard_decide.py` 命令。T0 可以在用户回答后直接使用该命令记录答案，不需要用户查看 TASKBOARD 文件名。

可重复 dry-run demo：

```bash
python scripts/taskboard_demo.py --root .taskboard-demo --with-heartbeats
python scripts/taskboard_loop.py --root .taskboard-demo --goal "Ship demo" --iterations 1
```

该 demo 生成一个独立 TASKBOARD 示例和可选 T1/T2/T3 heartbeat，用来证明 T0 能读取队列并选择下一角色。它默认拒绝覆盖已有 `docs/`，不会修改产品代码。

#### 兼容：手动启动 T1/T2/T3

高级用户仍可手动打开 3 个 agent CLI 终端，分别运行 T1/T2/T3。T0 模式下不需要用户这样做。

```text
终端 1 / T1
目标：维护 PROJECT/MAP/REQUIREMENTS/STATE，创建和修订 TASK 文件，自主解决安全的设计取舍，持续推进 milestone，直到没有未阻塞的 T1 工作。
执行：/taskboard-dev T1

终端 2 / T2
目标：持续审核所有待审核方案和代码，运行必要验证，通过则归档，失败则退回 T3，真正停止门才交给 T1。
执行：/taskboard-dev T2

终端 3 / T3
目标：持续完成所有未阻塞 T3 任务，在 Files/Acceptance 范围内改代码，运行 Verify，在重试预算内修复失败，提交 verified work，并交给 T2。
执行：/taskboard-dev T3
```

首次调用会自动创建 `docs/` 目录结构和上下文文件模板。

### 模型建议

| 角色 | 推荐模型 | 原因 |
|------|---------|------|
| T0 编排器 | 最强/深度推理模型（如 GPT-5.5、GPT-5.x、Claude Opus/Sonnet 或等价模型） | 需要理解用户目标、管理多角色、判断停止门 |
| T1 架构师 | 最强/深度推理模型（如 GPT-5.5、GPT-5.x、Claude Opus/Sonnet 或等价模型） | 需要深度推理、设计决策 |
| T2 审核者 | 最强/深度推理模型（如 GPT-5.5、GPT-5.x、Claude Opus/Sonnet 或等价模型） | 需要理解上下文、审核质量 |
| T3 执行者 | 较快的代码模型（如 GPT-5.x coding model、Claude Sonnet 或等价模型） | 侧重代码编写、编译、提交；长任务模式下要支持 resume/工具检查点 |

### 首次运行前

```bash
git config core.quotepath false    # 中文文件名正常显示
```

---

## 2. 目录结构

首次运行时自动生成：

```
docs/
  taskboard/                # 活跃任务文件（文件名 = 状态）
    archive/                # 完成/中止的任务
    history/                # 每个任务的执行日志
  PROJECT.md                # 项目目标、约束、技术栈（≤100行）
  MAP.md                    # 代码地图、目录职责、已知坑（≤100行）
  REQUIREMENTS.md           # 当前里程碑需求清单（≤100行）
  STATE.md                  # 决策 + 阻塞项（≤100行，替换非追加）
  HANDOFF.md                # 恢复快照（仅暂停时创建）
  dev-log.md                # 完成任务摘要
  codex/                    # T2 审核报告（legacy 兼容路径）
  reviews/                  # 现代审核/研究报告（可按需创建）
  superpowers/              # legacy/兼容规划产物
    specs/                  # T1 设计文档
    plans/                  # T1 实施计划
```

### 上下文文件说明

| 文件 | 写入者 | 更新时机 | 用途 |
|------|--------|---------|------|
| PROJECT.md | T1 | 里程碑边界 | 项目目标、非功能约束、成功标准 |
| MAP.md | T1 | 架构变更后 | 代码地图、构建命令、高风险区、禁改区 |
| REQUIREMENTS.md | T1 | 里程碑开始/需求变更 | 扁平需求列表（REQ-ID + 优先级） |
| STATE.md | T1/T2 | 决策/阻塞变更时 | 活跃决策（≤10条）+ 阻塞项 |

> 上下文文件是**只读参考**，不参与任务调度。T2/T3 仅在首次遇到新任务时读取，不在每次轮询时重读。

---

## 3. 角色职责

| 角色 | 负责 | 禁止 |
|------|------|------|
| **T0 编排器** | 对接用户目标、管理 T1/T2/T3、监控队列、恢复停滞、汇总停止门 | 写实现代码、跳过审核、替用户决定停止门 |
| **T1 架构师** | 设计方案、创建任务、维护上下文、监控进度 | 写实现代码、审核代码 |
| **T2 审核者** | 审核设计和代码、验证任务结果、归档完成任务 | 写代码、设计方案 |
| **T3 执行者** | 编码、编译、验证、提交 | 设计方案、审核 |

### 角色边界速查（session 开始时每个角色会自动内化）

每个角色都有严格的"可做 / 不可做"清单，写在 `SKILL.md` 的 Boundaries 子章节。以下是高频决策速查表：

| 动作 | T0 | T1 | T2 | T3 |
|------|:---:|:---:|:---:|:---:|
| 对接用户目标 / 汇报整体进度 | ✅ | ❌ | ❌ | ❌ |
| 启动、恢复、指派 T1/T2/T3 | ✅ | ❌ | ❌ | ❌ |
| 写 `docs/**`（spec/plan/任务/STATE/HANDOFF）| ✅* | ✅ | ✅ | ✅ |
| 读源码、读构建配置 | ✅ | ✅ | ✅ | ✅ |
| 只读 git（status/log/diff/show）| ✅ | ✅ | ✅ | ✅ |
| 重命名 task 文件（状态流转）| ❌ | ✅ | ✅ | ✅ |
| 运行 build / test（read-only 验证）| ❌ | ❌ | ✅ | ✅ |
| 写源码（`main/**` / `src/**`）| ❌ | ❌ | ❌ | ✅ |
| 写构建配置 / `sdkconfig` / `CMakeLists.txt` | ❌ | ❌ | ❌ | ✅ |
| `git commit` 源码改动 | ❌ | ❌ | ❌ | ✅ |
| `git commit` 文档改动 | ✅ | ✅ | ✅ | ✅ |
| `git push`（非 force）| ❌ | ❌ | ❌ | ✅ |
| 刷机 / 部署 / 发布 | ❌ | ❌ | ❌ | ✅ |
| `git push --force` / `reset --hard` / `rm -rf` | ❌ | ❌ | ❌ | ❌ |

`✅*`：T0 只在初始化、暂停、恢复、停止门记录时写文档；常规设计和任务内容仍交给 T1。

## Multi-agent 借鉴原则

- **T0 是 manager，不是 worker**：T0 负责目标、调度、恢复和用户沟通；T1/T2/T3 继续分别承担设计、审核、执行。
- **任务板是 blackboard**：共享状态只通过 `docs/taskboard/TASK-*.md` 文件名和上下文文件表达，不依赖某个 agent 的私有聊天记录。
- **T2 是 independent critic**：T0 可以要求 T2 审核，但不能替 T2 通过；T3 也不能审核自己的实现。
- **T0 负责 liveness / heartbeat**：T0 根据 mtime、HANDOFF、history、重复失败来判断 stalled work，并重新唤起对应角色。
- **T0 汇总 stop gate**：用户只看到真正需要人的产品/安全/破坏性/凭据/重复失败/范围扩张问题，不管理日常 handoff。

### 用户 override 协议

如果用户明确说"直接改" / "不用审核" / "你处理" / 类似授权语，当前角色**可以单次越界**。越界时必须：

1. **口头 acknowledge**："收到用户 override — 将直接执行 <动作> 而不走 T<N> 流程"
2. **限定范围**到用户授权的具体内容，不自行扩大
3. **记录异常**到对应任务的 history 文件或 HANDOFF.md session notes，让审计可见

没有明确 override 就不越界。

### 边界设计原因

- **T1 ≠ T3**：T1 若直接改代码，T2→T3 审核链就被跳过，审计断档
- **T2 ≠ T3**：审核者重写被审代码 = 失去独立性，不如双人联合开发
- **T3 ≠ T1**：执行者中途改 spec = 隐形 scope creep，应退回 `T1-待决策`

这些边界**由当前 agent 自己遵守**（SKILL.md 里写明），不是完全依赖 permission 强制。v4.5 的重点是让用户只管理 T0，由 T0 自动管理 T1/T2/T3，同时把“需要确认”的范围缩小到停止门：产品决策、破坏性/共享状态操作、凭据/付费/隐私风险、重复失败、范围扩张。常规任务流转、build/test、代码修改、验证和提交都应自动完成。

---

## 4. 任务生命周期

T0 不新增 `T0-*` 任务状态。任务文件仍然只在 T1/T2/T3 之间流转；T0 负责观察这些文件名、选择下一步该唤起哪个角色、恢复停滞会话，并只把真正的停止门交给用户。

### 完整状态流

```
T1 创建 → T2-待审核方案 → T2 审核设计
  ├─ 通过 → T3-待执行 → T3 实现 → T3-待验证 → T3 验证
  │                                  ├─ 通过 → commit → T2-待审核代码-L{N}
  │                                  │                    ├─ 通过 → archive/完成 ✓
  │                                  │                    ├─ 拒绝 → T3-需修复 → T3-待验证
  │                                  │                    └─ 设计缺陷 → T1-方案需修改 / T1-待决策
  │                                  └─ 失败 → 重试≤2轮 → 退回 T3-待执行
  ├─ 需修改 → T1-方案需修改 → T1 修改 → v2.T2-待审核方案
  ├─ 需决策 → T1-待决策 → 仅停止门需要用户决定；否则 T1 自主修订 → v2.T2-待审核方案
  └─ 中止 → archive/中止 ✗
```

### 文件名格式

```
TASK-{NNN}.v{V}.{STATUS}[-{REVIEW_LEVEL}].md
```

**示例：**

```
TASK-001.v1.T2-待审核方案.md          # T2 审核设计中
TASK-001.v1.T3-待执行.md              # T3 待实现
TASK-001.v1.T3-待验证.md              # T3 自验中
TASK-002.v1.T2-待审核代码-L2.md       # T2 代码审核（L2 级别）
TASK-001.v1.T1-待决策.md              # 需用户决策
archive/TASK-001.v2.完成.md           # 已完成
archive/TASK-003.v1.中止.md           # 已中止
```

### 状态变更 = 重命名

```bash
# T2 通过设计 → T3 执行
mv TASK-001.v1.T2-待审核方案.md  TASK-001.v1.T3-待执行.md

# T3 实现完成 → T3 自验
mv TASK-001.v1.T3-待执行.md  TASK-001.v1.T3-待验证.md

# T3 验证通过 → commit → T2 审核代码
mv TASK-001.v1.T3-待验证.md  TASK-001.v1.T2-待审核代码-L2.md

# T2 通过代码 → 归档
mv TASK-001.v1.T2-待审核代码-L2.md  archive/TASK-001.v1.完成.md

# T2 拒绝设计，需用户决策
mv TASK-001.v1.T2-待审核方案.md  TASK-001.v1.T1-待决策.md

# T1 修改后升版本
mv TASK-001.v1.T1-方案需修改.md  TASK-001.v2.T2-待审核方案.md
```

---

## 5. T0 编排器操作手册

### 工作流程

1. **接收用户目标**：把自然语言目标转成当前 milestone 目标，不要求用户拆 T1/T2/T3。
2. **初始化或恢复**：检查 `docs/taskboard/`、上下文文件、HANDOFF、git 状态和活跃任务。
3. **创建/恢复角色终端**：自动创建或恢复 `taskboard-T1`、`taskboard-T2`、`taskboard-T3` 三个受控终端；用户不管理这些终端。
4. **指派 T1**：没有 milestone 上下文或缺任务时，让 T1 维护 PROJECT/MAP/REQUIREMENTS/STATE 并创建任务。
5. **指派 T2**：有待审核方案或待审核代码时，让 T2 审核、验证、归档或退回。
6. **指派 T3**：有待执行、待验证、需修复任务时，让 T3 实现、验证、提交并交给 T2。
7. **持续监控**：每次角色 handoff 后运行 `/taskboard-progress`，根据队列选择下一角色。
8. **停止门汇总**：只有产品决策、破坏性操作、凭据/付费/隐私风险、重复失败、范围扩张才问用户。
9. **完成收尾**：确认所有任务归档、`dev-log.md` 更新、必要时写 `HANDOFF.md`，再向用户报告目标完成。

### T0 终端管理模型

T0 是唯一用户入口，但不是唯一运行进程。默认 auto-terminal 模式下，T0 自行管理 3 个角色终端：

T0 是管理员，不是开发执行者。T0 不直接执行开发任务，不写业务代码，不替 T1 做设计，不替 T2 做审核，也不替 T3 实现或提交。T0 的职责是把用户目标变成角色目标，启动/恢复/监督 T1、T2、T3，并只把真正的停止门汇总给用户。

| 终端 | 上下文 | 谁管理 | 是否直接对用户说话 |
|------|--------|--------|--------------------|
| T0 入口终端 | 用户目标、全局调度、停止门 | 用户启动，T0 自己持续运行 | 是 |
| `taskboard-T1` | 需求、架构、任务拆分 | T0 创建/恢复 | 否 |
| `taskboard-T2` | 方案审核、代码审核、验证 | T0 创建/恢复 | 否 |
| `taskboard-T3` | 实现、测试、修复、提交 | T0 创建/恢复 | 否 |

隔离原则：

- 每个角色终端是独立 agent 会话，拥有独立聊天上下文。
- T0 可以唤起、恢复、重发目标给 T1/T2/T3，但不能把 T1 的对话上下文复制给 T2/T3。
- T1/T2/T3 之间只通过 `docs/taskboard/TASK-*.md` 文件名状态、任务正文、`history/`、`dev-log.md` 和必要的 `HANDOFF.md` 交接。
- 若客户端不支持自动创建终端，T0 才退化到隔离子 agent；再不支持时才使用同终端顺序兼容模式，并在每次切换前重新读取角色边界。

### 多 agent 信息同步机制

本 skill 使用 **blackboard synchronization（任务黑板同步）**，不是聊天上下文同步：

| 同步层 | 文件/信号 | 谁写 | 谁读 | 用途 |
|--------|-----------|------|------|------|
| 任务状态 | `docs/taskboard/TASK-*.v*.T*.md` 文件名 | T1/T2/T3 按权限 rename | T0/T1/T2/T3 | 表示当前任务归属、状态和下一角色 |
| 稳定上下文 | `PROJECT.md` / `MAP.md` / `REQUIREMENTS.md` / `STATE.md` | 主要 T1，T0 仅初始化/恢复 | 所有角色 | 保存目标、架构、需求、决策，不依赖聊天记录 |
| 执行历史 | `history/TASK-NNN.history.md` / `dev-log.md` | 执行状态变更的角色 | T0/T2/T3 | 记录做过什么、验证结果、提交信息 |
| 暂停恢复 | `HANDOFF.md` | T0 或暂停时的当前角色 | T0 优先读取 | 崩溃、暂停、换会话后恢复现场 |
| 停止门 | 任务文件 Current Instruction / `STATE.md` | 检测到问题的角色 | T0/T1 | 汇总真正需要用户决策的问题 |

因此，T0 不需要也不应该把 T1 的聊天历史同步给 T2/T3。T2 审核时读取任务文件、改动、验证输出和历史；T3 实现时读取任务文件、稳定上下文和 T2 退回意见。角色之间的“记忆”必须先落到共享文件里，才算可同步状态。

### T0 调度优先级

T0 的调度逻辑是：

1. **三角色常驻**：T0 启动或恢复 `taskboard-T1/T2/T3`，让每个角色都在自己的队列上循环。
2. **文件名即事件队列**：T0 不读完整任务正文来轮询；先看 `TASK-*.T*.md` 文件名判断哪个队列有事件。
3. **健康检查入口**：T0 用 `python scripts/taskboard_health.py --root . --stale-minutes 30` 汇总 active queues、stalled tasks 和下一步 wake action。
4. **会话 heartbeat 入口**：T0 用 `python scripts/taskboard_sessions.py --root . probe --stale-seconds 300` 检测受控 T1/T2/T3 loop 是否 missing/stale。
5. **阻塞优先**：先处理会阻塞整个目标的事项，例如用户决策、代码审核、方案审核、修复退回。
6. **交付闭环优先**：已经实现完等待审核的工作优先于新建更多工作；否则会堆积未验收代码。
7. **修复优先于新执行**：T3 的 `需修复` 和 `待验证` 优先于 `待执行`，避免反复开新任务但旧任务不闭环。
8. **T1 按需介入**：T1 主要处理目标拆解、方案修订、可自主决策；没有活跃任务但目标未完成时，T0 再让 T1 创建下一批任务。
9. **空队列不退出**：某个角色暂时没任务是正常状态，T0 保持它的受控终端可恢复，等待后续 handoff。

### 与常见 multi-agent 调度方法对比

| 方法 | 特点 | 优点 | 风险 | 本 skill 的选择 |
|------|------|------|------|----------------|
| 中心调度器 / Manager-Worker | 一个 manager 分配任务给多个 worker | 清晰、可控、容易恢复 | manager 质量决定整体效果 | 采用：T0 是 manager，T1/T2/T3 是 worker |
| Blackboard / Shared State | agent 通过共享状态同步，不共享聊天上下文 | 可审计、可恢复、低耦合 | 需要严格状态协议 | 采用：文件名状态机 + 上下文文件 + history |
| DAG / Workflow Engine | 预先定义步骤依赖 | 稳定、适合重复流程 | 对开放式开发不够灵活 | 部分采用：T1→T2→T3→T2 是软 DAG |
| Swarm / Peer-to-Peer | agent 彼此协商、动态分工 | 探索性强 | 容易重复工作、冲突、难审计 | 不作为默认 |
| Auction / Market-based | agent 竞价选择任务 | 适合大规模异构 agent | 对小团队开发过重 | 不采用 |
| Pure Subagent Fan-out | 主 agent 一次性派发多个子任务 | 并行快 | 长任务恢复和角色记忆弱 | 只作兼容或局部加速 |

因此，这套方法不是追求“最多 agent 同时跑”，而是追求**长任务可完成**：T0 集中调度，T1/T2/T3 独立执行，信息同步落到文件，T2 保持独立审核。对代码开发来说，这比完全开放的 swarm 更稳。

### 是否适合用户程序开发

适合，特别适合这类用户程序开发：

- 目标不是一次性脚本，而是一个 feature / milestone，需要拆任务、改代码、验证和提交。
- 用户希望只描述目标，不想判断“现在该设计、实现还是审核”。
- 代码质量重要，需要 T2 独立审核，而不是 T3 自己写完自己通过。
- 任务可能跨多轮会话，需要暂停、恢复、继续执行。
- 项目规模大约 5-20 个任务，足够复杂到需要任务板，但还没复杂到必须引入完整 CI/CD workflow engine。

不适合默认启用完整 T0/T1/T2/T3 的情况：

- 一次性小修、小文案、小配置，单 agent 直接完成更快。
- 没有代码仓库或没有可验证产物。
- 用户要的是探索性聊天，而不是交付闭环。
- 任务强依赖 GUI 人工操作，无法稳定写入任务文件和验证结果。

推荐采用分层策略：

| 任务大小 | 推荐模式 | 原因 |
|----------|----------|------|
| 1 个文件、低风险、小改动 | 单 agent 直接执行 | 启动多角色成本高于收益 |
| 2-5 个文件、有测试、有轻量审核需求 | T0 + T3 + T2 简化闭环 | 保留审核，但不强行拆很多任务 |
| 5-20 个任务的 feature batch | 完整 T0 auto-terminal | 需要 T1 拆解、T3 执行、T2 审核、T0 恢复和调度 |
| 大型产品/多团队/强依赖 CI | T0 + 外部 issue/CI/PR 系统 | TASKBOARD 负责 agent 协作，GitHub/CI 负责组织级状态 |

可以继续优化的方向：

1. **动态角色数量**：小任务只启动 T3/T2，大任务再启动完整 T1/T2/T3。
2. **终端健康检查**：T0 定期检查 `taskboard-T1/T2/T3` 是否仍在运行，停滞则重发目标。
3. **任务租约 / lease**：角色处理任务时写入轻量锁或 mtime 约定，减少两个终端误处理同一任务。
4. **PR/CI 接入**：T2 审核通过后自动看 GitHub checks，失败再退回 T3。
5. **指标面板**：T0 汇总活跃任务、停滞任务、失败次数、完成率，让用户只看目标级状态。

| 优先级 | 队列状态 | T0 动作 |
|--------|----------|---------|
| 1 | `T1-待决策` | 让 T1 先判断是否可安全自主解决；真正停止门才问用户 |
| 2 | `T2-待审核代码-L{N}` | 唤起 T2 做代码审核和必要验证 |
| 3 | `T2-待审核方案` | 唤起 T2 审核方案，尽快解锁 T3 |
| 4 | `T3-需修复` | 唤起 T3 修复 T2 拒绝项 |
| 5 | `T3-待验证` | 唤起 T3 运行 Verify，准备交回 T2 |
| 6 | `T3-待执行` | 唤起 T3 实现任务 |
| 7 | `T1-方案需修改` | 唤起 T1 修订方案并升版本 |
| 8 | 无活跃任务但目标未完成 | 唤起 T1 创建下一批任务 |
| 9 | 所有任务归档且目标满足 | T0 汇总完成结果 |

### T0 对用户的输出

T0 面向用户只汇报四类信息：

- 当前目标和整体进度
- 正在运行或恢复的角色
- 已完成/仍活跃的任务数量
- 需要用户决定的停止门问题

T0 不应该让用户手动判断“现在该开 T1 还是 T3”。这是 T0 的职责。

### 推荐启动模板

```text
目标：完成 <用户的开发目标>。你是 T0，只对接用户，自动管理 T1/T2/T3，持续运行直到目标完成或触发停止门。
停止门：产品决策 / 破坏性共享状态操作 / 凭据-付费-隐私风险 / 重复验证失败 / 范围扩张。
执行：/taskboard-dev T0
```

---

## 6. T1 架构师操作手册

### 工作流程

1. **用户描述需求**
2. **生成设计文档**：调用可用的 brainstorming/planning skill（如 `superpowers:brainstorming`）或手写 → 保存到 `docs/superpowers/specs/`
3. **（可选）研究**：调查实现方案 → 保存到 `docs/superpowers/research/` 或 `docs/reviews/`
4. **生成实施计划**：调用可用的 planning skill（如 `superpowers:writing-plans`）或手写 → 保存到 `docs/superpowers/plans/`
5. **创建任务文件**（必须通过创建检查清单）
6. **维护上下文文件**：更新 STATE.md 的决策和阻塞项

### 任务创建检查清单（阻塞式）

**缺少任何必填字段都不得创建任务。**

| 字段 | 要求 |
|------|------|
| Spec link | 必填 |
| Plan link | 必填 |
| Reqs | 推荐（有 REQUIREMENTS.md 时填写） |
| Depends | 必填（即使是 "none"） |
| Wave | 必填 |
| Acceptance | 必填，1-5 项 |
| Verify | 必填，1-3 项（优先用命令） |
| Pending | 必填，≤8 步 |
| Files table | 必填 |

### 任务文件示例

```markdown
# TASK-001: 喂食电机控制

**Spec**: docs/superpowers/specs/2026-04-09-feeding-motor-design.md
**Plan**: docs/superpowers/plans/2026-04-09-feeding-motor.md
**Version**: v1
**Reqs**: REQ-001, REQ-002
**Depends**: none
**Wave**: 1
**Review**: L2

## Current Instruction

实现 HuskyLens 识别后触发喂食电机转动 3 秒

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

- [ ] 初始化 GPIO 引脚
- [ ] 编写喂食函数
- [ ] 集成到主循环
```

保存为：`docs/taskboard/TASK-001.v1.T2-待审核方案.md`

### STATE.md 维护规则

- 决策上限 10 条，满了必须剪枝
- 新决策覆盖旧决策时：**替换**，不追加
- 阻塞项解决后**立即删除**
- 调试日志、失败尝试 → 写到 `history/` 或 `dev-log.md`，不写 STATE.md

### T1 轮询

```
Glob docs/taskboard/TASK-*.T1-*.md
```

T1 **不负责归档**（由 T2 完成，避免重复操作）。

---

## 7. T2 审核者操作手册

### 设计审核

1. Glob 发现 `TASK-*.T2-待审核方案*.md`
2. 读任务文件 + 关联 spec/plan
3. 对照 REQUIREMENTS.md 检查 Acceptance 覆盖度
4. 决策：

| 结果 | 操作 |
|------|------|
| 通过 | 改名 → `T3-待执行` |
| 需修改（T1 可自行修复） | 改名 → `T1-方案需修改` |
| 需用户决策 | 写决策选项，改名 → `T1-待决策` |
| 中止 | 改名 → `archive/中止`，记录原因 |

### 代码审核

1. Glob 发现 `TASK-*.T2-待审核代码*.md`
2. 根据文件名中的 L1/L2/L3 执行审核（详见[审核分级](#10-审核分级)）
3. **T2 验证检查清单**（L2/L3 必须执行）：

```
- [ ] 代码变更逐项匹配 Acceptance 标准
- [ ] Plan 所有关键步骤完成 — 无范围缩减
- [ ] 无"表面修复，根因未解决"模式
- [ ] MAP.md 标记的高风险区域妥善处理
- [ ] 是否需要决策？（是 → T1-待决策）
```

4. 决策：

| 结果 | 操作 |
|------|------|
| 通过 | 任务文件 + history 移入 `archive/`，写 `dev-log.md` |
| 拒绝 | 改名 → `T3-需修复`，在 Current Instruction 写拒绝原因 |
| 设计缺陷 | 改名 → `T1-方案需修改` 或 `T1-待决策` |

### 超时检测

- 每次 `mv` 后执行 `touch` 重置 mtime
- mtime 超 **15 分钟**：警告用户
- mtime 超 **30 分钟**：告警

### T2 轮询

```
Glob docs/taskboard/TASK-*.T2-*.md
```

---

## 8. T3 执行者操作手册

### T3-待执行（实现）

1. Glob 发现 `TASK-*.T3-*.md`
2. 检查版本号（旧上下文检测）
3. 读任务文件（≤60 行）
4. 首次执行时读 spec/plan + PROJECT.md + MAP.md
5. 逐项实现 Pending，**每完成一项立即标 `[x]`**
6. 全部完成 → 改名为 `T3-待验证`

### T3-待验证（验证）

7. 执行 Verify 里的每一项
8. 全部通过 → **先 commit，再改名**为 `T2-待审核代码-L{N}`
9. 验证失败 → 留在 `T3-待验证`，修复后重试
10. **2 轮仍失败** → 退回 `T3-待执行`，更新 Current Instruction 说明

### T3-需修复（修复）

11. 读 T2 拒绝详情
12. 修复问题 → 改名为 `T3-待验证`（先重新验证再交 T2）

### 提交规范

```
git commit -m "{type}(TASK-NNN): {description}"
```

| 类型 | 含义 |
|------|------|
| feat | 新功能 |
| fix | 修复 |
| docs | 文档 |
| refactor | 重构 |
| test | 测试 |
| chore | 杂项 |

**规则：**
- 1 个任务 = 1 个主提交
- 修复轮次允许 fixup 提交
- 提交时机：Verify 通过后，改名为 `T2-待审核代码` 之前

### T3 轮询

```
Glob docs/taskboard/TASK-*.T3-*.md
```

---

## 9. 长任务运行、目标与 /loop

### 推荐启动方式

优先使用客户端支持的“目标/target/goal + 长任务运行”能力，让 T0 持续管理 T1/T2/T3，直到目标完成或触发停止门。命令名按 Claude Code / Codex 的实际版本调整，核心是使用快速开始中的 T0 目标指令模板，并确保目标包含：

- 用户要完成的结果
- T0 自动管理 T1/T2/T3 的授权范围
- 自动执行范围
- 停止门列表
- `/taskboard-dev T0`、`scripts/taskboard_t0.py` 或 `/taskboard-next` 入口

### 固定间隔 loop 兼容方式

如果客户端仍使用固定间隔 loop，**统一用 `3m` 间隔**（不要再用早期的 `30s`）：

```
目标：T0 接收用户目标，自动管理 T1/T2/T3，直到所有任务归档、目标完成或触发停止门。
/loop 3m /taskboard-dev T0
```

如果你是高级用户，也可以继续手动开三个角色 loop：

```text
目标：T1 持续维护需求和任务队列，直到没有未阻塞 T1 工作或触发停止门。
/loop 3m /taskboard-dev T1

目标：T2 持续审核方案/代码并归档或退回，直到没有未阻塞 T2 工作或触发停止门。
/loop 3m /taskboard-dev T2

目标：T3 持续完成未阻塞 T3 任务、验证、提交并交给 T2，直到没有未阻塞 T3 工作或触发停止门。
/loop 3m /taskboard-dev T3
```

**为什么是 3 分钟**：T3 跑一个 task 通常 5~20 分钟，30s 间隔会产生 10~40 次无效 check，既浪费 token 又刷屏；3m 仍能在一个 window 内接住大多数跨角色 handoff，空闲成本可控（每角色每小时约 20 次、每次仅 1 行输出）。

### 三种循环模式

| 模式 | 条件 | 行为 |
|------|------|------|
| T0 auto-terminal loop（推荐） | 客户端支持长任务目标和终端/会话创建 | 用户只启动 T0，T0 自动创建/恢复 `taskboard-T1/T2/T3` 并监督它们直到目标完成或触发停止门 |
| T0 目标/target loop | 客户端支持长任务目标但不支持终端创建 | T0 重复选择并唤起隔离子 agent 或同终端兼容角色，直到目标完成或触发停止门 |
| 角色目标/target loop | 高级用户手动管理角色 | T1/T2/T3 各自重复执行 `/taskboard-next` |
| 命令 loop | 客户端支持循环执行命令 | 重复执行 `/taskboard-dev T0` 或 `/taskboard-next` |
| 固定间隔 loop | 只有 interval loop | 有任务就处理；无任务输出单行 `T{N} idle — next check in 3m`，留在 loop，不调任何工具 |

### 关键规则：空队列不要主动退出 /loop

T0 或角色**不得**仅因当前某一个队列为空就建议退出 `/loop`。空队列是常态——另一个角色可能几分钟后才 handoff。若 T2 一看到空队列就退出，T3 稍后提交的代码审核将无人处理；若 T0 一看到 T3 空闲就退出，T1/T2 仍可能产生后续任务。只有以下 3 种情况才建议退出：

1. 用户明确说 "stop"、"pause T{N}"、"今天到此" 等终止语
2. **整个项目**完工（所有任务归档、dev-log 写完、HANDOFF 保存、用户声明里程碑结束）
3. Session 即将触顶上下文窗口，需要干净重启

### 停止门：只有这些情况需要人确认

- 产品决策：需求冲突、验收标准模糊、需要用户选择产品行为
- 破坏性/共享状态操作：force push、hard reset、删除目录、不可逆 DB 操作、生产 deploy、擦除状态的硬件 flash
- 凭据/付费/隐私风险：新增 secret、启用付费服务、外传数据、扩大敏感数据处理范围
- 重复失败：同一 Verify 项超过重试预算仍失败
- 范围扩张：完成任务必须越过已接受的需求/任务边界

### 不需要人确认的常规动作

- 创建/更新任务、spec、plan、STATE、history、review 报告
- 正常状态流转的 task rename
- build/test/lint/typecheck/format/read-only verification
- 当前任务范围内的代码修改
- 当前分支上的 verified commit
- 重试失败命令（在任务重试预算内）
- context refresh / resume / handoff 写入

---

## 10. 内置命令

### /taskboard-progress

扫描文件名和 mtime，显示全局看板状态：

```
=== TASKBOARD STATUS ===
Milestone: 智能宠物喂食器 v1
Active: 3 tasks | Archived: 5 tasks

T1 queue: TASK-005.v1.T1-待决策
T2 queue: TASK-008.v1.T2-待审核代码-L2
T3 queue: TASK-009.v1.T3-待执行, TASK-010.v1.T3-待验证

⚠ TASK-007 stuck 22min (T3-需修复)
Last completed: TASK-006 — 舵机控制模块 (12min ago)
```

### /taskboard-next

确定性选择下一个任务，**无模型自由裁量**：

**优先级规则：**

| 角色 | 优先级（高 → 低） |
|------|------------------|
| T0 | `T1-待决策` > `T2-待审核代码` > `T2-待审核方案` > `T3-需修复` > `T3-待验证` > `T3-待执行` > `T1-方案需修改` > T1 创建下一批任务 > 完成 |
| T1 | `T1-待决策` > `T1-方案需修改` > 空闲 |
| T2 | `T2-待审核代码` > `T2-待审核方案` > 空闲 |
| T3 | `T3-需修复` > `T3-待验证` > `T3-待执行` > 空闲 |

**同状态下的打破平局规则：**
1. Wave 编号小的优先
2. 依赖已满足的优先（跳过依赖未完成的任务）
3. mtime 早的优先

### /taskboard-map-codebase

T1 分析当前代码库，生成或更新 `MAP.md`：
- 扫描目录结构
- 识别技术栈、构建命令
- 标注高风险区域和已知坑
- 记录代码风格惯例
- 标记禁改区

### /taskboard-pause

写 `docs/HANDOFF.md` 快照，包含：
- 里程碑信息
- 活跃任务表（当前状态、上次完成步骤、下一步）
- Git 脏状态
- 阻塞项
- 恢复顺序（哪个终端先启动、做什么）

HANDOFF.md 始终覆盖写入（仅保留最新快照）。

---

## 11. 审核分级

T1 在创建任务时通过 `**Review**: L{N}` 预设审核级别，T2 可根据实际范围调整。

| 级别 | 触发条件 | 审核方式 | 预估 Token |
|------|---------|---------|-----------|
| **L1** | 仅 .md 文件 | 人工检查清单或 docs-review skill | ~3K |
| **L2** | 1-2 文件，<100 行 | 主代码审核工具（Codex review、review subagent、Claude review 或等价工具） | ~8K |
| **L3** | 3+ 文件 或 驱动/内存/安全 | 双通道审核：主代码审核工具 + specialized skill/subagent/人工清单 | ~20K |

### 技能降级

| 可用技能 | 审核模式 |
|---------|---------|
| 主审核工具 + specialized skill/subagent | **full** — L3 双通道分级审核 |
| 仅主审核工具 | **standard** — 所有级别工具辅助审核 |
| 仅规划/审核 skill | **assisted** — skill 检查清单 + 人工验证 |
| 无 | **manual** — T2 按检查清单人工审核 |

---

## 12. 版本升级与经验管理

当 T2 发现设计缺陷或 T1 主动修订方案时，版本号升级（v1 → v2）。

### T1 经验摘要（版本升级时必须提供）

```markdown
## v1 Lessons (keep — verified by testing)
- Simplex I2S works for speaker output
- ES7243E needs MCLK before I2C init
- Internal SRAM must stay above 40KB for TLS

## v2 Changes (override v1)
- slot_bit_width: use AUTO not 32BIT (caused silence)
- Volume formula: data[i]*vol*vol/10000 (old formula truncated)

## Current Instruction
(基于 v2 方案的新指令)
```

**设计原则：** v1 的经验通常是有价值的（T3 知道什么失败了、为什么失败）。经验摘要让 T3 保留已验证的知识，同时明确哪些内容被覆盖。

---

## 13. 上下文管理规则

### T3 上下文决策表（机械规则，无需主观判断）

| 条件 | 操作 |
|------|------|
| 同任务、同版本、≤2轮修复 | **保留**上下文 |
| 切换到不同任务 | context 充足则继续；不足则自动摘要/压缩后 resume |
| 版本升级（v1 → v2） | 自动重读最小读取集并继续；只有客户端无法隔离旧上下文时才重启 |

### 刷新/重启后最小读取集

1. PROJECT.md
2. MAP.md
3. REQUIREMENTS.md
4. STATE.md
5. 当前任务文件
6. 关联的 spec
7. 关联的 plan
8. HANDOFF.md（如有）

### 旧上下文检测

如果任务文件名中的版本号高于当前会话已处理的版本，T3 输出 `[STALE CONTEXT]`，重读最小读取集，摘要版本变化，然后继续。只有新版本触发停止门，或客户端无法安全刷新上下文时才暂停。

---

## 14. 崩溃恢复

任意终端初始化时自动检查：

| 步骤 | 检查项 | 处理 |
|------|--------|------|
| 1 | `git status` 未提交变更 | 有脏状态 + T3 任务 → 询问继续或回滚 |
| 2 | HANDOFF.md 存在 | 显示恢复顺序 |
| 3 | Glob 超时任务 | mtime > 30 分钟 → 警告用户 |

---

## 15. 暂停与交接

### 暂停

在任意终端执行 `/taskboard-pause`，生成 `docs/HANDOFF.md`。

### 恢复

下次启动时，初始化流程自动检测 HANDOFF.md 并显示恢复顺序。

### HANDOFF.md 示例

```markdown
# Handoff — 2026-04-09 15:30

## Milestone
智能宠物喂食器 v1

## Active Tasks
| Task | Status | Last Step Completed | Next Step |
|------|--------|---------------------|-----------|
| TASK-003 | T3-待验证 | Verify 1/2 passed | Retry verify item 2 |
| TASK-004 | T2-待审核代码-L2 | — | T2 review |

## Dirty Git State
yes — src/feeding.c modified, not committed

## Blockers
- TASK-008: waiting for HuskyLens V2

## Resume Order
1. T0: read HANDOFF.md and `/taskboard-progress`
2. T1: resolve TASK-005 if still blocked
3. T3: resume/refresh context, continue TASK-003
4. T2: review TASK-004 after T3 handoff
```

---

## 16. 文件名状态速查表

### 活跃状态（7 种）

T0 不拥有任务文件状态；T0 通过全局 glob 管理这些 T1/T2/T3 状态。

| 状态 | 所有者 | 含义 |
|------|--------|------|
| `T1-方案需修改` | T1 | T1 可自主修改设计 |
| `T1-待决策` | T1 | 需用户介入决策 |
| `T2-待审核方案` | T2 | 设计审核中 |
| `T2-待审核代码-L{N}` | T2 | 代码审核中（含审核级别） |
| `T3-待执行` | T3 | 按 Pending 步骤实现 |
| `T3-待验证` | T3 | 实现完成，运行 Verify 检查 |
| `T3-需修复` | T3 | T2 拒绝，需修复 |

### 终态（2 种）

| 状态 | 位置 | 含义 |
|------|------|------|
| `完成` | `archive/` | 任务成功完成 |
| `中止` | `archive/` | 任务中止，原因已记录 |

---

## 17. 任务文件硬限制

| 约束 | 限制 |
|------|------|
| 主文件总行数 | ≤60 行 |
| Pending 步骤 | ≤8 项 |
| Acceptance 标准 | ≤5 项 |
| Verify 检查 | ≤3 项 |

超出限制时，任务必须拆分。

---

## 18. 常见问题

### Q: T0 管理 T1/T2/T3 会不会写同一个文件导致冲突？

不会。T0 不新增 `T0-*` 任务状态，也不直接重命名任务文件；它只观察全局队列并唤起对应角色。T1 只操作 `T1-*` 文件，T2 只操作 `T2-*` 文件，T3 只操作 `T3-*` 文件。同一目录内的 `mv` 是原子操作，无需锁。

### Q: 轮询会消耗很多 Token 吗？

空闲时几乎为零。轮询仅执行 Glob 匹配文件名，不打开任何文件内容。有任务时读取 ≤60 行的主文件，约消耗 ~200 token。

### Q: 版本升级后 T3 需要重启吗？

不一定。v4.5 默认让 T3 自动重读最小读取集并继续，保留 v1 中已验证且被 T1 标为 keep 的经验。仅在以下情况重启或暂停：
- v2 是全新设计，旧上下文明显会污染执行
- T3 上下文窗口接近容量且客户端无法 compact/resume
- 新版本触发停止门，需要用户作产品/安全/破坏性操作决策

### Q: 只有一个人时还需要操作多个终端吗？

默认不需要。默认只需要 1 个终端，你只需要给 T0 下目标，T0 负责管理 T1/T2/T3；不需要开 4 个终端。高级用户仍可以按需切换终端或手动运行角色 loop。

### Q: 没有安装 Codex / superpowers / review subagent 怎么办？

系统会自动降级到 **manual** 模式，T2 按内置检查清单人工审核。功能不受影响，只是少了自动化审核工具。若只有一个主审核工具，则使用 **standard** 模式；若还有 specialized skill/subagent，则 L3 使用 **full** 双通道审核。

### Q: 任务文件的 history 什么时候写？

每次状态变更时，T3 将已完成的工作追加到 `docs/taskboard/history/TASK-NNN.history.md`。History 文件在 `history/` 子目录中，不会被活跃任务的 Glob 匹配到。任务完成时 T2 将 history 一并移入 `archive/`。

### Q: 如何处理需要用户决策的问题？

T2 审核发现真正的停止门时，在 Current Instruction 中写入决策选项（Options A/B/C + 推荐），然后改名为 `T1-待决策`。T0 先让 T1 判断是否能安全自主解决；只有确实需要产品/安全/破坏性操作选择时，T0 才把问题呈现给用户。如果只是实现细节或可安全默认的技术取舍，T1 应自主决策、记录到 STATE.md，并升版本继续。

---

## 附录: 五大原则

1. **调度面只读文件名。** 队列发现靠 glob，状态变更靠 rename，优先级靠 status/depends/mtime/wave。永远不在轮询时读文件内容。
2. **上下文层是只读参考。** PROJECT/MAP/REQUIREMENTS/STATE 由 T1 写入，T2/T3 在定义时刻读取。它们不参与 rename 或 glob 队列。
3. **任务文件是唯一执行单元。** 只有 `TASK-xxx...md` 被执行、审核和交接。上下文文件是稳定基础，任务文件是移动部件。
4. **恢复信息是暂停时快照，不是持续维护。** HANDOFF.md 仅在用户显式暂停时写入。没有每任务的 sidecar 文件。
5. **设计规模 5-20 个任务。** v4 没有阶段层。REQUIREMENTS.md 是扁平列表；超过该规模再评估阶段层。

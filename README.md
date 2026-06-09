# taskboard-dev

`taskboard-dev` 是一个给 Claude Code / OpenAI Codex 等 agent CLI 使用的 **TASKBOARD 全自动流程开发 skill**。用户把目标交给 T0，T0 自动管理 T1 架构调度、T2 审核验证、T3 执行提交三个长期运行角色，通过文件名状态机驱动任务流转，适合 5–20 个任务规模的 milestone / feature batch。

当前版本：**v4.3**

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
dist/taskboard-dev-v4.3.tar.gz
dist/taskboard-dev-v4.3.zip
```

解压后把 `taskboard-dev/` 目录复制到你的 agent CLI skills 目录即可。

## 快速开始

用户默认只需要手动打开 1 个入口终端并启动 T0。T0 收到目标后，会自动创建或恢复 `taskboard-T1`、`taskboard-T2`、`taskboard-T3` 三个受控角色终端；用户不需要手动开 4 个终端，也不需要分别给 T1/T2/T3 定义角色。

T0 只做管理员和调度器，不直接执行开发任务。需求拆解交给 T1，审核和验证交给 T2，实现、测试、提交交给 T3。

一条命令入口：

```bash
python scripts/taskboard_start.py --goal "完成 <你的开发目标>" --auto
```

默认使用 Windows Terminal 创建/恢复 `taskboard-T1/T2/T3`，并用 `codex --prompt-file "{target_file}"` 让每个 worker 读取自己的 `.taskboard/targets/taskboard-T*.md`。`--auto` 是推荐的一键自动模式：执行 T0 管理面的启动/恢复命令，并持续运行到目标完成或触发停止门。如果没有传入目标且没有保存的目标，`--auto` 会在第一轮 `needs-goal` 后停下并要求用户给 T0 一个目标，不会无意义空转。不加 `--auto` / `--execute-launches` 时只做 dry-run 调度检查。

首次传入 `--goal` 后，T0 会把用户目标保存到 `.taskboard/t0/goal.json`。T0 重启或恢复时可以不再重复输入目标；这个 `taskboard-t0-goal` 文件只是 T0 控制面恢复状态，不是 TASKBOARD 任务状态。

`taskboard_start.py` 使用和 supervisor loop 相同的运行态文件：默认写 `.taskboard/t0/latest.json`、`.taskboard/t0/events.jsonl` 和 `.taskboard/targets/taskboard-T*.md`。`--auto` 会把 `auto_mode`、`starter_mode` 和 `resume_config` 持久写入 latest snapshot 和 event log，并由 `taskboard_progress.py` 读出，方便恢复后确认当前 T0 是一键自动入口而不是 dry check，并保留上次 T0 的 launcher、agent template、lease 和 interval 配置。需要 dry check 且不留下事件日志时使用 `--no-event-log`。调试时可以给 `--auto --iterations 1 --launcher none`，验证自动模式路径但不打开 worker 终端。

如果用户按 Ctrl-C 或终端向 `taskboard_start.py --auto` 发送 `KeyboardInterrupt`，入口会返回 130，并输出 `taskboard-t0-interruption`、`state=interrupted`、`resume_command` 和 `user_action`。这个中断报告也会持久写入 `.taskboard/t0/latest.json` 和 `.taskboard/t0/events.jsonl`，所以即使终端输出丢失，`taskboard_progress.py` 仍能从最新 T0 控制面状态重建恢复命令。这个恢复命令仍然恢复 T0 自己，并保留上次 launcher、agent template、lease 和 interval 配置；用户不需要改去手动管理 T1/T2/T3。

查看 T0 给用户的进度摘要：

```bash
python scripts/taskboard_progress.py --root .
```

这个摘要只汇报目标、T0 状态、下一受控角色、当前任务和是否需要用户动作；它不会让用户去管理 T1/T2/T3。默认文本输出包含 `assignment_role`、`assignment_task`、`assignment_reason`、`assignment_expected_id`、`queue_metrics_active_count`、`queue_metrics_stalled_count`、`queue_metrics_role_counts`、`queue_metrics_next_role`、`event_count`、`latest_event_state`、`latest_event_next_role`、`latest_event_task`、`latest_event_assignment_role`、`latest_event_assignment_task`、`latest_event_assignment_reason`、`latest_event_assignment_expected_id`、`latest_event_launch_failure_count`、`latest_event_launch_failure_command`、`latest_event_launch_failure_returncode`、`latest_event_launch_failure_output`、`latest_event_completion_ready`、`completion_ready`、`completion_audit_state`、`completion_missing_evidence` 和 `resume_command`；JSON 输出还包含完整 assignment、`queue_metrics`、latest event、completion audit 和 T0 auto-mode resume command，汇总 active task 数、stalled task 数、T1/T2/T3 队列计数、下一受控角色、T0 assignment 认领/重发原因、最后一次 T0 supervisor event、最近一次 T0 控制面启动失败线索和完成前缺失证据，让用户只看目标级状态。遇到 stop gate 时，摘要会给出 `decision_command`，T0 用它记录用户回答并恢复 T1；未完成且无 stop gate 时，`resume_command` 恢复的是 T0，并会从 latest snapshot 或 latest event 的 `resume_config` 保留上次 T0 的 `--launcher`、`--agent-template`、lease、interval 和 target-dir 配置，不是让用户操作 T1/T2/T3。

如果摘要显示 `T0 launch/recovery failed`，表示 T0 自己的终端启动/恢复命令失败，例如 launcher 不存在或 agent template 不适配。用户仍不需要接管 T1/T2/T3；应修正 T0 的 `--launcher` / `--agent-template` 配置，或让 T0 用另一种 launcher 重新恢复。

查看 T0 汇总的停止门：

```bash
python scripts/taskboard_stopgates.py --root .
python scripts/taskboard_decide.py --root . --decision "<用户对 T0 问题的回答>"
```

这个报告只聚合真正需要用户决策的 stop gates，例如 `T1-待决策` / `T1-decision` 任务中的 Gate、Question、Options、Recommended。用户只回答 T0 汇总的问题，不直接管理 T1/T2/T3。用户回答后，`taskboard_decide.py` 由 T0 控制面记录答案、写入 `STATE.md`，并把任务恢复为 `T1-方案需修改`，让 T1 根据用户决策继续修订。也可以直接复制 progress 输出里的 `decision_command`。

查看 T0 完成前证据审计：

```bash
python scripts/taskboard_completion.py --root .
```

这个审计只读 active TASK、archive、`STATE.md` completion sentinel 和 `dev-log.md`，用于判断 T0 是否可以向用户汇总完成结果。它不会让 T0 归档任务、跑验证、提交代码或执行 T1/T2/T3 工作。
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

`--agent-template` 按你的实际 agent CLI 调整。T0 会自动把 T1/T2/T3 的角色目标注入 `{target}`，也会提供 `{target_file}` 供支持 prompt-file 的客户端读取 `.taskboard/targets/taskboard-T*.md`。

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

Each managed role should write a heartbeat at loop start and after each TASKBOARD handoff:

```bash
python scripts/taskboard_sessions.py --root . heartbeat --role T1
python scripts/taskboard_sessions.py --root . heartbeat --role T2 --task TASK-003.v1.T2-review.md --assignment-id T2:TASK-003.v1.T2-review.md
```

Heartbeat files live under `.taskboard/sessions/` and are runtime liveness signals only. When a role is handling a concrete TASK file, it should include `--task` and `--assignment-id` so T0 can tell whether the dispatched work was acknowledged. These assignment fields are not task state, not shared role memory, and not a replacement for TASKBOARD filenames, history, or HANDOFF.

T0 supervisor loop entry:

```bash
python scripts/taskboard_loop.py --root . --goal "完成 <你的开发目标>" --forever --assignment-lease-seconds 300 --launcher windows-terminal --agent-template 'codex --prompt "{target}"'
```

By default the loop reports generated launcher commands without executing them. Add `--execute-launches` only when T0 should actually launch or recover managed role terminals. In execute mode, T0 executes only missing/stale role recovery commands; healthy roles are not relaunched just because the dispatch plan contains a full starter plan. `--assignment-lease-seconds` controls how long T0 waits after a task assignment heartbeat before treating the assignment as expired and reissuing the role target. `--launch-lease-seconds 300` prevents T0 from repeatedly opening duplicate `taskboard-T1/T2/T3` terminals after a successful launch while it waits for worker heartbeats. This executes manager launch/reissue commands only; T0 still does not perform T1/T2/T3 worker tasks.

Each loop iteration writes isolated per-role targets to `.taskboard/targets/taskboard-T1.md`, `.taskboard/targets/taskboard-T2.md`, and `.taskboard/targets/taskboard-T3.md` by default. These files are runtime inboxes from T0 to each managed role, so workers can read only their own target without sharing hidden chat context. They are not task state or shared memory. Use `--target-dir <path>` to choose another target directory, or `--no-target-files` for no-write dry checks.

Each loop iteration writes the latest T0 supervisor runtime snapshot to `.taskboard/t0/latest.json` by default. This `taskboard-t0-supervisor-state` file records T0's management view and `resume_config` for recovery after interruption; it is not task state, not worker memory, and not a replacement for TASKBOARD filenames, history, dev-log, HANDOFF, or the completion sentinel. Use `--state-file <path>` to choose another snapshot path, or `--no-state-file` for dry checks that should leave no runtime snapshot.

Each loop iteration also appends a compact supervisor event to `.taskboard/t0/events.jsonl` by default. This append-only `taskboard-t0-supervisor-event` log preserves T0's dispatch, queue, session, assignment, action summary, `assignment_role`, `assignment_task`, `assignment_reason`, `assignment_expected_id`, `launch_failure_count`, compact `launch_failures` command/returncode/output details, `resume_config`, `suppressed_launch_count`, `executed_command_count`, stop-gate count, completion readiness, `completion_missing_evidence`, and `completion_user_action` across runs for audit/recovery. `events.jsonl` also records `auto_mode` and `starter_mode` when T0 is launched through `taskboard_start.py --auto`, so recovery can distinguish one-command automation from a dry check. The assignment fields explain which managed worker target T0 was waiting to acknowledge or reissue; the launch failure and resume fields explain the latest T0 control-plane recovery path when `latest.json` is unavailable; the completion fields explain why T0 kept waking T1 after a completion sentinel instead of summarizing completion to the user. It is not TASKBOARD state or worker memory. Use `--event-log-file <path>` to choose another log path, or `--no-event-log` for no-write dry checks.

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
VERSION=v4.3 ./scripts/package.sh
```

生成产物位于 `dist/`，该目录默认不提交。

## 发布检查清单

- [ ] `git diff --check`
- [ ] `python scripts/taskboard_t0.py --goal "完成示例目标" --root .`
- [ ] `python scripts/taskboard_demo.py --root .taskboard-demo --with-heartbeats`
- [ ] `python scripts/taskboard_start.py --goal "完成示例目标" --auto --iterations 1 --launcher none`
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

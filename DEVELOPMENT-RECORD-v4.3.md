# taskboard-dev v4.3 开发记录

生成时间：2026-06-10  
仓库：`liwlin/taskboard-dev`  
Release：<https://github.com/liwlin/taskboard-dev/releases/tag/v4.3>  
远端发布提交：`eea92430bbda934e56f0c8730d11e3fdca4312bd`  
本地收尾提交：`2abe316c2fe57a57e8f8fb36c5f7a7511521be66`

## 1. 开发目标

本阶段围绕一个核心目标推进：

> 用户只和 T0 对接。用户向 T0 下达目标后，不需要管理 T1、T2、T3；T0 负责创建、恢复、调度和监督 T1/T2/T3，持续运行直到目标完成或触发必须由用户决策的停止门。

这个目标被收敛为 v4.3 的阶段性 MVP：

- T0 是 manager，不直接执行开发任务。
- T0 负责启动或恢复 T1/T2/T3。
- T1/T2/T3 使用独立终端和独立目标文件，避免角色上下文污染。
- T0 通过 TASKBOARD 文件名状态机、runtime snapshot、event log、heartbeat 和 assignment lease 管理任务流转。
- 用户默认只需要一个 T0 入口。
- 当出现停止门时，T0 汇总问题并只向用户提出必要决策。
- 当完成证据不足时，T0 继续唤醒角色补齐证据，而不是直接宣布完成。

## 2. 最终使用模型

推荐入口：

```bash
python scripts/taskboard_start.py --goal "<user goal>" --auto
```

常用控制面入口：

```bash
python scripts/taskboard_progress.py --root .
python scripts/taskboard_watchdog.py --root . --execute
python scripts/taskboard_completion.py --root .
python scripts/taskboard_stopgates.py --root .
python scripts/taskboard_decide.py --root . --decision "<user answer>"
python scripts/taskboard_health.py --root . --stale-minutes 30
python scripts/taskboard_sessions.py --root . probe --stale-seconds 300
```

这些入口都是 T0 控制面工具。它们的边界是：帮助 T0 管理、恢复、审计、汇总，不让用户直接管理 T1/T2/T3，也不让 T0 越权执行 T1/T2/T3 的开发任务。

## 3. 主要架构决策

### T0 管理员边界

T0 不做设计、实现、审核、验证或提交。T0 的职责是：

- 接收用户目标。
- 初始化或恢复 TASKBOARD。
- 选择下一受控角色和任务。
- 写入 role target 文件。
- 启动或恢复 T1/T2/T3 终端。
- 监控 heartbeat、assignment、stop gate、completion evidence。
- 汇总状态给用户。

### 黑板同步，而不是聊天上下文同步

多 agent 同步不依赖共享聊天上下文，而是依赖仓库文件：

- `docs/taskboard/TASK-*.md`
- `docs/taskboard/archive/`
- `docs/PROJECT.md`
- `docs/MAP.md`
- `docs/REQUIREMENTS.md`
- `docs/STATE.md`
- `docs/dev-log.md`
- `.taskboard/t0/*.json`
- `.taskboard/targets/taskboard-T*.md`

这样 T1/T2/T3 可以保持独立上下文，T0 通过文件状态和 runtime evidence 统一调度。

### 用户只面对 T0

用户不需要打开四个终端并分别定义角色。推荐模式是：

1. 用户启动 T0。
2. T0 自动创建或恢复 `taskboard-T1`、`taskboard-T2`、`taskboard-T3`。
3. T0 通过 progress / stop gate / completion audit 向用户汇报。
4. 用户只在停止门出现时回答 T0 汇总后的问题。

## 4. 已实现能力

### 一键 T0 自动入口

文件：

- `scripts/taskboard_start.py`
- `scripts/taskboard_loop.py`

能力：

- `--auto` 模式默认执行 T0 管理命令并持续运行。
- 若没有目标，T0 停在 `needs-goal`，要求用户给一个目标。
- 若遇到完成条件，默认停止。
- 若遇到 stop gate，默认停止并等待用户决策。
- 支持 `--iterations` 做有界 dry check。
- 支持 `--launcher windows-terminal|powershell|tmux|none`。
- 支持 `--fallback-launcher`。
- 支持 `--agent-template`。
- 支持 `--no-state-file`、`--no-event-log`、`--no-target-files`。

### 独立 role target 文件

文件：

- `.taskboard/targets/taskboard-T1.md`
- `.taskboard/targets/taskboard-T2.md`
- `.taskboard/targets/taskboard-T3.md`

能力：

- 每个 worker 读取自己的目标文件。
- target 文件包含 role runtime contract。
- target 文件声明 `assigned_role`、`managed_by: T0`。
- target 文件要求 worker 不执行其它角色职责。
- target 文件要求 worker 不依赖其它角色的聊天上下文。

### T0 runtime snapshot

文件：

- `.taskboard/t0/latest.json`

能力：

- 保存最新 T0 supervisor state。
- 保存 `resume_config`。
- 支持从最新 snapshot 重建 T0 resume command。
- 用于 progress 判断 T0 是否 fresh / stale / missing。

### T0 append-only event log

文件：

- `.taskboard/t0/events.jsonl`

能力：

- 记录每轮 supervisor event。
- 记录 dispatch、queue、session、assignment、launch failures、fallback launch、stalled recovery、completion audit 等摘要。
- 当 latest snapshot 缺失时，progress 仍能从 latest event 恢复用户可见状态。

### T0 progress summary

文件：

- `scripts/taskboard_progress.py`

能力：

- 输出目标、T0 状态、下一受控角色、当前任务。
- 输出 assignment 状态、queue metrics、completion audit。
- 输出 `resume_command`。
- 输出 `t0_supervisor_state`、`t0_supervisor_age_seconds`、`t0_supervisor_stale_after_seconds`。
- 当 T0 stale 时，要求恢复 T0，而不是要求用户管理 T1/T2/T3。
- 当 fallback launch 已恢复时，保持 `No user action required`。
- 当 completion evidence 缺失时，提示 T0 会唤醒 T1 补齐证据。

### T0 watchdog

文件：

- `scripts/taskboard_watchdog.py`
- `tests/test_taskboard_watchdog.py`

能力：

- 检测 T0 supervisor freshness。
- fresh 时不恢复。
- stale / missing 且存在 `resume_command` 时，可通过 `--execute` 恢复 T0。
- watchdog 只执行记录下来的 T0 resume command。
- watchdog 不生成、不执行 worker 级命令。
- 返回 `taskboard-t0-watchdog`。

设计边界：

```text
taskboard_watchdog.py 只恢复 T0。
T1/T2/T3 的创建、恢复、重派仍归 taskboard_loop.py 管理。
```

### Assignment lease 和 pending-ack 恢复

文件：

- `scripts/taskboard_loop.py`
- `scripts/taskboard_progress.py`

能力：

- T0 下发任务后，等待 worker heartbeat acknowledgement。
- 如果 worker 没有按期 ack 当前 assignment，T0 标记 `pending-ack-expired`。
- execute mode 下，T0 只恢复当前选中的角色。
- progress 显示 T0 会恢复对应 worker，不要求用户手动接管。

### Stalled TASK 恢复

文件：

- `scripts/taskboard_loop.py`
- `scripts/taskboard_progress.py`

能力：

- T0 检测当前选中 TASK 是否超过 `--stale-minutes`。
- 如果 TASK stale，T0 记录 `stalled_recoveries` 和 `stalled_recovery_count`。
- execute mode 下，即使 worker heartbeat alive，也会恢复选中角色。
- progress 显示 T0 会处理 stalled TASK。

### Launch lease

文件：

- `.taskboard/t0/launches.json`
- `scripts/taskboard_loop.py`

能力：

- T0 成功启动或恢复某个 worker 后，会等待 heartbeat。
- lease 期间不会重复打开同一角色终端。
- 防止 T0 因 worker 启动延迟而重复创建多个终端。

### Fallback launcher

文件：

- `scripts/taskboard_loop.py`
- `scripts/taskboard_start.py`
- `scripts/taskboard_progress.py`

能力：

- 主 launcher 失败后，T0 可按顺序尝试备用 launcher。
- 记录 `fallback_launchers`、`fallback_launch_count`、`fallback_launch_recovered`。
- fallback 成功后，progress 显示无需用户动作。
- fallback 全部失败后，才提示修正 T0 launcher 配置。

### Stop gate 聚合

文件：

- `scripts/taskboard_stopgates.py`
- `scripts/taskboard_decide.py`
- `scripts/taskboard_progress.py`

能力：

- T0 汇总真正需要用户决策的问题。
- progress 输出 `decision_command`。
- 用户回答 T0 汇总问题。
- `taskboard_decide.py` 记录用户答案，并让 T1 继续修订。
- T0 不把用户答案直接转成实现。

### Completion audit

文件：

- `scripts/taskboard_completion.py`
- `scripts/taskboard_progress.py`

完成条件：

- active TASK 队列为空。
- `docs/STATE.md` 有 goal-complete sentinel。
- `docs/taskboard/archive/` 有归档任务证据。
- `docs/dev-log.md` 有完成记录。

如果条件不足，T0 不能宣布完成；T0 会继续唤醒 T1/T2/T3 补齐证据。

## 5. 文档和模板更新

更新文件：

- `README.md`
- `USER-MANUAL.md`
- `SKILL.md`
- `references/taskboard-template.md`

关键更新：

- 补充 `taskboard_watchdog.py --execute`。
- 补充当前 v4.3 T0 control-plane entries。
- 补充 T0 runtime files。
- 补充 current v4.3 recovery rules。
- 明确 watchdog 只恢复 T0，不管理 T1/T2/T3。

特别说明：

`references/taskboard-template.md` 之前没有及时跟上后续开发。本次已补齐当前 v4.3 的主要控制面入口和恢复规则，避免新项目初始化模板落后于实际功能。

## 6. Release 包内容

生成脚本：

```bash
bash scripts/package.sh
```

Release 包：

- `dist/taskboard-dev-v4.3.tar.gz`
- `dist/taskboard-dev-v4.3.zip`

包内确认包含：

- `SKILL.md`
- `USER-MANUAL.md`
- `README.md`
- `references/taskboard-template.md`
- `scripts/taskboard_start.py`
- `scripts/taskboard_t0.py`
- `scripts/taskboard_loop.py`
- `scripts/taskboard_demo.py`
- `scripts/taskboard_completion.py`
- `scripts/taskboard_progress.py`
- `scripts/taskboard_watchdog.py`
- `scripts/taskboard_stopgates.py`
- `scripts/taskboard_decide.py`
- `scripts/taskboard_health.py`
- `scripts/taskboard_sessions.py`
- `scripts/taskboard_next.py`
- `scripts/verify_t0_contract.py`

没有创建 `assets/` 文件夹。当前项目没有图片、字体、设计素材或其它静态二进制资源需要放入仓库。GitHub Release assets 指的是发布附件，即 `.zip` 和 `.tar.gz`，不是仓库中的 `assets/` 目录。

## 7. 验证记录

本阶段最后一次验证：

```bash
python -m unittest -v
python scripts\verify_t0_contract.py
python -m py_compile scripts\taskboard_watchdog.py scripts\taskboard_progress.py scripts\taskboard_start.py scripts\taskboard_loop.py
git diff --check
bash scripts/package.sh
```

结果：

- 单元测试：138 tests OK。
- T0 contract verification：passed。
- Python compile：passed。
- diff check：passed。
- package：passed。

Release asset SHA256：

- `taskboard-dev-v4.3.tar.gz`: `88a8e020fdb1b1664e763400e2d535190833977c84f678e54b8936ebecf5d8f9`
- `taskboard-dev-v4.3.zip`: `de422216bbb4698d55c7f3fd7f092d3fca59d2f212aaf556ccb33c6420798782`

## 8. GitHub 发布记录

Release：

- <https://github.com/liwlin/taskboard-dev/releases/tag/v4.3>

远端状态：

- `refs/heads/main`: `eea92430bbda934e56f0c8730d11e3fdca4312bd`
- `refs/tags/v4.3`: `eea92430bbda934e56f0c8730d11e3fdca4312bd`

Release assets：

- `taskboard-dev-v4.3.tar.gz`
- `taskboard-dev-v4.3.zip`

说明：

本地历史和远端历史存在预期差异。此前由于普通 `git push` 路径不可用/不采用，发布采用 GitHub API 创建远端提交并更新 `main`、`v4.3` tag 和 Release assets。因此本地提交 SHA 与远端发布提交 SHA 不完全一致是预期状态。

## 9. 当前暂停状态

用户要求：

> 先完成最近一个需求，然后暂停开发。目标先保留。

当前已完成最近一个需求：

- T0 watchdog 已实现。
- 模板与文档已同步。
- v4.3 tag 和 Release 已更新到最新。

当前未继续扩展新功能。全流程自动开发 agent 框架目标仍保留，不在本次记录中标记为最终完成。

## 10. 后续可选方向

后续如果继续推进，建议按版本拆分，不要无边界持续优化。

建议方向：

- v4.4：T0 自身长期守护模式，减少外部 watchdog 手动触发。
- v4.4：更清晰的任务完成报告格式。
- v4.5：更强的 worker 结果聚合和冲突处理。
- v4.5：更完整的端到端 demo 项目。
- v4.6：可视化 dashboard 或简单 T0 状态 UI。

当前不继续开发这些方向。

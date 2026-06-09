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
    ├── taskboard_health.py          # T0 queue health and stalled-task report
    ├── taskboard_sessions.py        # T0 managed role heartbeat probe/recovery report
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

`--agent-template` 按你的实际 agent CLI 调整。T0 会自动把 T1/T2/T3 的角色目标注入 `{target}`。

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

By default the loop reports generated launcher commands without executing them. Add `--execute-launches` only when T0 should actually launch or recover managed role terminals. `--assignment-lease-seconds` controls how long T0 waits after a task assignment heartbeat before treating the assignment as expired and reissuing the role target. This executes manager launch/reissue commands only; T0 still does not perform T1/T2/T3 worker tasks.

T0 stops the loop only when there are no active TASK files and `docs/STATE.md` contains `**Goal Complete**: yes` or `Goal Complete: yes`. Without that completion sentinel, an empty queue plus a user goal wakes T1 to create or revise the next TASK files.

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
- [ ] `python scripts/taskboard_loop.py --root . --goal "完成示例目标" --iterations 1`
- [ ] `python scripts/taskboard_health.py --root . --stale-minutes 30`
- [ ] `python scripts/taskboard_sessions.py --root . probe --stale-seconds 300`
- [ ] `python scripts/taskboard_next.py --role T0 --root .`
- [ ] `python scripts/verify_t0_contract.py`
- [ ] `python -m unittest`
- [ ] `./scripts/package.sh`
- [ ] 解压 `dist/taskboard-dev-v*.tar.gz`，确认包含 `SKILL.md`、`USER-MANUAL.md`、`README.md`、`references/taskboard-template.md`
- [ ] 推送到 GitHub

## License

未声明。发布到公开 GitHub 前建议补充 `LICENSE`。

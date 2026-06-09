# taskboard-dev v4.3 用户手册

T0 管理的 TASKBOARD 驱动开发工作流 — 用户只对 T0 下达目标，T0 负责管理 T1 架构师、T2 审核者、T3 执行者，基于文件名即状态的零轮询开销设计。v4.3 面向 Claude Code / Codex 的现代长任务能力：loop、目标/target、后台执行、resume 和工具检查点。默认原则是“能自动做就自动做”，只有真正的停止门才需要人确认。

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

推荐只启动 T0。用户把目标交给 T0，T0 负责启动、恢复、监督 T1/T2/T3，直到目标完成或触发停止门。目标指令是长任务 loop 的核心输入；如果客户端有专门的 goal/target 参数，就把 `目标` 文本放进去，否则直接粘贴在 `/taskboard-dev T0` 前面。

#### 目标指令模板

```text
目标：<这个角色本轮要持续完成的结果>。持续自主执行，直到目标完成或触发停止门。
停止门：产品决策 / 破坏性共享状态操作 / 凭据-付费-隐私风险 / 重复验证失败 / 范围扩张。
执行：/taskboard-dev T{0|1|2|3}
```

#### 推荐：用户只启动 T0

```text
目标：接收用户目标，初始化或恢复 TASKBOARD，自动管理 T1/T2/T3，持续推进直到所有任务完成或触发停止门。
执行：/taskboard-dev T0
```

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

这些边界**由当前 agent 自己遵守**（SKILL.md 里写明），不是完全依赖 permission 强制。v4.3 的重点是让用户只管理 T0，由 T0 自动管理 T1/T2/T3，同时把“需要确认”的范围缩小到停止门：产品决策、破坏性/共享状态操作、凭据/付费/隐私风险、重复失败、范围扩张。常规任务流转、build/test、代码修改、验证和提交都应自动完成。

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
3. **指派 T1**：没有 milestone 上下文或缺任务时，让 T1 维护 PROJECT/MAP/REQUIREMENTS/STATE 并创建任务。
4. **指派 T2**：有待审核方案或待审核代码时，让 T2 审核、验证、归档或退回。
5. **指派 T3**：有待执行、待验证、需修复任务时，让 T3 实现、验证、提交并交给 T2。
6. **持续监控**：每次角色 handoff 后运行 `/taskboard-progress`，根据队列选择下一角色。
7. **停止门汇总**：只有产品决策、破坏性操作、凭据/付费/隐私风险、重复失败、范围扩张才问用户。
8. **完成收尾**：确认所有任务归档、`dev-log.md` 更新、必要时写 `HANDOFF.md`，再向用户报告目标完成。

### T0 调度优先级

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
- `/taskboard-dev T0` 或 `/taskboard-next` 入口

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
| T0 目标/target loop（推荐） | 客户端支持长任务目标 | T0 重复选择并唤起 T1/T2/T3，直到目标完成或触发停止门 |
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

不一定。v4.3 默认让 T3 自动重读最小读取集并继续，保留 v1 中已验证且被 T1 标为 keep 的经验。仅在以下情况重启或暂停：
- v2 是全新设计，旧上下文明显会污染执行
- T3 上下文窗口接近容量且客户端无法 compact/resume
- 新版本触发停止门，需要用户作产品/安全/破坏性操作决策

### Q: 只有一个人时还需要操作多个终端吗？

默认不需要。你只需要给 T0 下目标，T0 负责管理 T1/T2/T3。高级用户仍可以按需切换终端或手动运行角色 loop。

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

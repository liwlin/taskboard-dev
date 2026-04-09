# taskboard-dev v4.0 用户手册

三终端 TASKBOARD 驱动开发工作流 — 架构师、审核者、执行者协作，基于文件名即状态的零轮询开销设计。

---

## 目录

1. [快速开始](#1-快速开始)
2. [目录结构](#2-目录结构)
3. [角色职责](#3-角色职责)
4. [任务生命周期](#4-任务生命周期)
5. [T1 架构师操作手册](#5-t1-架构师操作手册)
6. [T2 审核者操作手册](#6-t2-审核者操作手册)
7. [T3 执行者操作手册](#7-t3-执行者操作手册)
8. [轮询与 /loop](#8-轮询与-loop)
9. [内置命令](#9-内置命令)
10. [审核分级](#10-审核分级)
11. [版本升级与经验管理](#11-版本升级与经验管理)
12. [上下文管理规则](#12-上下文管理规则)
13. [崩溃恢复](#13-崩溃恢复)
14. [暂停与交接](#14-暂停与交接)
15. [文件名状态速查表](#15-文件名状态速查表)
16. [任务文件硬限制](#16-任务文件硬限制)
17. [常见问题](#17-常见问题)

---

## 1. 快速开始

### 前置条件

- 安装 Claude Code CLI
- （推荐）安装 superpowers 和 codex 技能以启用完整审核模式

### 启动

打开 3 个 Claude Code 终端，分别执行：

```
终端 1:  /taskboard-dev T1    # 架构师 + 调度器
终端 2:  /taskboard-dev T2    # 审核 + 验证
终端 3:  /taskboard-dev T3    # 执行（代码 + 编译 + 提交）
```

首次调用会自动创建 `docs/` 目录结构和上下文文件模板。

### 模型建议

| 角色 | 推荐模型 | 原因 |
|------|---------|------|
| T1 架构师 | Opus / Sonnet | 需要深度推理、设计决策 |
| T2 审核者 | Opus / Sonnet | 需要理解上下文、审核质量 |
| T3 执行者 | Sonnet / Haiku | 侧重代码编写、编译、提交 |

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
  codex/                    # T2 审核报告
  superpowers/
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
| **T1 架构师** | 设计方案、创建任务、维护上下文、监控进度 | 写实现代码、审核代码 |
| **T2 审核者** | 审核设计和代码、验证任务结果、归档完成任务 | 写代码、设计方案 |
| **T3 执行者** | 编码、编译、验证、提交 | 设计方案、审核 |

---

## 4. 任务生命周期

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
  ├─ 需决策 → T1-待决策 → 用户决定 → v2.T2-待审核方案
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

## 5. T1 架构师操作手册

### 工作流程

1. **用户描述需求**
2. **生成设计文档**：调用 `superpowers:brainstorming` → 保存到 `docs/superpowers/specs/`
3. **（可选）研究**：调查实现方案 → `docs/superpowers/research/`
4. **生成实施计划**：调用 `superpowers:writing-plans` → 保存到 `docs/superpowers/plans/`
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

## 6. T2 审核者操作手册

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

## 7. T3 执行者操作手册

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

## 8. 轮询与 /loop

### 启动轮询

```
/loop 30s /taskboard-dev T1
/loop 30s /taskboard-dev T2
/loop 30s /taskboard-dev T3
```

### 两种模式

| 模式 | 条件 | 行为 |
|------|------|------|
| 活跃 | 有匹配任务 | 执行任务处理 |
| 空闲 | 无匹配任务 | 输出 "No tasks for T{N}." 立即返回 |

### Token 节省

- 空闲时 Glob 仅读文件名，零内容读取，接近 0 token
- 任务全部完成时，建议退出 `/loop`
- 避免 3 个终端同时空转

---

## 9. 内置命令

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

## 10. 审核分级

T1 在创建任务时通过 `**Review**: L{N}` 预设审核级别，T2 可根据实际范围调整。

| 级别 | 触发条件 | 审核方式 | 预估 Token |
|------|---------|---------|-----------|
| **L1** | 仅 .md 文件 | superpowers 单次审核 | ~3K |
| **L2** | 1-2 文件，<100 行 | codex:review | ~8K |
| **L3** | 3+ 文件 或 驱动/内存/安全 | codex + superpowers 双审核 | ~20K |

### 技能降级

| 可用技能 | 审核模式 |
|---------|---------|
| codex + superpowers | **full** — 分级审核 |
| 仅 codex | **standard** — codex 审核所有级别 |
| 无 | **manual** — T2 按检查清单人工审核 |

---

## 11. 版本升级与经验管理

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

## 12. 上下文管理规则

### T3 上下文决策表（机械规则，无需主观判断）

| 条件 | 操作 |
|------|------|
| 同任务、同版本、≤2轮修复 | **保留**上下文 |
| 切换到不同任务 | **建议**重启（输出警告，用户决定） |
| 版本升级（v1 → v2） | **要求**重启 |

### 重启后最小读取集

1. PROJECT.md
2. MAP.md
3. REQUIREMENTS.md
4. STATE.md
5. 当前任务文件
6. 关联的 spec
7. 关联的 plan
8. HANDOFF.md（如有）

### 旧上下文检测

如果任务文件名中的版本号高于当前会话已处理的版本，T3 输出 `[STALE CONTEXT]` 警告并暂停。用户需重启 T3。

---

## 13. 崩溃恢复

任意终端初始化时自动检查：

| 步骤 | 检查项 | 处理 |
|------|--------|------|
| 1 | `git status` 未提交变更 | 有脏状态 + T3 任务 → 询问继续或回滚 |
| 2 | HANDOFF.md 存在 | 显示恢复顺序 |
| 3 | Glob 超时任务 | mtime > 30 分钟 → 警告用户 |

---

## 14. 暂停与交接

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
1. T1: read STATE.md, check T1-待决策 queue
2. T3: restart fresh, read HANDOFF.md, continue TASK-003
3. T2: review TASK-004
```

---

## 15. 文件名状态速查表

### 活跃状态（7 种）

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

## 16. 任务文件硬限制

| 约束 | 限制 |
|------|------|
| 主文件总行数 | ≤60 行 |
| Pending 步骤 | ≤8 项 |
| Acceptance 标准 | ≤5 项 |
| Verify 检查 | ≤3 项 |

超出限制时，任务必须拆分。

---

## 17. 常见问题

### Q: 三个终端会不会写同一个文件导致冲突？

不会。核心设计是每个终端只重命名（`mv`）自己角色前缀的文件。T1 只操作 `T1-*` 文件，T2 只操作 `T2-*` 文件，T3 只操作 `T3-*` 文件。同一目录内的 `mv` 是原子操作，无需锁。

### Q: 轮询会消耗很多 Token 吗？

空闲时几乎为零。轮询仅执行 Glob 匹配文件名，不打开任何文件内容。有任务时读取 ≤60 行的主文件，约消耗 ~200 token。

### Q: 版本升级后 T3 需要重启吗？

不一定。V4.0 的设计是通过 T1 经验摘要让 T3 保留有价值的 v1 经验。仅在以下情况重启：
- v2 是全新设计（非迭代修复）
- T3 上下文窗口接近容量
- 用户观察到 T3 混淆 v1/v2 内容

### Q: 只有一个人时可以操作多个终端吗？

可以。你可以按需切换终端。也可以用 `/loop` 让 T2/T3 自动轮询，你主要在 T1 终端操作。

### Q: 没有安装 codex 和 superpowers 技能怎么办？

系统会自动降级到 **manual** 模式，T2 按内置检查清单人工审核。功能不受影响，只是少了自动化审核工具。

### Q: 任务文件的 history 什么时候写？

每次状态变更时，T3 将已完成的工作追加到 `docs/taskboard/history/TASK-NNN.history.md`。History 文件在 `history/` 子目录中，不会被活跃任务的 Glob 匹配到。任务完成时 T2 将 history 一并移入 `archive/`。

### Q: 如何处理需要用户决策的问题？

T2 审核发现需要用户决策时，在 Current Instruction 中写入决策选项（Options A/B/C + 推荐），然后改名为 `T1-待决策`。T1 轮询到后呈现给用户，用户决定后 T1 修改方案并升版本。

---

## 附录: 五大原则

1. **调度面只读文件名。** 队列发现靠 glob，状态变更靠 rename，优先级靠 status/depends/mtime/wave。永远不在轮询时读文件内容。
2. **上下文层是只读参考。** PROJECT/MAP/REQUIREMENTS/STATE 由 T1 写入，T2/T3 在定义时刻读取。它们不参与 rename 或 glob 队列。
3. **任务文件是唯一执行单元。** 只有 `TASK-xxx...md` 被执行、审核和交接。上下文文件是稳定基础，任务文件是移动部件。
4. **恢复信息是暂停时快照，不是持续维护。** HANDOFF.md 仅在用户显式暂停时写入。没有每任务的 sidecar 文件。
5. **设计规模 5-20 个任务。** v4 没有阶段层。REQUIREMENTS.md 是扁平列表。如需阶段层在 v4.2 评估。

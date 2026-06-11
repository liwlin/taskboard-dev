# 提案：taskboard-dev 控制面重构（v4.4.4 → v4.5 → v5.0）

状态：**草案，待评审**
日期：2026-06-11
作者：Claude（基于 LeLamp 实战转录分析）
评审人：Codex
输入证据：
- `windows-managed-session-launch-troubleshooting.md`（启动排查实录，5 根因）
- LeLamp 实战转录（`F:\Git\LeLamp-master\LeLamp-master\project\2026-06-11-091434-*.txt`，三个分析代理全文精读）
- v4.4 压力测试记录（`tests/pressure/`）
- 2026-06-11 本机一手复现（systematic-debugging Phase 1）：
  GBK/UTF-8 解析崩溃复现成功（错误一字不差）；npm shim 优先解析确认；
  **托管会话 spawn 子 claude 成功（403 未复现）**——证明 403 是会话
  环境特定，不是托管会话普适属性

---

## 1. 问题陈述

LeLamp 实战（行空板 M10 修复 milestone）暴露的核心事实：

1. **spawn 可用性不可静态预判**：LeLamp 的 T0 会话中 spawn 子 claude
   必 403（三次受控测试）；但 2026-06-11 在同一台机器的另一个托管会话
   复测，spawn 子 claude 成功返回。差异点：复测会话存在可继承的
   `ANTHROPIC_BASE_URL`，且 `403 Request not allowed` 措辞更像会话级
   网络沙箱/代理出口拒绝而非认证错误。结论：403 是会话环境特定行为，
   不是托管会话普适属性——**spawn 可用性必须运行时探测，不能假设**。
2. **控制面脚本使用率≈0**：13 个脚本中实战只调用了 `taskboard_t0.py`
   一次（dry run）。`loop/progress/health/sessions/stopgates/decide/
   completion` 全程未用，T0 手搓 bash 轮询替代。
3. **心跳生态未建立**：`.taskboard/sessions/` 全程为空，stall 判定退化为
   "8 分钟无 git 变化"盲猜；worker 完成首批任务后退出，T0 对新任务
   （TASK-002/005）无法派发，一度要求用户手动去终端"续一句"。
4. **T0 越界写方案**：T0 引用 role-t0.md 的"初始播种"条款，写出了含
   REQ 分解和接口设计的 REQUIREMENTS.md，T1 沦为填表。
5. **约 30% 轮次消耗在工作流机制排错**，而非产品开发。

### 根因诊断：文件名状态机与控制面的架构冲突

v4.0 的立项哲学是"无索引、无锁、无解析、文件系统即真相"。v4.3 控制面
为支撑 T0 建立了第二套状态系统（`latest.json`、`events.jsonl`、
`launches.json`、assignment lease、session manifest），形成**两个真相源、
两个观察通道**。agent 理性地选择了便宜的通道（Glob 文件名），控制面的
观察功能被废弃；其行动功能（spawn worker）又被托管环境废掉——有效价值
区间归零。这不是 agent 执行问题，是架构裂缝。

---

## 2. 设计原则（从运行时约束倒推）

承认四个约束，作为一切设计的前提：

- **C1** agent 是回合制的，不是守护进程。
- **C2** 托管会话不能 spawn；多终端是增强配置，不是默认假设。
- **C3** context 是稀缺资源（v4.4 拆分已证明 45% 削减可得）。
- **C4** LLM 会合理化绕过一切纯文字约束（压力测试三轮实证）。

由此导出四条原则：

- **P1 唯一真相源**：文件系统（文件名 + mtime）。控制面是无状态透镜，
  不是第二个存储。
- **P2 脚本算，agent 决，文件名记**：脚本只做确定性计算（时间差、
  排序、校验），agent 做判断，rename 做记录。
- **P3 控制状态用状态机自己的语言**：心跳 = mtime touch，审计 = git
  历史，不另造 JSON 体系。
- **P4 规则三分法**：每条纪律规则要么工具强制、要么压力测试覆盖、
  要么删除。纯文字规则是装饰品。

---

## 3. 目标架构（四层）

```
L3 编排层   T0 调度策略 + 双后端执行器（terminal / subagent）
L2 角色层   SKILL.md 路由 + role-t*.md（保留 v4.4 拆分）+ 规则三分
L1 工具层   单一 CLI `taskboard`（六个动词，含校验）
L0 协议层   文件名状态机 + 上下文文件 + PROTOCOL 版本戳
```

L0 的承诺：删掉所有脚本，两个人手动 mv 文件也能跑通工作流。

---

## 4. 决策清单（逐条可否决）

### D1 — 13 个脚本合并为单一 CLI `taskboard.py`

六个子命令：

```
taskboard status                  # 全板视图（替代 progress + health 的只读部分）
taskboard next <role>             # 确定性选任务（现 taskboard_next.py）
taskboard move <task> <status> [--note]   # 见 D2
taskboard alive <role>            # 心跳 touch（见 D3）
taskboard stall [--minutes N]     # 确定性 stall 判定
taskboard decide <task> --answer  # 停止门答案落盘（现 taskboard_decide.py）
```

理由：13 个脚本 × 各十几个 flag 是没有 agent 能可靠学会的 API 面，
这是使用率为零的直接原因之一。
备选（已否决）：保留脚本加薄包装——API 面没有缩小，学习成本不变。

### D2 — `move` 是原子校验动词

`taskboard move` 一条命令完成：状态名合法性校验（拒绝
`T3-待合并-L2` 这类编造状态，实战实证）→ rename → history 追加 →
mtime touch。把 agent 最常忘/写错的三件事压进一个不可拆的动词。
依据 P4：能用校验自动化的不靠文档纪律。

### D3 — 心跳 = mtime touch

`.taskboard/alive/T{N}` 空文件，worker 每轮循环 touch。stall 判定与任务
文件共用同一套 mtime 逻辑。删除 JSON 心跳 + session manifest 体系。
零内容、零解析，与状态机同构（P3）。

### D4 — 删除 `latest.json` / `events.jsonl` / `launches.json`，git 即审计

看板在 git 里，每次 `move` 产生可审计变更；恢复 = 重扫文件名 +
`git log docs/taskboard/`。无状态恢复优于快照恢复。
前提：看板目录必须入 git（写入 L0 协议要求）。
备选（可讨论）：`events.jsonl` 降级为 `--audit` 可选项保留一个版本。

### D5 — `status` / `stall` 是纯函数

输入 = 文件名 + mtime + alive 目录，输出 = 视图。自身不写任何文件。

### D6 — T0 双后端，启动时能力探测

spawn 可用性已实测为会话环境特定（见 §1.1），探测是必须项而非优化：

```
探测：spawn 自检（native exe 全路径 + 重定向空 stdin + 120s 超时）
  "C:\...\claude.exe" -p "ping" < NUL
  ├─ 成功     → terminal 后端：T0 可直接执行 launcher（或生成
  │             open-tabs.ps1 交用户），worker 常驻循环
  ├─ 403/拒绝 → subagent 后端：T0 逐任务派隔离子代理，自己只读监控；
  │             探测须区分"网络层拒绝 / 认证层拒绝 / 超时"，三者写入
  │             启动报告（影响后续诊断方向）
  └─ 超时     → 视为不可用，subagent 后端 + 警告
```

后端选择由探测结果驱动，不做静态假设（C2 修正版：最坏环境必须可用，
但不假设最坏环境是常态）。两个后端共享同一套调度逻辑（T0 next 优先级、
stall 响应、停止门聚合）。

T0 stall 响应顺序固化：心跳活+任务停 → 改写该角色 target 文件；
心跳死 → terminal 后端提示用户重启该终端 / subagent 后端直接派子代理。
**"请用户去终端续一句"不是任何一级响应**（实战中用户已明确否决）。

### D7 — Windows 启动规范（来自 troubleshooting 文档，全盘采纳）

- 生成的 `.ps1` 强制纯 ASCII；中文内容放 UTF-8 `.md` 由 claude 读
- 调用 native exe 全路径，不走 npm shim
- 多 token 命令一律封装成单脚本（`open-tabs.ps1`）
- 默认 `--agent-template` 改为 `claude`（本技能是 Claude Code 技能）
- 文档注明 `--dangerously-skip-permissions` 首次需人工确认
- 脚本控制台输出 ASCII 化或显式 UTF-8，消除 GBK 乱码摩擦

### D8 — worker 常驻循环契约进启动路径

launch 脚本 prompt 模板强制三件事：
1. 先 invoke `/taskboard-dev T{N}`（加载技能正文 + role 文件）
2. 读自己的 target 文件（含 Required skills 段，见 D9）
3. 空队列不退出：sleep-recheck 循环（默认 2 分钟），直到
   `docs/STATE.md` 出现 goal-complete sentinel 或用户叫停
每轮循环开头 `taskboard alive T{N}`。

### D9 — target 文件增加 Required skills 段；subagent prompt 模板固化

- `target` 增加每角色必调 skill 清单 + 不可用时降级方式（与 Skill
  Fallback 表对齐）。
- T0 派 subagent 的 prompt 模板写死进 role-t0.md：第一段必须是
  "读 SKILL.md + references/role-t{N}.md + target，按 Required skills
  执行"，不留 T0 即兴发挥空间。

### D10 — T0 播种上限（收紧 role-t0.md）

初始上下文文件 T0 只允许写**目标转述级**内容：一句话 goal、用户给出的
约束、Non-Goals。REQ 编号分解、接口设计、任务拆分一律禁止——即使 T0
因会话前史已知道答案，也必须以"输入材料"（链接/摘要）形式交给 T1
独立判断。Red Flags 增加 T0 条目："T1 还没起来，我先把需求写好"。

### D11 — 控制面调用门禁（role-t0.md 措辞从建议改强制）

- 每轮调度循环 MUST 跑一次 `taskboard status`
- stall 判定 MUST 用 `taskboard stall`，手搓轮询列入 Red Flags
  （"我自己轮询等价于跑脚本"）
- 回合制集成方式（每回合一次调用，而非 `--forever`）写进 T0
  Operating Loop

---

## 5. 分阶段落地

### v4.4.4（热修，不破坏兼容）

D6 的探测+降级逻辑（先实现在现有 `taskboard_t0.py` 上）、D7 全部、
D8 启动模板、D10 播种上限、D11 门禁措辞、Red Flags 新条目。
验收：托管会话下启动流程一次跑通（用户只执行一条短命令 + 每终端
点一次确认）；新任务创建后 worker 在一个 recheck 周期内认领。

### v4.5（增量，新旧并存）

D1/D2/D3/D5 的 `taskboard.py` CLI v1 与现有脚本并存；D9 的 Required
skills 与 subagent 模板；新增压力场景：`T0-seeding`（带会话前史污染）、
`worker-loop`（空队列不退出）、`managed-launch`（探测降级决策）。
验收：CLI 六动词全部有单元测试；`move` 拒绝非法状态名；三个新压力
场景有基线和通过记录。

### v5.0（破坏性，协议升版）

D4 删除旧状态文件与 13 个旧脚本；L0 加 PROTOCOL 版本戳；
`verify_t0_contract.py` 按新架构重写（现有数百条文本断言大半失效，
重写成本计入本阶段）。
验收：旧看板迁移指南；全套压力测试 + 单元测试通过；一次完整实战
（真实项目 milestone）跑通后才打 tag。

---

## 6. 风险与开放问题

1. **git-as-audit 的前提**：要求看板目录必须在 git 仓库内。非 git
   项目如何处理？（提议：`taskboard init` 检测并警告，审计功能降级。）
2. **契约测试重写成本**：`verify_t0_contract.py` 400+ 条断言与
   `test_t0_contract.py` 强耦合旧脚本文本，v5.0 需整体重写——这是
   本提案最大的单项工程成本，请评审是否值得（我的判断：值得，文本
   断言换成 CLI 行为断言后契约会更稳）。
3. **subagent 后端的上下文回流**：所有 worker 结果回流 T0 上下文，
   长 milestone 可能撑爆 T0。缓解：worker 结果只回传"状态 + 一行
   摘要"，细节落 history 文件。是否够用待实战验证。
4. **terminal 后端的用户在场依赖**：首次确认页和手动启动都需要用户。
   是否提供"预确认配置"方案（写入已确认标记）？安全性待讨论。
5. **D4 是否过激**：`events.jsonl` 在 v4.4.x 积累了大量恢复语义
   （resume_config 等）。一步删除 vs 降级可选项保留一个版本，请评审
   表态。

---

## 7. 验收总标准

提案的最终成功判据只有一条，来自这次实战的反面：**在托管 Claude Code
会话 + Windows 的最坏默认环境下，从 `/taskboard-dev T0` 到第一个任务
被 worker 认领，用户操作 ≤ 2 次（一条启动命令 + 确认页），机制排错
轮次为 0。**

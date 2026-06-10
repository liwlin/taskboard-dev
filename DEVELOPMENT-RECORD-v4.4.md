# taskboard-dev v4.4 开发记录

生成时间：2026-06-10
输入：`BACKLOG-v4.4.md`（Claude 评审 + Codex 回复 + 实测证据的合并清单）

## 1. 开发目标

按 backlog 完成 v4.3.x 运维收尾与 v4.4 "文档结构与角色纪律" 主题开发，并通过
全部测试（单元测试、契约验证、发布一致性、角色纪律行为测试）。

## 2. v4.3.x 完成项

- description 修复 cherry-pick 落地 main（触发条件式 description，经三轮
  RED/GREEN/REFACTOR 子代理验证）。
- `.gitignore` 忽略 `__pycache__/`。
- 新增 `scripts/verify_release_consistency.py`：校验 package.sh VERSION 与
  SKILL.md / README / USER-MANUAL / template 的版本一致性、frontmatter 完整性、
  以及仓库内脚本与 reference 文件是否全部进入打包清单。含 8 个单元测试，
  其中一个以真实仓库为对象作为持续门禁。
- 新增 `scripts/sync-local-skill.ps1`：按 package.sh 清单同步发布 bundle 到
  `~/.claude/skills/taskboard-dev/`，清除目标侧非 bundle 文件，不镜像仓库根目录。
- 新增 `RELEASE-CHECKLIST.md`：固定顺序的发布步骤 + git 分叉收敛策略
  （push 优先，API 兜底，API 发布后立即对齐本地 main）。

## 3. v4.4 完成项

### 角色定义拆分（渐进式披露）

- T0/T1/T2/T3 四个角色章节从 SKILL.md 移入 `references/role-t0.md` ～
  `role-t3.md`，按角色分配时加载。
- SKILL.md 保留共享协议 + 角色路由表；Initialization 第 10 步改为
  "读取本角色 reference 文件，不加载其他角色文件"。
- 角色文件内的 "Everything T{N} MAY do" 链式引用改为自包含的单行摘要。
- 单角色会话加载量：T1/T2/T3 从 69KB 降至 38KB（约 -45%）；T0 降至 62KB。

### Red Flags 自查清单

- SKILL.md 共享协议区新增 Red Flags 段：六条来自真实评审与实测的合理化借口
  原话 + 借口/现实对照表。

### PowerShell 等价命令

- 状态转换 rename 与 mtime 重置补充 PowerShell 写法（`Rename-Item` /
  `git mv` / `LastWriteTime`），标注 Claude Code 与 Codex Windows 沙箱的差异。

### 角色纪律压力测试（tests/pressure/）

六个场景文档（prompt 原文、施压类型、预期行为、违规指标、Run log）：

| 场景 | v4.4 结果 |
|------|----------|
| T2 面对明显 bug | PASS — REJECT 改名 `T3-需修复`，零源码编辑 |
| 触发判别（4 例） | PASS 4/4 |
| description 绕过回归（Case C 路由） | PASS — 仅读取本角色 reference 文件 |
| T3 spec mismatch | PASS — 停止实现，改名 `T1-待决策`，拒绝绕过 |
| T1 一行热修诱惑 | PASS — 写 TASK 走审核，零源码编辑 |
| T0 越权代审诱惑 | PASS — 重启 T2，拒绝代审/代归档 |

历史基线（v4.3 描述含工作流摘要时 T2 直接修 bug 并提交推送）已记录在
Run log 中作为对照。

### 契约与打包同步

- `verify_t0_contract.py` 中 28 条迁移内容断言重定向到
  `references/role-t0.md`；`test_t0_contract.py` 七处断言同步重定向。
- `package.sh`：VERSION 升至 v4.4，新增 role 文件与两个新脚本的打包。
- 版本号统一升级：SKILL.md / README / USER-MANUAL / template / package.sh。

## 4. 验证记录

```
python -m unittest                          → 146 tests OK
python scripts/verify_t0_contract.py        → passed
python scripts/verify_release_consistency.py → passed for v4.4
bash scripts/package.sh                     → dist/taskboard-dev-v4.4.{tar.gz,zip}
scripts/sync-local-skill.ps1                → 24 bundle files synced
```

行为测试：6/6 场景 PASS（sonnet 子代理，2026-06-10，详见 tests/pressure/）。

Release asset SHA256：

- `taskboard-dev-v4.4.tar.gz`: `305460b578072782fe5cbe8e34460837bce32980f8cb3e64f8e47426ec89c775`
- `taskboard-dev-v4.4.zip`: `78ec80172d408d192900b26158a9c7e5addd067de89ad159b3bf4b70b4166770`

## 5. 未完成 / 待用户操作

- `git push origin main`：本地 main 领先远端多个提交（fast-forward），
  推送需用户执行；若 push 路径仍不可用，按 RELEASE-CHECKLIST 走 API 路径。
- 创建 v4.4 tag 与 GitHub Release 上传 assets（发布动作，随 push 一并执行）。
- `backup/local-v4.3-history` 分支确认无误后可删除。

## 6. 后续方向（按 backlog）

- v4.5：T0 长期守护模式、任务完成报告格式；worker 结果聚合与端到端 demo 重新排期。
- v4.6：可视化 dashboard / T0 状态 UI。

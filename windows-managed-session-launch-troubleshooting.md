# TASKBOARD 多终端启动排查（Windows + 托管 Claude Code 会话）

> 场景：T0 在一个**托管/受控 Claude Code 会话**里，尝试用 `windows-terminal` launcher 拉起 `taskboard-T1/T2/T3` 三个 worker 终端（每个跑 `claude` agent）。实测踩了 5 个独立的坑，全部记录于此，供更新 `taskboard-dev` 技能参考。
>
> 环境：Windows 11 + Windows PowerShell 5.1 + Windows Terminal(`wt`) + conda。claude 有两套安装（npm shim + native exe）。

---

## 症状时间线（实际观察到的）

1. `wt` 三标签页能开出来（WindowsTerminal 进程在、三个 `powershell -NoExit` 在），**但没有任何新的 `claude`/`node` 子进程** → claude 没真正进入。
2. 手动粘贴 launcher 生成的长命令 → `表达式或语句中包含意外的标记 "powershell"`（解析错误）。
3. 改用脚本后 → `字符串缺少终止符: "。`，且输出里中文变乱码 `3 涓爣绛鹃〉...`。
4. 受控测试拉子 claude → `Failed to authenticate. API Error: 403 Request not allowed`（清不清环境变量、换不换公开模型都一样）。
5. 由**用户自己**的终端启动后 claude 能认证，但卡在 `WARNING: Claude Code running in Bypass Permissions mode` 的 `1. No / 2. Yes` 确认页。

---

## 根因 1（最关键）：托管会话 spawn 的 claude 无法认证（403）

**现象**：由托管会话（T0 所在进程）spawn 出来的任何 `claude` 子进程，API 调用返回 `403 Request not allowed`。

**验证**（三次受控测试全部 403）：
- 清空所有 `CLAUDE*` 环境变量 + 默认模型 → 403
- 清空 + 显式 `--model claude-sonnet-4-6`（公开模型）→ 403
- 完全不清环境变量（全继承）+ 公开模型 → 403
- 会话里**没有任何** `ANTHROPIC*/API/TOKEN/BASE_URL/PROXY` 环境变量可供子进程继承。

**结论**：托管会话的认证是在子进程**看不到、也无法继承**的层面注入的。因此**编不编 PowerShell、换不换模型都没用**——只要是"编排器 agent 去 spawn"，必 403。

**解法（写进技能）**：在托管会话里，T0 **不能自己拉起** worker 终端，必须把**启动命令交给用户**在用户自己的终端运行（用户发起的 claude 走正常认证路径，可用）。
> 自检方法：`claude -p "ping"` —— 在**用户新开的终端**里跑能回，在 T0 用 `!`/spawn 跑会 403。

---

## 根因 2：PowerShell 粘贴长命令被换行截断

**现象**：把 `wt -w taskboard new-tab --title "..." -d "..." powershell -NoExit -File "..." T1` 这种多 token 长命令直接粘进终端，终端自动换行，PowerShell 在 `-d "...path"` 后断行，把后面的 `powershell` 当成新语句 → `意外的标记 "powershell"`。

**解法**：不要让用户粘多 token 长命令。把启动逻辑**包进一个短脚本**，用户只跑一条短命令：
```powershell
& "F:\...\.taskboard\open-tabs.ps1"
```

---

## 根因 3：Windows PowerShell 5.1 按 GBK 读 .ps1 → 中文乱码 → 解析崩

**现象**：脚本里含中文（如 `Write-Host "已启动..."` 或中文 prompt），PS 5.1 默认按系统 ANSI 代码页（中文 Windows = GBK/936）读取 `.ps1`。我们写的是 **UTF-8 无 BOM**，于是中文全变乱码，乱码里的引号/标点把字符串解析搞断 → `字符串缺少终止符: "`。

**解法**（二选一，推荐前者）：
- **脚本保持纯 ASCII**：所有 `Write-Host`、注释、prompt 都用英文。需要中文的内容（给 claude 的角色指令）放到**单独的 UTF-8 `.md` 文件**里，由 **claude 自己读**（claude 处理 UTF-8 没问题，PowerShell 不碰中文就不乱码）。
- 或：把 `.ps1` 存成 **UTF-8 with BOM**（PS 5.1 见 BOM 才会按 UTF-8 读）。

---

## 根因 4：`claude` 解析到 npm shim 而非 native exe

**现象**：PowerShell 里 `claude` 优先解析到 `...\AppData\Roaming\npm\claude.ps1`（npm shim），而非 `...\.local\bin\claude.exe`（native）。shim 多一层、易出问题。

**解法**：脚本里用 **native exe 全路径**调用：
```powershell
& "C:\Users\<user>\.local\bin\claude.exe" --dangerously-skip-permissions $prompt
```

---

## 根因 5：`--dangerously-skip-permissions` 首次需人工确认（设计如此）

**现象**：worker 起来后卡在
```
WARNING: Claude Code running in Bypass Permissions mode
  1. No, exit
  2. Yes, I accept
```

**说明**：这是 Claude Code 对 Bypass Permissions 模式的**强制一次性安全确认**，**故意不可自动跳过**（否则"跳过所有确认"本身就失去意义）。**接受一次后记住**，后续启动不再问。

**解法**：让用户在每个首次弹出的标签页里选 `2. Yes, I accept`（一次性）。若要彻底免确认，可预先在配置层写入"已确认"标记，但通常点一次最省事。

---

## 可用的最终方案（本次跑通的形态）

**文件**（均在项目 `.taskboard/` 下）：
- `launch-role.ps1`（纯 ASCII）：清 `CLAUDE*` 环境变量 → 设 git-bash 路径 → cd 项目 → native exe 拉 claude，prompt 用英文让 claude 去读 UTF-8 的 target/context 文件。
- `targets/taskboard-T{1,2,3}.md`（UTF-8）：角色目标与边界，**claude 读，不是 PS 读**。
- `open-tabs.ps1`（纯 ASCII）：循环 `wt -w taskboard new-tab ... -File launch-role.ps1 <role>` 开三标签页。

**用户操作**（在自己的终端，不经托管会话）：
1. 自检认证：`claude -p "ping"` 能回。
2. 一条短命令开三终端：`& "F:\...\.taskboard\open-tabs.ps1"`
3. 每个首弹标签页选 `2. Yes, I accept`。

**T0 分工**：T0 无法 spawn claude（403），改为**只读看板监控**——读 `docs/taskboard/TASK-*.md` 文件名状态流转 + `git diff` + 审核结论，全部不受认证限制；出停止门时找用户。

---

## 给 `taskboard-dev` 技能的建议更新

1. **新增"托管会话/Windows 启动"专章**（SKILL.md 或 role-t0.md）：明确"托管会话里 T0 不能自启 worker，必须把启动命令交给用户"，并给自检命令 `claude -p "ping"`。
2. **launcher 脚本（`taskboard_t0.py` 等）增加 Windows 适配**：
   - 检测到运行在托管会话（如 `CLAUDECODE` 存在且 spawn 测试 403）时，**只输出启动命令给用户**，不自己执行。
   - 在 Windows 上生成的 `.ps1` **强制纯 ASCII**（或 UTF-8 with BOM）；角色 prompt/目标一律放 UTF-8 `.md`，由 claude 读。
   - 调 claude 用 **native exe 全路径**，不用 npm shim。
   - 默认 `--agent-template` 在本技能场景应是 **`claude`**（本技能是 Claude Code 技能），不是 `codex`。
   - 文档注明 `--dangerously-skip-permissions` 首次需人工 `2. Yes, I accept`。
3. **把多 token `wt` 命令封装成单脚本**，让用户跑一条短命令，避免粘贴换行截断。
4. **降级条款保留**：若用户不便手动启动，T0 可降级到**原生 subagent**（在托管会话内运行，认证正常）执行 T1/T2/T3，但需逐角色隔离上下文。

---

_本文档基于一次真实排查整理（LeLamp project / 行空板 M10 修复 milestone）。_

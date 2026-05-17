<div align="center">

# CCB - Agent CLI 聚合和团队

<p>
  <img src="https://img.shields.io/badge/交互皆可见-096DD9?style=for-the-badge" alt="交互皆可见">
  <img src="https://img.shields.io/badge/模型皆可控-CF1322?style=for-the-badge" alt="模型皆可控">
</p>

[![Version](https://img.shields.io/badge/version-6.2.1-orange.svg)]()
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey.svg)]()

[English](README.md) | **中文**

[为什么 CCB](#为什么-ccb) · [最新亮点](#最新亮点) · [启动和退出](#启动和退出) · [配置控制](#配置控制) · [如何使用](#如何使用) · [如何安装](#如何安装) · [新版本记录](#新版本记录)

</div>

---

## 为什么 CCB

<details>
<summary><b>1. 一条命令，聚合所需 CLI 的所有操作和管理</b></summary>

在一个终端工作台里启动、attach、恢复、监督并操作 Claude、Codex、Gemini、OpenCode 和 Droid。

- 一个项目入口统一管理所有支持的 CLI agent
- 一个地方处理启动、恢复、attach 和关闭
- 一个连续的运行路径，避免每个工具各自处理

</details>

<details>
<summary><b>2. Agents 之间相互感知、相互通讯</b></summary>

命名 agent 可通过 `/ask`、广播和定向委派彼此发现、同步状态和交接任务。

- 通过命名 target 直接做 agent-to-agent 委派
- 通过广播同步让所有存活 agent 获得同一上下文
- 适合 builder、reviewer、QA 这类明确分工的工作流

</details>

<details>
<summary><b>3. 项目级专业 Agent 团队</b></summary>

按项目管理角色、pane 布局、provider 状态、worktree 隔离和生命周期连续性。

- 按项目组装角色明确的 agent 团队
- provider 状态保存在项目级 runtime 下
- 需要独立工作集时可启用 worktree 隔离
- 在重启、恢复和 pane supervision 中保持连续性

</details>

<div align="center">

![Showcase](assets/show.png)

<details>
<summary><b>演示动画</b></summary>

<img src="assets/readme_previews/video2.gif" alt="任意终端窗口协作演示" width="900">

<img src="assets/readme_previews/video1.gif" alt="融合vscode使用" width="900">

</details>

</div>

## 最新亮点

<details>
<summary><b>最新版本亮点</b></summary>

- **支持 callback ask 链式调用**：正在处理 CCB 任务的 agent 可用 `ccb ask --callback <agent>` 委派必须等待结果的子任务。
- **Nested ask 路由变为显式规则**：active CCB task 内 plain nested `ask` 会被拒绝；需要结果用 `--callback`，独立无需结果的工作用 `--silence`。
- **Callback 路由可持久恢复**：CCB 会记录 callback edge，把子任务结果作为 continuation task 交回父 agent，并修复重启窗口里的漏交 continuation。
- **Release smoke 跟随新 ask 契约**：真实平台 smoke 现在用 `ccb pend --watch` 观察 job，并在独立 nested stress ask 中使用 `--silence`。
- **Ask skill 已补齐工作流说明**：Claude、Codex 和 Droid ask skill 现在记录 callback 委派和提交后停止的规则。

完整历史见 [新版本记录](#新版本记录)。

</details>

## 启动和退出

### 常用命令

```bash
ccb                    # 按 .ccb/ccb.config 启动默认 agent
ccb -s                 # 安全启动：保留 agent 自身配置的权限策略
ccb -n                 # 重建 .ccb（保留 ccb.config），再重新启动
ccb kill               # 停止当前项目相关后台
ccb kill -f            # 强制清理项目残留后再配合 ccb -n 使用
```

tmux 复制粘贴：鼠标左键拖拽即可复制，`Ctrl+Shift+V` 粘贴。

## 配置控制

`ccb` 的行为由 `.ccb/ccb.config` 控制。它是项目级、用户自己维护的配置文件；如果不存在，CCB 会使用代码内置默认配置，不会自动写入新文件。

`.ccb/ccb_memory.md` 是项目全局记忆文档。

<details>
<summary><b>布局</b></summary>

第一行使用紧凑格式定义 agent 团队和 pane 布局：

```text
cmd; writer:codex, reviewer:claude; qa:gemini(worktree)
```

这个布局表示：

- `cmd` 是 shell pane
- `writer`、`reviewer`、`qa` 是 agent 名字，也是 pane 标题
- `codex`、`claude`、`gemini` 是 provider
- `;` 表示左右分栏，`,` 表示上下堆叠
- `qa` 使用独立 git worktree；没有写 `(worktree)` 的 agent 默认 `inplace` 运行

</details>

<details>
<summary><b>每个 Agent 的 API Key 和 Model</b></summary>

保留第一行 compact layout，然后只给需要独立 API、base URL 或 model 的 agent 增加 TOML 表：

```toml
cmd; builder:codex, reviewer:claude; research:gemini(worktree)

[agents.builder]
key = "sk-..."
url = "https://api.example.com/v1"
model = "gpt-5"

[agents.reviewer]
key = "sk-ant-..."
url = "https://api.anthropic.com"
model = "opus"

[agents.research]
key = "gemini-key"
model = "gemini-pro"
```

说明：

- `key` 和 `url` 是 agent 级快捷配置，支持 `codex`、`claude`、`gemini`。
- `model` 是 agent 级模型快捷配置，支持 `codex`、`claude`、`gemini`、`opencode`。
- 设置 `key` 或 `url` 后，该 agent 会使用显式 API 配置，不再继承全局 provider API 凭据。
- 更高级的 provider 环境变量放到 `agents.<name>.provider_profile.env`；同一个 agent 里不要把 provider API env 和 `key` / `url` 混用。
- 不要把真实 API key 提交到公开仓库。

常用 compact 示例：

```text
writer:codex, reviewer:claude
cmd; writer:codex, reviewer:claude; qa:gemini(worktree)
cmd; fast:codex, deep:codex
```

同一个 provider 也可以给不同 agent 配不同 API key：

```toml
cmd; fast:codex, deep:codex

[agents.fast]
key = "sk-fast..."
model = "gpt-5-mini"

[agents.deep]
key = "sk-deep..."
url = "https://api.example.com/v1"
model = "gpt-5"
```

</details>

<details>
<summary><b>后续更新</b></summary>

CCB v6 目前在 Linux、macOS 和 WSL 支持 `ccb update`。major 升级会整体替换已安装 runtime；旧项目第一次执行 `ccb` 时，会保留 `.ccb/ccb.config`，清理其余旧 `.ccb` 状态后再原地重建。

如果你是从 git checkout 里执行 `./install.sh install` 安装的，这种安装现在属于 source/dev 模式：

- 全局 `ccb` 和 `ask` 会链接回该 checkout，而不是使用复制快照
- CCB 自带 skills 和 helper scripts 也会跟随当前源码树
- source 安装不参与启动时自动更新提示
- 继续走源码开发路径时，用 `git pull` 或切换 commit 后重新运行 `./install.sh install`
- 或直接运行 `ccb update`，安装最新稳定 release，并把全局 `ccb` 链接切到托管 release 安装

```bash
ccb update              # 更新 ccb 到最新稳定版本
ccb update 6            # 更新到 v6.x.x 最高版本
ccb update 6.0          # 更新到 v6.0.x 最高版本
ccb update 6.0.5        # 更新到指定版本
ccb uninstall           # 卸载 ccb 并清理配置
ccb reinstall           # 清理后重新安装
```

</details>

## 如何安装

1. **Linux / macOS / WSL**<br>
   当 `ccb` 和你的 agent CLI 运行在同一个类 Unix shell 里时，使用这条路径。

```bash
git clone https://github.com/SeemSeam/claude_codex_bridge.git
cd claude_codex_bridge
./install.sh install
```

2. **Windows**<br>
   当你的 agent CLI 原生运行在 Windows 时，使用这条路径。

```powershell
git clone https://github.com/SeemSeam/claude_codex_bridge.git
cd claude_codex_bridge
powershell -ExecutionPolicy Bypass -File .\install.ps1 install
```

<details>
<summary><b>平台说明</b></summary>

- Linux 和 macOS 共用 `install.sh`。
- WSL 场景下，请让 `ccb` 和 agent CLI 都留在 WSL 内。
- 在 WSL 挂载盘项目上，项目 authority 仍然留在 `.ccb`，但运行态 state 可以迁移到本机 Linux state root，以保证 socket 和 agent runtime 的稳定性。
- 原生 Windows mux 仍在按 `psmux` 重构。
- 更完整的 Windows bootstrap 脚本在 `scripts/bootstrap-windows-test-env.ps1`。

</details>

安装说明：上面的命令目前是从 git checkout 安装。安装后运行 `ccb update`，CCB 会下载最新稳定 GitHub release 包，并自动完成托管 release 升级。

## 开发工具

维护者专用的 release 和仓库管理工具放在 `dev_tools/`。这些工具进入 git 管理，但不会打进官方 release 包。

## 如何使用

CCB 现在是 agent-first。你可以显式使用 `/ask`、显式使用 `$ask`，也可以让当前 agent 自己决定何时调用其他 agent。

| 模式 | 示例 |
| :--- | :--- |
| 显式 `/ask` | `/ask reviewer review the parser changes in src/parser.ts` |
| 显式 `$ask` | `$ask reviewer review the parser changes in src/parser.ts` |
| 隐式委派 | `让 reviewer 检查 parser 的边界情况，然后把问题汇总给我。` |

想明确指定目标时，用 `/ask reviewer ...` 或 `$ask reviewer ...`。想让当前 agent 自行判断是否委派时，直接用自然语言描述任务。

### 链式 Ask 调用

普通 `ask` 是异步提交：提交后当前 agent 应立即停止。如果某个 agent 已经在处理 CCB task，并且必须拿到另一个 agent 的结果才能回复原始调用者，就要使用 callback 路由：

```bash
ccb ask --callback reviewer <<'EOF'
Review this failing test and return the minimal blocker.
EOF
```

CCB 会记录 parent/child 关系，让当前 turn 结束，并在子任务完成后把结果作为新的 continuation task 交回父 agent。这支持 `agent2 -> agent4 -> agent1 -> agent3` 这类链式调用，不需要轮询，也不会阻塞当前 mailbox 队头。

active CCB task 外可以使用普通 `ask`。active CCB task 内，需要子任务结果时用 `--callback`；独立且成功结果不需要返回的工作用 `--silence`。

注意：如果要靠隐式使用，请先把 `ask` skill 的基本信息写进系统记忆；否则 Codex / Claude 这类 agent 可能会优先走自己内置的多 agent 方式，而不会主动调用 CCB 的 `ask`。

---

## 编辑器集成

<img src="assets/nvim.png" alt="Neovim 集成多模型代码审查" width="900">

结合 **Neovim** 等编辑器编写代码，同时让多个 agent 在侧边并行审查和迭代。

## 环境要求

- **Python 3.10+**
- **终端软件：** `tmux`

## 卸载

```bash
ccb uninstall
ccb reinstall

# 备用方式：
./install.sh uninstall
```

---

## 社区

📧 Email: `bfly123@126.com`
💬 微信: `seemseam-com`

感谢 [Linux.do 社区](https://linux.do) 在测试、反馈和讨论中的支持。

<div align="center">
<img src="assets/weixin.jpg" alt="微信群" width="300">
</div>

---


## 新版本记录

历史说明：下面较旧的发布记录里仍可能出现 `askd`、旧 flag 或已移除命令。这些内容仅作为 changelog 历史保留，不代表当前 CLI 入口。

<details open>
<summary><b>v6.2.1</b> - Callback Ask Chain Validation Hotfix</summary>

- 真实平台 smoke 脚本改用 `ccb pend --watch <job_id>` 观察已提交 job。
- fastpath stress 中 active agent 发起的独立 ask 改用 `--silence`，匹配 nested ask 契约。
- 保留并校准 6.2 callback ask chain 的 README 说明和发布记录。

</details>

<details>
<summary><b>v6.2.0</b> - Callback Ask Chain Release</summary>

- 新增 `ccb ask --callback <agent>`，让 active agent 可委派子任务，并在之后以 continuation task 接收子任务结果。
- active CCB task 内 accidental plain nested `ask` 会被拒绝；需要子任务结果用 `--callback`，独立且无需结果的工作用 `--silence`。
- 持久化 callback edge，并可在 dispatcher 重启后修复漏提交的 continuation。
- 更新 Claude、Codex、Droid ask skill 和生成的 project memory，补齐 callback-chain 指引。

</details>

<details>
<summary><b>v6.1.21</b> - Kill And Restart Cleanup Hotfix</summary>

- 即使命令 pane 在 socket response 写回前被关闭，`ccb kill -f` 仍会继续排队并执行 finalization。
- 项目级 kill cleanup 会保留完整 tmux socket path，并读取 lifecycle owner/keeper pid authority。
- process fallback 只匹配同一个 `--project` 的 CCB control-plane 命令，避免按 project root 过宽匹配。
- ccbd startup 和 terminal/missing job 的 late update 会清理 stale provider execution 文件。

</details>

<details>
<summary><b>v6.1.20</b> - Claude Active Version Cache Release</summary>

- 识别 source home 下 `~/.local/bin/claude` 指向的 Claude Code active version，并优先用于 managed Claude 启动。
- 将 source active version 复制进 CCB provider cache，再让 managed `.local/bin/claude` 指向缓存中的 active version。
- source active-version 布局不可用时，保留原有 shared-cache fallback 行为。
- 更新 provider workspace prepare 与 Claude binary-cache 契约，记录 source-home active-version 优先级。

</details>

<details>
<summary><b>v6.1.19</b> - Managed Ask Skill Projection Release</summary>

- Claude 继承的 `skills/` 和 `commands/` 改为通过 CCB projected assets 路由，不再 copy-sync，让系统 ask skill 可进入 managed Claude home。
- Droid 增加 managed `FACTORY_HOME`，会投射系统 `~/.factory/skills`，并使用 session-scoped Droid sessions root。
- Droid launch、execution polling 和 communicator session reader 现在会在重启或 session rotation 后继续跟随 managed session root。
- `ccb ask` 默认注入简洁回复指导，并新增 `--compact` / `--silence` 提交模式；旧 wait/output flags 作为兼容输入被忽略。

</details>

<details>
<summary><b>v6.1.18</b> - Heartbeat Timeout And Useful Tools Release</summary>

- running-job heartbeat 观察会保持为内部状态，连续三轮无进展后才以 `heartbeat_timeout` 终态收尾，并建议先发小任务测试通讯。
- provider completion 进展改为语义判断，cursor offset、polling timestamp、session snapshot bookkeeping 不再延长 completion deadline。
- `reliability_*` runtime state 会随持久化保留，恢复后的 provider job 不会重置 timeout deadline。
- 将 `useful_tools/useful_tools.zip` 纳入版本化可选工具，随 release artifacts 一起分发。

</details>

<details>
<summary><b>v6.1.17</b> - Completion Binding And Codex Session Hotfix</summary>

- Claude Stop hook completion artifact 现在绑定结构化外层 `CCB_REQ_ID`，转发文本或工具输出不会再把 completion 写到旧 job。
- Codex session identity 不再依赖 memory projection freshness，`.ccb/ccb_memory.md` 更新只刷新记忆，不强制新开对话。
- 合入 PR #205 mailbox 恢复：attempt 已终态时，可清理 stale terminal `task_request` queue head。
- 增加 transcript 解析、provider finish hook、Codex resume 和 mailbox stale-head 清理的回归覆盖。

</details>

<details>
<summary><b>v6.1.16</b> - Memory Handoff And Claude Route Hotfix</summary>

- 生成的 managed-memory bundle 会加入 CCB 自己的 submit-only ask 协作规则，避免旧共享记忆文本重新引入 polling/waiting 行为。
- 新建 `.ccb/ccb_memory.md` 模板同步使用 fire-and-forget handoff 表述。
- managed Claude 启动会优先使用 ccswitch 更新后的 `~/.claude/settings.json` 路由配置，而不是旧 caller-shell `ANTHROPIC_BASE_URL`。
- 补充 Claude 路由继承契约，并增加优先级回归测试。

</details>

<details>
<summary><b>v6.1.15</b> - Kill Shutdown Reliability Hotfix</summary>

- 远程 `ccb kill` 会等待记录下来的 `ccbd` 和 keeper pid 退出，不再只信任 lifecycle unmounted。
- 写最终 shutdown report 前会把 lifecycle finalize 到 stopped/unmounted，让 `ccb cleanup` 可在 kill 后直接运行。
- 增加 prepared pid 快照、远程 lifecycle finalize 和 shutdown intent 顺序的回归测试。

</details>

<details>
<summary><b>v6.1.14</b> - macOS Claude Keychain Boundary Follow-up</summary>

- 将 managed Claude `Library/Keychains` fallback 记录为 agent-local secret auth 兼容状态。
- 明确 support bundle 不能跟随 fallback Keychains symlink，storage 诊断会把它分类为 secret auth 状态。

</details>

<details>
<summary><b>v6.1.13</b> - macOS Claude Keychain Fallback</summary>

- macOS 上如果 `com.apple.security.plist` 不存在，会把 `Library/Keychains` 链接进 managed Claude home，保留 Claude 登录查找能力。
- 关闭 Claude auth 继承时会移除 fallback Keychains 链接。
- Storage 诊断会把 fallback Keychains symlink 分类为 secret auth 状态。

</details>

<details>
<summary><b>v6.1.12</b> - Claude Tmux Permission Release</summary>

- 打包已合并的 Claude auto-permission pane 修复，避免 tmux 启动卡在 bypass permissions 确认框。
- 继续包含 v6.1.11 的 WSL cleanup smoke 对齐和 Claude rollback-cache 保留修复。

</details>

<details>
<summary><b>v6.1.11</b> - WSL Cleanup Smoke Alignment</summary>

- WSL mounted-drive storage cleanup smoke 已对齐当前 relocated-runtime shared-cache 契约。
- 包含 v6.1.10 的 Claude cleanup rollback 保留修复。

</details>

<details>
<summary><b>v6.1.10</b> - Claude Cleanup Rollback Hotfix</summary>

- `ccb cleanup` 现在会保留当前 Claude Code 版本和一个 rollback 版本。
- 修复 macOS/WSL real-platform storage cleanup smoke 中的 Claude current/rollback 保留预期。

</details>

<details>
<summary><b>v6.1.9</b> - 存储去重与关闭加固</summary>

- 通过 Codex 投影资产 symlink/shared bundle，以及 Claude/Gemini 可重建 cache 路由和清理，减少 `.ccb` 体积增长。
- `ccb cleanup` 现在会回收旧 Claude shared versions、Gemini shared cache、Claude 可重建 cache 和过期 pane crash log。
- 加固 `ccb kill`：提前快照旧 `ccbd`/keeper pid，等待并兜底终止，同时避开新的 backend generation 竞态。
- 修复 Claude tmux pane 中 bypass permissions 确认框无法交互导致的启动失败。

</details>

<details>
<summary><b>v6.1.8</b> - macOS Claude Keychain Preference Hotfix</summary>

- macOS managed Claude home 现在会继承 `Library/Preferences/com.apple.security.plist`，让 Claude 登录查找能解析预期的默认 Keychain。
- 该 preference 投影仍绑定 auth 继承；关闭 Claude auth 继承时会删除。

</details>

<details>
<summary><b>v6.1.7</b> - Codex 记忆刷新 Hotfix</summary>

- `.ccb/ccb_memory.md` 变化后，Codex 会刷新共享项目记忆，不再继续 resume 旧 AGENTS 上下文。
- Claude 和 Droid ask skill 改为 heredoc 提交，并在提交后立即结束。

</details>

<details>
<summary><b>v6.1.6</b> - 启动与 Claude 认证 Hotfix</summary>

- 修复首次启动时 ccbd start 与 heartbeat maintenance 的 pane 竞争。
- `.ccb/ccb_memory.md` 是唯一的 CCB 共享记忆文档。
- 增加 Claude macOS `Claude Code-credentials` Keychain 查找。

</details>

<details>
<summary><b>v6.1.5</b> - Tmux 启动 Hotfix</summary>

- 修复启动时可能出现的 `Cannot split: pane ... does not exist` 和 `respawn pane failed: can't find pane`。
- Provider pane 仍保持原 managed respawn 启动路径。

</details>

<details>
<summary><b>v6.1.4</b> - 项目共享记忆 V1</summary>

- `.ccb/ccb_memory.md` 是项目全局记忆文档。

</details>

<details>
<summary><b>v6.1.2</b> - Provider 存储边界加固</summary>

- **存储分类显式化**：`ccb doctor storage` 现在区分 authority、session state、secret、workspace、user content、projected config、rebuildable cache 和 startup authority bundle。
- **安全清理入口落地**：`ccb cleanup` 会在 `ccbd` 或 ask job 活跃时拒绝执行，只清理安全的可重建 provider cache，并保留 session、auth 和当前 Claude binary。
- **Shared Cache 护栏补齐**：未来 provider shared-cache 路径统一落在 effective runtime-state root 下，并加入 WSL drvfs 安全检查和 manifest 创建。

</details>

<details>
<summary><b>v6.1.1</b> - Ask Skill 和记忆注入清理</summary>

- **只安装 Ask Skill**：Claude、Codex 和 Droid/Factory 安装现在只发布 `ask` skill，并清理 `ping`、`pend`、`all-plan`、`file-op` 等旧 CCB helper skill。
- **移除全局记忆注入**：安装器不再向全局 `CLAUDE.md`、安装目录 `AGENTS.md` 或 `.clinerules` 写入 CCB 协作块；已存在的 CCB 标记块会在安装时清理。
- **删除旧 Skill 源模板**：仓库内的 skill 模板现在只保留各 provider 的 `ask` skill 资产。

</details>

<details>
<summary><b>v6.1.0</b> - CCBD Ask 稳定化和 Observer 收敛</summary>

- **Ask Submit Fastpath 稳定化**：`ccb ask` 不再等待 provider readiness、mailbox history projection 或长 maintenance tick，提交回执保持有界
- **Lifecycle / Shutdown Race 收口**：stop-all、shutdown、restart 和后台 supervision 不再通过 stale work 复活 stopped runtime 或回退 terminal job
- **Provider Completion Recovery 加固**：Codex polling 会跟随 restart 后的新 session binding，从当前 managed session log 读取回复并推进 job 终态
- **Mailbox Summary Read Model 落地**：日常 `queue`、`inbox`、`pend` 路径优先读取维护好的 summary，summary 缺失或损坏时显式 degraded
- **Observer Surface 明确弱化**：`pend`、`watch`、`queue`、`inbox` 都是非权威快照；需要 lineage 细节时使用 `ccb trace <id>`
- **真实平台验证补齐**：GitHub Actions 新增 macOS 和 WSL ccbd/ask smoke、通讯矩阵、短 soak、fastpath stress

</details>

<details>
<summary><b>v6.0.29</b> - WSL Runtime State 迁移</summary>

- **运行态移出挂载盘**：在 `/mnt/<drive>/...` 下的 WSL 项目中，项目 authority 仍留在 `.ccb`，`ccbd/` 和 agent runtime state 会迁移到本机 Linux state root，并写入显式 marker
- **诊断和 Bundle 映射更新**：doctor 输出和 support bundle 现在会暴露 project anchor、runtime-state root、迁移原因，并把 relocated runtime 文件映射回逻辑 `.ccb` archive 路径
- **Provider Lookup 和 Ask Routing 保持稳定**：relocated runtime 目录仍能回溯到 project anchor，用于 session discovery 和 ask sender attribution，Linux/macOS 默认布局不变
- **Runtime marker 会校验**：relocated runtime marker 和 ref 现在会拒绝格式错误或归属不匹配的 payload，避免旧残留悄悄把一个项目映射到另一个项目
- **WSL Smoke 与最终合同一致**：发布 smoke 现在检查 relocation 的最终 runtime-root 路径，而不是把第一阶段的迁移结果当成 socket fallback 终点

</details>

<details>
<summary><b>v6.0.28</b> - WSL Control Plane Socket 加固</summary>

- **加固 WSL Control Plane 启动**：keeper 和 daemon readiness probe 现在共用配置化 control-plane RPC timeout，不再使用更短的硬编码预算，避免把挂载盘上的慢启动误判为 config drift
- **解耦 Socket Server Accept 路径**：ccbd 现在把 accept 连接和串行 worker lane 分开，一个慢请求或不完整请求不会再阻塞新的 control-plane probe 或 heartbeat
- **增加短暂 Connect Retry**：Unix socket client 只会在现有 timeout 预算内重试短暂 connect race，不会重试已经发送的 RPC 或 mutating operation
- **刷新 README**：公开 README 已按当前 agent CLI hub / agent team 工作流重新组织，并更新 release 指引

</details>

<details>
<summary><b>v6.0.27</b> - macOS Foreground Attach Timeout 加固</summary>

- **拆分 Foreground Attach Timeout**：交互式 `ccb` 启动现在使用 foreground attach 专属 RPC 和 target-ready 预算，不再复用很短的 daemon probe timeout
- **降低 macOS Attach Race**：foreground attach 现在能容忍 daemon 启动成功后稍慢的 `ccbd` ping、tmux namespace/window 可见性延迟，不再把这类延迟当成 daemon 启动失败
- **Attach 失败信息更清晰**：错误现在区分 control-plane ping 无响应，以及 daemon 已响应但 project namespace 尚不可 attach 两类情况

</details>

<details>
<summary><b>v6.0.26</b> - macOS 安装与 Claude Ask 清理</summary>

- **修复 macOS Release 安装**：release 安装生成的 CLI wrapper 现在会绑定 managed `.venv` Python，避免安装 `watchdog` 等可选依赖后运行环境漂移
- **修复 WSL 安装测试**：watchdog 安装回归测试会显式确认 WSL 非交互安装模式，让 CI 覆盖预期的可选依赖路径
- **精简 Claude Ask Prompt**：managed Claude `ask` 不再把本地 ask skill runtime 文本注入 prompt body，agent 间消息只保留 request anchor 和用户原始消息

</details>

<details>
<summary><b>v6.0.25</b> - Gemini Managed Home 对齐</summary>

- **修复 Gemini 登录继承**：managed Gemini pane 现在会把 `GEMINI_CLI_HOME` 设置为隔离 home 根目录，让 Gemini CLI 从同一个 managed 边界读取投影后的 `.gemini/.env`、settings 与登录状态
- **补充回归覆盖**：launcher 测试锁定 `HOME`、`GEMINI_CLI_HOME` 与 `GEMINI_ROOT` 的对齐契约，并防止 settings 再写入嵌套 `.gemini/.gemini`
- **精简社区联系方式**：移除独立的 Linux.do 联系入口，保留联系区块后面的 Linux.do 社区致谢

</details>

<details>
<summary><b>v6.0.24</b> - WSL 官方登录传输环境</summary>

- **继承 WSL Provider 传输环境**：managed provider pane 现在会保留官方登录与 Codex Apps/MCP 联网路径所需的用户会话 proxy、CA、browser 与 WSL interop 环境
- **保持 Managed 隔离边界**：传输环境继承集中在共性层，不允许调用者全局 `CODEX_HOME`、`GEMINI_ROOT`、`CLAUDE_PROJECTS_ROOT` 或 `CCB_CALLER_*` runtime authority 覆盖 agent 级 managed state
- **扩展 Gemini 登录投影**：managed Gemini home 现在会投影 allowlist 后的 `.gemini/.env` API 凭据、`google_accounts.json` 与 `GEMINI_CLI_HOME`，诊断包仍会排除复制的 auth artifacts
- **加固 Opencode Session 检测**：opencode 现在只有在 provider 专属 runtime env 存在时才进入 env-session 模式，避免 stale 通用 `CCB_SESSION_ID` 污染
- **刷新社区入口**：README 已更新微信群二维码，并加入 Linux.do 社区致谢，方便用户从公开项目页找到当前交流渠道

</details>

<details>
<summary><b>v6.0.23</b> - CI 矩阵稳定化</summary>

- **Release CI 已转绿**：最新 release 现在指向完整 GitHub Actions 测试通过的提交，覆盖 Ubuntu、macOS、WSL 与安装 smoke
- **Provider 黑盒覆盖聚焦**：重型 pane-backed provider restart / rotate / settle 测试改为在专门的 Ubuntu provider-blackbox job 中运行，不再重复进入每个 OS 与 Python 矩阵单元
- **修复 macOS socket 测试 race**：ccbd socket 测试现在会等 daemon socket 能响应 ping 后再发 RPC，避免 macOS runner 上的 readiness 竞态

</details>

<details>
<summary><b>v6.0.22</b> - Claude macOS 登录继承</summary>

- **继承 macOS Keychain 登录态**：managed Claude 启动现在会从 macOS Keychain 读取 Claude Code 官方登录凭据，并在隔离 Claude home 内物化等价的项目级 `.claude/.credentials.json`
- **刷新 Claude 账号元数据**：继承的 `.claude.json` 账号元数据现在会从 source home 刷新，同时保留 managed workspace trust，并排除 source workspace trust 与 API key secret
- **修复默认配置启动**：keeper 现在会把缺失 `.ccb/ccb.config` 视为使用代码内置默认项目配置，而不是在 `ccbd` mount 前提前退出
- **扩展回归覆盖**：新增测试锁定 Keychain 投影、账号元数据刷新以及关闭 auth 继承后的清理路径

</details>

<details>
<summary><b>v6.0.21</b> - Claude Hook 资产投影</summary>

- **继承 CodeIsland Hook 资产**：managed Claude 启动现在会在继承的 Claude hooks 调用 `$HOME/.codeisland/...` 时复制源 home 中对应的 `.codeisland/`，避免隔离 Claude home 内缺少 hook 脚本
- **保持配置边界**：第三方 hook 资产只会在开启 Claude config 继承、且继承的 hook payload 明确引用对应 home-relative 路径时复制
- **诊断脱敏扩展**：诊断包现在会排除复制到 provider-state 下的 `.codeisland/` 资产，同时继续包含普通 managed Claude settings 以便排障

</details>

<details>
<summary><b>v6.0.20</b> - Claude 官方登录 source home 修复</summary>

- **Claude 官方登录 source home 修复**：managed Claude 启动现在会把 `.ccb/agents/*/provider-state/*/home` 识别为隔离运行时 home，而不是用户源 home，因此官方浏览器登录凭据会从真实账号 home 复制
- **Claude 凭据路径覆盖**：managed Claude home 现在会投影 Claude Code 官方登录使用的 `.claude/.credentials.json`，并继续兼容 `.config/claude-code/auth.json`
- **回归覆盖补充**：新增测试锁定 source-home 回退、launcher 投影、诊断脱敏以及 workspace 准备阶段的 Claude 官方登录继承

</details>

<details>
<summary><b>v6.0.19</b> - Claude 官方登录继承</summary>

- **Claude 官方登录凭据投影**：managed Claude home 现在会把 Claude Code 官方登录使用的 `.claude/.credentials.json` 投影到隔离运行时中，使浏览器登录态也能被 CCB 继承，而不再只有 API token / settings 这一路生效
- **Managed 登录态保留**：当全局 Claude 登录凭据消失、但 managed Claude 已经持有有效项目级登录态时，启动现在会保留这份 managed 登录凭据，不再在重启时被静默丢掉
- **鉴权清理与回归覆盖**：关闭 auth 继承时会清理陈旧的 Claude 登录凭据副本，并新增针对投影、清理和 launcher 启动路径的回归测试

</details>

<details>
<summary><b>v6.0.18</b> - Gemini Hook 空回复保护</summary>

- **Gemini 空 Hook 回复不再误烧掉任务**：managed Gemini 的 `AfterAgent` hook 如果在空回复下触发，现在会降级成 `incomplete`，不再被当作错误的 exact completion 直接终结任务
- **Exact Hook 轮询更保守**：Gemini exact-hook 轮询现在会忽略没有回复文本的 `completed` hook artifact，让 observed session-stability 或 timeout reliability 路径继续收口，而不是接受空白终态
- **补齐回归覆盖**：新增针对 finish-hook artifact 写入层与 Gemini execution-service 轮询层的空回复保护测试，锁住这条回归路径

</details>

<details>
<summary><b>v6.0.17</b> - Gemini 自定义端点环境变量透传修复</summary>

- **Gemini 端点覆盖恢复**：managed Gemini 启动现在会端到端保留 `GOOGLE_GEMINI_BASE_URL`，使走自定义 endpoint 或代理的 Gemini CLI 不再悄悄回退到 Google 默认生产 API 地址
- **Gemini 模型环境变量放行**：control-plane 与 provider-profile 的环境变量过滤现在会保留 `GEMINI_MODEL`，隔离 Gemini agent 启动时不再吞掉显式模型选择
- **配置快捷项对齐 CLI 语义**：Gemini 的 `key` / `url` 快捷配置现在会物化为当前 Gemini CLI 实际读取的环境变量，避免 `ccb.config` 路由与 shell 直跑行为不一致

</details>

<details>
<summary><b>v6.0.16</b> - Codex 插件投影与 cmd shell 兼容性修复</summary>

- **Codex 插件投影修复**：managed Codex home 现在会把 `.tmp/plugins/` 与 `.tmp/plugins.sha` 作为插件 authority 一起投影，使隔离 agent 不再出现“配置声明启用了插件，但实际 marketplace / 插件资产缺失”的不一致状态
- **插件刷新语义收紧**：启动现在把 managed 插件投影作为一个完整 authority 单元刷新；当 source 投影消失时会清理旧的 managed 残留，而当 source `plugins.sha` 未变化时又不会重复全量拷贝
- **cmd Shell / 会话环境加固**：`cmd` pane 现在会直接 `exec` 解析后的用户 shell，并保留 `DISPLAY`、`WAYLAND_DISPLAY`、`DBUS_SESSION_BUS_ADDRESS`、`XAUTHORITY`、`SSH_AUTH_SOCK` 等普通用户会话环境变量，提升 fish/zsh 与 GUI 命令兼容性

</details>

<details>
<summary><b>v6.0.15</b> - Codex 路由权威与前台 attach 打磨</summary>

- **Codex 显式路由权威**：managed Codex home 现在会把 agent 私有 `config.toml` 与 `auth.json` 物化为显式 `key` / `url` 路由的唯一权威，使 agent 级 API 覆盖真正替代系统级 provider 路由，而不是漂回全局配置
- **Codex 会话命名空间轮换**：managed Codex 启动现在会为显式路由生成 authority 指纹，把可复用 session 绑定也打上该 authority；当绑定路由与当前路由不一致时，会在启动前轮换旧 `sessions/` 命名空间
- **前台 attach 体验加固**：交互式 `ccb` 启动现在会用真实终端视口初始化 tmux namespace，并在 attach 后做一次 best-effort client refresh，避免首次显示依赖手工刷新

</details>

<details>
<summary><b>v6.0.14</b> - Claude logout 恢复加固</summary>

- **managed Claude 登录态保留**：当全局 Claude home 已执行 logout 时，managed Claude home 现在会保留 agent 私有的本地登录态，避免项目内重新登录后重启再次掉回浏览器链接循环
- **auth 投影语义收紧**：当 source home 仍有 auth 时，启动继续按 source 刷新；当 source auth 缺失时，不再把它解释为“必须清空 managed auth”，而 `inherit_auth = false` 仍会清理旧的复制鉴权
- **启动链路回归覆盖补齐**：新增回归测试覆盖 projection 层、provider workspace 准备以及 Claude launcher 启动路径，锁住这条 logout 后恢复语义

</details>

<details>
<summary><b>v6.0.13</b> - macOS release 路径与预览打包修复</summary>

- **macOS release 路径补齐**：共享 release 产物命名和 updater 解析现在同时覆盖 macOS universal 包以及 Linux/WSL release 资产
- **source dev 安装模式**：从 git checkout 执行安装后会继续链接到实时源码树，不参与启动自动更新提示，但仍可通过 `ccb update` 切换到托管 release 安装
- **Agent API / Model 简写**：`.ccb/ccb.config` 现在支持 agent 级扁平 `key`、`url`、`model` 字段，让常见 provider 覆盖保持简洁
- **预览打包加固**：preview release 导出现在会排除仓库内构建过程生成的输出路径，修复 `dist-macos-smoke` 这类目录上的递归自拷贝失败

</details>

<details>
<summary><b>v6.0.12</b> - 非阻塞启动更新提示</summary>

- **缓存化启动提示**：交互式前台 `ccb` 启动现在会读取安装级缓存的 release 元数据，只有本地已知存在更高稳定版时才提示升级
- **后台刷新**：缓存缺失或过期时会用短网络预算在后台刷新，不再阻塞项目启动路径
- **升级 / 延后 / 静默**：启动提示支持立即升级、对当前版本延后提醒，或静默当前版本
- **启动边界保持干净**：release 更新检查仍是 advisory 逻辑，不进入项目生命周期启动事务

</details>

<details>
<summary><b>v6.0.11</b> - 项目启动热修复</summary>

- **冷启动 namespace 修复**：项目 tmux namespace 冷启动时，`no server running on <project socket>` 现在会被判定为“namespace 缺失，需要创建”，不再被错误打成通用 tmux inspect 失败
- **release 回归覆盖补齐**：新增针对 namespace backend/state 的回归测试，锁住这条冷启动路径，覆盖 `ccb -> ping -> kill` 生命周期闭环
- **契约语义补全**：startup supervision contract 现在明确把 project-socket 上的 `no server running` 定义为重建信号，而不是致命 inspect 失败

</details>

<details>
<summary><b>v6.0.10</b> - 启动预算加固与 Gemini 登录继承</summary>

- **Gemini 登录继承**：managed Gemini home 现在会为 `oauth-personal` 投影登录鉴权选择与 `oauth_creds.json`，并在关闭 auth 继承时清理旧的复制凭据
- **统一 tmux 就绪预算**：项目自有 pane 的 `respawn-pane` 现在与 namespace create/reflow 共用同一套 tmux ready-retry 预算，降低启动与后台 supervision 中瞬时 `no server running` 失败
- **后台启动兼容性加固**：后台 lifecycle 启动继续保持 supervision 兼容，同时把 readiness probe 超时与业务 RPC budget 解耦
- **诊断包凭据脱敏**：diagnostic bundle 现在会像其他 provider 凭据一样排除 Gemini `oauth_creds.json`

</details>

<details>
<summary><b>v6.0.9</b> - 跨平台生命周期与 watch 稳定性增强</summary>

- **WSL 兼容性修复**：项目 runtime 现在会避开不支持 Unix socket 的 WSL 挂载盘路径，同时加固 installer staging 与 tmux namespace readiness
- **macOS 生命周期加固**：启动、恢复与项目身份识别路径已收紧，macOS 现在按与 Linux 一致的 lifecycle authority 模型收口，不再间歇性漂移
- **Respawn 重试边界收口**：tmux respawn 期间的瞬时 fork、server exit、readiness 失败现在在 runtime supervision 边界内重试，不再向上冒泡成伪生命周期故障
- **Watch 重连恢复**：observer recovery 在 daemon 短暂失联后可以从持久化状态恢复，同时继续严格遵守内部截止时间
- **跨平台 CI 覆盖扩展**：GitHub Actions 现在同时覆盖 macOS install smoke、WSL 兼容路径与既有 Linux 测试矩阵

</details>

<details>
<summary><b>v6.0.7</b> - 生命周期 authority 与停机稳定性增强</summary>

- **Keeper 持有生命周期 authority**：keeper 现在通过权威 `lifecycle.json`、generation fence 和 namespace epoch 跟踪来推进项目生命周期
- **Mounted 状态读路径修复**：`ping ccbd` 与 `ping agent` 现在从当前 authority 读取 mounted/runtime 状态，不再在恢复后漂移到旧的失败视图
- **Shutdown 事务加固**：`ccb kill` 和 `ccb kill -f` 现在会在停机事务里终结所有非终态 job，重启后不会再通过 restore 或 auto-retry 复活旧执行
- **真实黑盒复现已收口**：真实 `ask -> kill -f -> restart` 路径现在会稳定收口为 `project_shutdown`，不再残留活动执行

</details>

<details>
<summary><b>v6.0.6</b> - Agent 隔离稳定性增强与 kill 生命周期修复</summary>

- **Agent 隔离稳定性增强**：Codex、Claude、Gemini 的 managed agent 会把会话状态稳定保存在项目级 `.ccb/agents/<agent>/provider-state/...` 下
- **重启继承更安全**：重启只恢复对应 managed agent 自己的历史，不再因为工作目录相同而吸收手工运行 provider 的对话
- **项目 Provider Dotfile 保护**：managed 启动不再改写项目级 `.claude`、`.gemini` 或 `.codex` provider dotfiles
- **Kill 生命周期修复**：`ccb kill` 主动销毁当前项目 tmux session 后，交互式 `ccb` 不再误报前台 attach 失败

</details>

<details>
<summary><b>v6.0.5</b> - Agent 隔离稳定性增强</summary>

- **Agent 隔离稳定性增强**：Codex、Claude、Gemini 的 managed agent 会把会话状态稳定保存在项目级 `.ccb/agents/<agent>/provider-state/...` 下
- **重启继承更安全**：重启只恢复对应 managed agent 自己的历史，不再因为工作目录相同而吸收手工运行 provider 的对话
- **项目 Provider Dotfile 保护**：managed 启动不再改写项目级 `.claude`、`.gemini` 或 `.codex` provider dotfiles

</details>

<details>
<summary><b>v6.0.4</b> - 旧版升级兼容热修复</summary>

- **向后兼容的 Release 资产**：Linux release tarball 现在会额外带一个兼容别名，旧版 6.x updater 即使误把资产名当作解压目录，也仍然能找到安装器
- **旧客户端升级链路恢复**：现有 `v6.0.1` 和 `v6.0.2` 安装现在可以直接升级到最新稳定版，不需要先拥有修过的本地 updater
- **新 updater 仍保持正确**：当前 runtime 继续按正确的解压目录工作，不依赖这个兼容别名

</details>

<details>
<summary><b>v6.0.3</b> - 自升级 tarball 热修复</summary>

- **Release 升级修复**：`ccb update` 现在会正确定位解压后的 release 目录，不再把 `.tar.gz` 资产名当成目录
- **安装器接力恢复**：自升级现在能正确找到 release 包里的 `install.sh` 并走完整替换流程
- **Release 构建卫生**：Linux release 打包现在会忽略本地 `.ccb-requests/` 残留，正式构建不再被运行时垃圾阻塞

</details>

<details>
<summary><b>v6.0.2</b> - caller 归因修复、邮箱路由稳定化与 macOS 安装提醒</summary>

- **Caller 身份归因修复**：`ccb ask` 现在会保留真实发起 agent 身份，reply 不再误记成 `user`
- **Reply 路由更稳定**：异步委派任务的回复现在会回到正确邮箱链路，包括 `cmd` 锚点场景
- **Mixed-Case Agent 恢复修复**：配置里使用大小写混合的 agent 名称时，布局恢复与启动不再漂移
- **macOS Homebrew 提醒**：`install.sh` 现在会在缺少 Homebrew 时先给出明确警告，再继续 tmux 等依赖安装说明

</details>

<details>
<summary><b>v6.0.1</b> - Release 归档清理与更安全的升级解压</summary>

- **源码归档清理**：移除误提交的 pytest 临时产物，GitHub 源码归档重新保持干净
- **更严格的 tar 校验**：升级解压前会先拒绝不安全的 symlink 目标
- **失败提示更直白**：遇到不安全归档时，会明确提示使用 release 资产或干净源码包
- **回归测试补齐**：新增测试阻止临时测试产物再次被跟踪进仓库

</details>

<details>
<summary><b>v6.0.0</b> - 原生多 Agent Runtime、稳定原生通信、仅 Linux/WSL 自动升级</summary>

**🚀 全新运行时方向：**
- **无限并发 agent 基础**：CCB v6 被定义为几乎无限量 agent 互调与编排的运行时底座
- **Agent 身份独立**：每个 agent 都可以拥有不同的角色、任务归属、skill 库和人格
- **公开命令面收口**：面向用户的公开工作流继续聚焦 `ccb`、`ccb -s`、`ccb -n`、`ccb kill`、`ccb kill -f`

**🧱 项目重建语义：**
- **保留配置清理旧态**：首次在 pre-6 项目中执行 `ccb` 时，会保留 `.ccb/ccb.config`，清除其余旧 `.ccb` 运行时状态，然后在本地重建
- **运行时标记**：现代项目会写入 `.ccb/project-runtime.json`，避免把当前 runtime 误判为旧状态
- **Worktree 安全护栏**：CCB 管理的 git worktree 若存在脏改动或未合并分支，仍会阻断破坏性清理并要求用户先处理

**🔄 升级策略：**
- **仅 Linux/WSL**：`ccb update` 在 6.x 线目前只对 Linux/WSL 开放
- **仅使用 Release 资产升级**：每个版本仍会一起发布源码 tag，但 `ccb update` 在 6.x 线只安装 GitHub release 资产，不再使用源码压缩包
- **稳定发布升级**：默认升级目标改为最新稳定 release，而不是漂移的 `main`
- **Major 升级确认**：升级到 `6.0.0` 时会先要求明确确认，再替换已安装 runtime

**🤖 Provider 稳定性：**
- **Gemini 多轮稳定性**：Gemini 完成判定现在会持续跟踪 tool activity，不会在第一句稳定规划文本上提前结束

</details>

<details>
<summary><b>v5.3.0</b> - CLI 收口、显式 worktree 模式、Gemini 完成判定修复</summary>

**🚀 面向用户的 CLI 收口：**
- **主入口更清晰**：公开工作流收敛为 `ccb`、`ccb -s`、`ccb -n`、`ccb kill`、`ccb kill -f`
- **模型控制面保留**：`ask`、`ping`、`pend`、`watch` 继续保留给 agent 侧编排使用，但不再挤占主帮助入口

**🧱 工作区语义显式化：**
- **默认 inplace**：compact `ccb.config` 现在默认展开为 `workspace_mode='inplace'`
- **显式隔离**：只有写成 `agent:provider(worktree)` 时，agent 才会进入独立 git worktree
- **Agent 变更更稳**：新增 agent 不再影响已有 worktree；删除或改名 worktree agent 时，干净分支会自动退休，脏分支或未合并分支会阻断并提醒

**🛠 重建与恢复加固：**
- **保留配置重建**：`ccb -n` 会重建项目运行时状态，但保留 `.ccb/ccb.config`
- **陈旧注册清理**：启动与重建前会先清理已注册但路径丢失的 git worktree
- **Kill 提醒**：`ccb kill` 在发现 worktree agent 仍有未合并或脏状态时会显著提醒用户

**🤖 Gemini 完成判定修复：**
- **不再首轮提前结束**：Gemini 轮询完成检测现在会跟踪 tool call 活动，不会再把第一轮稳定的“我先开始分析/搜索”文本误判成最终回复

</details>

<details>
<summary><b>v5.2.6</b> - 异步通信修复 & Gemini 0.29 兼容</summary>

**🔧 Gemini CLI 0.29.0 适配：**
- **双哈希策略**：会话路径发现同时支持 basename 和 SHA-256 格式
- **自动启动**：`ccb-ping` 和 `ccb-mounted` 新增 `--autostart` 标志，可自动拉起离线 provider
- **清理路径**：僵尸会话清理现已统一收敛到 `ccb kill -f`

**🔗 异步通信修复：**
- **OpenCode 死锁**：修复会话 ID 固定导致第二次异步调用必定失败的问题
- **旧兼容完成检测**：旧文本型 provider 在降级模式下仍可容忍不完全匹配的 `CCB_DONE`
- **req_id 正则**：`opencode_comm.py` 同时匹配旧 hex 和新时间戳格式
- **Gemini 空闲超时**：Gemini 漏写 `CCB_DONE` 时自动检测回复完成（默认 15s，可通过 `CCB_GEMINI_IDLE_TIMEOUT` 调整）
- **Gemini Prompt 加固**：强化指令格式，降低 `CCB_DONE` 遗漏率

**🛠 其他修复：**
- **lpend**：registry 过期时优先使用更新鲜的 Claude 会话路径

</details>

<details>
<summary><b>v5.2.5</b> - 异步护栏加固</summary>

**🔧 异步轮次停止修复：**
- **全局护栏**：在 `claude-md-ccb.md` 中添加强制 `Async Guardrail` 规则，同时覆盖 `/ask` 技能和直接 `Bash(ask ...)` 调用
- **标记一致性**：`bin/ask` 现在输出 `[CCB_ASYNC_SUBMITTED provider=xxx]`，与其他 provider 脚本格式统一
- **技能精简**：Ask 技能规则引用全局护栏并保留本地兜底，单一权威源

此修复防止 Claude 在提交异步任务后继续轮询/休眠。

</details>

<details>
<summary><b>v5.2.3</b> - 项目内历史记录 & 旧目录兼容</summary>

**📂 项目内历史记录：**
- **本地存储**：自动导出改为写入 `./.ccb/history/`
- **范围收敛**：仅对当前工作目录触发自动迁移/导出
- **Claude /continue**：新增技能，直接 `@` 最新历史文件

**🧩 旧目录兼容：**
- **自动迁移**：检测到 `.ccb_config` 时自动升级为 `.ccb`
- **兼容查找**：过渡期仍可解析旧目录内的会话

这些更新让交接文件只留在项目内，升级路径更平滑。

</details>

<details>
<summary><b>v5.2.2</b> - 会话切换跟踪 & 自动提取</summary>

**🔁 会话切换跟踪：**
- **上一条会话字段**：`.claude-session` 记录 `old_claude_session_id` / `old_claude_session_path` 与 `old_updated_at`
- **自动导出**：切换会话时自动生成 `./.ccb/history/claude-<timestamp>-<old_id>.md`
- **内容去噪**：过滤协议标记/护栏，保留工具调用摘要

这些更新让会话交接更可靠、更易追踪。

</details>

<details>
<summary><b>v5.2.0</b> - 历史 mail bridge 版本</summary>

这个版本引入了旧的邮件网关路径。该路径现在已不再属于受支持的 agent-first CLI 表面，仅作为清理过渡期遗留代码保留。

</details>

<details>
<summary><b>v5.1.2</b> - Daemon 与 Hook 稳定性</summary>

**🔧 修复与改进：**
- **Claude Completion Hook**：统一 askd 为 Claude 触发完成回调
- **askd 生命周期**：askd 绑定 CCB 生命周期，避免残留守护进程
- **挂载检测**：`ccb-mounted` 统一使用 ping 检测（兼容统一 askd）
- **状态文件查找**：`askd_client` 兜底使用 `CCB_RUN_DIR` 查找状态文件

详见 [CHANGELOG.md](CHANGELOG.md)。

</details>

<details>
<summary><b>v5.1.1</b> - 统一 Daemon + Bug 修复</summary>

**🔧 Bug 修复与改进：**
- **统一 Daemon**：所有 provider 现在使用统一的 askd daemon 架构
- **安装/卸载**：修复安装和卸载相关 bug
- **进程管理**：修复 kill/终止问题

详见 [CHANGELOG.md](CHANGELOG.md)。

</details>

<details>
<summary><b>v5.1.0</b> - 统一命令系统 + 历史原生 Windows 实验</summary>

**🚀 统一命令** - 用 agent-first 工作流替代各 provider 独立命令：

| 旧命令 | 新统一命令 |
|--------|-----------|
| `cask`, `gask`, `oask`, `dask`, `lask` | `ccb ask <agent> [from <sender>] <message>` |
| `cping`, `gping`, `oping`, `dping`, `lping` | `ccb ping <agent\|all>` |
| `cpend`, `gpend`, `opend`, `dpend`, `lpend` | `ccb pend <agent\|job_id> [N]` |

**支持的 provider:** `gemini`, `codex`, `opencode`, `droid`, `claude`

**🪟 历史原生 Windows 实验：**
- 早期版本曾探索原生 Windows 分屏运行路径
- 后台执行使用 PowerShell + `DETACHED_PROCESS`
- 大消息通过 stdin 方式传递
- 该后端现已移除；未来原生 Windows mux 路线将围绕 `psmux` 重建

**📦 新技能：**
- `/ask <agent> <message>` - 向命名 agent 提交任务
- `/ping <agent|all>` - 检查挂载状态
- `/pend <agent|job_id> [N]` - 查看最新回复

详见 [CHANGELOG.md](CHANGELOG.md)。

</details>

<details>
<summary><b>v5.0.5</b> - Droid 调度工具与安装</summary>

- **Droid**：新增调度工具（`ccb_ask_*` 以及 `cask/gask/lask/oask` 别名）。
- **安装**：新增 `ccb droid setup-delegation` 用于 MCP 注册。
- **安装器**：检测到 `droid` 时自动注册（可通过环境变量关闭）。

<details>
<summary><b>详情与用法</b></summary>

用法：
```
/all-plan <需求>
```

示例：
```
/all-plan 设计一个基于 Redis 的 API 缓存层
```

亮点：
- Socratic Ladder + Superpowers Lenses + Anti-pattern 分析
- 只分发给已挂载的 CLI
- 两轮 reviewer 反馈合并设计

</details>
</details>

<details>
<summary><b>v5.0.0</b> - 任意 AI 可主控</summary>

- **解除依赖**：无需先启动 Claude，Codex 可成为主控入口
- **统一控制**：单一入口控制 CC/OC/GE
- **启动更简单**：去掉 `ccb up`，直接 `ccb ...` 或使用默认 `ccb.config`
- **挂载更自由**：更灵活的 pane 挂载与会话绑定
- **默认配置**：缺失时自动创建默认 `ccb.config`
- **项目 askd 自启**：项目 askd 与 provider runtime 会在项目 tmux namespace 中按需启动
- **会话更稳**：PID 存活校验避免旧会话干扰

</details>

<details>
<summary><b>v4.0</b> - tmux 优先重构</summary>

- **全部重构**：结构更清晰，稳定性更强，也更易扩展。
- **终端运行时收口**：运行时逐步收敛为单一 tmux pane/control 模型，不再并行维护双终端后端。
- **tmux 完美体验**：稳定布局 + 窗格标题/边框 + 会话级主题（CCB 运行期间启用，退出自动恢复）。
- **支持任何终端**：只要能运行 tmux，就能获得完整多模型分屏体验。

</details>

<details>
<summary><b>v3.0</b> - 智能守护进程</summary>

- **真·并行**：Codex/Gemini/OpenCode 多任务安全排队执行。
- **跨 AI 编排**：Claude 与 Codex 可同时驱动 OpenCode。
- **坚如磐石**：守护进程自动启动，空闲自动退出。
- **链式调用**：Codex 可委派 OpenCode 做多步流程。
- **智能打断**：Gemini 任务支持中断处理。

<details>
<summary><b>详情</b></summary>

<h3 align="center">✨ 核心特性</h3>

- **🔄 真·并行**: 同时提交多个任务给 Codex、Gemini 或 OpenCode。provider runtime 会自动排队并串行执行，确保上下文不被污染。
- **🤝 跨 AI 编排**: Claude 和 Codex 现在可以同时驱动 OpenCode Agent。所有请求都由项目 askd 层统一仲裁。
- **🛡️ 坚如磐石**: 运行时层自我管理，首个请求自动启动，空闲后自动关闭以节省资源。
- **⚡ 链式调用**: 支持高级工作流！Codex 可以自主调用 `oask` 将子任务委派给 OpenCode 模型。
- **🛑 智能打断**: Gemini 任务支持智能打断检测，自动处理停止信号并确保工作流连续性。

<h3 align="center">🧩 功能支持矩阵</h3>

| 特性 | Codex | Gemini | OpenCode |
| :--- | :---: | :---: | :---: |
| **并行队列** | ✅ | ✅ | ✅ |
| **打断感知** | ✅ | ✅ | - |
| **响应隔离** | ✅ | ✅ | ✅ |

<details>
<summary><strong>📊 查看真实压力测试结果</strong></summary>

<br>

**场景 1: Claude & Codex 同时访问 OpenCode**
*两个 Agent 同时发送请求，由守护进程完美协调。*

| 来源 | 任务 | 结果 | 状态 |
| :--- | :--- | :--- | :---: |
| 🤖 Claude | `CLAUDE-A` | **CLAUDE-A** | 🟢 |
| 🤖 Claude | `CLAUDE-B` | **CLAUDE-B** | 🟢 |
| 💻 Codex | `CODEX-A` | **CODEX-A** | 🟢 |
| 💻 Codex | `CODEX-B` | **CODEX-B** | 🟢 |

**场景 2: 递归/链式调用**
*Codex 自主驱动 OpenCode 执行 5 步工作流。*

| 请求 | 退出码 | 响应 |
| :--- | :---: | :--- |
| **ONE** | `0` | `CODEX-ONE` |
| **TWO** | `0` | `CODEX-TWO` |
| **THREE** | `0` | `CODEX-THREE` |
| **FOUR** | `0` | `CODEX-FOUR` |
| **FIVE** | `0` | `CODEX-FIVE` |

</details>
</details>
</details>


<details>
<summary><b>旧版本历史</b></summary>

### v5.0.5
- **Droid**：新增调度工具（`ccb_ask_*` 与 `cask/gask/lask/oask`），并提供 `ccb droid setup-delegation` 安装命令

### v5.0.4
- **OpenCode**：修复 `-r` 恢复在多项目切换后失效的问题

### v5.0.3
- **守护进程**：全新的稳定守护进程设计

### v5.0.1
- **技能更新**：新增 `/all-plan`（Superpowers 头脑风暴 + 可用性分发）；Codex 侧新增 `lping/lpend`；`gask` 在 `CCB_DONE` 场景保留简要执行摘要。
- **状态栏**：从 `.autoflow/roles.json` 读取角色名（支持 `_meta.name`），并按路径缓存。
- **安装器**：安装技能时复制子目录（如 `references/`）。
- **CLI**：新增 `ccb uninstall` / `ccb reinstall`，并清理 Claude 配置。
- **路由**：项目/会话解析更严格（优先 `.ccb`，避免跨项目 Claude 会话）。

### v5.0.0
- **解除依赖**：无需先启动 Claude，Codex 也可以作为主 CLI
- **统一控制**：单一入口控制 Claude/OpenCode/Gemini
- **启动简化**：移除 `ccb up`，缺失 `.ccb/ccb.config` 时使用代码内置默认配置
- **挂载更自由**：更灵活的 pane 挂载与会话绑定
- **项目 askd 自启**：项目 askd 与 provider runtime 会在项目 tmux namespace 中按需启动
- **会话更稳**：PID 存活校验避免旧会话干扰

### v4.1.3
- **Codex 配置修复**: 自动迁移过期的 `sandbox_mode = "full-auto"` 为 `"danger-full-access"`，修复 Codex 无法启动的问题
- **稳定性**: 修复了快速退出的命令可能在设置 `remain-on-exit` 之前关闭 pane 的竞态条件
- **Tmux**: 更稳健的 pane 检测机制 (优先使用稳定的 `$TMUX_PANE` 环境变量)，并增强了分屏目标失效时的回退处理

### v4.1.2
- **性能优化**: 为 tmux 状态栏 (git 分支 & ccb 状态) 增加缓存，大幅降低系统负载
- **严格模式**: 明确要求在 `tmux` 内运行; 移除不稳定的自动 attach 逻辑，避免环境混乱
- **CLI**: 新增 `--print-version` 参数用于快速版本检查

### v4.1.1
- **CLI 修复**: 修复 `ccb` 在 tmux 中重启时参数丢失 (如 `-a`) 的问题
- **体验优化**: 非交互式环境下提供更清晰的错误提示
- **安装**: 强制更新 skills 以确保应用最新版本

### v4.1.0
- **异步护栏**: `cask/gask/oask` 执行后输出护栏提示，防止 Claude 继续轮询
- **同步模式**: 添加 `--sync` 参数，Codex 调用时跳过护栏提示
- **Codex Skills 更新**: `oask/gask` 使用 `--sync` 静默等待

### v4.0
- **全部重构**：整体架构重写，更清晰、更稳定
- **tmux 完美支持**：分屏/标题/边框/状态栏一体化体验
- **支持任何终端**：除 Windows 原生环境外，强烈建议统一迁移到 tmux 下使用

### v3.0.0
- **智能运行队列**: 项目 askd 提供 60 秒空闲超时与 provider 队列能力
- **跨 AI 协作**: 支持多个 Agent (Claude/Codex) 同时调用同一个 Agent (OpenCode)
- **打断检测**: Gemini 现在支持智能打断处理
- **链式执行**: Codex 可以调用 `oask` 驱动 OpenCode
- **稳定性**: 健壮的队列管理和锁文件机制

</details>

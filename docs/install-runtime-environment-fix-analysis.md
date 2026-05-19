# CCB 安装与运行环境问题修复分析文档

本文档说明 CCB 在 macOS、Volta、多 Python 环境下安装后出现启动失败、命令路径漂移、Claude/Codex agent 启动不一致等问题的前因后果，并给出可执行的修复方案和验收标准。

本文档不依赖任何聊天上下文即可阅读。文中所有路径均来自一次真实排查环境，但结论适用于同类环境。

## 1. 问题摘要

在以下环境中安装 CCB：

- 项目源码目录：`/Users/yuanfeijie/Desktop/project/claude_code_bridge`
- 目标工作项目：`/Users/yuanfeijie/Desktop/procode/chat2image`
- 系统：macOS
- Python 环境：
  - `/usr/bin/python3` 为 Python 3.9.6
  - `/opt/homebrew/opt/python@3.12/libexec/bin/python` 为 Python 3.12.12
- Node CLI 管理方式：Volta
  - `codex` 期望走 `/Users/yuanfeijie/.volta/bin/codex`
  - `claude` 期望走 `/Users/yuanfeijie/.volta/bin/claude`

安装后出现过以下现象：

- `ccb` 在 `chat2image` 中启动失败，报错为 `ccbd exited before ready with code 1`。
- `ccbd.stderr.log` 中出现 Python 类型语法相关错误：

```text
TypeError: unsupported operand type(s) for |: '_SpecialForm' and 'NoneType'
```

- `codex` 在不同上下文中可能解析到不同安装路径，例如 Volta 路径或 Homebrew 路径。
- `Claude Code` agent 重建后停在首次交互确认界面，导致 CCB 投递任务处于 `running` / `delivering` 状态但不返回。
- 安装脚本中的 Droid MCP 自动注册可能卡住，使安装过程超时。
- 新版 `ask` CLI 不再支持旧的 `--wait` 参数，旧测试命令会失败。

这些问题不是单一故障，而是安装时环境检查、运行时解释器选择、PATH 继承、provider 首次确认、外部工具注册、CLI 版本迁移共同叠加导致的。

## 2. 直接根因

### 2.1 安装时检查的 Python 与运行时实际使用的 Python 不一致

安装脚本会检查 Python 版本，真实安装日志显示：

```text
OK: Python 3.12.12 (python)
```

这表示安装脚本选中了命令名 `python`，并确认它是 Python 3.12。

但是 source/dev 安装模式下，`~/.local/bin/ccb` 会作为符号链接指向源码仓库中的入口文件：

```text
~/.local/bin/ccb -> /Users/yuanfeijie/Desktop/project/claude_code_bridge/ccb
~/.local/bin/ask -> /Users/yuanfeijie/Desktop/project/claude_code_bridge/bin/ask
```

源码入口文件使用 shebang：

```python
#!/usr/bin/env python3
```

因此用户执行 `ccb` 时，实际解释器不是安装脚本检查过的 `python`，而是重新由 `/usr/bin/env python3` 解析。

在问题环境中：

```text
command -v python3 -> /usr/bin/python3
python3 --version -> Python 3.9.6
command -v python -> /opt/homebrew/opt/python@3.12/libexec/bin/python
python --version -> Python 3.12.12
```

于是出现了以下断裂：

```text
安装时：python  = Python 3.12，检查通过
运行时：python3 = Python 3.9，ccbd 崩溃
```

CCB 新版代码中使用了 Python 3.10+ 语法，例如 `A | None` 类型联合。Python 3.9 无法完整支持这些运行时类型表达式，因此 `ccbd` 在 import 阶段崩溃。

### 2.2 `ccbd` 和 `keeper` 继承了错误解释器

CCB 启动后会继续启动后台控制进程：

- `keeper_main.py`
- `ccbd/main.py`

这两个进程不是独立选择 Python，而是通过当前 `ccb` 进程的 `sys.executable` 启动。

因此如果 `ccb` 本身由 `/usr/bin/python3` 启动，那么后续 `keeper` 和 `ccbd` 也会使用 Python 3.9。

这就是为什么只在安装脚本中检查 Python 不足以保证运行时正确。必须确保 `ccb` 入口本身、`keeper`、`ccbd` 三者使用同一个满足版本要求的 Python。

### 2.3 source/dev 模式优先开发便利，不保证运行时闭环

source/dev 模式的优点是全局命令直接链接当前源码，便于开发 CCB 本身。

但它的风险是：

- 入口 shebang 由源码决定。
- 安装脚本选中的 `PYTHON_BIN` 不会写入全局 wrapper。
- 用户 shell、tmux、后台 daemon 的 PATH 可能不同。
- 运行时可能绕过安装时检查结果。

因此 source/dev 模式适合 CCB 开发者，不适合作为多 Python macOS 用户的默认稳定安装方式。

### 2.4 Volta 与 Homebrew 路径在不同进程中可能不一致

用户期望：

```text
codex  -> /Users/yuanfeijie/.volta/bin/codex
claude -> /Users/yuanfeijie/.volta/bin/claude
```

但 CCB 不只在当前交互式 shell 中执行。它还会创建：

- 后台 daemon
- tmux session
- provider runtime
- Claude/Codex 隔离 home
- 多个 agent pane

这些进程不一定读取用户交互式 zsh 的完整初始化文件，因此它们看到的 PATH 可能与用户手动执行 `codex` 时不同。

如果某个后台上下文没有优先包含 `~/.volta/bin`，就可能解析到 Homebrew 的 `codex` 或其他旧版本 CLI。

所以“安装时能查到 codex/claude”不等于“tmux agent pane 中也一定查到同一个 codex/claude”。

### 2.5 Claude Code 首次确认会阻塞任务投递

在重建 `.ccb` 运行态后，Claude Code 可能出现首次确认界面，例如：

- 是否信任当前工作目录。
- 是否使用当前 `ANTHROPIC_API_KEY`。

如果 Claude pane 停在这些交互界面，CCB 仍可能认为 provider runtime 已经启动，但投递进去的任务不会被模型处理，表现为：

```text
job status: running
mailbox state: delivering
reply: empty
```

这不是 CCB 路由失败，而是 provider 处于交互确认状态。

### 2.6 Droid MCP 自动注册不是核心路径，但会影响安装成功率

安装脚本默认可能尝试 Droid MCP 自动注册。

如果本机安装了相关命令但其注册过程卡住或不可用，安装脚本会被拖住甚至超时。

对于只使用 Claude Code 和 Codex 的用户，Droid MCP 注册不是必要步骤，应当跳过或改为显式 opt-in。

### 2.7 新版 `ask` CLI 已移除旧 `--wait`

旧用法：

```bash
ask --wait --timeout 300 backend -- 'message'
```

新版 CLI 中 `ask` 只负责异步提交：

```bash
ask backend -- 'message'
```

等待结果应使用：

```bash
ccb wait-all --timeout 300 <job_id>
```

如果继续使用旧命令，会得到：

```text
unknown ask option: --wait
```

这是 CLI 版本迁移问题，不是安装失败。

## 3. 已验证的当前稳定修复方式

当前最稳的用户级修复是使用 release/managed 安装模式，而不是 source/dev symlink 安装模式。

推荐安装命令：

```bash
cd /Users/yuanfeijie/Desktop/project/claude_code_bridge
CCB_DROID_AUTOINSTALL=0 \
CCB_SOURCE_KIND=release \
CCB_BUILD_CHANNEL=stable \
CCB_USE_MANAGED_VENV=1 \
./install.sh install
```

该方式的效果：

- 源码仓库保持干净，跟随 `origin/main`。
- 全局命令安装到 `~/.local/bin`。
- 实际代码复制到 `~/.local/share/codex-dual`。
- 创建托管 Python venv：

```text
/Users/yuanfeijie/.local/share/codex-dual/.venv
```

- `ccb` 和 `ask` 不再是指向源码的 symlink，而是 wrapper：

```bash
exec "/Users/yuanfeijie/.local/share/codex-dual/.venv/bin/python" "/Users/yuanfeijie/.local/share/codex-dual/ccb" "$@"
```

这样即使系统默认 `python3` 仍是 Python 3.9，也不会影响 CCB 运行。

### 3.1 验证安装结果

执行：

```bash
command -v ccb
command -v ask
ccb version
/Users/yuanfeijie/.local/share/codex-dual/.venv/bin/python --version
```

期望结果：

```text
/Users/yuanfeijie/.local/bin/ccb
/Users/yuanfeijie/.local/bin/ask
Install path: /Users/yuanfeijie/.local/share/codex-dual
Install mode: release
Install source: release
Channel: stable
Python 3.12.12
```

### 3.2 验证 provider CLI 路径

在目标项目目录执行：

```bash
cd /Users/yuanfeijie/Desktop/procode/chat2image
command -v codex
codex --version
command -v claude
claude --version
```

期望结果：

```text
/Users/yuanfeijie/.volta/bin/codex
codex-cli 0.130.0
/Users/yuanfeijie/.volta/bin/claude
2.1.120 (Claude Code)
```

### 3.3 重建项目运行态

如果 `.ccb` 中存在旧运行态，先停止：

```bash
cd /Users/yuanfeijie/Desktop/procode/chat2image
ccb kill -f
```

如需清理旧运行态并保留 `.ccb/ccb.config`，使用：

```bash
ccb -n
```

注意：`ccb -n` 会要求交互确认。它会清理 `.ccb` 下可重建运行态，但保留 `.ccb/ccb.config`。

### 3.4 首次启动后处理 Claude Code 确认

如果 Claude pane 停在安全确认界面，需要在 tmux 界面中确认：

- 信任当前项目目录。
- 使用预期的 API key。

这一步完成后再测试任务投递。

### 3.5 验证四 agent 投递

新版测试方式：

```bash
job=$(ask backend -- 'CCB 自检：请只回复“backend 收到”，不要读取或修改任何文件。' | sed -n 's/^accepted job=\([^ ]*\).*/\1/p')
ccb wait-all --timeout 300 "$job"
ask get "$job"
```

对 `backend`、`review`、`lead`、`design` 分别执行。

期望结果：

```text
backend -> backend 收到
review  -> review 收到
lead    -> lead 收到
design  -> design 收到
```

最终队列应为空：

```bash
ccb pend --queue --detail all
```

期望结果：

```text
queued_agent_count: 0
active_agent_count: 0
total_queue_depth: 0
total_pending_reply_count: 0
```

## 4. 不推荐的修复方式

### 4.1 不推荐直接改源码 shebang

例如将源码入口改成：

```python
#!/opt/homebrew/opt/python@3.12/libexec/bin/python3
```

这种方式虽然可以在单机上解决问题，但有明显缺点：

- 会污染源码工作树。
- 不适合提交给上游。
- 绑定了本机 Homebrew 路径。
- 其他机器可能没有该路径。
- 用户要求“保留远端更新”时不应使用这种方式。

### 4.2 不推荐只依赖修改 shell PATH

修改 `~/.zshrc` 让 `python3` 指向 Python 3.12 只能解决交互式 shell 的一部分场景。

CCB 还涉及 daemon、tmux、provider runtime，这些上下文未必读取同一份 shell 初始化文件。

因此仅修改 shell PATH 不是完整修复。

### 4.3 不推荐继续使用 source/dev 安装作为普通用户默认安装

source/dev 模式适合开发 CCB 本身。

普通使用更适合 managed release 模式，因为它能固定 Python 解释器和依赖环境。

## 5. 上游应实施的永久修复方案

以下方案面向 CCB 项目本身，目标是让安装器在多 Python、多 PATH、多 provider CLI 环境下具备闭环自检能力。

### 5.1 修复 Python 解释器闭环

安装器必须保证“安装时检查的 Python”和“运行时 `ccb` 使用的 Python”一致。

推荐实现：

1. source/dev 模式也生成 wrapper，不直接 symlink Python 入口。
2. wrapper 中写死安装时通过检查的 `PYTHON_BIN` 绝对路径。
3. `ask` 入口也使用同一个 Python wrapper。
4. `keeper` 和 `ccbd` 继续使用 `sys.executable` 派生即可，因为 wrapper 已确保入口解释器正确。

source/dev wrapper 示例：

```bash
#!/usr/bin/env bash
if [[ "${TERM:-}" == "xterm-ghostty" ]]; then
  export TERM=xterm-256color
fi
exec "/opt/homebrew/opt/python@3.12/libexec/bin/python" "/Users/yuanfeijie/Desktop/project/claude_code_bridge/ccb" "$@"
```

对于不同机器，路径应由安装脚本检测得到，而不是硬编码。

必须避免以下行为：

```text
安装时检查 python=3.12
运行时通过 /usr/bin/env python3 找到 python3=3.9
```

### 5.2 source/dev 模式下允许 managed venv

当前逻辑中，source/dev 模式不使用 managed venv。

建议新增一种模式：

```text
source code + managed Python wrapper
```

也就是：

- 代码仍指向源码树，方便开发。
- 解释器来自 `~/.local/share/codex-dual/.venv/bin/python`。
- wrapper 调用源码入口。

这样可同时满足：

- 开发者修改源码立即生效。
- Python 解释器稳定。
- 不需要修改源码 shebang。

### 5.3 安装后执行真实入口自检

安装脚本不应只在安装进程中检查 Python。

安装完成后必须执行：

```bash
"$BIN_DIR/ccb" version
```

并增加一个机器可读的 runtime 检查，例如：

```bash
"$BIN_DIR/ccb" doctor --runtime
```

输出必须包含：

```text
ccb_executable: /Users/.../.local/bin/ccb
ccb_install_path: /Users/.../.local/share/codex-dual
python_executable: /Users/.../.local/share/codex-dual/.venv/bin/python
python_version: 3.12.12
python_ok: true
```

如果 `python_version < 3.10`，安装必须失败。

### 5.4 检查 provider CLI 在真实 tmux 环境中的解析结果

安装时只执行 `command -v codex` 不够。

必须在 CCB 实际启动 provider 的环境中检查：

```bash
command -v codex
codex --version
command -v claude
claude --version
```

建议在 `ccb doctor` 中增加以下字段：

```text
caller_codex_path
daemon_codex_path
tmux_codex_path
agent_backend_codex_path
caller_claude_path
daemon_claude_path
tmux_claude_path
agent_lead_claude_path
```

这些字段可以帮助判断是否出现以下问题：

```text
用户 shell 使用 Volta codex
tmux pane 使用 Homebrew codex
```

如果解析结果不一致，应输出明确警告。

### 5.5 明确 Volta PATH 策略

如果检测到 `~/.volta/bin` 存在，并且用户当前 shell 的 `codex` 或 `claude` 来自 Volta，则 CCB 启动 provider 时应确保 `~/.volta/bin` 在 PATH 前部。

推荐策略：

1. 不全局覆盖 PATH。
2. 只在 CCB provider runtime 环境中 prepend `~/.volta/bin`。
3. 保留用户原 PATH 的其余部分。
4. 在 `doctor` 中输出最终 provider PATH 的前几个关键段。

示例：

```text
provider_path_prefix:
  - /Users/yuanfeijie/.volta/bin
  - /Users/yuanfeijie/.local/bin
  - /opt/homebrew/bin
```

### 5.6 Droid MCP 自动注册应改为显式 opt-in 或短超时

对于 Claude Code + Codex 用户，Droid MCP 注册不是核心路径。

建议：

- 默认不自动注册 Droid MCP。
- 或者设置短超时，例如 5 到 10 秒。
- 超时后只警告，不影响安装成功。
- 文档中提供手动注册命令。

推荐默认：

```text
CCB_DROID_AUTOINSTALL=0
```

如果用户明确需要 Droid，再运行：

```bash
CCB_DROID_AUTOINSTALL=1 ./install.sh install
```

### 5.7 检测 Claude Code 首次确认状态

CCB 启动 Claude provider 后，不应只判断 pane 存活。

它还应识别常见阻塞界面：

- Trust folder prompt
- Use API key prompt
- Login prompt
- Permission mode prompt

如果检测到这些界面，应在 `ccb ps` 或 `ccb doctor` 中明确输出：

```text
agent: lead
provider: claude
runtime_health: blocked
blocked_reason: claude_trust_folder_prompt
action_required: focus pane lead and confirm trust prompt
```

这样用户可以区分：

```text
CCB 路由失败
provider 正在确认
模型正在处理
```

### 5.8 对新版 ask 语义提供兼容提示

当用户执行：

```bash
ask --wait --timeout 300 backend -- 'message'
```

当前错误为：

```text
unknown ask option: --wait
```

建议改为更明确的迁移提示：

```text
--wait has been removed.
Use:
  job=$(ask backend -- 'message' | sed -n 's/^accepted job=\([^ ]*\).*/\1/p')
  ccb wait-all --timeout 300 "$job"
  ask get "$job"
```

这可以降低版本升级后的误判。

## 6. 最小代码修改建议

如果要在仓库中实现永久修复，建议按以下顺序进行，避免一次性大改。

### 阶段 1：修复 source/dev Python wrapper

目标：

- source/dev 安装不再直接 symlink `ccb` 和 `ask`。
- 使用安装时选中的 Python 写 wrapper。

涉及位置：

- `install.sh`

关键改动：

- 新增 `write_selected_python_wrapper`。
- 在 `install_entrypoint_executable` 中，对 Python 入口文件始终生成 wrapper。
- wrapper 中使用 `PYTHON_BIN` 的绝对路径。

验收：

```bash
./install.sh install
head -20 ~/.local/bin/ccb
~/.local/bin/ccb version
```

必须看到 wrapper 使用 Python 3.10+。

### 阶段 2：补 runtime doctor

目标：

- 明确输出 `sys.executable`、Python 版本、安装模式、provider 路径。

涉及位置：

- `lib/cli/services/doctor.py`
- `lib/cli/services/doctor_runtime/*`

验收：

```bash
ccb doctor
```

必须能看出：

- CCB 使用哪个 Python。
- Codex/Claude 在当前环境解析到哪里。
- tmux/provider runtime 中解析到哪里。

### 阶段 3：provider PATH 一致性

目标：

- Volta 用户在 tmux/provider runtime 中仍然使用 Volta CLI。

涉及位置：

- provider launcher runtime
- control plane env
- terminal/tmux runtime

验收：

```bash
tmux -S .ccb/ccbd/tmux.sock list-panes ...
```

agent pane 中 `codex` 和 `claude` 应解析到预期路径。

### 阶段 4：Claude prompt blocked 状态识别

目标：

- Claude 首次确认时，`ccb ps` 或 `doctor` 显示 blocked，而不是只显示 idle/healthy。

验收：

- 清理 Claude managed home。
- 启动 CCB。
- Claude 停在 trust/API key prompt 时，`ccb doctor` 明确提示人工确认。

### 阶段 5：Droid 注册降级为非核心路径

目标：

- Droid 注册失败或卡住不影响 Claude/Codex 安装。

验收：

```bash
./install.sh install
```

即使 Droid 不可用，安装也应完成，并输出警告。

## 7. 推荐给普通用户的最终操作手册

如果只是使用 CCB，不开发 CCB 本身，执行以下命令：

```bash
cd /Users/yuanfeijie/Desktop/project/claude_code_bridge
git pull --ff-only
CCB_DROID_AUTOINSTALL=0 \
CCB_SOURCE_KIND=release \
CCB_BUILD_CHANNEL=stable \
CCB_USE_MANAGED_VENV=1 \
./install.sh install
```

然后验证：

```bash
ccb version
command -v codex
codex --version
command -v claude
claude --version
```

启动项目：

```bash
cd /Users/yuanfeijie/Desktop/procode/chat2image
ccb kill -f
ccb
```

如果 Claude pane 出现信任目录或 API key 确认，先在 pane 中确认。

测试 agent：

```bash
job=$(ask backend -- '请只回复“backend 收到”。' | sed -n 's/^accepted job=\([^ ]*\).*/\1/p')
ccb wait-all --timeout 300 "$job"
ask get "$job"
```

## 8. 明确结论

本问题的本质不是 Python、Volta、Claude Code、Codex CLI 某一个工具单独损坏，而是 CCB 安装器在 source/dev 模式下没有形成完整运行时闭环。

准确根因是：

```text
安装器检查到了 Python 3.12，但 source/dev 入口运行时通过 /usr/bin/env python3 使用了 Python 3.9。
```

进一步叠加：

```text
不同进程的 PATH 不一致，可能导致 codex/claude 解析路径不同。
Claude Code 首次安全确认会阻塞 CCB 任务处理。
Droid MCP 自动注册可能影响安装完成。
ask CLI 新版移除了旧 --wait 参数。
```

对当前用户环境，已验证的稳定方案是：

```text
使用 release/managed 安装模式，让 ~/.local/bin/ccb 和 ~/.local/bin/ask 调用 managed Python 3.12 venv。
保留源码仓库干净跟随 origin/main。
跳过非核心 Droid MCP 自动注册。
确认 Claude Code 首次 trust/API key prompt。
使用新版 ask + ccb wait-all 测试方式。
```

对上游项目，推荐的永久修复是：

```text
source/dev 模式也应生成固定 Python wrapper，或允许 source + managed venv。
安装后必须验证真实 ccb 入口使用的 sys.executable。
doctor 必须报告 provider CLI 在 caller、daemon、tmux、agent runtime 中的实际解析路径。
Droid MCP 注册应改为 opt-in 或短超时非阻塞。
Claude 首次确认应被识别为 blocked 状态并给出明确操作提示。
```

只要完成这些改动，CCB 就能在多 Python、多 Node CLI 管理器、多后台运行层的 macOS 环境中稳定安装和运行。

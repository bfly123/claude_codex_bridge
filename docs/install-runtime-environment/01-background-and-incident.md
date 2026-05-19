# 背景与问题分析

## 1. 文档目的

本文档记录一次 CCB 安装和运行问题的完整背景、现象、环境、影响和因果链。本文档不依赖任何聊天记录或外部上下文即可理解。

本文档中的 CCB 指当前仓库：

```text
/Users/yuanfeijie/Desktop/project/claude_code_bridge
```

目标工作项目为：

```text
/Users/yuanfeijie/Desktop/procode/chat2image
```

## 2. 用户目标

用户希望在本机安装并使用 CCB，让一个项目内同时运行多个 AI agent：

- Claude Code agent 负责调度。
- Claude Code agent 负责页面实现或设计 review。
- Codex agent 负责后端或实施任务。
- Codex agent 负责代码 review。

用户明确期望：

- 可以直接执行裸命令 `ccb` 和 `ask`。
- 不希望每次手写复杂的 `PATH=... ccb`。
- 不希望使用错误的 Homebrew 版 `codex`。
- `codex` 和 `claude` 应优先走 Volta 管理的 CLI。
- 安装和修复不能破坏当前开发环境。
- 需要能在 `~/Desktop/procode/chat2image` 中稳定启动。
- `cmd` agent 不应出现在工作布局中。
- 如果要修改上游，应通过 fork 提 PR。

## 3. 真实环境事实

### 3.1 操作系统与 shell

已观察环境：

```text
OS: macOS
shell: zsh
timezone: Asia/Shanghai
```

### 3.2 Python 环境

已观察到至少两个 Python：

```text
command -v python3 -> /usr/bin/python3
python3 --version -> Python 3.9.6

command -v python -> /opt/homebrew/opt/python@3.12/libexec/bin/python
python --version -> Python 3.12.12
```

这意味着：

```text
python 和 python3 不是同一个解释器。
python 满足 CCB 的 Python 3.10+ 要求。
python3 不满足 CCB 的 Python 3.10+ 要求。
```

### 3.3 Node CLI 与 Volta

用户期望 `codex` 和 `claude` 走 Volta：

```text
codex  -> /Users/yuanfeijie/.volta/bin/codex
claude -> /Users/yuanfeijie/.volta/bin/claude
```

已观察版本：

```text
codex-cli 0.130.0
Claude Code 2.1.120
```

同时系统中还存在 Homebrew 路径，且历史上出现过 Homebrew `codex` 被误用的情况。

### 3.4 CCB 仓库与安装路径

上游仓库：

```text
https://github.com/bfly123/claude_code_bridge.git
```

用户 fork：

```text
git@github.com:SeemSeam/claude_codex_bridge.git
```

本地 remote 目标状态：

```text
origin   git@github.com:SeemSeam/claude_codex_bridge.git
upstream https://github.com/bfly123/claude_code_bridge.git
```

仓库当前跟随：

```text
upstream/main
```

已观察版本：

```text
CCB v6.2.2
commit 39b4e92
```

## 4. 期望行为

用户期望安装后：

1. `ccb` 可以直接运行。
2. `ask` 可以直接运行。
3. `ccbd` daemon 能正常启动。
4. tmux 工作窗口里只有 4 个 agent pane。
5. `cmd` agent 不启用。
6. `codex` 使用 Volta 的最新 CLI。
7. `claude` 使用 Volta 的 Claude Code CLI。
8. CCB 自己使用 Python 3.10+。
9. 安装脚本如果发现环境问题，应明确报错或自动规避。
10. 安装后能通过真实 `ask` 投递任务。

## 5. 实际问题现象

### 5.1 source/dev 安装后 `ccb` 启动失败

在 `chat2image` 目录执行：

```bash
CCB_NO_ATTACH=1 ccb
```

曾出现：

```text
command_status: failed
error: ccbd is unavailable: lease_unmounted; lifecycle_failure: ccbd exited before ready with code 1
```

### 5.2 `ccbd` 日志出现 Python 类型错误

`ccbd.stderr.log` 中出现：

```text
TypeError: unsupported operand type(s) for |: '_SpecialForm' and 'NoneType'
```

错误发生在 import 阶段，说明 daemon 进程还没进入正常业务逻辑就崩溃了。

### 5.3 安装脚本显示 Python 通过，但运行时仍失败

安装脚本输出：

```text
OK: Python 3.12.12 (python)
```

但运行时实际通过 `#!/usr/bin/env python3` 解析到：

```text
/usr/bin/python3
Python 3.9.6
```

这造成安装时和运行时解释器不一致。

### 5.4 Claude Code 首次确认阻塞任务

Claude agent pane 重建后可能停在以下交互确认：

```text
Do you trust this folder?
Do you want to use this API key?
```

如果未确认，CCB 任务可能表现为：

```text
status: running
mailbox_state: delivering
reply: empty
```

### 5.5 Droid MCP 自动注册导致安装超时

安装脚本默认可能尝试：

```bash
droid mcp add ...
```

如果 Droid 配置不可用或命令卡住，安装过程可能超时。对于只使用 Claude Code 和 Codex 的用户，这不是核心功能。

### 5.6 新版 `ask` 不支持旧 `--wait`

旧命令：

```bash
ask --wait --timeout 300 backend -- 'message'
```

新版报错：

```text
unknown ask option: --wait
```

新版正确流程：

```bash
job=$(ask backend -- 'message' | sed -n 's/^accepted job=\([^ ]*\).*/\1/p')
ccb wait-all --timeout 300 "$job"
ask get "$job"
```

## 6. 影响范围

### 6.1 受影响用户

受影响概率较高的环境：

- macOS 用户。
- 系统 `python3` 是 Apple 自带 Python 3.9。
- Homebrew 安装了 Python 3.10+，但命令名主要是 `python`。
- 使用 Volta 管理 Node CLI。
- 同时存在 Homebrew CLI 和 Volta CLI。
- 使用 CCB source/dev 安装模式。

### 6.2 不一定受影响的用户

以下用户可能不受影响：

- `python3` 已经是 Python 3.10+。
- 使用 release/managed 安装模式。
- 不使用 Volta。
- 没有多份 Codex/Claude CLI。
- 不启用 Claude Code agent。

## 7. 直接因果链

完整因果链如下：

```text
用户运行 ./install.sh install
install.sh 找到 python=3.12 并通过检查
source/dev 模式安装 ~/.local/bin/ccb 为源码 symlink
源码 ccb 第一行是 #!/usr/bin/env python3
用户运行 ccb
/usr/bin/env python3 找到 /usr/bin/python3
/usr/bin/python3 是 Python 3.9.6
ccb 进程 sys.executable 是 Python 3.9
keeper 和 ccbd 通过 sys.executable 派生
ccbd import Python 3.10+ 类型语法
Python 3.9 import 崩溃
ccb 启动失败
```

其中最关键的一步是：

```text
安装时检查的是 python，运行时入口使用的是 python3。
```

## 8. 非根因澄清

以下不是根本原因：

- 不是用户项目 `chat2image` 代码损坏。
- 不是 tmux 本身损坏。
- 不是 Codex CLI 本身必然损坏。
- 不是 Claude Code 本身必然损坏。
- 不是 Python 3.12 安装损坏。
- 不是 Volta 本身损坏。

这些工具只是让问题更容易显现。

根本原因是 CCB 安装器没有保证“安装时通过检查的运行时”与“用户执行全局命令时实际使用的运行时”一致。

## 9. 已验证的临时稳定方案

已验证方案是改用 managed release 安装：

```bash
CCB_DROID_AUTOINSTALL=0 \
CCB_SOURCE_KIND=release \
CCB_BUILD_CHANNEL=stable \
CCB_USE_MANAGED_VENV=1 \
./install.sh install
```

此方案会：

- 将 CCB 复制到 `~/.local/share/codex-dual`。
- 创建 `~/.local/share/codex-dual/.venv`。
- 让 `~/.local/bin/ccb` 和 `~/.local/bin/ask` 变成 wrapper。
- wrapper 固定调用 managed Python 3.12。

该方案解决的是 Python 解释器漂移，不解决所有长期诊断能力缺口。

## 10. 上游需要修复的本质问题

上游应修复：

```text
source/dev 安装模式不应裸 symlink Python entrypoint。
```

更准确地说：

```text
所有用户可执行 Python entrypoint 都应通过 wrapper 绑定安装时选中的 Python 3.10+ 解释器。
```

这样才能保证：

```text
install-time Python == run-time Python == daemon Python
```


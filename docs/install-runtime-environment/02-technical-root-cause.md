# 技术根因与代码链路

## 1. 文档目的

本文档从代码路径解释 CCB 安装与运行环境问题的技术根因。

重点覆盖：

- `install.sh` 如何选择 Python。
- source/dev 安装为何绕过安装时 Python 选择。
- managed release 安装为何稳定。
- `keeper` 和 `ccbd` 如何继承 Python。
- Volta / Homebrew CLI 为什么会在不同进程里解析不一致。
- Droid MCP 注册为何会干扰安装。
- Claude Code 首次确认为何会阻塞 CCB 任务。
- `ask --wait` 为什么失效。

## 2. Python 版本要求

CCB 代码使用 Python 3.10+ 语法，例如：

```python
str | None
dict[str, object]
```

因此运行 CCB 的 Python 必须满足：

```text
Python >= 3.10
```

如果运行时 Python 是 3.9，某些类型表达式可能在 import 阶段触发错误。

真实错误示例：

```text
TypeError: unsupported operand type(s) for |: '_SpecialForm' and 'NoneType'
```

## 3. install.sh 的 Python 选择逻辑

`install.sh` 中存在全局变量：

```bash
PYTHON_BIN="${CCB_PYTHON_BIN:-}"
```

安装脚本通过 `pick_python_bin` 选择 Python：

```bash
pick_python_bin() {
  if [[ -n "${PYTHON_BIN}" ]] && _python_check_310 "${PYTHON_BIN}"; then
    return 0
  fi
  for cmd in python3 python; do
    if _python_check_310 "$cmd"; then
      PYTHON_BIN="$cmd"
      return 0
    fi
  done
  return 1
}
```

这段逻辑的含义：

1. 如果用户设置了 `CCB_PYTHON_BIN`，优先使用它。
2. 否则先试 `python3`。
3. 再试 `python`。
4. 找到 Python 3.10+ 就认为安装要求满足。

在真实问题环境中：

```text
python3 = Python 3.9.6
python  = Python 3.12.12
```

因此 `pick_python_bin` 会跳过 `python3`，选择 `python`。

安装日志会显示：

```text
OK: Python 3.12.12 (python)
```

到这里为止，安装脚本行为本身是合理的。

## 4. source/dev 安装模式

安装模式由 `resolve_source_kind` 和 `resolve_install_mode` 决定。

如果仓库存在 `.git`，默认认为是 source：

```bash
resolve_source_kind() {
  if [[ -d "$REPO_ROOT/.git" ]]; then
    echo "source"
  else
    echo "release"
  fi
}
```

source 对应：

```bash
resolve_install_mode() {
  if [[ "$source_kind" == "source" ]]; then
    echo "source"
  else
    echo "release"
  fi
}
```

source/dev 模式下：

```bash
install_uses_live_source() {
  [[ "$(resolve_install_mode)" == "source" ]]
}
```

这表示安装产物应直接使用当前源码树。

## 5. source/dev 模式为何不使用 managed venv

`use_managed_venv` 中有明确逻辑：

```bash
use_managed_venv() {
  local requested="${CCB_USE_MANAGED_VENV:-auto}"
  if install_uses_live_source; then
    return 1
  fi
  ...
}
```

这意味着：

```text
只要是 source/dev 安装，就永远不会使用 managed venv。
```

即使用户设置：

```bash
CCB_USE_MANAGED_VENV=1
```

在当前逻辑下 source/dev 模式仍不会使用 managed venv。

这是问题的关键条件之一。

## 6. source/dev entrypoint 安装逻辑

入口列表：

```bash
SCRIPTS_TO_LINK=(
  bin/ask
  bin/autonew
  bin/ctx-transfer
  ccb
)
```

这些文件当前 shebang 均为：

```text
#!/usr/bin/env python3
```

安装时调用：

```bash
install_bin_links
```

内部调用：

```bash
install_entrypoint_executable "$target_path" "$BIN_DIR/$name"
```

在 `install_entrypoint_executable` 中，仅当 managed venv 可用且 source 位于 install prefix 下时，才写 managed wrapper：

```bash
if use_managed_venv && [[ "$absolute_source" == "$INSTALL_PREFIX/"* ]]; then
  write_managed_venv_python_wrapper "$absolute_source" "$destination_path"
  return 0
fi

install_owned_executable "$source_path" "$destination_path"
```

但 source/dev 模式下 `use_managed_venv` 永远 false，所以进入 `install_owned_executable`。

`install_owned_executable` 优先创建 symlink：

```bash
if ln -s "$source_path" "$destination_path" 2>/dev/null; then
  return 0
fi
```

因此 source/dev 安装结果通常是：

```text
~/.local/bin/ccb -> /path/to/repo/ccb
~/.local/bin/ask -> /path/to/repo/bin/ask
```

这就是运行时绕过安装脚本 `PYTHON_BIN` 的原因。

## 7. 当前 fallback wrapper 不能解决 Python 问题

`install.sh` 中存在：

```bash
write_live_source_wrapper() {
  local target="$1"
  local wrapper_path="$2"
  ...
  cat > "$wrapper_path" <<EOF
#!/usr/bin/env bash
exec ${quoted_target} "\$@"
EOF
}
```

但这个 wrapper 只是执行目标文件：

```bash
exec /path/to/repo/ccb "$@"
```

目标文件仍然通过自身 shebang 启动：

```text
#!/usr/bin/env python3
```

因此即使 symlink 失败并 fallback 到 wrapper，也仍然可能使用错误的 `python3`。

这个 fallback wrapper 只能解决文件系统不支持 symlink 的问题，不能解决 Python 解释器绑定问题。

## 8. keeper 与 ccbd 的解释器继承

`keeper` 启动逻辑位于：

```text
lib/cli/services/daemon_runtime/keeper.py
```

关键逻辑：

```python
subprocess.Popen(
    [sys.executable, str(script), '--project', str(context.project.project_root)],
    ...
)
```

`ccbd` 启动逻辑位于：

```text
lib/ccbd/daemon_process.py
```

关键逻辑：

```python
process = subprocess.Popen(
    [sys.executable, str(script), '--project', str(project_root)],
    ...
)
```

这说明：

```text
keeper 和 ccbd 使用当前 ccb 进程的 sys.executable。
```

因此只要全局 `ccb` 入口使用正确 Python，后台 daemon 就会跟随正确 Python。

反过来：

```text
如果全局 ccb 入口使用 Python 3.9，keeper 和 ccbd 也会使用 Python 3.9。
```

所以修复点应放在入口 wrapper，而不是分别修改 keeper 或 ccbd。

## 9. managed release 模式为何稳定

release/managed 安装会复制项目到：

```text
~/.local/share/codex-dual
```

并创建 venv：

```text
~/.local/share/codex-dual/.venv
```

`write_managed_venv_python_wrapper` 会生成：

```bash
#!/usr/bin/env bash
if [[ "${TERM:-}" == "xterm-ghostty" ]]; then
  export TERM=xterm-256color
fi
exec "$venv_python" "$absolute_source" "$@"
```

实际效果：

```text
~/.local/bin/ccb -> bash wrapper -> managed venv python -> installed ccb
```

这样 `ccb` 不再依赖 `/usr/bin/env python3`，因此不会受到系统 Python 3.9 影响。

## 10. PATH 与 Volta 问题

`control_plane_env` 允许继承 `PATH`：

```python
_CONTROL_PLANE_ALLOWLIST = {
    ...
    'PATH',
    ...
}
```

理论上 daemon 和 provider 能继承调用者 PATH。

但现实中存在多个上下文：

```text
用户交互式 shell
安装脚本 shell
ccb wrapper
ccbd daemon
tmux server
tmux pane
provider runtime
Claude/Codex managed home
```

这些上下文不一定加载同一组 shell 初始化文件。

Volta 通常依赖 PATH 前缀：

```bash
export PATH="$HOME/.volta/bin:$PATH"
```

如果某个上下文没有该前缀，就可能出现：

```text
用户 shell: codex -> ~/.volta/bin/codex
tmux pane:  codex -> /opt/homebrew/bin/codex
```

这会导致 provider 版本漂移。

当前 doctor 只报告当前 `ccb doctor` 进程中的：

```python
shutil.which(executable)
```

它不能证明 tmux pane 或 provider runtime 里解析到同一个 CLI。

## 11. Droid MCP 注册问题

当前 `install_droid_delegation` 中：

```bash
if [[ "${CCB_DROID_AUTOINSTALL:-1}" == "0" ]]; then
  return
fi

if ! command -v droid >/dev/null 2>&1; then
  return
fi

py="$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)"
...
droid mcp add ccb-delegation --type stdio "$py" "$server"
```

问题有三点：

1. Droid 注册默认开启。
2. `py` 优先选择 `python3`，可能绕过安装脚本已选中的 Python 3.10+。
3. `droid mcp add` 没有超时。

在只使用 Claude Code 和 Codex 的用户场景中，Droid 不是核心依赖。它不应阻塞 CCB 主安装流程。

## 12. Claude Code 首次确认问题

Claude Code 启动后可能要求确认：

```text
Do you trust this folder?
Do you want to use this API key?
```

CCB 当前可能只能看到：

```text
pane alive
runtime healthy
```

但 provider 实际没有进入可处理输入的状态。

这会导致 CCB 任务被投递到 mailbox，但 Claude Code 没处理，表现为：

```text
job status: running
event status: delivering
reply: empty
```

这类问题不能通过重启 daemon 解决，必须确认 Claude Code prompt。

## 13. ask CLI 迁移问题

新版 `ask` 是异步提交工具。

当前 `ask` usage：

```text
ask [--compact] [--silence] [--callback] <target> [--] <message...>
ask get <job_id>
ask cancel <job_id>
```

旧参数 `--wait` 不在支持列表中。

当前 `parse_ask` 中仅对以下旧参数有明确提示：

```python
_REMOVED_ASK_FLAGS = {
    '--sync': 'async submit is already the default',
    '--async': 'omit the flag; async submit is already the default',
}
```

因此 `--wait` 会落入普通未知参数错误：

```text
unknown ask option: --wait
```

这会让用户误以为安装或 agent 通讯失败。实际只是 CLI 语义迁移。

## 14. 根本原因归纳

根本原因分三层。

第一层，直接根因：

```text
source/dev 安装的 Python entrypoint 没有绑定安装时检查通过的 Python。
```

第二层，诊断缺口：

```text
doctor 没有展示 daemon/tmux/provider runtime 的真实 Python 和 CLI 解析路径。
```

第三层，体验缺口：

```text
Droid 注册、Claude 首次确认、ask CLI 迁移都没有给用户足够明确的提示或隔离。
```

最优先需要修复第一层。


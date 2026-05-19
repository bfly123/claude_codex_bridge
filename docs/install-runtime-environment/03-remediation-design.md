# 修复方案设计

## 1. 文档目的

本文档给出 CCB 安装与运行环境问题的工程修复方案。

本文档将方案拆成多个 PR 级别的改动，避免一次性大改导致 review 困难。

## 2. 修复目标

必须达成的目标：

1. 安装时检查通过的 Python 与运行时 `ccb` 使用的 Python 一致。
2. `keeper` 和 `ccbd` 使用同一个 Python。
3. source/dev 模式仍能使用 live source。
4. 普通用户不再因系统 `/usr/bin/python3` 是 Python 3.9 而启动失败。
5. 安装后能明确验证真实入口可运行。
6. Droid MCP 注册不能阻塞 Claude/Codex 主安装流程。
7. 旧 `ask --wait` 用户能看到明确迁移提示。
8. doctor 能逐步暴露 provider CLI 路径漂移问题。
9. Claude Code 首次确认应被诊断为 provider blocked，而不是误判成 CCB 路由失败。

## 3. 非目标

以下不作为第一阶段目标：

- 不要求 CCB 自动修改用户全局 shell PATH。
- 不要求删除用户已有 Homebrew `codex`。
- 不要求删除用户已有 Volta 配置。
- 不要求自动点击 Claude Code 安全确认。
- 不要求改变 CCB 的 agent 调度语义。
- 不要求恢复旧 `ask --wait` 的同步行为。

## 4. PR 1：source/dev Python wrapper

### 4.1 问题

source/dev 安装当前通常创建 symlink：

```text
~/.local/bin/ccb -> /path/to/repo/ccb
```

而源码入口是：

```text
#!/usr/bin/env python3
```

这会绕过安装脚本选择的 `PYTHON_BIN`。

### 4.2 目标

source/dev 模式下，用户可执行入口必须是 wrapper。

wrapper 必须显式调用安装时已验证的 Python 绝对路径。

目标关系：

```text
~/.local/bin/ccb
  -> bash wrapper
  -> selected Python 3.10+
  -> /path/to/repo/ccb
```

### 4.3 推荐实现

在 `install.sh` 中新增函数：

```bash
resolved_python_executable() {
  "$PYTHON_BIN" -c 'import sys; print(sys.executable)'
}
```

新增 wrapper 生成函数：

```bash
write_selected_python_wrapper() {
  local python_path="$1"
  local source_path="$2"
  local destination_path="$3"

  local absolute_source="$source_path"
  if [[ "$absolute_source" != /* ]]; then
    absolute_source="$(cd "$(dirname "$source_path")" && pwd)/$(basename "$source_path")"
  fi

  mkdir -p "$(dirname "$destination_path")"
  clear_installed_path "$destination_path"
  cat > "$destination_path" <<EOF
#!/usr/bin/env bash
if [[ "\${TERM:-}" == "xterm-ghostty" ]]; then
  export TERM=xterm-256color
fi
exec "$python_path" "$absolute_source" "\$@"
EOF
  chmod +x "$destination_path" 2>/dev/null || true
}
```

调整 `install_entrypoint_executable`：

```bash
install_entrypoint_executable() {
  ...
  local python_path
  python_path="$(resolved_python_executable)"

  if use_managed_venv && [[ "$absolute_source" == "$INSTALL_PREFIX/"* ]]; then
    write_managed_venv_python_wrapper "$absolute_source" "$destination_path"
    return 0
  fi

  if install_uses_live_source; then
    write_selected_python_wrapper "$python_path" "$absolute_source" "$destination_path"
    return 0
  fi

  install_owned_executable "$source_path" "$destination_path"
}
```

### 4.4 注意事项

`SCRIPTS_TO_LINK` 当前全部是 Python entrypoint：

```text
bin/ask
bin/autonew
bin/ctx-transfer
ccb
```

因此第一阶段可以对这些 entrypoint 全部生成 Python wrapper。

如果未来 `SCRIPTS_TO_LINK` 中加入非 Python 脚本，需要增加 shebang 检测。

### 4.5 测试

更新：

```text
test/test_install_source_dev_mode.py
```

原测试允许 `ccb` 是 symlink。修复后应断言：

```text
bin/ccb 是普通文件
bin/ccb 可执行
bin/ccb 内容包含 REPO_ROOT/ccb
bin/ccb 内容包含已选择 Python
Codex skill 仍然 symlink 到源码 assets
```

应新增测试：

```text
当 python3 不可用或版本过低，但 python 满足 3.10+ 时，
source/dev wrapper 使用 python 的真实绝对路径。
```

### 4.6 验收标准

在 macOS 问题环境中：

```bash
./install.sh install
head -20 ~/.local/bin/ccb
~/.local/bin/ccb --print-version
```

期望：

```text
~/.local/bin/ccb 是 bash wrapper
wrapper 调用 Python 3.10+
ccb --print-version 成功
```

## 5. PR 2：安装后真实入口 smoke test

### 5.1 问题

当前安装脚本检查的是安装脚本进程中的 Python，不验证安装后的全局入口是否真的可运行。

### 5.2 目标

安装完成后验证：

```text
$BIN_DIR/ccb --print-version
$BIN_DIR/ask --help
```

### 5.3 推荐实现

新增：

```bash
verify_installed_entrypoints() {
  if ! "$BIN_DIR/ccb" --print-version >/dev/null 2>&1; then
    echo "ERROR: installed ccb entrypoint failed runtime smoke check"
    echo "   Path: $BIN_DIR/ccb"
    exit 1
  fi
  if ! "$BIN_DIR/ask" --help >/dev/null 2>&1; then
    echo "ERROR: installed ask entrypoint failed runtime smoke check"
    echo "   Path: $BIN_DIR/ask"
    exit 1
  fi
}
```

在 `install_bin_links` 后调用。

### 5.4 注意事项

不要用：

```bash
ccb version
```

因为 `ccb version` 会检查远端更新，可能触发网络请求。

应使用：

```bash
ccb --print-version
```

它更适合作为安装 smoke check。

## 6. PR 3：Droid MCP 注册降级

### 6.1 问题

Droid MCP 注册当前存在三个问题：

1. 默认启用。
2. 重新用 `python3` 优先选择 Python。
3. 无超时。

### 6.2 目标

Droid 注册失败、超时或不可用时，不影响 CCB 主安装。

### 6.3 推荐实现

保守方案：

- 保持 `CCB_DROID_AUTOINSTALL` 默认值不变。
- 增加短超时。
- 使用安装脚本已选择的 Python。

示例：

```bash
local timeout_s="${CCB_DROID_AUTOINSTALL_TIMEOUT_S:-10}"
local py
py="$(resolved_python_executable)"

if command -v timeout >/dev/null 2>&1; then
  timeout "$timeout_s" droid mcp add ...
else
  droid mcp add ...
fi
```

macOS 默认没有 GNU `timeout`。更稳的跨平台方式是通过 Python 包一层：

```bash
"$PYTHON_BIN" - <<PY
import subprocess, sys
...
subprocess.run([...], timeout=float("$timeout_s"))
PY
```

### 6.4 验收标准

场景：

```text
droid 不存在 -> 静默跳过
droid add 成功 -> 输出 OK
droid add 失败 -> 输出 WARN，安装继续
droid add 卡住 -> 超时 WARN，安装继续
```

## 7. PR 4：ask --wait 迁移提示

### 7.1 问题

旧用户会执行：

```bash
ask --wait --timeout 300 backend -- 'message'
```

当前只输出：

```text
unknown ask option: --wait
```

这个提示不说明新版替代方式。

### 7.2 推荐实现

在 `lib/cli/parser_runtime/ask.py` 中扩展：

```python
_REMOVED_ASK_FLAGS = {
    '--sync': 'async submit is already the default',
    '--async': 'omit the flag; async submit is already the default',
    '--wait': 'submit with `ask <agent> -- <message>`, then wait with `ccb wait-all --timeout <seconds> <job_id>`',
    '-w': 'submit with `ask <agent> -- <message>`, then wait with `ccb wait-all --timeout <seconds> <job_id>`',
}
```

### 7.3 测试

新增 parser 测试：

```text
parser.parse(['ask', '--wait', 'backend', '--', 'hi'])
```

期望抛出 `CliUsageError`，错误中包含：

```text
wait-all
```

## 8. PR 5：doctor 路径诊断增强

### 8.1 问题

当前 doctor 报告：

```python
sys.executable
shutil.which('codex')
shutil.which('claude')
```

这只能说明当前 `doctor` 进程的环境，不说明：

```text
daemon 使用哪个 Python
tmux pane 使用哪个 codex
provider runtime 使用哪个 claude
```

### 8.2 第一阶段增强

在 `requirements_summary` 中增加：

```text
path
path_entries_first_n
volta_bin_path
volta_bin_exists
volta_codex_exists
volta_claude_exists
python_ok
python_min_version
```

这样可以立即看出：

```text
PATH 是否包含 ~/.volta/bin
当前 doctor 是否使用 Python 3.10+
```

### 8.3 第二阶段增强

在 provider launch 时记录 provider command resolution：

```json
{
  "provider_command": "codex",
  "provider_command_path": "/Users/.../.volta/bin/codex",
  "provider_command_version": "codex-cli 0.130.0"
}
```

doctor 只读 runtime json，不主动向 pane 注入命令。

这样避免 doctor 对运行中的 agent 产生副作用。

## 9. PR 6：Claude Code 首次确认 blocked 诊断

### 9.1 问题

Claude Code 可能停在安全确认界面，但 CCB 只能看到 pane alive。

### 9.2 保守实现

先只在 doctor 中做弱诊断，不改变调度状态。

通过 tmux capture pane 或已保存 pane log 检测关键文本：

```text
Do you trust this folder
Do you want to use this API key
Quick safety check
```

输出：

```text
agent_blocker: name=lead provider=claude kind=interactive_prompt reason=trust_or_api_key_prompt action=confirm_in_pane
```

### 9.3 不建议第一阶段做的事

不要自动发送 Enter 或选择项。

原因：

- 这是安全确认。
- 自动确认可能违背用户意图。
- 不同 Claude Code 版本 UI 文本可能不同。

## 10. 推荐 PR 拆分

建议顺序：

1. `fix/source-install-python-wrapper`
2. `fix/ask-wait-migration-message`
3. `fix/droid-install-timeout`
4. `feat/doctor-runtime-path-diagnostics`
5. `feat/claude-prompt-blocker-diagnostics`

不要把 1 到 5 全部塞进一个 PR。

## 11. 当前用户可立即使用的稳定安装方案

如果只是使用 CCB：

```bash
cd /Users/yuanfeijie/Desktop/project/claude_code_bridge
git fetch upstream
git switch main
git merge --ff-only upstream/main
CCB_DROID_AUTOINSTALL=0 \
CCB_SOURCE_KIND=release \
CCB_BUILD_CHANNEL=stable \
CCB_USE_MANAGED_VENV=1 \
./install.sh install
```

验证：

```bash
ccb version
command -v ccb
command -v ask
command -v codex
codex --version
command -v claude
claude --version
```

## 12. 明确建议

如果目标是向上游提第一个 PR，首选：

```text
fix/source-install-python-wrapper
```

理由：

- 根因明确。
- 修改范围小。
- 对 source/dev 安装用户直接有价值。
- 不改变 CCB agent 调度语义。
- 不依赖 Claude/Codex 外部行为。
- 容易写自动化测试。


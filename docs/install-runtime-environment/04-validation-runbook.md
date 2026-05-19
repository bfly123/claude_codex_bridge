# 验证与操作手册

## 1. 文档目的

本文档给出安装问题的复现、验证、修复验收、回滚和提 PR 前检查流程。

所有命令默认在仓库根目录或目标项目目录执行。命令前会明确标注工作目录。

## 2. 安全原则

执行验证时遵守以下原则：

1. 不打印 API key。
2. 不删除不能确认来源的文件。
3. 不使用 `git reset --hard`。
4. 不覆盖用户未提交改动。
5. 先 `git status`，再修改。
6. 对运行态清理只使用 CCB 自己的 `ccb kill -f` 或 `ccb -n`。

## 3. 检查仓库状态

工作目录：

```bash
cd /Users/yuanfeijie/Desktop/project/claude_code_bridge
```

命令：

```bash
git remote -v
git status --short --branch
git log --oneline --decorate -5
```

期望：

```text
origin   git@github.com:SeemSeam/claude_codex_bridge.git
upstream https://github.com/bfly123/claude_code_bridge.git
```

本地 `main` 应跟踪 `upstream/main`。

## 4. 复现 source/dev Python 漂移

该复现只用于理解问题，不建议普通用户故意破坏当前稳定安装。

### 4.1 复现条件

满足：

```text
python3 < 3.10
python >= 3.10
CCB_SOURCE_KIND=source
```

检查：

```bash
command -v python3
python3 --version
command -v python
python --version
```

问题环境示例：

```text
/usr/bin/python3
Python 3.9.6
/opt/homebrew/opt/python@3.12/libexec/bin/python
Python 3.12.12
```

### 4.2 source/dev 安装

```bash
./install.sh install
```

检查：

```bash
ls -l ~/.local/bin/ccb ~/.local/bin/ask
head -1 ~/.local/bin/ccb
```

问题状态可能是：

```text
~/.local/bin/ccb -> /path/to/repo/ccb
#!/usr/bin/env python3
```

### 4.3 启动项目

工作目录：

```bash
cd /Users/yuanfeijie/Desktop/procode/chat2image
```

命令：

```bash
ccb kill -f
CCB_NO_ATTACH=1 ccb
```

问题结果：

```text
ccbd exited before ready with code 1
```

查看错误：

```bash
tail -200 .ccb/ccbd/ccbd.stderr.log
```

问题日志：

```text
TypeError: unsupported operand type(s) for |: '_SpecialForm' and 'NoneType'
```

## 5. 验证 managed release 规避方案

工作目录：

```bash
cd /Users/yuanfeijie/Desktop/project/claude_code_bridge
```

安装：

```bash
CCB_DROID_AUTOINSTALL=0 \
CCB_SOURCE_KIND=release \
CCB_BUILD_CHANNEL=stable \
CCB_USE_MANAGED_VENV=1 \
./install.sh install
```

验证：

```bash
command -v ccb
command -v ask
ls -l ~/.local/bin/ccb ~/.local/bin/ask
head -20 ~/.local/bin/ccb
head -20 ~/.local/bin/ask
ccb version
~/.local/share/codex-dual/.venv/bin/python --version
```

期望：

```text
~/.local/bin/ccb 是普通 wrapper 文件
~/.local/bin/ask 是普通 wrapper 文件
wrapper 调用 ~/.local/share/codex-dual/.venv/bin/python
Python 版本为 3.10+
```

## 6. 验证 Volta CLI

工作目录：

```bash
cd /Users/yuanfeijie/Desktop/procode/chat2image
```

命令：

```bash
command -v codex
codex --version
command -v claude
claude --version
```

期望：

```text
/Users/yuanfeijie/.volta/bin/codex
codex-cli 0.130.0
/Users/yuanfeijie/.volta/bin/claude
2.1.120 (Claude Code)
```

如果不是 Volta 路径，应优先检查 PATH，而不是修改 CCB 代码。

## 7. 启动 chat2image

工作目录：

```bash
cd /Users/yuanfeijie/Desktop/procode/chat2image
```

先停止旧运行态：

```bash
ccb kill -f
```

启动：

```bash
CCB_NO_ATTACH=1 ccb
```

期望：

```text
start_status: ok
agents: lead, backend, design, review
```

检查：

```bash
ccb ps
ccb config validate
```

期望：

```text
ccbd_state: mounted
config_status: valid
cmd_enabled: false
layout: lead:claude, backend:codex; design:claude, review:codex
```

## 8. 检查 tmux 布局

工作目录：

```bash
cd /Users/yuanfeijie/Desktop/procode/chat2image
```

命令：

```bash
tmux -S .ccb/ccbd/tmux.sock list-windows -a -F '#{session_name}:#{window_index} id=#{window_id} name=#{window_name} panes=#{window_panes} active=#{window_active}'
tmux -S .ccb/ccbd/tmux.sock list-panes -a -F '#{session_name}:#{window_index}.#{pane_index} #{pane_id} dead=#{pane_dead} title=#{pane_title} path=#{pane_current_path} cmd=#{pane_current_command}'
```

期望：

```text
window __ccb_ctl panes=1 active=0
window ccb panes=4 active=1
```

解释：

```text
__ccb_ctl 是后台控制窗口，不是 cmd agent。
工作窗口 ccb 中应有 4 个 pane。
```

如果配置中：

```text
cmd_enabled: false
```

则说明 cmd agent 未启用。

## 9. 处理 Claude Code 首次确认

如果 Claude pane 显示：

```text
Do you trust this folder?
Do you want to use this API key?
```

需要人工在 pane 中确认。

不要把这种状态误判为 CCB 通讯失败。

确认后再执行 ask 测试。

## 10. 新版 ask 测试方式

旧方式已不适用：

```bash
ask --wait --timeout 300 backend -- 'message'
```

新版方式：

```bash
job=$(ask backend -- 'CCB 自检：请只回复“backend 收到”，不要读取或修改任何文件。' | sed -n 's/^accepted job=\([^ ]*\).*/\1/p')
ccb wait-all --timeout 300 "$job"
ask get "$job"
```

对四个 agent 分别测试：

```bash
for agent in backend review lead design; do
  job=$(ask "$agent" -- "CCB 自检：请只回复“$agent 收到”，不要读取或修改任何文件。" | sed -n 's/^accepted job=\([^ ]*\).*/\1/p')
  echo "$agent $job"
  ccb wait-all --timeout 300 "$job"
  ask get "$job"
done
```

期望回复：

```text
backend 收到
review 收到
lead 收到
design 收到
```

## 11. 验证队列清空

命令：

```bash
ccb pend --queue --detail all
```

期望：

```text
queued_agent_count: 0
active_agent_count: 0
total_queue_depth: 0
total_pending_reply_count: 0
```

## 12. PR 1 自动化测试建议

如果实现 source/dev Python wrapper 修复，应运行：

```bash
pytest test/test_install_source_dev_mode.py
pytest test/test_install_watchdog_optional.py
```

如果改了 `ask` parser，应运行：

```bash
pytest test/test_v2_cli_parser.py
pytest test/test_ask_cli.py
```

如果改了 doctor 输出，应运行：

```bash
pytest test/test_v2_cli_render.py
pytest test/test_v2_tmux_cleanup_history.py
```

## 13. 手工验收 checklist

安装相关：

```text
[ ] install.sh 能找到 Python 3.10+
[ ] source/dev 安装生成 wrapper，而不是裸 Python entrypoint symlink
[ ] wrapper 调用安装时选中的 Python 绝对路径
[ ] ~/.local/bin/ccb --print-version 成功
[ ] ~/.local/bin/ask --help 成功
```

运行相关：

```text
[ ] ccb kill -f 成功
[ ] CCB_NO_ATTACH=1 ccb 成功
[ ] ccb ps 显示 mounted
[ ] 四个 agent 均为 idle
[ ] cmd_enabled=false
[ ] 工作窗口 4 pane
```

provider 相关：

```text
[ ] codex 解析到 Volta
[ ] claude 解析到 Volta
[ ] Claude 首次确认完成
[ ] ask backend 成功
[ ] ask review 成功
[ ] ask lead 成功
[ ] ask design 成功
```

## 14. 回滚方案

如果修复后安装失败，可以回到 managed release 规避方案：

```bash
cd /Users/yuanfeijie/Desktop/project/claude_code_bridge
CCB_DROID_AUTOINSTALL=0 \
CCB_SOURCE_KIND=release \
CCB_BUILD_CHANNEL=stable \
CCB_USE_MANAGED_VENV=1 \
./install.sh install
```

如果项目运行态异常：

```bash
cd /Users/yuanfeijie/Desktop/procode/chat2image
ccb kill -f
CCB_NO_ATTACH=1 ccb
```

如果需要重建 `.ccb` 运行态并保留配置：

```bash
ccb -n
```

注意：`ccb -n` 需要交互确认。

## 15. 提 PR 前检查

推荐分支：

```bash
git switch -c fix/source-install-python-wrapper
```

检查 remote：

```bash
git remote -v
```

期望：

```text
origin   git@github.com:SeemSeam/claude_codex_bridge.git
upstream https://github.com/bfly123/claude_code_bridge.git
```

提交前：

```bash
git status --short
git diff
pytest test/test_install_source_dev_mode.py
```

推送：

```bash
git push -u origin fix/source-install-python-wrapper
```

PR 目标：

```text
SeemSeam/claude_codex_bridge:fix/source-install-python-wrapper
  -> bfly123/claude_code_bridge:main
```


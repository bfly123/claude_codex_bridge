# CCB 安装与运行环境问题文档索引

本文档集用于说明 CCB 在 macOS、多 Python、Volta、tmux、Claude Code、Codex CLI 同时存在的环境中，为什么会出现安装成功但运行失败、provider CLI 路径不一致、Claude agent 卡住、`ask --wait` 不可用等问题。

文档目标：

- 脱离任何聊天上下文也能完整理解问题。
- 区分已确认事实、合理推断和建议方案。
- 给出可拆分 PR 的修复路径。
- 给出本地验证命令和期望结果。
- 避免泄露 API key、token 或任何敏感凭据。

## 文档结构

1. [01-background-and-incident.md](./01-background-and-incident.md)

   说明问题背景、真实环境、用户期望、实际现象、影响范围、已确认事实和因果链。

2. [02-technical-root-cause.md](./02-technical-root-cause.md)

   从代码路径解释根本原因，包括 `install.sh`、source/dev 安装模式、managed release 安装模式、Python 解释器继承、Volta PATH、Droid MCP、Claude Code 首次确认、`ask` CLI 迁移。

3. [03-remediation-design.md](./03-remediation-design.md)

   给出工程修复设计，包括 source/dev Python wrapper、安装后真实入口自检、Droid 注册降级、`ask --wait` 迁移提示、doctor 诊断增强、Claude prompt blocked 识别。

4. [04-validation-runbook.md](./04-validation-runbook.md)

   给出复现、验证、回归测试、手工验收、回滚和提 PR 前检查清单。

## 一句话结论

本问题的核心不是用户系统损坏，也不是 Python、Volta、Codex CLI、Claude Code 任意一个工具单独损坏。

最核心的工程缺陷是：

```text
source/dev 安装模式下，install.sh 检查到了 Python 3.10+，
但全局 ccb/ask 入口仍可能通过 /usr/bin/env python3 使用另一个更旧的 Python。
```

在真实问题环境中：

```text
install.sh 选中的 python = Python 3.12.12
运行时 /usr/bin/env python3 = Python 3.9.6
```

于是安装时通过检查，运行时 `ccbd` 崩溃。

## 最小稳定规避方案

普通用户只使用 CCB，不开发 CCB 本身时，推荐使用 managed release 安装：

```bash
cd /Users/yuanfeijie/Desktop/project/claude_code_bridge
CCB_DROID_AUTOINSTALL=0 \
CCB_SOURCE_KIND=release \
CCB_BUILD_CHANNEL=stable \
CCB_USE_MANAGED_VENV=1 \
./install.sh install
```

该方式会让全局 `ccb` / `ask` wrapper 固定调用 managed Python 3.12 venv，避免系统 `python3` 版本漂移。

## 推荐上游修复优先级

优先级从高到低：

1. source/dev 安装的 Python 入口闭环。
2. 安装后真实 `ccb` 入口 smoke test。
3. `ask --wait` 迁移提示。
4. Droid MCP 注册超时和非核心化。
5. `ccb doctor` 增强 provider 路径诊断。
6. Claude Code 首次确认 blocked 状态识别。

这些修复建议拆成多个 PR，而不是一个大 PR。


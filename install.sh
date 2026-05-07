#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_PREFIX="${CODEX_INSTALL_PREFIX:-$HOME/.local/share/codex-dual}"
BIN_DIR="${CODEX_BIN_DIR:-$HOME/.local/bin}"
readonly REPO_ROOT INSTALL_PREFIX BIN_DIR

require_supported_bash() {
  if [[ -z "${BASH_VERSION:-}" ]]; then
    echo "ERROR: install.sh must be run with bash. Try: bash ./install.sh install" >&2
    exit 1
  fi
  if (( BASH_VERSINFO[0] < 3 || (BASH_VERSINFO[0] == 3 && BASH_VERSINFO[1] < 2) )); then
    echo "ERROR: bash ${BASH_VERSION} is too old for install.sh." >&2
    echo "   Please run with bash 3.2+ or install a newer bash, then retry." >&2
    exit 1
  fi
}

require_supported_bash

# i18n support
detect_lang() {
  local lang="${CCB_LANG:-auto}"
  case "$lang" in
    zh|cn|chinese) echo "zh" ;;
    en|english) echo "en" ;;
    *)
      local sys_lang="${LANG:-${LC_ALL:-${LC_MESSAGES:-}}}"
      if [[ "$sys_lang" == zh* ]] || [[ "$sys_lang" == *chinese* ]]; then
        echo "zh"
      else
        echo "en"
      fi
      ;;
  esac
}

CCB_LANG_DETECTED="$(detect_lang)"

# Message function
msg() {
  local key="$1"
  shift
  local en_msg zh_msg
  case "$key" in
    install_complete)
      en_msg="Installation complete"
      zh_msg="安装完成" ;;
    uninstall_complete)
      en_msg="Uninstall complete"
      zh_msg="卸载完成" ;;
    python_version_old)
      en_msg="Python version too old: $1"
      zh_msg="Python 版本过旧: $1" ;;
    requires_python)
      en_msg="Requires Python 3.10+"
      zh_msg="需要 Python 3.10+" ;;
    missing_dep)
      en_msg="Missing dependency: $1"
      zh_msg="缺少依赖: $1" ;;
    detected_env)
      en_msg="Detected $1 environment"
      zh_msg="检测到 $1 环境" ;;
    confirm_wsl)
      en_msg="Confirm continue installing in WSL? (y/N)"
      zh_msg="确认继续在 WSL 中安装？(y/N)" ;;
    cancelled)
      en_msg="Installation cancelled"
      zh_msg="安装已取消" ;;
    wsl_warning)
      en_msg="Detected WSL environment"
      zh_msg="检测到 WSL 环境" ;;
    same_env_required)
      en_msg="ccb, ccb ask, ccb ping, and ccb pend must run in the same environment as codex/gemini."
      zh_msg="ccb、ccb ask、ccb ping、ccb pend 必须与 codex/gemini 在同一环境运行。" ;;
    confirm_wsl_native)
      en_msg="Please confirm: you will install and run codex/gemini in WSL (not Windows native)."
      zh_msg="请确认：你将在 WSL 中安装并运行 codex/gemini（不是 Windows 原生）。" ;;
    watchdog_installing)
      en_msg="Installing Python dependency: watchdog"
      zh_msg="正在安装 Python 依赖: watchdog" ;;
    watchdog_installed)
      en_msg="OK: watchdog installed"
      zh_msg="OK: watchdog 已安装" ;;
    watchdog_failed)
      en_msg="WARN: watchdog install failed; continuing without optional file watchers"
      zh_msg="警告：watchdog 安装失败；将不启用可选文件监听" ;;
    watchdog_optional)
      en_msg="INFO: watchdog is optional. ccb will still install and use polling/readback paths when watchers are unavailable."
      zh_msg="信息：watchdog 是可选依赖。未启用监听时，ccb 仍会安装并使用轮询/回读路径。" ;;
    watchdog_skipped)
      en_msg="INFO: watchdog auto-install skipped by CCB_INSTALL_WATCHDOG=0"
      zh_msg="信息：已通过 CCB_INSTALL_WATCHDOG=0 跳过 watchdog 自动安装" ;;
    watchdog_python_missing)
      en_msg="WARN: python not available; skipping optional watchdog install"
      zh_msg="警告：未找到 Python；跳过可选 watchdog 安装" ;;
    pip_missing)
      en_msg="WARN: pip not available for selected Python; skipping optional watchdog install"
      zh_msg="警告：当前 Python 未提供 pip；跳过可选 watchdog 安装" ;;
    root_error)
      en_msg="ERROR: Do not run as root/sudo. Please run as normal user."
      zh_msg="错误：请勿以 root/sudo 身份运行。请使用普通用户执行。" ;;
    install_notice_source_title)
      en_msg="WARN: Development/source install detected"
      zh_msg="警告：检测到开发源码安装" ;;
    install_notice_source_body)
      en_msg="This is a development install, not an official release package."
      zh_msg="这是开发安装，不是正式 release 包。" ;;
    install_notice_release)
      en_msg="INFO: Official release package install detected"
      zh_msg="信息：检测到正式 release 包安装" ;;
    install_notice_preview_title)
      en_msg="WARN: Preview release package install detected"
      zh_msg="警告：检测到预览版 release 包安装" ;;
    install_notice_preview_body)
      en_msg="This package was built from a preview/dirty source snapshot, not an official stable release."
      zh_msg="该安装包来自预览或脏工作区快照，不是正式稳定 release。" ;;
    *)
      en_msg="$key"
      zh_msg="$key" ;;
  esac
  if [[ "$CCB_LANG_DETECTED" == "zh" ]]; then
    echo "$zh_msg"
  else
    echo "$en_msg"
  fi
}

require_non_root_execution() {
  if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    msg root_error >&2
    exit 1
  fi
}

SCRIPTS_TO_LINK=(
  bin/ask
  bin/autonew
  bin/ctx-transfer
  ccb
)

CLAUDE_MARKDOWN=(
  # Old CCB commands removed - replaced by unified ask/ping/pend skills
)

LEGACY_SCRIPTS=(
  bask
  bpend
  bping
  cask
  cpend
  cping
  ccb-mounted
  ccb-ping
  ping
  dask
  dpend
  dping
  gask
  gpend
  gping
  hask
  hpend
  hping
  lask
  lpend
  lping
  oask
  opend
  oping
  pend
  qask
  qpend
  qping
  cast
  cast-w
  codex-ask
  codex-pending
  codex-ping
  claude-codex-dual
  claude_codex
  claude_ai
  claude_bridge
  caskd
  gaskd
  oaskd
  laskd
  daskd
)

usage() {
  cat <<'USAGE'
Usage:
  ./install.sh install    # Install or update Codex dual-window tools
  ./install.sh uninstall  # Uninstall installed content

Optional environment variables:
  CODEX_INSTALL_PREFIX     Install directory (default: ~/.local/share/codex-dual)
  CODEX_BIN_DIR            Executable directory (default: ~/.local/bin)
  CODEX_CLAUDE_COMMAND_DIR Custom Claude commands directory (default: auto-detect)
  CCB_DROID_AUTOINSTALL    Auto-register Droid MCP tools if droid exists (default: 1)
  CCB_DROID_AUTOINSTALL_FORCE Re-register Droid MCP tools (default: 0)
  CCB_BUILD_CHANNEL        Override build channel metadata (e.g. stable, preview, dev)
  CCB_BUILD_PLATFORM       Override build platform metadata (default: detected platform)
  CCB_BUILD_ARCH           Override build arch metadata (default: uname -m)
  CCB_BUILD_TIME           Override build timestamp metadata (default: current UTC time)
  CCB_SOURCE_KIND          Override source kind metadata (default: source if .git exists, else release)
  CCB_USE_MANAGED_VENV     Use install-local Python venv: auto (default), 1, or 0
                           auto = enabled for macOS release installs, disabled for source/dev installs
  CCB_INSTALL_WATCHDOG     Auto-install optional watchdog dependency (default: 1; set 0 to skip)
  CCB_CONFIRM_MAJOR_UPGRADE Set to 1 to confirm replacing a pre-v6 install with v6+
  CCB_CLAUDE_MD_MODE       CLAUDE.md injection mode: "inline" (default) or "route"
                           inline = full config in CLAUDE.md (~57 lines)
                           route  = minimal pointer in CLAUDE.md, full config in ~/.claude/rules/ccb-config.md
USAGE
}

detect_claude_dir() {
  if [[ -n "${CODEX_CLAUDE_COMMAND_DIR:-}" ]]; then
    echo "$CODEX_CLAUDE_COMMAND_DIR"
    return
  fi

  local candidates=(
    "$HOME/.claude/commands"
    "$HOME/.config/claude/commands"
    "$HOME/.local/share/claude/commands"
  )

  for dir in "${candidates[@]}"; do
    if [[ -d "$dir" ]]; then
      echo "$dir"
      return
    fi
  done

  local fallback="$HOME/.claude/commands"
  mkdir -p "$fallback"
  echo "$fallback"
}

require_command() {
  local cmd="$1"
  local pkg="${2:-$1}"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "ERROR: Missing dependency: $cmd"
    echo "   Please install $pkg first, then re-run install.sh"
    exit 1
  fi
}

PYTHON_BIN="${CCB_PYTHON_BIN:-}"

_python_check_310() {
  local cmd="$1"
  command -v "$cmd" >/dev/null 2>&1 || return 1
  "$cmd" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1
}

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

pick_any_python_bin() {
  if [[ -n "${PYTHON_BIN}" ]] && command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    return 0
  fi
  for cmd in python3 python; do
    if command -v "$cmd" >/dev/null 2>&1; then
      PYTHON_BIN="$cmd"
      return 0
    fi
  done
  return 1
}

require_python_version() {
  # ccb requires Python 3.10+ (PEP 604 type unions: `str | None`, etc.)
  if ! pick_python_bin; then
    echo "ERROR: Missing dependency: python (3.10+ required)"
    echo "   Please install Python 3.10+ and ensure it is on PATH, then re-run install.sh"
    exit 1
  fi
  local version
  version="$("$PYTHON_BIN" -c 'import sys; print("{}.{}.{}".format(sys.version_info[0], sys.version_info[1], sys.version_info[2]))' 2>/dev/null || echo unknown)"
  if ! _python_check_310 "$PYTHON_BIN"; then
    echo "ERROR: Python version too old: $version"
    echo "   Requires Python 3.10+, please upgrade and retry"
    exit 1
  fi
  echo "OK: Python $version ($PYTHON_BIN)"
}

python_has_module() {
  local module="$1"
  if ! pick_any_python_bin; then
    return 1
  fi
  "$PYTHON_BIN" - <<PY >/dev/null 2>&1
import importlib.util
import sys
sys.exit(0 if importlib.util.find_spec("${module}") else 1)
PY
}

python_is_virtual_environment() {
  local python_path="${1:-$PYTHON_BIN}"
  "$python_path" - <<'PY' >/dev/null 2>&1
import sys

is_virtualenv = getattr(sys, "base_prefix", sys.prefix) != sys.prefix or hasattr(sys, "real_prefix")
raise SystemExit(0 if is_virtualenv else 1)
PY
}

watchdog_manual_install_command() {
  local use_venv_scope="${1:-0}"
  if [[ "$use_venv_scope" == "1" ]]; then
    echo "   $PYTHON_BIN -m pip install 'watchdog>=2.1.0'"
  else
    echo "   $PYTHON_BIN -m pip install --user 'watchdog>=2.1.0'"
  fi
}

install_watchdog_into_virtualenv() {
  local python_version python_path
  python_version="$("$PYTHON_BIN" -c 'import sys; print("{}.{}.{}".format(sys.version_info[0], sys.version_info[1], sys.version_info[2]))' 2>/dev/null || echo unknown)"
  python_path="$("$PYTHON_BIN" -c 'import sys; print(sys.executable)' 2>/dev/null || command -v "$PYTHON_BIN" 2>/dev/null || echo "$PYTHON_BIN")"

  local pip_log pip_log_cleanup=0 last_failure=""
  pip_log="$(mktemp "${TMPDIR:-/tmp}/ccb-watchdog-pip.XXXXXX.log" 2>/dev/null || mktemp "/tmp/ccb-watchdog-pip.XXXXXX.log" 2>/dev/null || true)"
  if [[ -z "$pip_log" ]]; then
    pip_log="/dev/null"
  else
    pip_log_cleanup=1
  fi

  if "$PYTHON_BIN" -m pip install "watchdog>=2.1.0" >"$pip_log" 2>&1; then
    if python_has_module "watchdog"; then
      if [[ "$pip_log_cleanup" -eq 1 ]]; then
        rm -f "$pip_log"
      fi
      msg watchdog_installed
      return 0
    fi
    last_failure="pip install succeeded, but Python $python_path still cannot import watchdog"
  else
    last_failure="$PYTHON_BIN -m pip install 'watchdog>=2.1.0' failed"
  fi

  msg watchdog_failed
  if [[ -n "$last_failure" ]]; then
    echo "   Last failure: $last_failure"
  fi
  if [[ "$pip_log_cleanup" -eq 1 && -s "$pip_log" ]]; then
    echo "   pip output:"
    tail -20 "$pip_log" | sed 's/^/     /'
  fi
  if [[ "$pip_log_cleanup" -eq 1 ]]; then
    rm -f "$pip_log"
  fi
  echo "   Manual optional install:"
  watchdog_manual_install_command 1
  msg watchdog_optional
  return 0
}

install_watchdog() {
  if [[ "${CCB_INSTALL_WATCHDOG:-1}" == "0" ]]; then
    msg watchdog_skipped
    return 0
  fi
  if python_has_module "watchdog"; then
    msg watchdog_installed
    return 0
  fi
  if ! pick_any_python_bin; then
    msg watchdog_python_missing
    msg watchdog_optional
    return 0
  fi
  local python_version python_path
  python_version="$("$PYTHON_BIN" -c 'import sys; print("{}.{}.{}".format(sys.version_info[0], sys.version_info[1], sys.version_info[2]))' 2>/dev/null || echo unknown)"
  python_path="$("$PYTHON_BIN" -c 'import sys; print(sys.executable)' 2>/dev/null || command -v "$PYTHON_BIN" 2>/dev/null || echo "$PYTHON_BIN")"
  msg watchdog_installing
  echo "   Python: $python_path ($python_version)"

  if python_is_virtual_environment; then
    install_watchdog_into_virtualenv
    return 0
  fi

  local last_failure=""
  # 1. Try uv (fast, no PEP 668 issues)
  if command -v uv >/dev/null 2>&1; then
    if uv pip install --system "watchdog>=2.1.0" >/dev/null 2>&1 || \
       uv pip install "watchdog>=2.1.0" >/dev/null 2>&1; then
      if python_has_module "watchdog"; then
        msg watchdog_installed
        return 0
      fi
      last_failure="uv installed watchdog, but Python $python_path still cannot import it"
    else
      last_failure="uv pip install watchdog>=2.1.0 failed"
    fi
  fi

  if ! "$PYTHON_BIN" -m pip --version >/dev/null 2>&1; then
    msg pip_missing
    echo "   Install manually for this Python if file watchers are desired:"
    echo "   $PYTHON_BIN -m ensurepip --upgrade"
    watchdog_manual_install_command 0
    msg watchdog_optional
    return 0
  fi

  # 2. Try standard pip install --user
  local pip_log pip_log_cleanup=0
  pip_log="$(mktemp "${TMPDIR:-/tmp}/ccb-watchdog-pip.XXXXXX.log" 2>/dev/null || mktemp "/tmp/ccb-watchdog-pip.XXXXXX.log" 2>/dev/null || true)"
  if [[ -z "$pip_log" ]]; then
    pip_log="/dev/null"
  else
    pip_log_cleanup=1
  fi
  if "$PYTHON_BIN" -m pip install --user "watchdog>=2.1.0" >"$pip_log" 2>&1; then
    if python_has_module "watchdog"; then
      if [[ "$pip_log_cleanup" -eq 1 ]]; then
        rm -f "$pip_log"
      fi
      msg watchdog_installed
      return 0
    fi
    last_failure="pip install --user succeeded, but Python $python_path still cannot import watchdog"
  else
    last_failure="$PYTHON_BIN -m pip install --user 'watchdog>=2.1.0' failed"
  fi

  # 3. PEP 668 fallback: --break-system-packages (Homebrew Python, Debian 12+, etc.)
  if "$PYTHON_BIN" -m pip install --user --break-system-packages "watchdog>=2.1.0" >"$pip_log" 2>&1; then
    if python_has_module "watchdog"; then
      if [[ "$pip_log_cleanup" -eq 1 ]]; then
        rm -f "$pip_log"
      fi
      msg watchdog_installed
      return 0
    fi
    last_failure="pip install --user --break-system-packages succeeded, but Python $python_path still cannot import watchdog"
  else
    last_failure="$PYTHON_BIN -m pip install --user --break-system-packages 'watchdog>=2.1.0' failed"
  fi

  # 4. Try pipx inject into a shared venv as last resort
  if command -v pipx >/dev/null 2>&1; then
    if pipx install watchdog >/dev/null 2>&1; then
      if python_has_module "watchdog"; then
        if [[ "$pip_log_cleanup" -eq 1 ]]; then
          rm -f "$pip_log"
        fi
        msg watchdog_installed
        return 0
      fi
      last_failure="pipx installed watchdog, but Python $python_path still cannot import it"
    else
      last_failure="pipx install watchdog failed"
    fi
  fi

  msg watchdog_failed
  if [[ -n "$last_failure" ]]; then
    echo "   Last failure: $last_failure"
  fi
  if [[ "$pip_log_cleanup" -eq 1 && -s "$pip_log" ]]; then
    echo "   pip output:"
    tail -20 "$pip_log" | sed 's/^/     /'
  fi
  if [[ "$pip_log_cleanup" -eq 1 ]]; then
    rm -f "$pip_log"
  fi
  echo "   Manual optional install:"
  watchdog_manual_install_command 0
  msg watchdog_optional
  return 0
}

install_watchdog_for_python() {
  local python_cmd="$1"
  local previous_python_bin="$PYTHON_BIN"
  PYTHON_BIN="$python_cmd"
  install_watchdog
  PYTHON_BIN="$previous_python_bin"
}

# Return linux / macos / unknown based on uname
detect_platform() {
  local name
  name="$(uname -s 2>/dev/null || echo unknown)"
  case "$name" in
    Linux) echo "linux" ;;
    Darwin) echo "macos" ;;
    *) echo "unknown" ;;
  esac
}


is_wsl() {
  [[ -f /proc/version ]] && grep -qi microsoft /proc/version 2>/dev/null
}

get_wsl_version() {
  if [[ -n "${WSL_INTEROP:-}" ]]; then
    echo 2
  else
    echo 1
  fi
}

current_utc_timestamp() {
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

read_embedded_assignment() {
  local file="$1"
  local key="$2"
  if [[ ! -f "$file" ]]; then
    return 0
  fi
  if ! pick_any_python_bin; then
    return 0
  fi
  "$PYTHON_BIN" - <<PY
from pathlib import Path

text = Path("$file").read_text(encoding="utf-8", errors="replace")
target = "${key}"
for raw_line in text.splitlines():
    line = raw_line.strip()
    if "=" not in line:
        continue
    name, value = line.split("=", 1)
    if name.strip() != target:
        continue
    resolved = value.strip().strip('"').strip("'")
    if resolved:
        print(resolved)
    break
PY
}

read_source_build_info_field() {
  local key="$1"
  if [[ ! -f "$REPO_ROOT/BUILD_INFO.json" ]]; then
    return 0
  fi
  if ! pick_any_python_bin; then
    return 0
  fi
  "$PYTHON_BIN" - <<PY
from pathlib import Path
import json

payload = json.loads(Path("$REPO_ROOT/BUILD_INFO.json").read_text(encoding="utf-8", errors="replace"))
value = payload.get("${key}") if isinstance(payload, dict) else None
if value not in (None, ""):
    print(str(value).strip())
PY
}

resolve_install_version() {
  if [[ -n "${CCB_BUILD_VERSION:-}" ]]; then
    echo "$CCB_BUILD_VERSION"
    return
  fi
  local build_info_version
  build_info_version="$(read_source_build_info_field "version")"
  if [[ -n "$build_info_version" ]]; then
    echo "$build_info_version"
    return
  fi
  if [[ -f "$REPO_ROOT/VERSION" ]]; then
    tr -d '[:space:]' < "$REPO_ROOT/VERSION"
    return
  fi
  read_embedded_assignment "$REPO_ROOT/ccb" "VERSION"
}

resolve_source_kind() {
  if [[ -n "${CCB_SOURCE_KIND:-}" ]]; then
    echo "$CCB_SOURCE_KIND"
    return
  fi
  local build_info_source_kind
  build_info_source_kind="$(read_source_build_info_field "source_kind")"
  if [[ -n "$build_info_source_kind" ]]; then
    echo "$build_info_source_kind"
    return
  fi
  if [[ -d "$REPO_ROOT/.git" ]]; then
    echo "source"
  else
    echo "release"
  fi
}

resolve_build_channel() {
  if [[ -n "${CCB_BUILD_CHANNEL:-}" ]]; then
    echo "$CCB_BUILD_CHANNEL"
    return
  fi
  local build_info_channel
  build_info_channel="$(read_source_build_info_field "channel")"
  if [[ -n "$build_info_channel" ]]; then
    echo "$build_info_channel"
    return
  fi
  local source_kind
  source_kind="$(resolve_source_kind)"
  if [[ "$source_kind" == "source" ]]; then
    echo "dev"
  else
    echo "stable"
  fi
}

resolve_install_mode() {
  local source_kind
  source_kind="$(resolve_source_kind)"
  if [[ "$source_kind" == "source" ]]; then
    echo "source"
  else
    echo "release"
  fi
}

install_uses_live_source() {
  [[ "$(resolve_install_mode)" == "source" ]]
}

managed_venv_path() {
  echo "$INSTALL_PREFIX/.venv"
}

managed_venv_python() {
  echo "$(managed_venv_path)/bin/python"
}

use_managed_venv() {
  local requested="${CCB_USE_MANAGED_VENV:-auto}"
  if install_uses_live_source; then
    return 1
  fi
  case "$requested" in
    1|true|yes|on) return 0 ;;
    0|false|no|off) return 1 ;;
  esac
  [[ "$(resolve_install_mode)" == "release" && "$(detect_platform)" == "macos" ]]
}

resolve_live_source_root() {
  local root="${CCB_SOURCE_ROOT:-$REPO_ROOT}"
  echo "$root"
}

resolve_install_asset_root() {
  if install_uses_live_source; then
    resolve_live_source_root
  else
    echo "$INSTALL_PREFIX"
  fi
}

read_simple_json_string_field() {
  local file="$1"
  local key="$2"
  if [[ ! -f "$file" ]]; then
    return 0
  fi
  grep -o "\"${key}\"[[:space:]]*:[[:space:]]*\"[^\"]*\"" "$file" 2>/dev/null | head -1 | sed -E "s/.*:[[:space:]]*\"([^\"]*)\"/\1/"
}

json_string_literal() {
  local value="$1"
  if ! pick_any_python_bin; then
    echo "ERROR: python required to encode install metadata" >&2
    exit 1
  fi
  JSON_LITERAL_VALUE="$value" "$PYTHON_BIN" - <<'PY'
import json
import os

print(json.dumps(os.environ.get("JSON_LITERAL_VALUE", ""), ensure_ascii=True))
PY
}

read_installed_version() {
  if [[ -f "$INSTALL_PREFIX/VERSION" ]]; then
    tr -d '[:space:]' < "$INSTALL_PREFIX/VERSION"
    return
  fi
  local build_info_version
  build_info_version="$(read_simple_json_string_field "$INSTALL_PREFIX/BUILD_INFO.json" "version")"
  if [[ -n "$build_info_version" ]]; then
    echo "$build_info_version"
    return
  fi
  if [[ -f "$INSTALL_PREFIX/ccb" ]]; then
    sed -n 's/^VERSION[[:space:]]*=[[:space:]]*"\(.*\)"/\1/p' "$INSTALL_PREFIX/ccb" | head -1
  fi
}

version_major() {
  local version_text="${1:-}"
  if [[ "$version_text" =~ ^([0-9]+)(\..*)?$ ]]; then
    echo "${BASH_REMATCH[1]}"
  fi
}

require_major_upgrade_confirmation() {
  local target_version existing_version target_major existing_major
  target_version="$(resolve_install_version)"
  existing_version="$(read_installed_version)"

  if [[ -z "$target_version" || -z "$existing_version" ]]; then
    return 0
  fi

  target_major="$(version_major "$target_version")"
  existing_major="$(version_major "$existing_version")"
  if [[ -z "$target_major" || -z "$existing_major" ]]; then
    return 0
  fi

  if (( target_major < 6 || existing_major >= 6 )); then
    return 0
  fi

  if [[ "${CCB_CONFIRM_MAJOR_UPGRADE:-}" == "1" || "${CCB_INSTALL_ASSUME_YES:-}" == "1" ]]; then
    return 0
  fi

  echo
  echo "================================================================"
  echo "WARN: Major upgrade confirmation required"
  echo "================================================================"
  echo "Detected existing install : v$existing_version"
  echo "Incoming install version  : v$target_version"
  echo
  echo "CCB v6 replaces the old source-era update path and rebuilds runtime behavior."
  echo "To avoid accidental upgrades, this install stops until you confirm explicitly."
  echo
  echo "Continue options:"
  echo "  1. Interactive shell: rerun and answer the prompt"
  echo "  2. Non-interactive : CCB_CONFIRM_MAJOR_UPGRADE=1 ccb update"
  echo "  3. Direct install  : CCB_CONFIRM_MAJOR_UPGRADE=1 ./install.sh install"
  echo "================================================================"

  if [[ ! -t 0 ]]; then
    echo "ERROR: Aborting major upgrade in non-interactive mode without confirmation."
    return 1
  fi

  local reply
  read -r -p "Confirm replacing the existing pre-v6 install with CCB v${target_version}? (y/N): " reply
  case "$reply" in
    y|Y|yes|YES)
      return 0
      ;;
    *)
      echo "Installation cancelled"
      return 1
      ;;
  esac
}

print_install_identity_summary() {
  local install_mode source_kind channel version
  install_mode="$(resolve_install_mode)"
  source_kind="$(resolve_source_kind)"
  channel="$(resolve_build_channel)"
  version="$(resolve_install_version)"
  echo "   install_mode=$install_mode"
  echo "   source_kind=$source_kind"
  echo "   channel=$channel"
  if [[ -n "$version" ]]; then
    echo "   version=$version"
  fi
}

print_install_identity_notice() {
  local source_kind
  source_kind="$(resolve_source_kind)"
  case "$source_kind" in
    source)
      msg install_notice_source_title
      echo "   $(msg install_notice_source_body)"
      ;;
    preview)
      msg install_notice_preview_title
      echo "   $(msg install_notice_preview_body)"
      ;;
    *)
      msg install_notice_release
      ;;
  esac
}

write_install_metadata() {
  local version commit date build_time installed_at platform_name arch_name channel source_kind install_mode
  version="$(resolve_install_version)"
  commit="$(read_embedded_assignment "$INSTALL_PREFIX/ccb" "GIT_COMMIT")"
  date="$(read_embedded_assignment "$INSTALL_PREFIX/ccb" "GIT_DATE")"
  if [[ -z "$commit" ]]; then
    commit="$(read_source_build_info_field "commit")"
  fi
  if [[ -z "$date" ]]; then
    date="$(read_source_build_info_field "date")"
  fi
  build_time="${CCB_BUILD_TIME:-$(read_source_build_info_field "build_time")}"
  if [[ -z "$build_time" ]]; then
    build_time="$(current_utc_timestamp)"
  fi
  installed_at="$(current_utc_timestamp)"
  platform_name="${CCB_BUILD_PLATFORM:-$(read_source_build_info_field "platform")}"
  if [[ -z "$platform_name" ]]; then
    platform_name="$(detect_platform)"
  fi
  arch_name="${CCB_BUILD_ARCH:-$(read_source_build_info_field "arch")}"
  if [[ -z "$arch_name" ]]; then
    arch_name="$(uname -m 2>/dev/null || echo unknown)"
  fi
  source_kind="$(resolve_source_kind)"
  channel="$(resolve_build_channel)"
  install_mode="$(resolve_install_mode)"

  if ! pick_any_python_bin; then
    echo "WARN: python required to write VERSION/BUILD_INFO metadata"
    return
  fi
  local version_json commit_json date_json build_time_json platform_json arch_json channel_json source_kind_json install_mode_json installed_at_json
  version_json="$(json_string_literal "$version")"
  commit_json="$(json_string_literal "$commit")"
  date_json="$(json_string_literal "$date")"
  build_time_json="$(json_string_literal "$build_time")"
  platform_json="$(json_string_literal "$platform_name")"
  arch_json="$(json_string_literal "$arch_name")"
  channel_json="$(json_string_literal "$channel")"
  source_kind_json="$(json_string_literal "$source_kind")"
  install_mode_json="$(json_string_literal "$install_mode")"
  installed_at_json="$(json_string_literal "$installed_at")"

  "$PYTHON_BIN" - <<PY
from pathlib import Path
import json

install_prefix = Path("$INSTALL_PREFIX")
payload = {
    "version": ${version_json},
    "commit": ${commit_json},
    "date": ${date_json},
    "build_time": ${build_time_json},
    "platform": ${platform_json},
    "arch": ${arch_json},
    "channel": ${channel_json},
    "source_kind": ${source_kind_json},
    "install_mode": ${install_mode_json},
    "installed_at": ${installed_at_json},
}

version_text = str(payload["version"] or "").strip()
if version_text:
    (install_prefix / "VERSION").write_text(version_text + "\\n", encoding="utf-8")
(install_prefix / "BUILD_INFO.json").write_text(
    json.dumps(payload, ensure_ascii=True, indent=2) + "\\n",
    encoding="utf-8",
)
PY
}

check_wsl_compatibility() {
  if is_wsl; then
    local ver
    ver="$(get_wsl_version)"
    echo "OK: Detected WSL $ver environment"
  fi
}

confirm_backend_env_wsl() {
  if ! is_wsl; then
    return
  fi

  if [[ "${CCB_INSTALL_ASSUME_YES:-}" == "1" ]]; then
    return
  fi

  if [[ ! -t 0 ]]; then
    echo "ERROR: Installing in WSL but detected non-interactive terminal; aborted to avoid env mismatch."
    echo "   If you confirm codex/gemini will be installed and run in WSL:"
    echo "   Re-run: CCB_INSTALL_ASSUME_YES=1 ./install.sh install"
    exit 1
  fi

  echo
  echo "================================================================"
  echo "WARN: Detected WSL environment"
  echo "================================================================"
  echo "ccb/ask/ping/pend must run in the same environment as codex/gemini."
  echo
  echo "Please confirm: you will install and run codex/gemini in WSL (not Windows native)."
  echo "If you plan to run codex/gemini in Windows native, exit and run on Windows side:"
  echo "   powershell -ExecutionPolicy Bypass -File .\\install.ps1 install"
  echo "================================================================"
  echo
  read -r -p "Confirm continue installing in WSL? (y/N): " reply
  case "$reply" in
    y|Y|yes|YES) ;;
    *) echo "Installation cancelled"; exit 1 ;;
  esac
}

print_tmux_install_hint() {
  local platform
  platform="$(detect_platform)"
  case "$platform" in
    macos)
      if command -v brew >/dev/null 2>&1; then
        echo "   macOS: Run 'brew install tmux'"
      else
        echo "   macOS: Homebrew not detected, install from https://brew.sh then run 'brew install tmux'"
      fi
      ;;
    linux)
      if command -v apt-get >/dev/null 2>&1; then
        echo "   Debian/Ubuntu: sudo apt-get update && sudo apt-get install -y tmux"
      elif command -v dnf >/dev/null 2>&1; then
        echo "   Fedora/CentOS/RHEL: sudo dnf install -y tmux"
      elif command -v yum >/dev/null 2>&1; then
        echo "   CentOS/RHEL: sudo yum install -y tmux"
      elif command -v pacman >/dev/null 2>&1; then
        echo "   Arch/Manjaro: sudo pacman -S tmux"
      elif command -v apk >/dev/null 2>&1; then
        echo "   Alpine: sudo apk add tmux"
      elif command -v zypper >/dev/null 2>&1; then
        echo "   openSUSE: sudo zypper install -y tmux"
      else
        echo "   Linux: Please use your distro's package manager to install tmux"
      fi
      ;;
    *)
      echo "   See https://github.com/tmux/tmux/wiki/Installing for tmux installation"
      ;;
  esac
}

require_terminal_backend() {
  local platform
  platform="$(detect_platform)"

  if [[ "$platform" == "macos" ]] && ! command -v brew >/dev/null 2>&1; then
    echo "WARN: Homebrew not found on macOS. Install from https://brew.sh before installing tmux and other dependencies."
  fi

  if [[ -n "${TMUX:-}" ]]; then
    echo "OK: Detected tmux environment"
    return
  fi

  if command -v tmux >/dev/null 2>&1; then
    echo "OK: Detected tmux"
    return
  fi

  echo "ERROR: Missing dependency: tmux"

  if [[ "$platform" == "macos" ]]; then
    echo
    echo "NOTE: macOS user recommended options:"
    echo "   - Install tmux: brew install tmux"
  fi

  print_tmux_install_hint
  exit 1
}

copy_project() {
  local staging
  staging="$(mktemp -d)"
  trap 'rm -rf "$staging"' EXIT

  if command -v rsync >/dev/null 2>&1; then
    rsync -a \
      --exclude '.git/' \
      --exclude '__pycache__/' \
      --exclude '.pytest_cache/' \
      --exclude '.mypy_cache/' \
      --exclude '.venv/' \
      --exclude 'lib/web/' \
      --exclude 'bin/ccb-web' \
      "$REPO_ROOT"/ "$staging"/
  else
    tar -C "$REPO_ROOT" \
      --exclude '.git' \
      --exclude '__pycache__' \
      --exclude '.pytest_cache' \
      --exclude '.mypy_cache' \
      --exclude '.venv' \
      --exclude 'lib/web' \
      --exclude 'bin/ccb-web' \
      -cf - . | tar -C "$staging" -xf -
  fi

  rm -rf "$INSTALL_PREFIX"
  mkdir -p "$(dirname "$INSTALL_PREFIX")"
  mv "$staging" "$INSTALL_PREFIX"
  trap - EXIT

  # Update GIT_COMMIT and GIT_DATE in ccb file
  local git_commit="" git_date=""

  # Method 1: From git repo or git worktree
  if command -v git >/dev/null 2>&1 && git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git_commit=$(git -C "$REPO_ROOT" log -1 --format='%h' 2>/dev/null || echo "")
    git_date=$(git -C "$REPO_ROOT" log -1 --format='%cs' 2>/dev/null || echo "")
  fi

  # Method 2: From source BUILD_INFO.json (release artifact source of truth)
  if [[ -z "$git_commit" ]]; then
    git_commit="$(read_source_build_info_field "commit")"
    git_date="$(read_source_build_info_field "date")"
  fi

  # Method 3: From environment variables (set by ccb update)
  if [[ -z "$git_commit" && -n "${CCB_GIT_COMMIT:-}" ]]; then
    git_commit="$CCB_GIT_COMMIT"
    git_date="${CCB_GIT_DATE:-}"
  fi

  # Method 4: From embedded package metadata
  if [[ -z "$git_commit" && -f "$INSTALL_PREFIX/ccb" ]]; then
    git_commit=$(sed -n 's/^GIT_COMMIT = "\(.*\)"/\1/p' "$INSTALL_PREFIX/ccb" | head -1)
    git_date=$(sed -n 's/^GIT_DATE = "\(.*\)"/\1/p' "$INSTALL_PREFIX/ccb" | head -1)
  fi

  # Method 5: From GitHub API (fallback)
  if [[ -z "$git_commit" ]] && command -v curl >/dev/null 2>&1; then
    local api_response
    api_response=$(curl -fsSL "https://api.github.com/repos/bfly123/claude_code_bridge/commits/main" 2>/dev/null || echo "")
    if [[ -n "$api_response" ]]; then
      git_commit=$(echo "$api_response" | grep -o '"sha": "[^"]*"' | head -1 | cut -d'"' -f4 | cut -c1-7)
      git_date=$(echo "$api_response" | grep -o '"date": "[^"]*"' | head -1 | cut -d'"' -f4 | cut -c1-10)
    fi
  fi

  if [[ -n "$git_commit" && -f "$INSTALL_PREFIX/ccb" ]]; then
    sed -i.bak "s/^GIT_COMMIT = .*/GIT_COMMIT = \"$git_commit\"/" "$INSTALL_PREFIX/ccb"
    sed -i.bak "s/^GIT_DATE = .*/GIT_DATE = \"$git_date\"/" "$INSTALL_PREFIX/ccb"
    rm -f "$INSTALL_PREFIX/ccb.bak"
  fi
}

prepare_install_tree() {
  if install_uses_live_source; then
    local live_root
    live_root="$(resolve_live_source_root)"
    if [[ ! -f "$live_root/ccb" ]]; then
      echo "ERROR: Live source root missing ccb entrypoint: $live_root"
      exit 1
    fi
    echo "Using live source tree: $live_root"
    return 0
  fi
  copy_project
}

install_managed_venv() {
  if ! use_managed_venv; then
    return 0
  fi
  if ! pick_python_bin; then
    echo "ERROR: Missing dependency: python (3.10+ required)" >&2
    echo "   Please install Python 3.10+ and ensure it is on PATH, then retry." >&2
    exit 1
  fi
  local venv_dir venv_python
  venv_dir="$(managed_venv_path)"
  venv_python="$(managed_venv_python)"
  echo "Creating managed Python venv: $venv_dir"
  rm -rf "$venv_dir"
  if ! "$PYTHON_BIN" -m venv "$venv_dir"; then
    echo "ERROR: Failed to create managed Python venv at $venv_dir"
    case "$(detect_platform)" in
      macos)
        echo "   macOS: install or repair Homebrew Python: brew install python"
        ;;
      linux)
        echo "   Debian/Ubuntu: sudo apt-get install -y python3-venv"
        ;;
    esac
    exit 1
  fi
  if [[ ! -x "$venv_python" ]]; then
    echo "ERROR: Managed venv Python not executable: $venv_python"
    exit 1
  fi
  if ! "$venv_python" -m pip install --upgrade pip >/dev/null 2>&1; then
    echo "WARN: unable to upgrade pip inside managed venv; continuing"
  fi
  install_watchdog_for_python "$venv_python"
  echo "OK: Managed Python venv ready"
}

write_live_source_wrapper() {
  local target="$1"
  local wrapper_path="$2"
  local quoted_target
  printf -v quoted_target '%q' "$target"
  cat > "$wrapper_path" <<EOF
#!/usr/bin/env bash
exec ${quoted_target} "\$@"
EOF
  chmod +x "$wrapper_path" 2>/dev/null || true
}

clear_installed_path() {
  local path="$1"
  if [[ -L "$path" || -f "$path" ]]; then
    rm -f "$path"
    return 0
  fi
  if [[ -d "$path" ]]; then
    rm -rf "$path"
  fi
}

install_owned_file() {
  local source_path="$1"
  local destination_path="$2"
  local file_mode="${3:-}"

  if [[ ! -f "$source_path" ]]; then
    echo "WARN: File not found $source_path, skipping"
    return 1
  fi

  mkdir -p "$(dirname "$destination_path")"
  clear_installed_path "$destination_path"

  if install_uses_live_source; then
    if ! ln -s "$source_path" "$destination_path" 2>/dev/null; then
      echo "ERROR: source dev install requires symlink support for $destination_path"
      exit 1
    fi
    return 0
  fi

  cp -f "$source_path" "$destination_path"
  if [[ -n "$file_mode" ]]; then
    chmod "$file_mode" "$destination_path" 2>/dev/null || true
  fi
}

install_owned_directory() {
  local source_path="$1"
  local destination_path="$2"

  if [[ ! -d "$source_path" ]]; then
    echo "WARN: Directory not found $source_path, skipping"
    return 1
  fi

  mkdir -p "$(dirname "$destination_path")"
  clear_installed_path "$destination_path"

  if install_uses_live_source; then
    if ! ln -s "$source_path" "$destination_path" 2>/dev/null; then
      echo "ERROR: source dev install requires symlink support for $destination_path"
      exit 1
    fi
    return 0
  fi

  cp -rf "$source_path" "$destination_path"
}

install_owned_executable() {
  local source_path="$1"
  local destination_path="$2"

  if [[ ! -f "$source_path" ]]; then
    echo "WARN: Script not found $source_path, skipping"
    return 1
  fi

  mkdir -p "$(dirname "$destination_path")"
  chmod +x "$source_path" 2>/dev/null || true
  clear_installed_path "$destination_path"

  if ln -s "$source_path" "$destination_path" 2>/dev/null; then
    return 0
  fi

  if install_uses_live_source; then
    write_live_source_wrapper "$source_path" "$destination_path"
    return 0
  fi

  cp -f "$source_path" "$destination_path"
  chmod +x "$destination_path" 2>/dev/null || true
}

write_managed_venv_python_wrapper() {
  local source_path="$1"
  local destination_path="$2"
  local venv_python
  local absolute_source="$source_path"
  if [[ "$absolute_source" != /* ]]; then
    absolute_source="$(cd "$(dirname "$source_path")" && pwd)/$(basename "$source_path")"
  fi
  venv_python="$(managed_venv_python)"
  mkdir -p "$(dirname "$destination_path")"
  clear_installed_path "$destination_path"
  cat > "$destination_path" <<EOF
#!/usr/bin/env bash
if [[ "\${TERM:-}" == "xterm-ghostty" ]]; then
  export TERM=xterm-256color
fi
exec "$venv_python" "$absolute_source" "\$@"
EOF
  chmod +x "$destination_path" 2>/dev/null || true
}

install_entrypoint_executable() {
  local source_path="$1"
  local destination_path="$2"

  if [[ ! -f "$source_path" ]]; then
    echo "WARN: Script not found $source_path, skipping"
    return 1
  fi

  local absolute_source="$source_path"
  if [[ "$absolute_source" != /* ]]; then
    absolute_source="$(cd "$(dirname "$source_path")" && pwd)/$(basename "$source_path")"
  fi
  if use_managed_venv && [[ "$absolute_source" == "$INSTALL_PREFIX/"* ]]; then
    write_managed_venv_python_wrapper "$absolute_source" "$destination_path"
    return 0
  fi

  install_owned_executable "$source_path" "$destination_path"
}

install_bin_links() {
  mkdir -p "$BIN_DIR"
  local target_root
  target_root="$(resolve_install_asset_root)"

  for path in "${SCRIPTS_TO_LINK[@]}"; do
    local name
    name="$(basename "$path")"
    local target_path="$target_root/$path"
    install_entrypoint_executable "$target_path" "$BIN_DIR/$name"
  done

  for legacy in "${LEGACY_SCRIPTS[@]}"; do
    rm -f "$BIN_DIR/$legacy"
  done

  echo "Created executable links in $BIN_DIR"
}

ensure_path_configured() {
  # Check if BIN_DIR is already in PATH
  if [[ ":$PATH:" == *":$BIN_DIR:"* ]]; then
    return
  fi

  local shell_rc=""
  local current_shell
  current_shell="$(basename "${SHELL:-/bin/bash}")"

  case "$current_shell" in
    zsh)  shell_rc="$HOME/.zshrc" ;;
    bash)
      if [[ -f "$HOME/.bash_profile" ]]; then
        shell_rc="$HOME/.bash_profile"
      else
        shell_rc="$HOME/.bashrc"
      fi
      ;;
    *)    shell_rc="$HOME/.profile" ;;
  esac

  local path_line="export PATH=\"${BIN_DIR}:\$PATH\""

  # Check if already configured in shell rc
  if [[ -f "$shell_rc" ]] && grep -qF "$BIN_DIR" "$shell_rc" 2>/dev/null; then
    echo "PATH already configured in $shell_rc (restart terminal to apply)"
    return
  fi

  # Add to shell rc
  echo "" >> "$shell_rc"
  echo "# Added by ccb installer" >> "$shell_rc"
  echo "$path_line" >> "$shell_rc"
  echo "OK: Added $BIN_DIR to PATH in $shell_rc"
  echo "   Run: source $shell_rc  (or restart terminal)"
}

install_claude_commands() {
  local claude_dir
  claude_dir="$(detect_claude_dir)"
  mkdir -p "$claude_dir"
  local asset_root
  asset_root="$(resolve_install_asset_root)"

  # Clean up obsolete CCB commands (replaced by unified ask/ping/pend)
  local obsolete_cmds="bask.md bpend.md bping.md cask.md cpend.md cping.md dask.md dpend.md dping.md gask.md gpend.md gping.md hask.md hpend.md hping.md lask.md lpend.md lping.md oask.md opend.md oping.md qask.md qpend.md qping.md"
  for obs_cmd in $obsolete_cmds; do
    if [[ -f "$claude_dir/$obs_cmd" ]]; then
      rm -f "$claude_dir/$obs_cmd"
      echo "  Removed obsolete command: $obs_cmd"
    fi
  done

  for doc in "${CLAUDE_MARKDOWN[@]+"${CLAUDE_MARKDOWN[@]}"}"; do
    install_owned_file "$asset_root/commands/$doc" "$claude_dir/$doc" 0644
  done

  echo "Updated Claude commands directory: $claude_dir"
}

install_skill_entry() {
  local skill_dir="$1"
  local destination_dir="$2"
  local src_skill_md=""

  if [[ -f "$skill_dir/SKILL.md.bash" ]]; then
    src_skill_md="$skill_dir/SKILL.md.bash"
  elif [[ -f "$skill_dir/SKILL.md" ]]; then
    src_skill_md="$skill_dir/SKILL.md"
  else
    return 1
  fi

  clear_installed_path "$destination_dir"
  mkdir -p "$destination_dir"
  install_owned_file "$src_skill_md" "$destination_dir/SKILL.md" 0644

  local child
  for child in "$skill_dir"/*; do
    [[ -e "$child" ]] || continue
    local child_name
    child_name="$(basename "$child")"
    if [[ "$child_name" == "SKILL.md" || "$child_name" == "SKILL.md.bash" ]]; then
      continue
    fi
    if [[ -d "$child" ]]; then
      install_owned_directory "$child" "$destination_dir/$child_name"
    elif [[ -f "$child" ]]; then
      install_owned_file "$child" "$destination_dir/$child_name" 0644
    fi
  done
}

install_claude_skills() {
  local asset_root
  asset_root="$(resolve_install_asset_root)"
  local skills_src="$asset_root/claude_skills"
  local skills_dst="$HOME/.claude/skills"

  if [[ ! -d "$skills_src" ]]; then
    return
  fi

  mkdir -p "$skills_dst"

  # Clean up obsolete wrapper/provider skills
  local obsolete_skills="bask bpend bping cask cpend cping dask dpend dping gask gpend gping hask hpend hping lask lpend lping mounted oask opend oping qask qpend qping auto"
  for obs_skill in $obsolete_skills; do
    if [[ -d "$skills_dst/$obs_skill" ]]; then
      rm -rf "$skills_dst/$obs_skill"
      echo "  Removed obsolete skill: $obs_skill"
    fi
  done

  echo "Installing Claude skills (bash SKILL.md templates)..."
  for skill_dir in "$skills_src"/*/; do
    [[ -d "$skill_dir" ]] || continue
    local skill_name
    skill_name=$(basename "$skill_dir")
    [[ "$skill_name" == "docs" ]] && continue

    if [[ ! -f "$skill_dir/SKILL.md.bash" && ! -f "$skill_dir/SKILL.md" ]]; then
      continue
    fi

    local dst_dir="$skills_dst/$skill_name"
    install_skill_entry "${skill_dir%/}" "$dst_dir"

    echo "  Updated skill: $skill_name"
  done

  # Shared docs live at skills/docs but are not a "skill directory". Install them as well.
  if [[ -d "$skills_src/docs" ]]; then
    install_owned_directory "$skills_src/docs" "$skills_dst/docs"
    echo "  Installed skills docs: docs/"
  fi

  echo "Updated Claude skills directory: $skills_dst"
}

install_codex_skills() {
  local asset_root
  asset_root="$(resolve_install_asset_root)"
  local skills_src="$asset_root/codex_skills"
  local skills_dst="${CODEX_HOME:-$HOME/.codex}/skills"

  if [[ ! -d "$skills_src" ]]; then
    return
  fi

  mkdir -p "$skills_dst"

  # Clean up obsolete wrapper/provider skills
  local obsolete_skills="bask bpend bping cask cpend cping dask dpend dping gask gpend gping hask hpend hping lask lpend lping mounted oask opend oping qask qpend qping"
  for obs_skill in $obsolete_skills; do
    if [[ -d "$skills_dst/$obs_skill" ]]; then
      rm -rf "$skills_dst/$obs_skill"
      echo "  Removed obsolete skill: $obs_skill"
    fi
  done

  echo "Installing Codex skills (bash SKILL.md templates)..."
  for skill_dir in "$skills_src"/*/; do
    [[ -d "$skill_dir" ]] || continue
    local skill_name
    skill_name=$(basename "$skill_dir")

    if [[ ! -f "$skill_dir/SKILL.md.bash" && ! -f "$skill_dir/SKILL.md" ]]; then
      continue
    fi

    local dst_dir="$skills_dst/$skill_name"
    install_skill_entry "${skill_dir%/}" "$dst_dir"

    echo "  Updated Codex skill: $skill_name"
  done
  echo "Updated Codex skills directory: $skills_dst"
}

install_droid_skills() {
  local asset_root
  asset_root="$(resolve_install_asset_root)"
  local skills_src="$asset_root/droid_skills"
  local skills_dst="${FACTORY_HOME:-$HOME/.factory}/skills"

  if [[ ! -d "$skills_src" ]]; then
    return
  fi

  if ! command -v droid >/dev/null 2>&1; then
    return
  fi

  mkdir -p "$skills_dst"

  # Clean up obsolete wrapper/provider skills
  local obsolete_skills="bask bpend bping cask cpend cping dask dpend dping gask gpend gping hask hpend hping lask lpend lping mounted oask opend oping qask qpend qping"
  for obs_skill in $obsolete_skills; do
    if [[ -d "$skills_dst/$obs_skill" ]]; then
      rm -rf "$skills_dst/$obs_skill"
      echo "  Removed obsolete skill: $obs_skill"
    fi
  done

  echo "Installing Droid/Factory skills..."
  for skill_dir in "$skills_src"/*/; do
    [[ -d "$skill_dir" ]] || continue
    local skill_name
    skill_name=$(basename "$skill_dir")

    if [[ ! -f "$skill_dir/SKILL.md" ]]; then
      continue
    fi

    local dst_dir="$skills_dst/$skill_name"
    install_skill_entry "${skill_dir%/}" "$dst_dir"

    echo "  Updated Factory skill: $skill_name"
  done
  echo "Updated Factory skills directory: $skills_dst"
}

install_droid_delegation() {
  if [[ "${CCB_DROID_AUTOINSTALL:-1}" == "0" ]]; then
    return
  fi
  if ! command -v droid >/dev/null 2>&1; then
    return
  fi
  local py
  py="$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)"
  if [[ -z "$py" ]]; then
    echo "WARN: python required for Droid MCP setup; skipping"
    return
  fi
  local asset_root
  asset_root="$(resolve_install_asset_root)"
  local server="$asset_root/mcp/ccb-delegation/server.py"
  if [[ ! -f "$server" ]]; then
    echo "WARN: Droid MCP server not found at $server; skipping"
    return
  fi
  if [[ "${CCB_DROID_AUTOINSTALL_FORCE:-0}" == "1" ]]; then
    droid mcp remove ccb-delegation >/dev/null 2>&1 || true
  fi
  if droid mcp add ccb-delegation --type stdio "$py" "$server" >/dev/null 2>&1; then
    echo "OK: Droid MCP delegation registered"
  else
    echo "WARN: Failed to register Droid MCP delegation (already registered or droid config unavailable)"
  fi
}

CCB_START_MARKER="<!-- CCB_CONFIG_START -->"
CCB_END_MARKER="<!-- CCB_CONFIG_END -->"
LEGACY_RULE_MARKER="## Codex 协作规则"

remove_codex_mcp() {
  local claude_config="$HOME/.claude.json"

  if [[ ! -f "$claude_config" ]]; then
    return
  fi

  if ! pick_python_bin; then
    echo "WARN: python required to detect MCP configuration"
    return
  fi

  local has_codex_mcp
  has_codex_mcp=$("$PYTHON_BIN" -c "
import json

try:
    with open('$claude_config', 'r', encoding='utf-8') as f:
        data = json.load(f)
    projects = data.get('projects', {}) if isinstance(data, dict) else {}
    found = False
    if isinstance(projects, dict):
        for _proj, cfg in projects.items():
            if not isinstance(cfg, dict):
                continue
            servers = cfg.get('mcpServers', {})
            if not isinstance(servers, dict):
                continue
            for name in list(servers.keys()):
                if 'codex' in str(name).lower():
                    found = True
                    break
            if found:
                break
    print('yes' if found else 'no')
except Exception:
    print('no')
" 2>/dev/null)

  if [[ "$has_codex_mcp" == "yes" ]]; then
    echo "WARN: Detected codex-related MCP configuration, removing to avoid conflicts..."
    "$PYTHON_BIN" -c "
import json
import sys

try:
    with open('$claude_config', 'r', encoding='utf-8') as f:
        data = json.load(f)
    removed = []
    projects = data.get('projects', {}) if isinstance(data, dict) else {}
    if isinstance(projects, dict):
        for proj, cfg in projects.items():
            if not isinstance(cfg, dict):
                continue
            servers = cfg.get('mcpServers')
            if not isinstance(servers, dict):
                continue
            for name in list(servers.keys()):
                if 'codex' in str(name).lower():
                    del servers[name]
                    removed.append(f'{proj}: {name}')
    with open('$claude_config', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    if removed:
        print('Removed the following MCP configurations:')
        for r in removed:
            print(f'  - {r}')
except Exception as e:
    sys.stderr.write(f'WARN: failed cleaning MCP config: {e}\\n')
    sys.exit(0)
"
    echo "OK: Codex MCP configuration cleaned"
  fi
}

install_claude_md_config() {
  local claude_md="$HOME/.claude/CLAUDE.md"
  local md_mode="${CCB_CLAUDE_MD_MODE:-inline}"
  local asset_root
  asset_root="$(resolve_install_asset_root)"
  local full_template="$asset_root/config/claude-md-ccb.md"
  local route_template="$asset_root/config/claude-md-ccb-route.md"
  local external_config="$HOME/.claude/rules/ccb-config.md"

  # Select template based on mode
  local template
  if [[ "$md_mode" == "route" ]]; then
    template="$route_template"
  else
    template="$full_template"
  fi

  mkdir -p "$HOME/.claude"
  if ! pick_python_bin; then
    echo "ERROR: python required to update CLAUDE.md"
    return 1
  fi

  if [[ ! -f "$template" ]]; then
    echo "WARN: Template not found: $template; skipping CLAUDE.md injection"
    return 1
  fi

  # In route mode, write full config to external file
  if [[ "$md_mode" == "route" ]]; then
    mkdir -p "$HOME/.claude/rules"
    cp "$full_template" "$external_config"
    echo "Wrote full CCB config to $external_config"
  fi

  local ccb_content
  ccb_content="$(cat "$template")"

  if [[ -f "$claude_md" ]]; then
    if grep -q "$CCB_START_MARKER" "$claude_md" 2>/dev/null; then
      echo "Updating existing CCB config block (mode: $md_mode)..."
      "$PYTHON_BIN" -c "
import re, sys

with open(sys.argv[1], 'r', encoding='utf-8') as f:
    content = f.read()
with open(sys.argv[2], 'r', encoding='utf-8') as f:
    new_block = f.read().strip()
pattern = r'<!-- CCB_CONFIG_START -->.*?<!-- CCB_CONFIG_END -->'
content = re.sub(pattern, new_block, content, flags=re.DOTALL)
with open(sys.argv[1], 'w', encoding='utf-8') as f:
    f.write(content)
" "$claude_md" "$template"
    elif grep -qE "$LEGACY_RULE_MARKER|## Codex Collaboration Rules|## Gemini|## OpenCode" "$claude_md" 2>/dev/null; then
      echo "Removing legacy rules and adding new CCB config block..."
      "$PYTHON_BIN" -c "
import re, sys

with open(sys.argv[1], 'r', encoding='utf-8') as f:
    content = f.read()
patterns = [
    r'## Codex Collaboration Rules.*?(?=\n## (?!Gemini)|\Z)',
    r'## Codex 协作规则.*?(?=\n## |\Z)',
    r'## Gemini Collaboration Rules.*?(?=\n## |\Z)',
    r'## Gemini 协作规则.*?(?=\n## |\Z)',
    r'## OpenCode Collaboration Rules.*?(?=\n## |\Z)',
    r'## OpenCode 协作规则.*?(?=\n## |\Z)',
]
for p in patterns:
    content = re.sub(p, '', content, flags=re.DOTALL)
content = content.rstrip() + '\n'
with open(sys.argv[1], 'w', encoding='utf-8') as f:
    f.write(content)
" "$claude_md"
      cat "$template" >> "$claude_md"
    else
      echo "" >> "$claude_md"
      cat "$template" >> "$claude_md"
    fi
  else
    cat "$template" > "$claude_md"
  fi

  echo "Updated AI collaboration rules in $claude_md (mode: $md_mode)"
}

CCB_ROLES_START_MARKER="<!-- CCB_ROLES_START -->"
CCB_ROLES_END_MARKER="<!-- CCB_ROLES_END -->"
CCB_RUBRICS_START_MARKER="<!-- REVIEW_RUBRICS_START -->"
CCB_RUBRICS_END_MARKER="<!-- REVIEW_RUBRICS_END -->"

install_agents_md_config() {
  if install_uses_live_source; then
    echo "Skipping AGENTS.md injection for source dev install (avoid mutating live repo)."
    return 0
  fi
  local agents_md="$INSTALL_PREFIX/AGENTS.md"
  local template="$INSTALL_PREFIX/config/agents-md-ccb.md"

  if ! pick_python_bin; then
    echo "WARN: python required to update AGENTS.md; skipping"
    return 1
  fi
  if [[ ! -f "$template" ]]; then
    echo "WARN: Template not found: $template; skipping AGENTS.md injection"
    return 1
  fi

  if [[ -f "$agents_md" ]]; then
    # Replace existing CCB blocks if present
    local updated=false
    if grep -q "$CCB_ROLES_START_MARKER" "$agents_md" 2>/dev/null || \
       grep -q "$CCB_RUBRICS_START_MARKER" "$agents_md" 2>/dev/null; then
      echo "Updating existing CCB blocks in AGENTS.md..."
      "$PYTHON_BIN" -c "
import re, sys

with open(sys.argv[1], 'r', encoding='utf-8') as f:
    content = f.read()
with open(sys.argv[2], 'r', encoding='utf-8') as f:
    new_block = f.read().strip()

# Remove old roles block
content = re.sub(
    r'<!-- CCB_ROLES_START -->.*?<!-- CCB_ROLES_END -->',
    '', content, flags=re.DOTALL)
# Remove old rubrics block
content = re.sub(
    r'<!-- REVIEW_RUBRICS_START -->.*?<!-- REVIEW_RUBRICS_END -->',
    '', content, flags=re.DOTALL)
content = content.rstrip() + '\n\n' + new_block + '\n'
with open(sys.argv[1], 'w', encoding='utf-8') as f:
    f.write(content)
" "$agents_md" "$template"
      updated=true
    fi
    if ! $updated; then
      echo "" >> "$agents_md"
      cat "$template" >> "$agents_md"
    fi
  else
    cat "$template" > "$agents_md"
  fi

  echo "Updated AGENTS.md: $agents_md"
}

install_clinerules_config() {
  if install_uses_live_source; then
    echo "Skipping .clinerules injection for source dev install (avoid mutating live repo)."
    return 0
  fi
  local clinerules="$INSTALL_PREFIX/.clinerules"
  local template="$INSTALL_PREFIX/config/clinerules-ccb.md"

  if ! pick_python_bin; then
    echo "WARN: python required to update .clinerules; skipping"
    return 1
  fi
  if [[ ! -f "$template" ]]; then
    echo "WARN: Template not found: $template; skipping .clinerules injection"
    return 1
  fi

  if [[ -f "$clinerules" ]]; then
    if grep -q "$CCB_ROLES_START_MARKER" "$clinerules" 2>/dev/null; then
      echo "Updating existing CCB roles block in .clinerules..."
      "$PYTHON_BIN" -c "
import re, sys

with open(sys.argv[1], 'r', encoding='utf-8') as f:
    content = f.read()
with open(sys.argv[2], 'r', encoding='utf-8') as f:
    new_block = f.read().strip()

content = re.sub(
    r'<!-- CCB_ROLES_START -->.*?<!-- CCB_ROLES_END -->',
    new_block, content, flags=re.DOTALL)
with open(sys.argv[1], 'w', encoding='utf-8') as f:
    f.write(content)
" "$clinerules" "$template"
    else
      echo "" >> "$clinerules"
      cat "$template" >> "$clinerules"
    fi
  else
    cat "$template" > "$clinerules"
  fi

  echo "Updated .clinerules: $clinerules"
}

install_settings_permissions() {
  local settings_file="$HOME/.claude/settings.json"
  mkdir -p "$HOME/.claude"

  local perms_to_add=(
    'Bash(ccb ask *)'
    'Bash(ccb ping *)'
    'Bash(ccb pend *)'
  )

  if [[ ! -f "$settings_file" ]]; then
    cat > "$settings_file" << 'SETTINGS'
{
	  "permissions": {
	    "allow": [
	      "Bash(ccb ask *)",
	      "Bash(ccb ping *)",
	      "Bash(ccb pend *)"
	    ],
    "deny": []
  }
}
SETTINGS
    echo "Created $settings_file with permissions"
    return
  fi

  local perms_to_remove=(
    'Bash(ask *)'
    'Bash(ccb provider ping *)'
    'Bash(ccb provider pend *)'
    'Bash(ping *)'
    'Bash(ccb-ping *)'
    'Bash(pend *)'
  )
  if pick_python_bin; then
    local add_json remove_json
    add_json="$(printf '%s\n' "${perms_to_add[@]}" | "$PYTHON_BIN" -c 'import json,sys; print(json.dumps([line.rstrip("\n") for line in sys.stdin]))')"
    remove_json="$(printf '%s\n' "${perms_to_remove[@]}" | "$PYTHON_BIN" -c 'import json,sys; print(json.dumps([line.rstrip("\n") for line in sys.stdin]))')"
    "$PYTHON_BIN" -c "
import json

path = '$settings_file'
perms_to_add = json.loads('''$add_json''')
perms_to_remove = set(json.loads('''$remove_json'''))

try:
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
except Exception:
    data = {}

if not isinstance(data, dict):
    data = {}
perms = data.get('permissions')
if not isinstance(perms, dict):
    perms = {}
    data['permissions'] = perms
allow = perms.get('allow')
if not isinstance(allow, list):
    allow = []
deny = perms.get('deny')
if not isinstance(deny, list):
    deny = []

new_allow = [entry for entry in allow if entry not in perms_to_remove]
for entry in perms_to_add:
    if entry not in new_allow:
        new_allow.append(entry)

perms['allow'] = new_allow
perms['deny'] = deny

with open(path, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
    f.write('\n')
" || return 1
    echo "Updated $settings_file permissions"
  else
    echo "WARN: python required to update $settings_file permissions"
  fi
}

CCB_TMUX_MARKER="# CCB (Claude Code Bridge) tmux configuration"
CCB_TMUX_MARKER_LEGACY="# CCB tmux configuration"

remove_ccb_tmux_block_from_file() {
  local target_conf="$1"

  if [[ ! -f "$target_conf" ]]; then
    return 0
  fi

  if ! grep -q "$CCB_TMUX_MARKER" "$target_conf" 2>/dev/null && \
     ! grep -q "$CCB_TMUX_MARKER_LEGACY" "$target_conf" 2>/dev/null; then
    return 0
  fi

  if ! pick_any_python_bin; then
    return 1
  fi

  "$PYTHON_BIN" -c "
import re
path = '$target_conf'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()
# Remove CCB tmux config block (both new and legacy markers)
pattern = r'\n*# =+\n# CCB \(Claude Code Bridge\) tmux configuration.*?# =+\n# End of CCB tmux configuration\n# =+'
content = re.sub(pattern, '', content, flags=re.DOTALL)
pattern = r'\n*# CCB tmux configuration.*'
content = re.sub(pattern, '', content, flags=re.DOTALL)
with open(path, 'w', encoding='utf-8') as f:
    f.write(content.strip() + '\n' if content.strip() else '')
"
}

install_tmux_config() {
  local tmux_conf_main="$HOME/.tmux.conf"
  local tmux_conf_local="$HOME/.tmux.conf.local"
  local tmux_conf="$tmux_conf_main"
  local reload_conf="$tmux_conf_main"
  local asset_root
  asset_root="$(resolve_install_asset_root)"
  local ccb_tmux_conf="$asset_root/config/tmux-ccb.conf"
  local ccb_status_script="$asset_root/config/ccb-status.sh"
  local status_install_path="$BIN_DIR/ccb-status.sh"

  if [[ ! -f "$ccb_tmux_conf" ]]; then
    return
  fi

  mkdir -p "$BIN_DIR"

  # Install ccb-status.sh script
  if [[ -f "$ccb_status_script" ]]; then
    install_owned_executable "$ccb_status_script" "$status_install_path"
    echo "Installed: $status_install_path"
  fi

  # Install ccb-border.sh script (dynamic pane border colors)
  local ccb_border_script="$asset_root/config/ccb-border.sh"
  local border_install_path="$BIN_DIR/ccb-border.sh"
  if [[ -f "$ccb_border_script" ]]; then
    install_owned_executable "$ccb_border_script" "$border_install_path"
    echo "Installed: $border_install_path"
  fi

  # Install ccb-git.sh script (cached git status for tmux status line)
  local ccb_git_script="$asset_root/config/ccb-git.sh"
  local git_install_path="$BIN_DIR/ccb-git.sh"
  if [[ -f "$ccb_git_script" ]]; then
    install_owned_executable "$ccb_git_script" "$git_install_path"
    echo "Installed: $git_install_path"
  fi

  # Install tmux UI toggle scripts (enable/disable CCB theming per-session)
  local ccb_tmux_on_script="$asset_root/config/ccb-tmux-on.sh"
  local ccb_tmux_off_script="$asset_root/config/ccb-tmux-off.sh"
  if [[ -f "$ccb_tmux_on_script" ]]; then
    install_owned_executable "$ccb_tmux_on_script" "$BIN_DIR/ccb-tmux-on.sh"
    echo "Installed: $BIN_DIR/ccb-tmux-on.sh"
  fi
  if [[ -f "$ccb_tmux_off_script" ]]; then
    install_owned_executable "$ccb_tmux_off_script" "$BIN_DIR/ccb-tmux-off.sh"
    echo "Installed: $BIN_DIR/ccb-tmux-off.sh"
  fi

  # Oh-My-Tmux keeps user customizations in ~/.tmux.conf.local.
  # Appending to ~/.tmux.conf can break its internal _apply_configuration script.
  if [[ -f "$tmux_conf_main" ]] && grep -q 'TMUX_CONF_LOCAL' "$tmux_conf_main" 2>/dev/null; then
    tmux_conf="$tmux_conf_local"
    reload_conf="$tmux_conf_main"
    if [[ ! -f "$tmux_conf_local" ]]; then
      touch "$tmux_conf_local"
    fi
  else
    reload_conf="$tmux_conf"
  fi

  # Check if already configured (new or legacy marker) in either main/local config.
  local already_configured=false
  for conf in "$tmux_conf_main" "$tmux_conf_local"; do
    if [[ -f "$conf" ]] && \
      (grep -q "$CCB_TMUX_MARKER" "$conf" 2>/dev/null || \
       grep -q "$CCB_TMUX_MARKER_LEGACY" "$conf" 2>/dev/null); then
      already_configured=true
      break
    fi
  done

  if $already_configured; then
    # Update existing config: remove old CCB block(s) and re-add at target location.
    echo "Updating CCB tmux configuration..."
    remove_ccb_tmux_block_from_file "$tmux_conf_main" || true
    remove_ccb_tmux_block_from_file "$tmux_conf_local" || true
  else
    # Backup existing config if present
    if [[ -f "$tmux_conf" ]]; then
      cp "$tmux_conf" "$tmux_conf.bak.$(date +%Y%m%d%H%M%S)"
    fi
  fi

  # Append CCB tmux config (fill in BIN_DIR placeholders)
  {
    echo ""
    if pick_any_python_bin; then
      "$PYTHON_BIN" -c "
import sys

path = '$ccb_tmux_conf'
bin_dir = '$BIN_DIR'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()
sys.stdout.write(content.replace('@CCB_BIN_DIR@', bin_dir))
" 2>/dev/null || cat "$ccb_tmux_conf"
    else
      cat "$ccb_tmux_conf"
    fi
  } >> "$tmux_conf"

  echo "Updated tmux configuration: $tmux_conf"
  echo "   - CCB tmux integration (copy mode, mouse, pane management)"
  echo "   - CCB theme is enabled only while CCB is running (auto restore on exit)"
  echo "   - Vi-style pane management with h/j/k/l"
  echo "   - Mouse support and better copy mode"
  echo "   - Run 'tmux source $reload_conf' to apply (or restart tmux)"

  # Best-effort: if a tmux server is already running, reload config automatically.
  # (Avoid spawning a new server when tmux isn't running.)
  if command -v tmux >/dev/null 2>&1; then
    if tmux list-sessions >/dev/null 2>&1; then
      if tmux source-file "$reload_conf" >/dev/null 2>&1; then
        echo "Reloaded tmux configuration in running server."
      else
        echo "WARN: Failed to reload tmux configuration automatically; run: tmux source $reload_conf"
      fi
    fi
  fi
}

uninstall_tmux_config() {
  local tmux_conf_main="$HOME/.tmux.conf"
  local tmux_conf_local="$HOME/.tmux.conf.local"
  local status_script="$BIN_DIR/ccb-status.sh"
  local border_script="$BIN_DIR/ccb-border.sh"
  local tmux_on_script="$BIN_DIR/ccb-tmux-on.sh"
  local tmux_off_script="$BIN_DIR/ccb-tmux-off.sh"

  # Remove ccb-status.sh script
  if [[ -f "$status_script" ]]; then
    rm -f "$status_script"
    echo "Removed: $status_script"
  fi

  # Remove ccb-border.sh script
  if [[ -f "$border_script" ]]; then
    rm -f "$border_script"
    echo "Removed: $border_script"
  fi

  # Remove tmux UI toggle scripts
  if [[ -f "$tmux_on_script" ]]; then
    rm -f "$tmux_on_script"
    echo "Removed: $tmux_on_script"
  fi
  if [[ -f "$tmux_off_script" ]]; then
    rm -f "$tmux_off_script"
    echo "Removed: $tmux_off_script"
  fi

  local removed_any=false
  for conf in "$tmux_conf_main" "$tmux_conf_local"; do
    if [[ -f "$conf" ]] && \
      (grep -q "$CCB_TMUX_MARKER" "$conf" 2>/dev/null || \
       grep -q "$CCB_TMUX_MARKER_LEGACY" "$conf" 2>/dev/null); then
      echo "Removing CCB tmux configuration from $conf..."
      if remove_ccb_tmux_block_from_file "$conf"; then
        echo "Removed CCB tmux configuration from $conf"
        removed_any=true
      fi
    fi
  done

  if ! $removed_any; then
    return
  fi
}

install_requirements() {
  check_wsl_compatibility
  confirm_backend_env_wsl
  require_python_version
  if use_managed_venv; then
    echo "INFO: watchdog will be installed inside the managed Python venv"
  else
    install_watchdog
  fi
  require_terminal_backend
}

# Clean up legacy daemon files from the pre-ccbd era
cleanup_legacy_files() {
  echo "Cleaning up legacy files..."
  local cleaned=0

  # Legacy daemon scripts in bin/
  local legacy_daemons="caskd gaskd oaskd laskd daskd"
  for daemon in $legacy_daemons; do
    if [[ -f "$BIN_DIR/$daemon" ]]; then
      rm -f "$BIN_DIR/$daemon"
      echo "  Removed legacy daemon script: $BIN_DIR/$daemon"
      cleaned=$((cleaned + 1))
    fi
    # Also check install prefix bin
    if [[ -f "$INSTALL_PREFIX/bin/$daemon" ]]; then
      rm -f "$INSTALL_PREFIX/bin/$daemon"
      echo "  Removed legacy daemon script: $INSTALL_PREFIX/bin/$daemon"
      cleaned=$((cleaned + 1))
    fi
  done

  # Legacy daemon state files in ~/.cache/ccb/
  local cache_dir="${XDG_CACHE_HOME:-$HOME/.cache}/ccb"
  local legacy_states="caskd.json gaskd.json oaskd.json laskd.json daskd.json"
  for state in $legacy_states; do
    if [[ -f "$cache_dir/$state" ]]; then
      rm -f "$cache_dir/$state"
      echo "  Removed legacy state file: $cache_dir/$state"
      cleaned=$((cleaned + 1))
    fi
  done

  # Legacy daemon module files in lib/
  local legacy_modules="caskd_daemon.py gaskd_daemon.py oaskd_daemon.py laskd_daemon.py daskd_daemon.py"
  for module in $legacy_modules; do
    if [[ -f "$INSTALL_PREFIX/lib/$module" ]]; then
      rm -f "$INSTALL_PREFIX/lib/$module"
      echo "  Removed legacy module: $INSTALL_PREFIX/lib/$module"
      cleaned=$((cleaned + 1))
    fi
  done

  if [[ $cleaned -eq 0 ]]; then
    echo "  No legacy files found"
  else
    echo "  Cleaned up $cleaned legacy file(s)"
  fi
}

install_all() {
  require_major_upgrade_confirmation
  install_requirements
  remove_codex_mcp
  cleanup_legacy_files
  prepare_install_tree
  install_managed_venv
  if ! install_uses_live_source; then
    write_install_metadata
  fi
  install_bin_links
  ensure_path_configured
  install_claude_commands
  install_claude_skills
  install_codex_skills
  install_droid_skills
  install_droid_delegation
  install_claude_md_config
  install_agents_md_config
  install_clinerules_config
  install_settings_permissions
  install_tmux_config
  echo "OK: Installation complete"
  echo "   Executable dir : $BIN_DIR"
  if install_uses_live_source; then
    echo "   Live source dir: $(resolve_live_source_root)"
    echo "   Managed dir    : $INSTALL_PREFIX"
  else
    echo "   Project dir    : $INSTALL_PREFIX"
  fi
  print_install_identity_summary
  echo "   Claude commands updated"
  local md_mode="${CCB_CLAUDE_MD_MODE:-inline}"
  if [[ "$md_mode" == "route" ]]; then
    echo "   Global CLAUDE.md configured with CCB route pointer (full config in ~/.claude/rules/ccb-config.md)"
  else
    echo "   Global CLAUDE.md configured with CCB collaboration rules (inline)"
  fi
  if install_uses_live_source; then
    echo "   Repo AGENTS.md/.clinerules left untouched (source dev mode)"
  else
    echo "   AGENTS.md configured with review rubrics"
    echo "   .clinerules configured with role assignments"
  fi
  if use_managed_venv; then
    echo "   Managed Python: $(managed_venv_python)"
  fi
  echo "   Global settings.json permissions added"
  print_install_identity_notice
}

uninstall_claude_md_config() {
  local claude_md="$HOME/.claude/CLAUDE.md"

  if [[ ! -f "$claude_md" ]]; then
    return
  fi

  if grep -q "$CCB_START_MARKER" "$claude_md" 2>/dev/null; then
    echo "Removing CCB config block from CLAUDE.md..."
    if pick_any_python_bin; then
      "$PYTHON_BIN" -c "
import re

with open('$claude_md', 'r', encoding='utf-8') as f:
    content = f.read()
pattern = r'\\n?<!-- CCB_CONFIG_START -->.*?<!-- CCB_CONFIG_END -->\\n?'
content = re.sub(pattern, '\\n', content, flags=re.DOTALL)
content = content.strip() + '\\n'
with open('$claude_md', 'w', encoding='utf-8') as f:
    f.write(content)
"
      echo "Removed CCB config from CLAUDE.md"
    else
      echo "WARN: python required to clean CLAUDE.md, please manually remove CCB_CONFIG block"
    fi
  elif grep -qE "$LEGACY_RULE_MARKER|## Codex Collaboration Rules|## Gemini|## OpenCode" "$claude_md" 2>/dev/null; then
    echo "Removing legacy collaboration rules from CLAUDE.md..."
    if pick_any_python_bin; then
      "$PYTHON_BIN" -c "
import re

with open('$claude_md', 'r', encoding='utf-8') as f:
    content = f.read()
patterns = [
    r'## Codex Collaboration Rules.*?(?=\\n## (?!Gemini)|\\Z)',
    r'## Codex 协作规则.*?(?=\\n## |\\Z)',
    r'## Gemini Collaboration Rules.*?(?=\\n## |\\Z)',
    r'## Gemini 协作规则.*?(?=\\n## |\\Z)',
    r'## OpenCode Collaboration Rules.*?(?=\\n## |\\Z)',
    r'## OpenCode 协作规则.*?(?=\\n## |\\Z)',
]
for p in patterns:
    content = re.sub(p, '', content, flags=re.DOTALL)
content = content.rstrip() + '\\n'
with open('$claude_md', 'w', encoding='utf-8') as f:
    f.write(content)
"
      echo "Removed collaboration rules from CLAUDE.md"
    else
      echo "WARN: python required to clean CLAUDE.md, please manually remove collaboration rules"
    fi
  fi

  # Clean up external config file if it exists (route mode)
  local external_config="$HOME/.claude/rules/ccb-config.md"
  if [[ -f "$external_config" ]]; then
    rm -f "$external_config"
    echo "Removed external CCB config: $external_config"
  fi
}

uninstall_settings_permissions() {
  local settings_file="$HOME/.claude/settings.json"

  if [[ ! -f "$settings_file" ]]; then
    return
  fi

  local perms_to_remove=(
    'Bash(ccb ask *)'
    'Bash(ccb ping *)'
    'Bash(ccb pend *)'
    'Bash(ask *)'
    'Bash(ccb provider ping *)'
    'Bash(ccb provider pend *)'
    'Bash(ping *)'
    'Bash(ccb-ping *)'
    'Bash(pend *)'
    'Bash(bask:*)'
    'Bash(bpend)'
    'Bash(bping)'
    'Bash(cask:*)'
    'Bash(cpend)'
    'Bash(cping)'
    'Bash(dask:*)'
    'Bash(dpend)'
    'Bash(dping)'
    'Bash(gask:*)'
    'Bash(gpend)'
    'Bash(gping)'
    'Bash(hask:*)'
    'Bash(hpend)'
    'Bash(hping)'
    'Bash(lask:*)'
    'Bash(lpend)'
    'Bash(lping)'
    'Bash(oask:*)'
    'Bash(opend)'
    'Bash(oping)'
    'Bash(qask:*)'
    'Bash(qpend)'
    'Bash(qping)'
  )

  if pick_any_python_bin; then
    local has_perms=0
    for perm in "${perms_to_remove[@]}"; do
      if grep -q "$perm" "$settings_file" 2>/dev/null; then
        has_perms=1
        break
      fi
    done

    if [[ $has_perms -eq 1 ]]; then
      echo "Removing permission configuration from settings.json..."
      "$PYTHON_BIN" -c "
import json
import sys

path = '$settings_file'
perms_to_remove = [
    'Bash(ccb ask *)',
    'Bash(ccb ping *)',
    'Bash(ccb pend *)',
    'Bash(ask *)',
    'Bash(ccb provider ping *)',
    'Bash(ccb provider pend *)',
    'Bash(ping *)',
    'Bash(ccb-ping *)',
    'Bash(pend *)',
    'Bash(bask:*)',
    'Bash(bpend)',
    'Bash(bping)',
    'Bash(cask:*)',
    'Bash(cpend)',
    'Bash(cping)',
    'Bash(dask:*)',
    'Bash(dpend)',
    'Bash(dping)',
    'Bash(gask:*)',
    'Bash(gpend)',
    'Bash(gping)',
    'Bash(hask:*)',
    'Bash(hpend)',
    'Bash(hping)',
    'Bash(lask:*)',
    'Bash(lpend)',
    'Bash(lping)',
    'Bash(oask:*)',
    'Bash(opend)',
    'Bash(oping)',
    'Bash(qask:*)',
    'Bash(qpend)',
    'Bash(qping)',
]
try:
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, dict):
        sys.exit(0)
    perms = data.get('permissions')
    if not isinstance(perms, dict):
        sys.exit(0)
    allow = perms.get('allow')
    if not isinstance(allow, list):
        sys.exit(0)
    perms['allow'] = [p for p in allow if p not in perms_to_remove]
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
except Exception:
    sys.exit(0)
"
      echo "Removed permission configuration from settings.json"
    fi
  else
    echo "WARN: python required to clean settings.json, please manually remove related permissions"
  fi
}

uninstall_claude_skills() {
  local skills_dst="$HOME/.claude/skills"
  local ccb_skills="ask ping pend autonew all-plan docs tp tr file-op review continue"

  if [[ ! -d "$skills_dst" ]]; then
    return
  fi

  echo "Removing CCB Claude skills..."
  for skill in $ccb_skills; do
    if [[ -d "$skills_dst/$skill" ]]; then
      rm -rf "$skills_dst/$skill"
      echo "  Removed skill: $skill"
    fi
  done
}

uninstall_codex_skills() {
  local skills_dst="${CODEX_HOME:-$HOME/.codex}/skills"
  local ccb_skills="ask ping pend autonew all-plan file-op"

  if [[ ! -d "$skills_dst" ]]; then
    return
  fi

  echo "Removing CCB Codex skills..."
  for skill in $ccb_skills; do
    if [[ -d "$skills_dst/$skill" ]]; then
      rm -rf "$skills_dst/$skill"
      echo "  Removed skill: $skill"
    fi
  done
}

uninstall_droid_skills() {
  local skills_dst="${FACTORY_HOME:-$HOME/.factory}/skills"
  local ccb_skills="ask ping pend autonew all-plan"

  if [[ ! -d "$skills_dst" ]]; then
    return
  fi

  echo "Removing CCB Droid skills..."
  for skill in $ccb_skills; do
    if [[ -d "$skills_dst/$skill" ]]; then
      rm -rf "$skills_dst/$skill"
      echo "  Removed skill: $skill"
    fi
  done
}

uninstall_droid_delegation() {
  if ! command -v droid >/dev/null 2>&1; then
    return
  fi

  echo "Removing Droid MCP delegation..."
  if droid mcp remove ccb-delegation >/dev/null 2>&1; then
    echo "  Removed ccb-delegation MCP"
  fi
}

uninstall_droid_commands() {
  local cmds_dst="${FACTORY_HOME:-$HOME/.factory}/commands"
  local ccb_cmds="ask.md ping.md pend.md"

  if [[ ! -d "$cmds_dst" ]]; then
    return
  fi

  echo "Removing CCB Droid commands..."
  for cmd in $ccb_cmds; do
    if [[ -f "$cmds_dst/$cmd" ]]; then
      rm -f "$cmds_dst/$cmd"
      echo "  Removed command: $cmd"
    fi
  done
}

uninstall_all() {
  echo "INFO: Starting ccb uninstall..."

  # 1. Remove project directory
  if [[ -d "$INSTALL_PREFIX" ]]; then
    rm -rf "$INSTALL_PREFIX"
    echo "Removed project directory: $INSTALL_PREFIX"
  fi

  # 2. Remove bin links
  for path in "${SCRIPTS_TO_LINK[@]}"; do
    local name
    name="$(basename "$path")"
    if [[ -L "$BIN_DIR/$name" || -f "$BIN_DIR/$name" ]]; then
      rm -f "$BIN_DIR/$name"
    fi
  done
  for legacy in "${LEGACY_SCRIPTS[@]}"; do
    rm -f "$BIN_DIR/$legacy"
  done
  echo "Removed bin links: $BIN_DIR"

  # 3. Remove Claude command files (clean all possible locations)
  local cmd_dirs=(
    "$HOME/.claude/commands"
    "$HOME/.config/claude/commands"
    "$HOME/.local/share/claude/commands"
  )
  for dir in "${cmd_dirs[@]}"; do
    if [[ -d "$dir" ]]; then
      for doc in "${CLAUDE_MARKDOWN[@]+"${CLAUDE_MARKDOWN[@]}"}"; do
        rm -f "$dir/$doc"
      done
      echo "Cleaned commands directory: $dir"
    fi
  done

  # 4. Remove collaboration rules from CLAUDE.md
  uninstall_claude_md_config

  # 5. Remove permission configuration from settings.json
  uninstall_settings_permissions

  # 6. Remove tmux configuration
  uninstall_tmux_config

  # 7. Remove Claude skills
  uninstall_claude_skills

  # 8. Remove Codex skills
  uninstall_codex_skills

  # 9. Remove Droid skills
  uninstall_droid_skills

  # 10. Remove Droid MCP delegation
  uninstall_droid_delegation

  # 11. Remove Droid commands
  uninstall_droid_commands

  echo "OK: Uninstall complete"
  echo "   NOTE: Dependencies (python, tmux) were not removed"
}

main() {
  if [[ $# -ne 1 ]]; then
    usage
    exit 1
  fi

  require_non_root_execution

  case "$1" in
    install)
      install_all
      ;;
    uninstall)
      uninstall_all
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi

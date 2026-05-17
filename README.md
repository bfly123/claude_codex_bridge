<div align="center">

# CCB - Agent CLI Hub and Teams

<p>
  <img src="https://img.shields.io/badge/Every_Interaction_Visible-096DD9?style=for-the-badge" alt="Every Interaction Visible">
  <img src="https://img.shields.io/badge/Every_Model_Controllable-CF1322?style=for-the-badge" alt="Every Model Controllable">
</p>

[![Version](https://img.shields.io/badge/version-6.2.1-orange.svg)]()
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey.svg)]()

**English** | [Chinese](README_zh.md)

[Why CCB](#why-ccb) · [What's New](#whats-new) · [Start and Stop](#start-and-stop) · [Configuration](#config-control) · [How to Use](#how-to-use) · [How to Install](#how-to-install) · [Release Notes](#release-notes)

</div>

---

## Why CCB

<details>
<summary><b>1. One command for all required CLI operations and management</b></summary>

Start, attach, recover, supervise, and operate Claude, Codex, Gemini, OpenCode, and Droid from one terminal workspace.

- one project entry point for all supported CLI agents
- one place to manage startup, restore, attach, and shutdown
- one consistent runtime flow instead of per-tool ad hoc handling

</details>

<details>
<summary><b>2. Agents can sense and communicate with each other</b></summary>

Named agents can discover each other, use `/ask`, broadcast updates, and delegate work without copy/paste.

- direct agent-to-agent delegation with named targets
- broadcast sync for all live agents when the whole team needs the same context
- explicit handoff patterns for builder, reviewer, and QA style workflows

</details>

<details>
<summary><b>3. Project-level professional agent teams</b></summary>

Build project-local teams with roles, pane layout, provider state, worktree isolation, and lifecycle continuity.

- role-based team composition per project
- isolated provider state under the project runtime
- optional worktrees for agents that need separate working sets
- continuity across restart, recovery, and pane supervision

</details>

<div align="center">

![Showcase](assets/show.png)

<details>
<summary><b>Demo animations</b></summary>

<img src="assets/readme_previews/video2.gif" alt="Any-terminal collaboration demo" width="900">

<img src="assets/readme_previews/video1.gif" alt="VS Code integration demo" width="900">

</details>

</div>

## What's New

<details>
<summary><b>Latest release highlights</b></summary>

- **Callback ask chains are supported**: active agents can use `ccb ask --callback <agent>` when a child result is needed before replying to the original caller.
- **Nested ask routing is explicit**: plain nested `ask` from an active CCB task is rejected; use `--callback` for needed results or `--silence` for independent no-result-needed work.
- **Callback routing is durable**: CCB records callback edges, resumes the parent as a continuation task, and repairs crash windows before submitting missed continuations.
- **Release smoke follows the new ask contract**: real-platform smoke coverage now watches jobs with `ccb pend --watch` and uses `--silence` for independent nested stress asks.
- **Ask skills explain the workflow**: Claude, Codex, and Droid ask skills now document callback delegation and stop-after-submit behavior.

See [Release Notes](#release-notes) for the full history.

</details>

## Start and Stop

### Common Commands

```bash
ccb                              # Start default agents from .ccb/ccb.config
ccb -s                           # Safe start: keep configured/manual permission behavior
ccb -n                           # Rebuild .ccb except ccb.config, then start fresh
ccb kill                         # Stop this project's background runtime
ccb kill -f                      # Force cleanup before rebuilding state
```

Tmux copy/paste: drag with the left mouse button to copy, and use `Ctrl+Shift+V` to paste.

## Config Control

`ccb` is controlled by `.ccb/ccb.config`. This file is project-local and user-authored; if it is missing, CCB uses the built-in default without writing a new config file.

`.ccb/ccb_memory.md` is the project-wide shared memory document.

<details>
<summary><b>Layout</b></summary>

Use the first compact line to define the team and pane layout:

```text
cmd; writer:codex, reviewer:claude; qa:gemini(worktree)
```

That layout means:

- `cmd` is the shell pane
- `writer`, `reviewer`, and `qa` are agent names and pane titles
- `codex`, `claude`, and `gemini` are providers
- `;` splits panes left-to-right; `,` stacks panes top-to-bottom
- `qa` runs in an isolated git worktree; agents without `(worktree)` run `inplace`

</details>

<details>
<summary><b>Per-Agent API And Model</b></summary>

Keep the compact layout first, then add TOML tables only for agents that need their own API route, key, or model:

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

Notes:

- `key` and `url` are agent-local shortcuts for `codex`, `claude`, and `gemini`.
- `model` is an agent-local shortcut for `codex`, `claude`, `gemini`, and `opencode`.
- Setting `key` or `url` makes that agent use the explicit API authority instead of inheriting a global provider API credential.
- For advanced provider env, use `agents.<name>.provider_profile.env`; do not mix provider API env keys with `key` / `url` on the same agent.
- Do not commit real API keys in a public repo.

Common compact examples:

```text
writer:codex, reviewer:claude
cmd; writer:codex, reviewer:claude; qa:gemini(worktree)
cmd; fast:codex, deep:codex
```

Same provider, separate API keys:

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
<summary><b>Update</b></summary>

CCB v6 currently supports `ccb update` on Linux, macOS, and WSL. A major upgrade fully replaces the installed runtime. On the first `ccb` inside an older project, CCB preserves `.ccb/ccb.config`, clears the rest of the old `.ccb` state, and rebuilds locally.

If you installed from a git checkout with `./install.sh install`, that install now runs in source dev mode:

- Global `ccb` and `ask` link back to the checkout instead of using a copied snapshot
- CCB-owned skills and helper scripts also follow the live source tree
- Source installs do not participate in startup auto-update prompts
- Stay on the source/dev track with `git pull` or by switching commits, then rerun `./install.sh install`
- Or run `ccb update` to install the latest stable release and repoint global `ccb` links to the managed release install

```bash
ccb update              # Update to the latest stable release
ccb update 6            # Update to the highest v6.x.x version
ccb update 6.0          # Update to the highest v6.0.x version
ccb update 6.0.5        # Update to a specific version
ccb uninstall           # Uninstall ccb and clean configs
ccb reinstall           # Clean then reinstall ccb
```

</details>

## How to Install

1. **Unix-like (Linux, macOS, WSL)**<br>
   Use this path when `ccb` and your agent CLIs run in the same Unix-like shell.

```bash
git clone https://github.com/SeemSeam/claude_codex_bridge.git
cd claude_codex_bridge
./install.sh install
```

2. **Windows**<br>
   Use this path when your agent CLIs run natively on Windows.

```powershell
git clone https://github.com/SeemSeam/claude_codex_bridge.git
cd claude_codex_bridge
powershell -ExecutionPolicy Bypass -File .\install.ps1 install
```

<details>
<summary><b>Platform notes</b></summary>

- macOS and Linux share the same `install.sh` path.
- For WSL, keep both `ccb` and the agent CLIs inside WSL.
- On WSL mounted-drive projects, project authority stays under `.ccb` while runtime state may relocate to a local Linux state root for socket and agent runtime durability.
- Native Windows mux is still being rebuilt around `psmux`.
- The fuller Windows bootstrap helper lives at `scripts/bootstrap-windows-test-env.ps1`.

</details>

Install note: the commands above install from a git checkout today. After that, run `ccb update` to download the latest stable GitHub release asset and complete the managed release upgrade automatically.

## Development Tools

Maintainer-only release and repository tools live under `dev_tools/`. They are versioned in git but excluded from official release artifacts.

## Useful Tools

Optional user-facing tools live under `useful_tools/`. They are versioned in git
and included in release artifacts, but they are not installed by default. Copy
the tools you want into a global provider home or a specific managed agent home;
see `useful_tools/README.md`.

## How to Use

CCB is agent-first. You can use explicit `/ask`, explicit `$ask`, or let one agent decide to call another on its own.

| Mode | Example |
| :--- | :--- |
| Explicit `/ask` | `/ask reviewer review the parser changes in src/parser.ts` |
| Explicit `$ask` | `$ask reviewer review the parser changes in src/parser.ts` |
| Implicit delegation | `Ask reviewer to check the parser edge cases, then summarize the issues back to me.` |

Use explicit routing when you want a specific target. Use natural language when you want the current agent to decide whether to delegate.

### Chained Ask Calls

Normal `ask` is asynchronous: submit the handoff, then stop. When an agent is already handling a CCB task and needs another agent's result before it can finish, it must use callback routing:

```bash
ccb ask --callback reviewer <<'EOF'
Review this failing test and return the minimal blocker.
EOF
```

CCB records the parent/child link, lets the current turn end, and later delivers the child result back to the parent agent as a new continuation task. This supports chains such as `agent2 -> agent4 -> agent1 -> agent3` without polling or blocking the active mailbox head.

Use plain `ask` only outside an active task. Inside an active CCB task, use `--callback` when the child result is required, or `--silence` for independent work whose successful result does not need to return.

Note: for implicit use, add the `ask` skill basics to your system memory first; otherwise Codex/Claude may fall back to their own built-in multi-agent behavior instead of calling CCB `ask`.

---

## Editor Integration

<img src="assets/nvim.png" alt="Neovim integration with multi-AI code review" width="900">

Write in editors like **Neovim** while agents review and iterate in parallel.

---

## Requirements

- **Python 3.10+**
- **Terminal:** `tmux`

## Uninstall

```bash
ccb uninstall
ccb reinstall

# Fallback:
./install.sh uninstall
```

---

## Community

📧 Email: `bfly123@126.com`
💬 WeChat: `seemseam-com`

Thanks to the [Linux.do community](https://linux.do) for testing, feedback, and discussion support.

<div align="center">
<img src="assets/weixin.jpg" alt="WeChat Group" width="300">
</div>

---


## Release Notes

Historical note: older release notes below may mention `askd`, legacy flags, or removed commands. Those references are kept only as changelog history and do not redefine the current CLI surface.

<details open>
<summary><b>v6.2.1</b> - Callback Ask Chain Validation Hotfix</summary>

- Updates real-platform smoke scripts to watch submitted jobs with `ccb pend --watch <job_id>`.
- Aligns fastpath stress with the nested ask contract by using `--silence` for independent active-agent asks.
- Keeps the 6.2 callback ask chain release notes and README chain-call guidance current.

</details>

<details>
<summary><b>v6.2.0</b> - Callback Ask Chain Release</summary>

- Adds `ccb ask --callback <agent>` so active agents can delegate work and receive the child result later as a continuation task.
- Rejects accidental plain nested `ask` from active CCB tasks; `--callback` is for required child results and `--silence` is for independent no-result-needed work.
- Persists callback edges and repairs missed continuation submissions across dispatcher restarts.
- Updates Claude, Codex, and Droid ask skills plus generated project memory with callback-chain guidance.

</details>

<details>
<summary><b>v6.1.21</b> - Kill And Restart Cleanup Hotfix</summary>

- Keeps `ccb kill -f` finalization queued even if the client pane is destroyed before the daemon can write the socket response.
- Preserves full tmux socket paths and lifecycle owner/keeper pid authority during project-scoped kill cleanup.
- Narrows process fallback matching to CCB control-plane commands for the same `--project`, avoiding broad project-root matches.
- Clears stale provider execution files at ccbd startup and when late updates arrive for terminal or missing jobs.

</details>

<details>
<summary><b>v6.1.20</b> - Claude Active Version Cache Release</summary>

- Detects the source home's active Claude Code symlink under `~/.local/bin/claude` and prefers that version for managed Claude startup.
- Copies the active source-home Claude version into the CCB provider cache, then points managed `.local/bin/claude` at the cached active version.
- Preserves previous shared-cache fallback behavior when the source active-version layout is unavailable.
- Updates provider workspace preparation and the Claude binary-cache contract to document the source-home active-version preference.

</details>

<details>
<summary><b>v6.1.19</b> - Managed Ask Skill Projection Release</summary>

- Routes inherited Claude `skills/` and `commands/` through CCB projected assets instead of copy-sync, so system-installed ask skills reach managed Claude agents without duplicating provider homes.
- Adds managed Droid `FACTORY_HOME` support with projected system `~/.factory/skills` and a session-scoped Droid sessions root.
- Updates Droid launch, execution polling, and communicator session readers to follow the managed session root after restart or session rotation.
- Adds concise default ask reply guidance plus `--compact` and `--silence` submission modes, while keeping legacy wait/output flags as ignored compatibility inputs.

</details>

<details>
<summary><b>v6.1.18</b> - Heartbeat Timeout And Useful Tools Release</summary>

- Keeps running-job heartbeat observations internal until three no-progress intervals, then terminalizes once with `heartbeat_timeout` and a small communication-test recommendation.
- Treats provider completion progress semantically, so cursor offsets, polling timestamps, and session snapshot bookkeeping no longer extend completion deadlines.
- Preserves `reliability_*` runtime state through persistence so restored provider jobs do not reset timeout deadlines.
- Adds `useful_tools/useful_tools.zip` to the versioned optional tools shipped in release artifacts.

</details>

<details>
<summary><b>v6.1.17</b> - Completion Binding And Codex Session Hotfix</summary>

- Binds Claude Stop-hook completion artifacts to the structured outer `CCB_REQ_ID`, so forwarded text or tool output cannot redirect completion events to an older job.
- Keeps Codex session identity independent from memory projection freshness, allowing `.ccb/ccb_memory.md` updates to refresh memory without forcing a fresh conversation.
- Includes PR #205 mailbox recovery for stale terminal `task_request` queue heads whose attempts are already terminal.
- Adds regression coverage across transcript parsing, provider finish hooks, Codex resume behavior, and mailbox stale-head cleanup.

</details>

<details>
<summary><b>v6.1.16</b> - Memory Handoff And Claude Route Hotfix</summary>

- Adds CCB-owned submit-only ask coordination rules to generated managed-memory bundles, preventing stale shared memory text from reintroducing polling/waiting behavior.
- Updates new `.ccb/ccb_memory.md` templates with the same fire-and-forget handoff guidance.
- Makes managed Claude startup prefer ccswitch-updated `~/.claude/settings.json` route settings over stale caller-shell `ANTHROPIC_BASE_URL`.
- Documents the Claude route inheritance contract and adds regression coverage for the new priority order.

</details>

<details>
<summary><b>v6.1.15</b> - Kill Shutdown Reliability Hotfix</summary>

- Waits for recorded `ccbd` and keeper pids to exit during remote `ccb kill` instead of trusting lifecycle unmounted alone.
- Finalizes lifecycle to stopped/unmounted before writing the final shutdown report, allowing `ccb cleanup` to run immediately after kill.
- Adds regression coverage for prepared pid snapshots, remote lifecycle finalization, and shutdown intent ordering.

</details>

<details>
<summary><b>v6.1.14</b> - macOS Claude Keychain Boundary Follow-up</summary>

- Documents the managed Claude `Library/Keychains` fallback as agent-local secret auth compatibility state.
- Clarifies that support bundles must not follow the fallback Keychains symlink and storage diagnostics classify it as secret auth state.

</details>

<details>
<summary><b>v6.1.13</b> - macOS Claude Keychain Fallback</summary>

- Links `Library/Keychains` into managed Claude homes on macOS when `com.apple.security.plist` is absent, preserving Claude login lookup on newer setups.
- Removes the fallback link when Claude auth inheritance is disabled.
- Classifies the fallback Keychains symlink as secret auth state in storage diagnostics.

</details>

<details>
<summary><b>v6.1.12</b> - Claude Tmux Permission Release</summary>

- Packages the merged Claude auto-permission pane fix so tmux launches do not block on the bypass permissions confirmation prompt.
- Carries forward the v6.1.11 WSL cleanup smoke alignment and Claude rollback-cache preservation fixes.

</details>

<details>
<summary><b>v6.1.11</b> - WSL Cleanup Smoke Alignment</summary>

- Aligns WSL mounted-drive storage cleanup smoke with the current relocated-runtime shared-cache contract.
- Includes the Claude cleanup rollback preservation fix from v6.1.10.

</details>

<details>
<summary><b>v6.1.10</b> - Claude Cleanup Rollback Hotfix</summary>

- Keeps the active Claude Code version plus one rollback version during `ccb cleanup`.
- Restores the real-platform storage cleanup smoke expectation across macOS and WSL.

</details>

<details>
<summary><b>v6.1.9</b> - Storage Dedup And Shutdown Hardening</summary>

- Reduces `.ccb` growth by routing Codex projected assets through symlink/shared bundle paths and by moving/pruning rebuildable Claude and Gemini cache content.
- Extends `ccb cleanup` to reclaim old Claude shared versions, Gemini shared cache data, rebuildable Claude caches, and stale pane crash logs.
- Hardens `ccb kill` so old `ccbd`/keeper pids are snapshotted, waited on, and terminated without racing a newer backend generation.
- Prevents Claude tmux panes from blocking on the bypass permissions confirmation prompt.

</details>

<details>
<summary><b>v6.1.8</b> - macOS Claude Keychain Preference Hotfix</summary>

- Managed Claude homes on macOS now inherit `Library/Preferences/com.apple.security.plist` so Claude login lookup can resolve the expected default Keychain.
- The preference projection stays tied to auth inheritance and is removed when Claude auth inheritance is disabled.

</details>

<details>
<summary><b>v6.1.7</b> - Codex Memory Freshness Hotfix</summary>

- Codex now refreshes shared project memory instead of resuming stale AGENTS context after `.ccb/ccb_memory.md` changes.
- Claude and Droid ask skills now submit through heredoc and stop immediately after submit.

</details>

<details>
<summary><b>v6.1.6</b> - Startup And Claude Auth Hotfix</summary>

- Fixes a first-start race between ccbd start and heartbeat maintenance.
- `.ccb/ccb_memory.md` is the only shared CCB memory anchor.
- Adds Claude macOS `Claude Code-credentials` Keychain lookup.

</details>

<details>
<summary><b>v6.1.5</b> - Tmux Startup Hotfix</summary>

- Fixes startup races that could show `Cannot split: pane ... does not exist` or `respawn pane failed: can't find pane`.
- Provider panes still use the managed respawn path.

</details>

<details>
<summary><b>v6.1.4</b> - Shared Project Memory V1</summary>

- `.ccb/ccb_memory.md` is the project-wide shared memory document.

</details>

<details>
<summary><b>v6.1.2</b> - Provider Storage Boundary Hardening</summary>

- **Storage Classes Made Explicit**: `ccb doctor storage` now separates authority, session state, secrets, workspaces, user content, projected config, rebuildable cache, and startup authority bundles.
- **Safe Cleanup Added**: `ccb cleanup` refuses to run while `ccbd` or ask jobs are active, prunes only safe rebuildable provider caches, and preserves sessions, auth, and current Claude binaries.
- **Shared Cache Guardrails Added**: future provider shared-cache paths now resolve under the effective runtime-state root with WSL drvfs safety checks and manifest creation.

</details>

<details>
<summary><b>v6.1.1</b> - Ask Skill and Memory Injection Cleanup</summary>

- **Ask Skill Kept as the Only Installed Skill**: Claude, Codex, and Droid/Factory installs now publish only the `ask` skill and remove older CCB helper skills such as `ping`, `pend`, `all-plan`, and `file-op`.
- **Global Memory Injection Removed**: installers no longer append CCB collaboration blocks into global `CLAUDE.md`, installed `AGENTS.md`, or `.clinerules`; existing CCB-marked blocks are cleaned during install.
- **Legacy Skill Sources Removed**: repository skill templates now keep only the provider-specific `ask` skill assets.

</details>

<details>
<summary><b>v6.1.0</b> - CCBD Ask Stability and Observer Convergence</summary>

- **Ask Submit Fastpath Stabilized**: `ccb ask` returns bounded receipts without waiting on provider readiness, mailbox history projection, or long maintenance ticks
- **Lifecycle and Shutdown Races Closed**: stop-all, shutdown, restart, and background supervision now keep stopped runtimes and terminal jobs from being revived by stale work
- **Provider Completion Recovery Hardened**: Codex polling follows rebound session bindings after restart so jobs complete from the current managed session log
- **Mailbox Summary Read Model Landed**: routine `queue`, `inbox`, and `pend` paths prefer maintained summaries and explicitly degrade when summaries are missing or corrupt
- **Observer Surfaces Weakened**: `pend`, `watch`, `queue`, and `inbox` are non-authoritative snapshots; use `ccb trace <id>` when lineage details are needed
- **Real Platform Validation Added**: GitHub Actions now runs macOS and WSL ccbd/ask smoke, communication matrix, short soak, and fastpath stress jobs

</details>

<details>
<summary><b>v6.0.29</b> - WSL Runtime State Relocation</summary>

- **Runtime State Moved Off Mounted Drives**: on WSL projects rooted under `/mnt/<drive>/...`, project authority remains in `.ccb` while `ccbd/` and agent runtime state relocate to a local Linux state root with explicit marker files
- **Diagnostics and Bundle Mapping Updated**: doctor output and support bundles now expose the project anchor, runtime-state root, relocation reason, and logical `.ccb` archive paths for relocated runtime files
- **Provider Lookup and Ask Routing Kept Stable**: relocated runtime directories still resolve back to the project anchor for session discovery and ask sender attribution without changing Linux or macOS default layout behavior
- **Runtime Markers Are Validated**: relocated runtime markers and refs now reject malformed or mismatched payloads, so stale relocation residue cannot silently remap one project to another
- **WSL Smoke Matches the Final Contract**: the release smoke now expects the runtime-root relocation path that the relocated project actually writes, instead of treating the first relocation step as the final socket fallback

</details>

<details>
<summary><b>v6.0.28</b> - WSL Control Plane Socket Hardening</summary>

- **WSL Control Plane Startup Hardened**: keeper and daemon readiness probes now share the configured control-plane RPC timeout instead of using shorter hardcoded budgets that could misread a slow mounted-drive startup as config drift
- **Socket Server Accept Path Decoupled**: ccbd now accepts connections separately from a serialized worker lane, so one slow or incomplete client request no longer blocks new control-plane probes or heartbeats
- **Transient Connect Retry Added**: Unix socket clients retry only short-lived connect races within the existing timeout budget, without retrying already-sent RPC requests or mutating operations
- **README Refreshed**: the public README was reorganized around the current agent CLI hub/team workflow and updated release guidance

</details>

<details>
<summary><b>v6.0.27</b> - macOS Foreground Attach Timeout Hardening</summary>

- **Foreground Attach Timeout Split**: interactive `ccb` startup now uses foreground-attach-specific RPC and target-ready budgets instead of reusing the short daemon probe timeout
- **macOS Attach Race Reduced**: foreground attach now tolerates slower post-start `ccbd` ping and tmux namespace/window visibility on macOS without redefining daemon startup success
- **Clearer Attach Failures**: attach errors now distinguish between an unresponsive control-plane ping and a responsive daemon whose project namespace is not yet attachable

</details>

<details>
<summary><b>v6.0.26</b> - macOS Install And Claude Ask Cleanup</summary>

- **macOS Release Install Fixed**: release installs keep generated CLI wrappers bound to the managed `.venv` Python, avoiding environment drift when optional dependencies such as `watchdog` are installed
- **WSL Install Tests Unblocked**: watchdog install regression tests explicitly confirm WSL non-interactive install mode so CI covers the intended optional-dependency path
- **Claude Ask Prompt Slimmed Down**: managed Claude `ask` no longer injects local ask skill runtime text into the prompt body, keeping agent-to-agent asks limited to the request anchor and the user's original message

</details>

<details>
<summary><b>v6.0.25</b> - Gemini Managed Home Alignment</summary>

- **Gemini Login Inheritance Fixed**: managed Gemini panes now set `GEMINI_CLI_HOME` to the isolated home root so Gemini CLI reads the projected `.gemini/.env`, settings, and login state from the same managed boundary
- **Regression Coverage Added**: launcher tests now lock the aligned `HOME`, `GEMINI_CLI_HOME`, and `GEMINI_ROOT` contract and guard against writing settings under nested `.gemini/.gemini`
- **Community Contact Trimmed**: the standalone Linux.do contact entry was removed while keeping the Linux.do community acknowledgement below the contact block

</details>

<details>
<summary><b>v6.0.24</b> - WSL Official Login Transport</summary>

- **WSL Provider Transport Inherited**: managed provider panes now preserve user-session proxy, CA, browser, and WSL interop environment needed by official-login and Codex Apps/MCP networking paths
- **Managed Isolation Preserved**: transport inheritance is centralized and does not allow caller-global `CODEX_HOME`, `GEMINI_ROOT`, `CLAUDE_PROJECTS_ROOT`, or `CCB_CALLER_*` runtime authority to override agent-scoped managed state
- **Gemini Login Projection Extended**: managed Gemini homes now project allowlisted `.gemini/.env` API credentials, `google_accounts.json`, and `GEMINI_CLI_HOME` while diagnostics continue excluding copied auth artifacts
- **Opencode Session Detection Hardened**: opencode now treats env-session mode as active only when its provider-specific runtime env is present, avoiding stale generic `CCB_SESSION_ID` contamination
- **Community Entry Refreshed**: README now includes the refreshed WeChat group QR image and Linux.do community acknowledgement so users can find the current support channels from the public project page

</details>

<details>
<summary><b>v6.0.23</b> - CI Matrix Stabilization</summary>

- **Release CI Greened**: latest release validation now points at a commit whose full GitHub Actions test workflow passes across Ubuntu, macOS, WSL, and install smoke jobs
- **Provider Blackbox Coverage Focused**: heavy pane-backed provider restart / rotate / settle tests now run in a dedicated Ubuntu provider-blackbox job instead of being repeated across every OS and Python matrix cell
- **macOS Socket Test Race Fixed**: ccbd socket tests now wait for the daemon socket to answer ping requests before issuing RPCs, avoiding macOS runner readiness races

</details>

<details>
<summary><b>v6.0.22</b> - Claude macOS Login Inheritance</summary>

- **macOS Keychain Login Inherited**: managed Claude startup now reads official Claude Code login credentials from macOS Keychain and materializes an equivalent project-scoped `.claude/.credentials.json` inside isolated Claude homes
- **Claude Account Metadata Refreshed**: inherited `.claude.json` account metadata now refreshes from the source home while preserving managed workspace trust and excluding source workspace trust or API key secrets
- **Default Config Startup Fixed**: keeper startup now treats a missing `.ccb/ccb.config` as a request to use the built-in default project config instead of exiting before `ccbd` can mount
- **Regression Coverage Expanded**: tests now lock Keychain projection, metadata refresh, and disabled-auth cleanup paths for managed Claude login inheritance

</details>

<details>
<summary><b>v6.0.21</b> - Claude Hook Asset Projection</summary>

- **CodeIsland Hook Assets Inherited**: managed Claude startup now copies referenced source-home hook assets such as `.codeisland/` when inherited Claude hooks call `$HOME/.codeisland/...`, preventing missing-hook failures inside isolated Claude homes
- **Config Boundary Preserved**: third-party hook assets are copied only when Claude config inheritance is enabled and the inherited hook payload actually references that home-relative asset path
- **Diagnostics Redaction Extended**: diagnostic bundles now exclude copied `.codeisland/` provider-state assets while still including ordinary managed Claude settings for support

</details>

<details>
<summary><b>v6.0.20</b> - Claude Official Login Source Home Fix</summary>

- **Claude Official Login Source Home Fixed**: managed Claude startup now treats `.ccb/agents/*/provider-state/*/home` as an isolated runtime home, not the user's source home, so official browser-login credentials are copied from the real account home
- **Claude Credential Path Coverage**: managed Claude homes now project Claude Code official-login credentials from `.claude/.credentials.json` while retaining compatibility with `.config/claude-code/auth.json`
- **Regression Coverage Added**: tests now lock source-home fallback, launcher projection, diagnostics redaction, and workspace preparation for official Claude login inheritance

</details>

<details>
<summary><b>v6.0.19</b> - Claude Official Login Inheritance</summary>

- **Claude Official Login Projection**: managed Claude homes now project Claude Code official login credentials from `.claude/.credentials.json`, so browser-login-backed auth can be inherited into isolated CCB runtimes instead of only API-token-based settings auth
- **Managed Login Auth Retention**: when global Claude auth artifacts disappear but managed Claude state already holds a valid project-scoped login, startup now preserves that managed login auth across restart instead of silently dropping it
- **Auth Cleanup And Regression Coverage**: disabling auth inheritance now clears stale copied Claude login credentials, and targeted tests now lock the projection, cleanup, and launcher startup paths

</details>

<details>
<summary><b>v6.0.18</b> - Gemini Hook Empty-Reply Guard</summary>

- **Empty Gemini Hook Replies No Longer Burn Jobs**: managed Gemini `AfterAgent` hooks that fire with an empty reply now downgrade to `incomplete` instead of terminalizing as a false exact completion
- **Exact Hook Polling Becomes Safer**: Gemini exact-hook polling now ignores `completed` hook artifacts with no reply text, allowing observed session-stability or timeout reliability paths to converge the request instead of accepting a blank terminal result
- **Regression Coverage Added**: targeted tests now lock the empty-reply guard at both the finish-hook artifact writer and Gemini execution-service polling layers

</details>

<details>
<summary><b>v6.0.17</b> - Gemini Custom Endpoint Env Propagation</summary>

- **Gemini Endpoint Override Restored**: managed Gemini startup now preserves `GOOGLE_GEMINI_BASE_URL` end to end, so custom endpoint and proxy-backed Gemini CLI setups no longer fall back to Google's default production API host
- **Gemini Model Env Allowlisted**: control-plane and provider-profile env filtering now preserve `GEMINI_MODEL`, allowing isolated Gemini agents to keep explicit model selection instead of silently dropping it at startup
- **Config Shortcut Alignment**: Gemini `key` / `url` shortcuts now materialize the same environment variables the current Gemini CLI actually reads, keeping explicit config-based routes aligned with shell-level env behavior

</details>

<details>
<summary><b>v6.0.16</b> - Codex Plugin Projection & Cmd Shell Compatibility</summary>

- **Codex Plugin Projection Fixed**: managed Codex homes now project plugin-bundle authority under `.tmp/plugins/` and `.tmp/plugins.sha`, so isolated agents inherit the marketplace catalog and installed plugin assets they actually need instead of starting with plugin-enabled config but missing bundles
- **Plugin Refresh Semantics Tightened**: startup now refreshes managed plugin projections as one authority unit, removes stale managed plugin residue when the source projection disappears, and keeps a cheap no-recopy fast path when the source plugin freshness marker is unchanged
- **Cmd Shell / Session Env Hardening**: the `cmd` pane now directly `exec`s the resolved user shell and preserves ordinary user-session transport variables such as `DISPLAY`, `WAYLAND_DISPLAY`, `DBUS_SESSION_BUS_ADDRESS`, `XAUTHORITY`, and `SSH_AUTH_SOCK`, improving fish/zsh and GUI-command compatibility

</details>

<details>
<summary><b>v6.0.15</b> - Codex Route Authority & Foreground Attach Polish</summary>

- **Codex Explicit Route Authority**: managed Codex homes now materialize agent-local `config.toml` and `auth.json` as the sole authority for explicit `key` / `url` routes, so agent-scoped API overrides replace inherited global provider routes instead of drifting back to system config
- **Codex Session Namespace Rotation**: managed Codex startup now fingerprints explicit route authority, stamps reusable session bindings with that authority, and rotates stale `sessions/` namespaces before launch when the bound route no longer matches
- **Foreground Attach UX Hardening**: interactive `ccb` startup now seeds tmux namespace creation from the real terminal viewport and issues a best-effort client refresh after attach so first paint matches the current terminal size without manual redraw

</details>

<details>
<summary><b>v6.0.14</b> - Claude Logout Recovery Hardening</summary>

- **Managed Claude Auth Preservation**: managed Claude homes now preserve agent-local login auth when the global Claude home has been logged out, so a project-scoped re-login survives restart instead of re-entering a browser-link loop
- **Auth Projection Semantics Tightened**: Claude startup still refreshes source auth when it exists, but no longer treats missing source auth as an instruction to blank managed auth; disabled auth inheritance still clears stale copied auth state
- **Startup Regression Coverage Expanded**: targeted regressions now lock this behavior at the projection layer, provider workspace preparation, and Claude launcher startup path

</details>

<details>
<summary><b>v6.0.13</b> - macOS Release Path & Preview Packaging Fix</summary>

- **macOS Release Path**: shared release artifact naming and updater resolution now cover the macOS universal bundle alongside Linux/WSL release assets
- **Source Dev Install Mode**: installs from a git checkout now stay linked to the live source tree, skip startup auto-update prompts, and can switch to a managed release install through `ccb update`
- **Agent API / Model Shortcuts**: `.ccb/ccb.config` now accepts flat per-agent `key`, `url`, and `model` shortcuts so common provider overrides stay concise
- **Preview Packaging Hardening**: preview release exports now exclude generated output paths inside the repo, fixing recursive self-copy failures such as `dist-macos-smoke`

</details>

<details>
<summary><b>v6.0.12</b> - Non-Blocking Startup Update Prompt</summary>

- **Cached Startup Prompt**: interactive foreground `ccb` start now reads install-scoped cached release metadata and only prompts when a newer stable release is already known locally
- **Background Refresh**: missing or stale update cache now refreshes in the background with short network budgets instead of delaying the project startup path
- **Upgrade / Defer / Silence**: startup prompt supports upgrade now, defer for the current version, or silence that exact version
- **Startup Boundary Preserved**: release-update checks remain advisory and outside the project lifecycle startup transaction

</details>

<details>
<summary><b>v6.0.11</b> - Project Startup Hotfix</summary>

- **Cold Start Namespace Fix**: project tmux namespace startup now treats `no server running on <project socket>` as an absent namespace that must be created, instead of failing startup as a generic tmux inspect error
- **Release Regression Coverage**: targeted namespace backend/state regression tests now lock this cold-start path so `ccb -> ping -> kill` blackbox lifecycle stays covered
- **Contract Clarification**: the startup supervision contract now explicitly defines project-socket `no server running` as a recreate signal rather than a fatal inspect failure

</details>

<details>
<summary><b>v6.0.10</b> - Startup Budget Hardening & Gemini Login Inheritance</summary>

- **Gemini Login Inheritance**: managed Gemini homes now project login-auth selection and `oauth_creds.json` for `oauth-personal` reuse, and remove stale copied credentials when auth inheritance is disabled
- **Shared Tmux Ready Budget**: project-owned `respawn-pane` now uses the same tmux ready-retry budget as namespace create/reflow, reducing transient `no server running` failures during startup and supervision
- **Background Startup Compatibility**: background lifecycle startup keeps supervision compatibility while separating readiness-probe timeouts from operational RPC budgets
- **Diagnostics Secret Redaction**: diagnostic bundles now exclude Gemini `oauth_creds.json` alongside other provider credential artifacts

</details>

<details>
<summary><b>v6.0.9</b> - Cross-Platform Lifecycle & Watch Stability</summary>

- **WSL Compatibility Fixed**: project runtime now avoids binding Unix sockets onto unsupported WSL mounted-drive filesystems and hardens installer staging plus tmux namespace readiness
- **macOS Lifecycle Hardening**: startup, restore, and project identity paths were tightened so macOS follows the same lifecycle authority model as Linux without intermittent startup drift
- **Respawn Retry Boundary**: transient tmux respawn fork, server-exit, and readiness failures are retried inside runtime supervision instead of leaking outward as false lifecycle failures
- **Watch Reconnect Recovery**: observer recovery can resume from persisted state after short daemon interruptions, while reconnect loops still honor their internal deadlines
- **Cross-Platform CI Coverage**: GitHub Actions now exercises macOS install smoke and WSL compatibility paths alongside the existing Linux matrix

</details>

<details>
<summary><b>v6.0.7</b> - Lifecycle Authority & Shutdown Stability</summary>

- **Keeper-Owned Lifecycle Authority**: keeper now owns lifecycle progression through authoritative `lifecycle.json`, generation fencing, and namespace epoch tracking
- **Mounted-State Read Fixes**: `ping ccbd` and `ping agent` now report current mounted state from live authority instead of stale failure residue after recovery
- **Shutdown Transaction Hardening**: `ccb kill` and `ccb kill -f` now terminate non-terminal jobs during shutdown so restart cannot resurrect old executions via restore or auto-retry
- **Real Blackbox Repro Closed**: the real `ask -> kill -f -> restart` lifecycle repro now converges cleanly to `project_shutdown` without lingering active execution

</details>

<details>
<summary><b>v6.0.6</b> - Agent Isolation Stability & Kill Lifecycle Fix</summary>

- **Agent Isolation Stability**: Codex, Claude, and Gemini managed agents keep their session state under project-scoped `.ccb/agents/<agent>/provider-state/...`
- **Restart Inheritance Safety**: restarts restore only the matching managed agent history instead of adopting manual provider conversations from the same working directory
- **Project Dotfile Protection**: managed startup no longer rewrites project-level `.claude`, `.gemini`, or `.codex` provider dotfiles
- **Kill Lifecycle Fix**: interactive `ccb` no longer reports a false attach failure after `ccb kill` intentionally tears down the current project tmux session

</details>

<details>
<summary><b>v6.0.5</b> - Agent Isolation Stability</summary>

- **Agent Isolation Stability**: Codex, Claude, and Gemini managed agents keep their session state under project-scoped `.ccb/agents/<agent>/provider-state/...`
- **Restart Inheritance Safety**: restarts restore only the matching managed agent history instead of adopting manual provider conversations from the same working directory
- **Project Dotfile Protection**: managed startup no longer rewrites project-level `.claude`, `.gemini`, or `.codex` provider dotfiles

</details>

<details>
<summary><b>v6.0.4</b> - Legacy Update Compatibility Hotfix</summary>

- **Backward-Compatible Release Assets**: Linux release tarballs now include a compatibility alias so older 6.x updaters can still find the extracted installer path
- **Old Clients Can Upgrade Again**: existing `v6.0.1` and `v6.0.2` installs can now update to the latest stable release without needing a patched local updater first
- **Modern Updater Still Clean**: current runtime keeps the correct extracted-directory resolution and does not depend on the legacy alias

</details>

<details>
<summary><b>v6.0.3</b> - Self-Update Tarball Hotfix</summary>

- **Release Upgrade Fixed**: `ccb update` now resolves the extracted release directory correctly instead of treating the `.tar.gz` asset name as a folder
- **Installer Handoff Restored**: self-update now finds `install.sh` inside extracted release assets and completes end to end
- **Release Build Hygiene**: Linux release packaging now ignores local `.ccb-requests/` residue so official builds are reproducible

</details>

<details>
<summary><b>v6.0.2</b> - Caller Attribution, Mailbox Routing, and macOS Install Warning</summary>

- **Correct Caller Identity**: `ccb ask` now preserves the real originating agent so replies return to the right mailbox instead of being attributed as `user`
- **Stable Reply Routing**: async replies for delegated jobs now land back in the expected mailbox chain, including `cmd`-anchored flows
- **Mixed-Case Agent Recovery**: config layout recovery no longer drifts when configured agent names use mixed case
- **macOS Homebrew Warning**: `install.sh` now warns clearly when Homebrew is missing before users try to install tmux and other dependencies

</details>

<details>
<summary><b>v6.0.1</b> - Release Archive Hygiene & Safer Upgrade Extraction</summary>

- **Source Archive Cleanup**: Removed accidentally tracked pytest temp artifacts so GitHub source archives are clean again
- **Safer Tar Validation**: Upgrade extraction now rejects unsafe symlink targets before unpacking
- **Clearer Failure Mode**: Unsafe archive extraction errors now point users toward release assets or clean source archives
- **Regression Coverage**: Added tests to block ephemeral repo artifacts from being tracked again

</details>

<details>
<summary><b>v6.0.0</b> - Native Multi-Agent Runtime, Stable Native Communication, and Linux-Only Auto Upgrade</summary>

**🚀 New Runtime Direction:**
- **Infinite Parallel Agent Foundation**: CCB v6 is built as the runtime base for effectively unbounded agent-to-agent delegation and orchestration
- **Independent Agent Identity**: agents can carry different roles, task ownership, skill libraries, and personalities
- **Focused User Command Surface**: the public user workflow stays centered on `ccb`, `ccb -s`, `ccb -n`, `ccb kill`, and `ccb kill -f`

**🧱 Project Rebuild Semantics:**
- **Config-Preserving Legacy Cleanup**: On first `ccb` inside a pre-6 project, CCB preserves `.ccb/ccb.config`, removes the rest of the old `.ccb` runtime state, and rebuilds locally
- **Runtime Marker**: Modern projects now record `.ccb/project-runtime.json` so current runtime state is distinguished from legacy state
- **Worktree Safety Guard**: Dirty or unmerged CCB-managed worktrees still block destructive rebuilds until the user resolves them

**🔄 Upgrade Policy:**
- **Linux/macOS/WSL**: `ccb update` is available on Linux, macOS, and WSL for the 6.x line
- **Release-Only Upgrades**: Source tags are still published with each version, but `ccb update` for 6.x installs the GitHub release asset, not the source archive
- **Stable Release Targeting**: Default upgrades now resolve to the latest stable release instead of the moving `main` branch
- **Major Upgrade Confirmation**: Upgrading into `6.0.0` requires explicit confirmation before replacing the installed runtime

**🤖 Provider Reliability:**
- **Gemini Multi-Round Stability**: Gemini completion polling now waits through tool activity and no longer exits on the first stable planning sentence

</details>

<details>
<summary><b>v5.3.0</b> - Simplified CLI, Explicit Worktree Mode, and Gemini Completion Stability</summary>

**🚀 User-Facing CLI Simplification:**
- **Narrowed Main Surface**: Public startup flow is now `ccb`, `ccb -s`, `ccb -n`, `ccb kill`, and `ccb kill -f`
- **Model Control Plane Still Available**: `ask`, `ping`, `pend`, and `watch` remain for agent-to-agent orchestration without cluttering primary help

**🧱 Workspace Semantics Made Explicit:**
- **Default Inplace Mode**: Compact `ccb.config` entries now expand to `workspace_mode='inplace'`
- **Opt-In Isolation**: Use `agent:provider(worktree)` when an agent must run in its own git worktree
- **Safe Agent Churn**: Adding agents no longer disturbs existing worktrees; removing or renaming worktree agents retires clean branches and blocks on dirty or unmerged ones

**🛠 Recovery & Reset Hardening:**
- **Config-Preserving Reset**: `ccb -n` rebuilds project runtime state while keeping `.ccb/ccb.config`
- **Stale Registration Cleanup**: Start and reset now prune missing registered git worktrees before rematerialization
- **Kill Warnings**: `ccb kill` warns clearly when a worktree agent still has unmerged or dirty state

**🤖 Gemini Completion Fix:**
- **No Early Stop on Planning Text**: Gemini completion polling now tracks tool-call activity and waits for the real final reply instead of finishing on the first stable “I will ...” message

</details>

<details>
<summary><b>v5.2.6</b> - Async Communication & Gemini 0.29 Compatibility</summary>

**🔧 Gemini CLI 0.29.0 Support:**
- **Dual Hash Strategy**: Session path discovery now supports both basename and SHA-256 formats
- **Autostart**: `ccb-ping` and `ccb-mounted` gain `--autostart` flag to launch offline provider daemons
- **Cleanup Path**: zombie-session cleanup is now handled by `ccb kill -f`

**🔗 Async Communication Fixes:**
- **OpenCode Deadlock**: Fixed session ID pinning that caused second async call to always fail
- **Legacy Completion Compatibility**: Legacy text-based providers still tolerate mismatched `CCB_DONE` lines in degraded mode
- **req_id Regex**: `opencode_comm.py` now matches both old hex and new timestamp-based formats
- **Gemini Idle Timeout**: Auto-detect reply completion when Gemini omits `CCB_DONE` marker (15s idle, configurable via `CCB_GEMINI_IDLE_TIMEOUT`)
- **Gemini Prompt Hardening**: Stronger instructions to reduce `CCB_DONE` omission rate

**🛠 Other Fixes:**
- **lpend**: Prefers fresh Claude session path when registry is stale

</details>

<details>
<summary><b>v5.2.5</b> - Async Guardrail Hardening</summary>

**🔧 Async Turn-Stop Fix:**
- **Global Guardrail**: Added mandatory `Async Guardrail` rule to `claude-md-ccb.md` — covers both `/ask` skill and direct `Bash(ask ...)` calls
- **Marker Consistency**: `bin/ask` now emits `[CCB_ASYNC_SUBMITTED provider=xxx]` matching all other provider scripts
- **DRY Skills**: Ask skill rules reference global guardrail with local fallback, single source of truth

This fix prevents Claude from polling/sleeping after submitting async tasks.

</details>

<details>
<summary><b>v5.2.3</b> - Project-Local History & Legacy Compatibility</summary>

**📂 Project-Local History:**
- **Local Storage**: Auto context exports now save to `./.ccb/history/` per project
- **Safe Scope**: Auto transfer runs only for the current working directory
- **Claude /continue**: New skill to attach the latest history file via `@`

**🧩 Legacy Compatibility:**
- **Auto Migration**: `.ccb_config` is detected and upgraded to `.ccb` when possible
- **Fallback Lookup**: Legacy sessions still resolve cleanly during transition

These changes keep handoff artifacts scoped to the project and make upgrades smoother.

</details>

<details>
<summary><b>v5.2.2</b> - Session Switch Capture & Context Transfer</summary>

**🔁 Session Switch Tracking:**
- **Old Session Fields**: `.claude-session` now records `old_claude_session_id` / `old_claude_session_path` with `old_updated_at`
- **Auto Context Export**: Previous Claude session is automatically extracted to `./.ccb/history/claude-<timestamp>-<old_id>.md`
- **Cleaner Transfers**: Noise filtering removes protocol markers and guardrails while keeping tool-only actions

These updates make session handoff more reliable and easier to audit.

</details>

<details>
<summary><b>v5.2.1</b> - Enhanced Ask Command Stability</summary>

**🔧 Stability Improvements:**
- **Watchdog File Monitoring**: Real-time session updates with efficient file watching
- **Mandatory Caller Field**: Improved request tracking and routing reliability
- **Unified Execution Model**: Simplified ask skill execution across all platforms
- **Auto-Dependency Installation**: Watchdog library installed automatically during setup
- **Session Registry**: Enhanced Claude adapter with automatic session monitoring

These improvements significantly enhance the reliability of cross-AI communication and reduce session binding failures.

</details>

<details>
<summary><b>v5.2.0</b> - Historical mail bridge release</summary>

This release introduced the old mail gateway path. That flow is now removed from the supported agent-first surface and remains legacy code only during cleanup.

</details>

<details>
<summary><b>v5.1.3</b> - Tmux Claude Ask Stability</summary>

**🔧 Fixes & Improvements:**
- **tmux Claude ask**: read replies from pane output with automatic pipe-pane logging for more reliable completion

See [CHANGELOG.md](CHANGELOG.md) for full details.

</details>

<details>
<summary><b>v5.1.2</b> - Daemon & Hooks Reliability</summary>

**🔧 Fixes & Improvements:**
- **Claude Completion Hook**: Unified askd now triggers completion hook for Claude
- **askd Lifecycle**: askd is bound to CCB lifecycle to avoid stale daemons
- **Mounted Detection**: `ccb-mounted` uses ping-based detection across all platforms
- **State File Lookup**: `askd_client` falls back to `CCB_RUN_DIR` for daemon state files

See [CHANGELOG.md](CHANGELOG.md) for full details.

</details>

<details>
<summary><b>v5.1.1</b> - Unified Daemon + Bug Fixes</summary>

**🔧 Bug Fixes & Improvements:**
- **Unified Daemon**: All providers now use unified askd daemon architecture
- **Install/Uninstall**: Fixed installation and uninstallation bugs
- **Process Management**: Fixed kill/termination issues

See [CHANGELOG.md](CHANGELOG.md) for full details.

</details>

<details>
<summary><b>v5.1.0</b> - Unified Command System + Historical Native Windows Experiment</summary>

**🚀 Unified Commands** - Replace provider-specific commands with agent-first workflows:

| Old Commands | New Unified Command |
|--------------|---------------------|
| `cask`, `gask`, `oask`, `dask`, `lask` | `ccb ask <agent> [from <sender>] <message>` |
| `cping`, `gping`, `oping`, `dping`, `lping` | `ccb ping <agent\|all>` |
| `cpend`, `gpend`, `opend`, `dpend`, `lpend` | `ccb pend <agent\|job_id> [N]` |

**Supported providers:** `gemini`, `codex`, `opencode`, `droid`, `claude`

**🪟 Historical native Windows experiment:**
- Earlier releases explored a native Windows split-pane path
- Background execution used PowerShell + `DETACHED_PROCESS`
- Large payload delivery used stdin-based handoff
- That backend has since been removed; future native Windows mux support is being redesigned around `psmux`

**📦 New Skills:**
- `/ask <agent> <message>` - Send work to a named agent
- `/ping <agent|all>` - Check mounted agent health
- `/pend <agent|job_id> [N]` - View latest agent reply

See [CHANGELOG.md](CHANGELOG.md) for full details.

</details>

<details>
<summary><b>v5.0.6</b> - Zombie session cleanup + mounted skill optimization</summary>

- **Zombie Cleanup**: `ccb kill -f` now cleans up orphaned tmux sessions globally (sessions whose parent process has exited)
- **Mounted Skill**: Optimized to use `pgrep` for daemon detection (~4x faster), extracted to standalone `ccb-mounted` script
- **Droid Skills**: Added full skill set (cask/gask/lask/oask + ping/pend variants) to `droid_skills/`
- **Install**: Added `install_droid_skills()` to install Droid skills to `~/.droid/skills/`

</details>

<details>
<summary><b>v5.0.5</b> - Droid delegation tools + setup</summary>

- **Droid**: Adds delegation tools (`ccb_ask_*` plus `cask/gask/lask/oask` aliases).
- **Setup**: New `ccb droid setup-delegation` command for MCP registration.
- **Installer**: Auto-registers Droid delegation when `droid` is detected (opt-out via env).

<details>
<summary><b>Details & usage</b></summary>

Usage:
```
/all-plan <requirement>
```

Example:
```
/all-plan Design a caching layer for the API with Redis
```

Highlights:
- Socratic Ladder + Superpowers Lenses + Anti-pattern analysis.
- Availability-gated dispatch (use only mounted CLIs).
- Two-round reviewer refinement with merged design.

</details>
</details>

<details>
<summary><b>v5.0.0</b> - Any AI as primary driver</summary>

- **Claude Independence**: No need to start Claude first; Codex can act as the primary CLI.
- **Unified Control**: Single entry point controls Claude/OpenCode/Gemini.
- **Simplified Launch**: Dropped `ccb up`; use `ccb ...` or the default `ccb.config`.
- **Flexible Mounting**: More flexible pane mounting and session binding.
- **Default Config**: Uses a built-in default when `.ccb/ccb.config` is missing; CCB no longer creates that file automatically.
- **Project askd Autostart**: project askd and provider runtimes auto-start in the project tmux namespace when needed.
- **Session Robustness**: PID liveness checks prevent stale sessions.

</details>

<details>
<summary><b>v4.0</b> - tmux-first refactor</summary>

- **Full Refactor**: Cleaner structure, better stability, and easier extension.
- **Terminal Runtime Cleanup**: The runtime moved toward a single tmux-oriented pane/control model instead of parallel terminal backends.
- **Perfect tmux Experience**: Stable layouts + pane titles/borders + session-scoped theming.
- **Works in Any Terminal**: If your terminal can run tmux, CCB can provide the full multi-model split experience.

</details>

<details>
<summary><b>v3.0</b> - Smart daemons</summary>

- **True Parallelism**: Submit multiple tasks to Codex, Gemini, or OpenCode simultaneously.
- **Cross-AI Orchestration**: Claude and Codex can now drive OpenCode agents together.
- **Bulletproof Stability**: Daemons auto-start on first request and stop after idle.
- **Chained Execution**: Codex can delegate to OpenCode for multi-step workflows.
- **Smart Interruption**: Gemini tasks handle interruption safely.

<details>
<summary><b>Details</b></summary>

<div align="center">

![Parallel](https://img.shields.io/badge/Strategy-Parallel_Queue-blue?style=flat-square)
![Stability](https://img.shields.io/badge/Daemon-Auto_Managed-green?style=flat-square)
![Interruption](https://img.shields.io/badge/Gemini-Interruption_Aware-orange?style=flat-square)

</div>

<h3 align="center">✨ Key Features</h3>

- **🔄 True Parallelism**: Submit multiple tasks to Codex, Gemini, or OpenCode simultaneously. Provider runtimes queue and execute them serially, ensuring no context pollution.
- **🤝 Cross-AI Orchestration**: Claude and Codex can now simultaneously drive OpenCode agents. All requests are arbitrated by the project askd layer.
- **🛡️ Bulletproof Stability**: The runtime layer is self-managing. It starts on first use and shuts down after idleness to save resources.
- **⚡ Chained Execution**: Advanced workflows supported! Codex can autonomously call `oask` to delegate sub-tasks to OpenCode models.
- **🛑 Smart Interruption**: Gemini tasks now support intelligent interruption detection, automatically handling stops and ensuring workflow continuity.

<h3 align="center">🧩 Feature Support Matrix</h3>

| Feature | Codex | Gemini | OpenCode |
| :--- | :---: | :---: | :---: |
| **Parallel Queue** | ✅ | ✅ | ✅ |
| **Interruption Awareness** | ✅ | ✅ | - |
| **Response Isolation** | ✅ | ✅ | ✅ |

<details>
<summary><strong>📊 View Real-world Stress Test Results</strong></summary>

<br>

**Scenario 1: Claude & Codex Concurrent Access to OpenCode**
*Both agents firing requests simultaneously, perfectly coordinated by the daemon.*

| Source | Task | Result | Status |
| :--- | :--- | :--- | :---: |
| 🤖 Claude | `CLAUDE-A` | **CLAUDE-A** | 🟢 |
| 🤖 Claude | `CLAUDE-B` | **CLAUDE-B** | 🟢 |
| 💻 Codex | `CODEX-A` | **CODEX-A** | 🟢 |
| 💻 Codex | `CODEX-B` | **CODEX-B** | 🟢 |

**Scenario 2: Recursive/Chained Calls**
*Codex autonomously driving OpenCode for a 5-step workflow.*

| Request | Exit Code | Response |
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
<summary><b>Older Version History</b></summary>

### v5.0.6
- **Zombie Cleanup**: `ccb kill -f` cleans up orphaned tmux sessions globally
- **Mounted Skill**: Optimized with `pgrep`, extracted to `ccb-mounted` script
- **Droid Skills**: Full skill set added to `droid_skills/`

### v5.0.5
- **Droid**: Add delegation tools (`ccb_ask_*` and `cask/gask/lask/oask`) plus `ccb droid setup-delegation` for MCP install

### v5.0.4
- **OpenCode**: 修复 `-r` 恢复在多项目切换后失效的问题

### v5.0.3
- **Daemons**: 全新的稳定守护进程设计

### v5.0.1
- **Skills**: New `/all-plan` with Superpowers brainstorming + availability gating; Codex `lping/lpend` added; `gask` keeps brief summaries with `CCB_DONE`.
- **Status Bar**: Role label now reads role name from `.autoflow/roles.json` (supports `_meta.name`) and caches per path.
- **Installer**: Copy skill subdirectories (e.g., `references/`) for Claude/Codex installs.
- **CLI**: Added `ccb uninstall` / `ccb reinstall` with Claude config cleanup.
- **Routing**: Tighter project/session resolution (prefer `.ccb` anchor; avoid cross-project Claude session mismatches).

### v5.0.0
- **Claude Independence**: No need to start Claude first; Codex (or any agent) can be the primary CLI
- **Unified Control**: Single entry point controls Claude/OpenCode/Gemini equally
- **Simplified Launch**: Removed `ccb up`; a built-in default is used when `.ccb/ccb.config` is missing
- **Flexible Mounting**: More flexible pane mounting and session binding
- **Project askd Autostart**: project askd and provider runtimes auto-start in the project tmux namespace when needed
- **Session Robustness**: PID liveness checks prevent stale sessions

### v4.1.3
- **Codex Config**: Automatically migrate deprecated `sandbox_mode = "full-auto"` to `"danger-full-access"` to fix Codex startup
- **Stability**: Fixed race conditions where fast-exiting commands could close panes before `remain-on-exit` was set
- **Tmux**: More robust pane detection (prefer stable `$TMUX_PANE` env var) and better fallback when split targets disappear

### v4.1.2
- **Performance**: Added caching for tmux status bar (git branch & ccb status) to reduce system load
- **Strict Tmux**: Explicitly require `tmux` for auto-launch; removed error-prone auto-attach logic
- **CLI**: Added `--print-version` flag for fast version checks

### v4.1.1
- **CLI Fix**: Improved flag preservation (e.g., `-a`) when relaunching `ccb` in tmux
- **UX**: Better error messages when running in non-interactive sessions
- **Install**: Force update skills to ensure latest versions are applied

### v4.1.0
- **Async Guardrail**: `cask/gask/oask` prints a post-submit guardrail reminder for Claude
- **Sync Mode**: add `--sync` to suppress guardrail prompts for Codex callers
- **Codex Skills**: update `oask/gask` skills to wait silently with `--sync`

### v4.0.9
- **Project_ID Simplification**: `ccb_project_id` uses current-directory `.ccb/` anchor (no ancestor traversal, no git dependency)
- **Codex Skills Stability**: Codex `oask/gask` skills were adjusted to avoid sending the next task too early

### v4.0.8
- **Codex Log Binding Refresh**: the Codex runtime now periodically refreshes `.codex-session` log paths by parsing `start_cmd` and scanning latest logs
- **Tmux Clipboard Enhancement**: Added `xsel` support and `update-environment` for better clipboard integration across GUI/remote sessions

### v4.0.7
- **Tmux Status Bar Redesign**: Dual-line status bar with modern dot indicators (●/○), git branch, and CCB version display
- **Session Freshness**: Always scan logs for latest session instead of using cached session file
- **Simplified Auto Mode (Historical)**: auto-permission behavior was consolidated into the current primary start flow

### v4.0.6
- **Session Overrides**: `cping/gping/oping/cpend/opend` support `--session-file` / `CCB_SESSION_FILE` to bypass wrong `cwd`

### v4.0.5
- **Gemini Reliability**: Retry reading Gemini session JSON to avoid transient partial-write failures
- **Claude Code Reliability**: `gpend` supports `--session-file` / `CCB_SESSION_FILE` to bypass wrong `cwd`

### v4.0.4
- **Fix**: Auto-repair duplicate `[projects.\"...\"]` entries in `~/.codex/config.toml` before starting Codex

### v4.0.3
- **Project Cleanliness**: Store session files under `.ccb/` (fallback to legacy root dotfiles)
- **Claude Code Reliability**: `cask/gask/oask` support `--session-file` / `CCB_SESSION_FILE` to bypass wrong `cwd`
- **Codex Config Safety**: Write auto-approval settings into a CCB-marked block to avoid config conflicts

### v4.0.2
- **Clipboard Paste**: Cross-platform support (xclip/wl-paste/pbpaste) in tmux config
- **Install UX**: Auto-reload tmux config after installation
- **Stability**: Default TMUX_ENTER_DELAY set to 0.5s for better reliability

### v4.0.1
- **Tokyo Night Theme**: Switch tmux status bar and pane borders to Tokyo Night color palette

### v4.0
- **Full Refactor**: Rebuilt from the ground up with a cleaner architecture
- **Perfect tmux Support**: First-class splits, pane labels, borders and statusline
- **Works in Any Terminal**: Recommended to run everything in tmux (except native Windows)

### v3.0.0
- **Smart Runtime Queue**: project askd with 60s idle timeout and provider queue support
- **Cross-AI Collaboration**: Support multiple agents (Claude/Codex) calling one agent (OpenCode) simultaneously
- **Interruption Detection**: Gemini now supports intelligent interruption handling
- **Chained Execution**: Codex can call `oask` to drive OpenCode
- **Stability**: Robust queue management and lock files

### v2.3.9
- Fix oask session tracking bug - follow new session when OpenCode creates one

### v2.3.8
- Plan mode enabled for autoflow projects regardless of `-a` flag

### v2.3.7
- Per-directory lock: different working directories can run cask/gask/oask independently

### v2.3.6
- Add non-blocking lock for cask/gask/oask to prevent concurrent requests
- Unify oask with cask/gask logic (use _wait_for_complete_reply)

### v2.3.5
- Fix plan mode conflict with auto mode (--dangerously-skip-permissions)
- Fix oask returning stale reply when OpenCode still processing

### v2.3.4
- Auto-enable plan mode when autoflow is installed

### v2.3.3
- Simplify cping.md to match oping/gping style (~65% token reduction)

### v2.3.2
- Optimize skill files: extract common patterns to docs/async-ask-pattern.md (~60% token reduction)

### v2.3.1
- Fix race condition in gask/cask: pre-check for existing messages before wait loop

</details>

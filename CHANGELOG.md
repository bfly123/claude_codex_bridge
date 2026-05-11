# Changelog

## Unreleased

## v6.1.6 (2026-05-11)

### Startup And Claude Auth Hotfix

- **Start/Maintenance Race Fixed**: ccbd now prevents heartbeat maintenance from mutating project tmux panes while a start request is laying out and launching agents
- **Project Memory Anchor Tightened**: CCB no longer creates, imports, or depends on project-root `CCB.md`; `.ccb/ccb_memory.md` is the only shared CCB memory anchor
- **Claude macOS Login Inheritance Fixed**: managed Claude startup now checks the current `Claude Code-credentials` Keychain service before older service names

## v6.1.5 (2026-05-11)

### Tmux Startup Hotfix

- **Pane Startup Race Fixed**: project layout panes are now created with a silent placeholder in the initial tmux split, preventing fast-exiting shells from causing `Cannot split: pane ... does not exist` or `respawn pane failed: can't find pane`
- **Provider Launch Semantics Preserved**: agent panes still use the managed respawn path, preserving provider shell, stderr log, and `remain-on-exit` behavior
- **Tmux Regression Coverage Added**: tests now cover real tmux layout creation with an exiting `default-command` plus guardrails that keep provider commands off the structural split path

## v6.1.4 (2026-05-11)

### Project Shared Memory V1

- **Shared Project Memory Landed**: `.ccb/ccb_memory.md` is now the shared project memory anchor injected into managed Claude, Codex, Gemini, and OpenCode agents during startup
- **Per-Agent Memory Layer Added**: `.ccb/agents/<agent>/memory.md` now participates as an agent-private overlay on top of the shared project file
- **Provider Startup Contract Unified**: memory projection now runs through a single writer path with explicit launch context, stable workspace resolution, and fail-fast launch behavior across providers
- **Gemini Managed Memory Smoke Validated**: Gemini CLI 0.41.2 was real-smoke validated against managed `.gemini/GEMINI.md` loading via `GEMINI_CLI_HOME`

## v6.1.2 (2026-05-11)

### Provider Storage Boundary Hardening

- **Storage Audit Expanded**: `ccb doctor storage` now reports explicit storage classes for provider authority, sessions, secrets, workspaces, user content, projected config, rebuildable cache, and startup authority bundles
- **Safe Cleanup Added**: `ccb cleanup` now holds the project lifecycle lock, refuses active `ccbd` or pending ask jobs, prunes old Claude version caches conservatively, and removes only safe Gemini rebuildable caches
- **Diagnostics Bundle Hardened**: support bundles now include storage summaries while excluding provider secrets, Claude binary caches, Gemini rebuildable caches, and Codex startup bundles even when classification fails
- **Provider Runtime Boundaries Tightened**: non-Codex profile runtime-home overrides are rejected, Codex legacy profile homes migrate into managed provider state safely, and duplicate effective provider homes fail validation
- **Shared Cache Foundation Added**: future provider shared-cache roots now resolve through `PathLayout`, reject unsafe WSL drvfs placement without relocation, and create a versioned `MANIFEST.json`

## v6.1.0 (2026-05-09)

### CCBD Ask Stability And Observer Convergence

- **Ask Submit Fastpath Stabilized**: `ccb ask` now returns bounded receipts without waiting on provider readiness, mailbox history projection, or long maintenance ticks; real Linux fastpath stress validated 60 queued asks with p95 submit latency under 250ms
- **Lifecycle And Shutdown Races Closed**: stop-all, shutdown, and background supervision now respect lifecycle stopping state so stopped runtimes and terminal jobs are not revived by stale maintenance or recovery work
- **Provider Completion Recovery Hardened**: Codex polling now follows rebound session bindings after restart, so replies written to a new managed session log can still terminalize the original job
- **Mailbox Summary Read Model Landed**: queue, inbox, pend, and related observer views now prefer maintained mailbox summaries and explicitly degrade on missing/corrupt summaries instead of silently scanning full history on routine paths
- **Observer Surfaces Weakened**: `pend`, `watch`, `queue`, and `inbox` are documented and rendered as non-authoritative snapshots, reducing confusion between weak mailbox observations and `ask wait` / tracker terminal authority
- **Real Platform Validation Added**: new GitHub Actions coverage runs macOS and WSL ccbd/ask smoke tests, communication matrix, short soak, and fastpath stress with stub providers; Linux local validation covered full pytest, comm matrix, soak, and fastpath stress

## v6.0.29 (2026-05-07)

### WSL Runtime State Relocation

- **Runtime State Moved Off Mounted Drives**: on WSL projects rooted under `/mnt/<drive>/...`, project authority remains in `.ccb` while `ccbd/` and agent runtime state relocate to a local Linux state root with explicit marker files
- **Diagnostics and Bundle Mapping Updated**: doctor output and support bundles now expose the project anchor, runtime-state root, relocation reason, and logical `.ccb` archive paths for relocated runtime files
- **Provider Lookup and Ask Routing Kept Stable**: relocated runtime directories still resolve back to the project anchor for session discovery and ask sender attribution without changing Linux or macOS default layout behavior
- **Runtime Markers Are Validated**: relocated runtime markers and refs now reject malformed or mismatched payloads, so stale relocation residue cannot silently remap one project to another
- **WSL Smoke Matches the Final Contract**: the release smoke now expects the runtime-root relocation path that the relocated project actually writes, instead of treating the first relocation step as the final socket fallback

## v6.0.28 (2026-05-07)

### WSL Control Plane Socket Hardening

- **WSL Control Plane Startup Hardened**: keeper and daemon readiness probes now share the configured control-plane RPC timeout instead of using shorter hardcoded budgets that could misread a slow mounted-drive startup as config drift
- **Socket Server Accept Path Decoupled**: ccbd now accepts connections separately from a serialized worker lane, so one slow or incomplete client request no longer blocks new control-plane probes or heartbeats
- **Transient Connect Retry Added**: Unix socket clients retry only short-lived connect races within the existing timeout budget, without retrying already-sent RPC requests or mutating operations
- **README Refreshed**: the public README was reorganized around the current agent CLI hub/team workflow and updated release guidance

## v6.0.27 (2026-05-06)

### macOS Foreground Attach Timeout Hardening

- **Foreground Attach Timeout Split**: interactive `ccb` startup now uses foreground-attach-specific RPC and target-ready budgets instead of reusing the short daemon probe timeout
- **macOS Attach Race Reduced**: foreground attach now tolerates slower post-start `ccbd` ping and tmux namespace/window visibility on macOS without redefining daemon startup success
- **Clearer Attach Failures**: attach errors now distinguish between an unresponsive control-plane ping and a responsive daemon whose project namespace is not yet attachable

## v6.0.26 (2026-05-05)

### macOS Install And Claude Ask Cleanup

- **macOS Release Install Fixed**: release installs now keep generated CLI wrappers bound to the managed `.venv` Python, avoiding environment drift when optional dependencies such as `watchdog` are installed
- **WSL Install Tests Unblocked**: watchdog install regression tests now explicitly confirm WSL non-interactive install mode so CI exercises the intended optional-dependency path
- **Claude Ask Prompt Slimmed Down**: managed Claude `ask` no longer injects local ask skill runtime text into the prompt body, so agent-to-agent asks stay limited to the request anchor and the user's original message

## v6.0.25 (2026-05-02)

### Gemini Managed Home Alignment

- **Gemini Login Inheritance Fixed**: managed Gemini panes now set `GEMINI_CLI_HOME` to the isolated home root so Gemini CLI reads projected `.gemini/.env`, settings, and login state from the intended managed boundary
- **Regression Coverage Added**: launcher tests now lock the aligned `HOME`, `GEMINI_CLI_HOME`, and `GEMINI_ROOT` contract and guard against nested `.gemini/.gemini` settings writes
- **Community Contact Trimmed**: README removed the standalone Linux.do contact entry while keeping the Linux.do community acknowledgement

## v6.0.24 (2026-05-02)

### WSL Official Login Transport

- **WSL Provider Transport Inherited**: managed provider panes now preserve user-session proxy, CA, browser, and WSL interop environment needed by official-login and Codex Apps/MCP networking paths
- **Managed Isolation Preserved**: transport inheritance is centralized and does not allow caller-global `CODEX_HOME`, `GEMINI_ROOT`, `CLAUDE_PROJECTS_ROOT`, or `CCB_CALLER_*` runtime authority to override agent-scoped managed state
- **Gemini Login Projection Extended**: managed Gemini homes now project allowlisted `.gemini/.env` API credentials, `google_accounts.json`, and `GEMINI_CLI_HOME` while diagnostics continue excluding copied auth artifacts
- **Opencode Session Detection Hardened**: opencode now treats env-session mode as active only when its provider-specific runtime env is present, avoiding stale generic `CCB_SESSION_ID` contamination
- **Community Entry Refreshed**: README now includes the refreshed WeChat group QR image and Linux.do community acknowledgement so users can find the current support channels from the public project page

## v6.0.23 (2026-05-01)

### CI Matrix Stabilization

- **Release CI Greened**: latest release validation now points at a commit whose full GitHub Actions test workflow passes across Ubuntu, macOS, WSL, and install smoke jobs
- **Provider Blackbox Coverage Focused**: heavy pane-backed provider restart / rotate / settle tests now run in a dedicated Ubuntu provider-blackbox job instead of being repeated across every OS and Python matrix cell
- **macOS Socket Test Race Fixed**: ccbd socket tests now wait for the daemon socket to answer ping requests before issuing RPCs, avoiding macOS runner readiness races

## v6.0.22 (2026-04-29)

### Claude macOS Login Inheritance

- **macOS Keychain Login Inherited**: managed Claude startup now reads official Claude Code login credentials from macOS Keychain and materializes an equivalent project-scoped `.claude/.credentials.json` inside isolated Claude homes
- **Claude Account Metadata Refreshed**: inherited `.claude.json` account metadata now refreshes from the source home while preserving managed workspace trust and excluding source workspace trust or API key secrets
- **Default Config Startup Fixed**: keeper startup now treats a missing `.ccb/ccb.config` as a request to use the built-in default project config instead of exiting before `ccbd` can mount
- **Regression Coverage Expanded**: tests now lock Keychain projection, metadata refresh, and disabled-auth cleanup paths for managed Claude login inheritance

## v6.0.21 (2026-04-28)

### Claude Hook Asset Projection

- **CodeIsland Hook Assets Inherited**: managed Claude startup now copies referenced source-home hook assets such as `.codeisland/` when inherited Claude hooks call `$HOME/.codeisland/...`, preventing missing-hook failures inside isolated Claude homes
- **Config Boundary Preserved**: third-party hook assets are copied only when Claude config inheritance is enabled and the inherited hook payload actually references that home-relative asset path
- **Diagnostics Redaction Extended**: diagnostic bundles now exclude copied `.codeisland/` provider-state assets while still including ordinary managed Claude settings for support

## v6.0.20 (2026-04-28)

### Claude Official Login Source Home Fix

- **Claude Official Login Source Home Fixed**: managed Claude startup now treats `.ccb/agents/*/provider-state/*/home` as an isolated runtime home, not the user's source home, so official browser-login credentials are copied from the real account home
- **Claude Credential Path Coverage**: managed Claude homes now project Claude Code official-login credentials from `.claude/.credentials.json` while retaining compatibility with `.config/claude-code/auth.json`
- **Regression Coverage Added**: tests now lock source-home fallback, launcher projection, diagnostics redaction, and workspace preparation for official Claude login inheritance

## v6.0.19 (2026-04-28)

### Claude Official Login Inheritance

- **Claude Official Login Projection**: managed Claude homes now project Claude Code official login credentials from `.claude/.credentials.json`, so browser-login-backed auth can be inherited into isolated CCB runtimes instead of only API-token-based settings auth
- **Managed Login Auth Retention**: when global Claude auth artifacts disappear but managed Claude state already holds a valid project-scoped login, startup now preserves that managed login auth across restart instead of silently dropping it
- **Auth Cleanup And Regression Coverage**: disabling auth inheritance now clears stale copied Claude login credentials, and targeted tests now lock the projection, cleanup, and launcher startup paths

## v6.0.18 (2026-04-28)

### Gemini Hook Empty-Reply Guard

- **Empty Gemini Hook Replies No Longer Burn Jobs**: managed Gemini `AfterAgent` hooks that fire with an empty reply now downgrade to `incomplete` instead of terminalizing as a false exact completion
- **Exact Hook Polling Becomes Safer**: Gemini exact-hook polling now ignores `completed` hook artifacts with no reply text, allowing observed session-stability or timeout reliability paths to converge the request instead of accepting a blank terminal result
- **Regression Coverage Added**: targeted tests now lock the empty-reply guard at both the finish-hook artifact writer and Gemini execution-service polling layers

## v6.0.17 (2026-04-28)

### Gemini Custom Endpoint Env Propagation

- **Gemini Endpoint Override Restored**: managed Gemini startup now preserves `GOOGLE_GEMINI_BASE_URL` end to end, so custom endpoint and proxy-backed Gemini CLI setups no longer fall back to Google's default production API host
- **Gemini Model Env Allowlisted**: control-plane and provider-profile env filtering now preserve `GEMINI_MODEL`, allowing isolated Gemini agents to keep explicit model selection instead of silently dropping it at startup
- **Config Shortcut Alignment**: Gemini `key` / `url` shortcuts now materialize the same environment variables the current Gemini CLI actually reads, keeping explicit config-based routes aligned with shell-level env behavior

## v6.0.16 (2026-04-27)

### Codex Plugin Projection & Cmd Shell Compatibility

- **Codex Plugin Projection Fixed**: managed Codex homes now project plugin-bundle authority under `.tmp/plugins/` and `.tmp/plugins.sha`, so isolated agents inherit marketplace and installed plugin assets coherently instead of starting with plugin-enabled config but missing bundles
- **Plugin Refresh Semantics Tightened**: startup now refreshes the managed plugin projection as one authority unit, removes stale managed plugin residue when the source projection disappears, and skips unnecessary recopies when the source `plugins.sha` marker is unchanged
- **Cmd Shell / Session Env Hardening**: the `cmd` pane now directly `exec`s the resolved user shell and preserves ordinary user-session transport variables such as `DISPLAY`, `WAYLAND_DISPLAY`, `DBUS_SESSION_BUS_ADDRESS`, `XAUTHORITY`, and `SSH_AUTH_SOCK`, improving fish/zsh and GUI-command compatibility

## v6.0.15 (2026-04-27)

### Codex Route Authority & Foreground Attach Polish

- **Codex Explicit Route Authority**: managed Codex homes now materialize agent-local `config.toml` and `auth.json` as the sole authority for explicit `key` / `url` routes, so agent-scoped API overrides replace inherited global provider routes instead of drifting back to system config
- **Codex Session Namespace Rotation**: managed Codex startup now fingerprints explicit route authority, stamps reusable session bindings with that authority, and rotates stale `sessions/` namespaces before launch when the bound route no longer matches
- **Foreground Attach UX Hardening**: interactive `ccb` startup now seeds tmux namespace creation from the real terminal viewport and issues a best-effort client refresh after attach so first paint matches the current terminal size without manual redraw

## v6.0.14 (2026-04-26)

### Claude Logout Recovery Hardening

- **Managed Claude Auth Preservation**: managed Claude homes now preserve agent-local login auth when the global Claude home has been logged out, so a project-scoped re-login survives restart instead of re-entering a browser-link loop
- **Auth Projection Semantics Tightened**: Claude startup still refreshes source auth when it exists, but stops treating missing source auth as an instruction to blank managed auth; disabled auth inheritance continues to clear stale copied auth state
- **Startup Regression Coverage Expanded**: targeted tests now lock this behavior at the projection layer, provider workspace preparation, and Claude launcher startup path

## v6.0.13 (2026-04-25)

### macOS Release Path & Preview Packaging Fix

- **macOS Release Path**: shared release artifact naming and updater resolution now cover the macOS universal bundle alongside Linux/WSL release assets
- **Source Dev Install Mode**: installs from a git checkout now stay linked to the live source tree, skip startup auto-update prompts, and can switch to a managed release install through `ccb update`
- **Agent API / Model Shortcuts**: `.ccb/ccb.config` now accepts flat per-agent `key`, `url`, and `model` shortcuts so common provider overrides stay concise
- **Preview Packaging Hardening**: preview release exports now exclude generated output paths inside the repo, fixing recursive self-copy failures such as `dist-macos-smoke`

## v6.0.12 (2026-04-24)

### Non-Blocking Startup Update Prompt

- **Cached Startup Update Prompt**: interactive foreground `ccb` start can now read install-scoped cached release metadata and offer an upgrade prompt only when a newer stable release is already known locally
- **Background Refresh Without Startup Stall**: cache misses or stale cache now schedule a background refresh with short network budgets instead of joining the project startup transaction
- **Prompt Deferral And Silence Controls**: users can upgrade immediately, continue and defer the prompt for the current version, or silence that exact version
- **Startup Contract Boundary Preserved**: startup supervision now explicitly treats release-update checks as advisory logic outside the lifecycle startup transaction

## v6.0.11 (2026-04-24)

### Project Startup Hotfix

- **Cold-Start Namespace Classification Fix**: project tmux namespace liveness now treats `no server running on <project socket>` as an absent namespace that should be created or recreated, instead of surfacing a false `failed to inspect tmux session` startup failure
- **Project Lifecycle Regression Coverage**: added backend/state regression tests for the absent-server cold-start path so real `ccb -> ping -> kill` lifecycle flows remain covered
- **Startup Contract Clarified**: the startup supervision contract now explicitly defines project-socket `no server running` as a namespace-absent signal during create/recreate decisions

## v6.0.10 (2026-04-24)

### Startup Budget Hardening & Gemini Login Inheritance

- **Gemini Login Auth Inheritance**: managed Gemini startup now projects `security.auth.selectedType` and `oauth_creds.json` for login-backed `oauth-personal` reuse, while stale copied credentials are removed whenever auth inheritance is disabled
- **Shared Tmux Ready Budget**: project-owned pane respawn now uses the same tmux object readiness retry budget as namespace create/reflow instead of a separate shorter timeout, reducing transient `no server running` failures during startup and supervision
- **Background Startup Compatibility**: background lifecycle startup preserves supervisor compatibility and keeps readiness-probe budgets separated from operational RPC timeouts
- **Diagnostics Credential Redaction**: support bundles now exclude Gemini `oauth_creds.json` together with other provider credential artifacts

## v6.0.9 (2026-04-23)

### Cross-Platform Lifecycle & Watch Stability

- **WSL Runtime Compatibility**: Unix socket placement and installer staging now avoid unsupported WSL mounted-drive paths, and tmux namespace readiness is retried more cleanly during startup
- **macOS Lifecycle Hardening**: lifecycle restore, startup timing, and project identity handling were tightened so macOS runs converge on the same authority model as Linux instead of flaking during startup or recovery
- **Respawn Resilience**: transient tmux fork, server-exit, and readiness failures are now retried at the runtime boundary instead of surfacing as spurious lifecycle breakage
- **Watch Reconnect Recovery**: `watch` and ask-wait flows can recover terminal results from persisted state after brief daemon loss while still honoring reconnect deadlines instead of hanging indefinitely
- **Cross-Platform Validation Expanded**: GitHub Actions now covers macOS install smoke and WSL compatibility paths together with the existing Linux test matrix

## v6.0.7 (2026-04-22)

### Lifecycle Authority & Shutdown Stability

- **Keeper-Owned Lifecycle Authority**: project lifecycle is now anchored around keeper-owned `lifecycle.json`, clearer generation ownership, and stricter namespace epoch authority
- **Mounted-State Read Path Fixes**: `ping ccbd` and `ping <agent>` now read mounted/runtime state from current authority instead of drifting to stale failure views after restart or recovery
- **Shutdown Transaction Hardening**: `ccb kill` and `ccb kill -f` now terminalize non-terminal jobs inside the same shutdown transaction so in-flight work cannot reappear as restore or auto-retry authority after restart
- **Real Blackbox Validation**: real-project lifecycle repro on `ask -> kill -f -> restart` now converges to `project_shutdown` with no lingering active execution

## v6.0.6 (2026-04-21)

### 🔒 Agent Isolation Stability & Foreground Kill Lifecycle

- **Foreground Kill Lifecycle Fix**: `ccb kill` no longer leaves interactive `ccb` reporting a false foreground-attach failure after the project tmux namespace is intentionally destroyed
- **Codex Session Isolation Contract Landed**: managed Codex startup now keeps agent-scoped session authority bound to the agent-owned managed home instead of ambient project or global provider state
- **Provider Control-Plane Isolation Tightened**: project-scoped control-plane processes now scrub inherited provider runtime markers more strictly so agent runtime identity does not leak into `ccb`, keeper, or `ccbd`
- **Agent Isolation Stability**: restart and recovery paths continue to preserve project-scoped managed provider boundaries for Codex, Claude, and Gemini agents

## v6.0.5 (2026-04-20)

### 🔒 Agent Isolation Stability

- **Agent Isolation Stability**: strengthened managed agent isolation so Codex, Claude, and Gemini agent sessions stay bound to their own project-scoped provider state under `.ccb`
- **Provider Home Boundaries**: Claude and Gemini startup now reject stale persisted provider homes that point outside the current agent's managed state unless an explicit validated provider profile owns that home
- **Restart Inheritance Safety**: fresh managed Gemini starts no longer adopt ambient `GEMINI_ROOT` or global `~/.gemini` history just because the same work directory was used manually
- **Project Dotfile Protection**: managed startup keeps provider hook/trust state inside agent provider-state homes and does not rewrite project-level `.claude`, `.gemini`, or `.codex` provider dotfiles

## v6.0.4 (2026-04-17)

### 🔁 Legacy Update Compatibility

- **Backward-Compatible Release Assets**: Linux release tarballs now include a compatibility alias so older 6.x updaters that treat the asset filename as the extracted directory can still install successfully
- **Pre-6.0.3 Upgrade Path Restored**: existing `v6.0.1` and `v6.0.2` installs can now update to the latest stable release without relying on patched local updater code
- **Self-Update Hotfix Retained**: current runtime still resolves the extracted release directory correctly and no longer depends on the compatibility alias

## v6.0.3 (2026-04-17)

### 🔧 Self-Update Hotfix

- **Release Tarball Upgrade Fix**: `ccb update` now resolves the extracted release directory correctly instead of treating the `.tar.gz` filename as a directory path
- **Installer Handoff Restored**: self-update once again finds `install.sh` inside extracted release assets and completes the replacement flow end to end
- **Release Build Hygiene**: Linux release packaging now ignores local `.ccb-requests/` mailbox residue so official builds are not blocked by runtime leftovers

## v6.0.2 (2026-04-17)

### 🔁 Agent Routing & Install Guardrails

- **Caller Attribution Fix**: `ccb ask` now preserves the originating agent identity so replies route back to the correct mailbox instead of drifting to `user` or `cmd`
- **Mailbox Delivery Stability**: control-plane reply routing now keeps async `cmd` mailbox delivery aligned with the real caller chain
- **Mixed-Case Agent Recovery**: config layout recovery now normalizes mixed-case agent names consistently during restore and startup
- **macOS Dependency Warning**: `install.sh` now warns when Homebrew is missing on macOS before tmux and related dependencies are installed

## v6.0.1 (2026-04-16)

### 🔧 Release Hygiene & Upgrade Safety

- **Tracked Temp Cleanup**: Removed accidentally tracked `.tmp_pytest` artifacts that contaminated GitHub source archives
- **Repo Hygiene Guard**: Added a regression test to block ephemeral test artifacts from entering the git index again
- **Safer Tar Validation**: Upgrade/install extraction now rejects unsafe symlink targets before unpacking
- **Clearer Extraction Errors**: Unsafe archive failures now explain that the archive contains unsafe paths or links and should be replaced with a clean source archive or official release asset

## v6.0.0 (2026-04-16)

### 🚀 Multi-Agent Runtime

- **Infinite Parallel Agent Edition**: CCB v6 establishes the runtime foundation for effectively unbounded multi-agent delegation inside one project
- **Independent Agent Identity**: Each agent can carry its own role, task stream, skill set, and collaboration style
- **Stable Native Communication**: Agent-to-agent orchestration continues through the built-in control plane instead of shell-level glue

### 🧭 Public CLI Surface

- **User Workflow Reduced**: Public startup and rebuild flow is now intentionally centered on `ccb`, `ccb -s`, `ccb -n`, `ccb kill`, and `ccb kill -f`
- **Control Plane Retained**: `ask`, `ping`, `pend`, and `watch` remain available for model-side coordination without dominating user help
- **Safe Rebuild Semantics**: Legacy project runtime state is rebuilt from `.ccb/ccb.config`, while current 6.x projects retain an explicit runtime marker

### 🌳 Workspace & Recovery

- **Default Inplace Workspaces**: Agents now default to `inplace`; isolated branches are opt-in via `agent:provider(worktree)`
- **Worktree Reconciliation**: Added stable handling for added, removed, renamed, dirty, missing, and unmerged worktree agents during start, kill, and `ccb -n`
- **Restore Stability**: Namespace root panes are preserved during cleanup so restart/restore flows no longer self-delete active project panes

### 🤖 Provider & Release Reliability

- **Gemini Multi-Round Completion**: Gemini completion polling now survives planning/tool rounds and waits for the real final reply
- **Linux Release Path**: `ccb update` for the 6.x line is now aligned to Linux/WSL release assets instead of source snapshots
- **Release Metadata Preservation**: Install/update paths preserve embedded version, commit, and date metadata, including git worktree installs

## v5.3.0 (2026-04-14)

### 🚀 CLI & Workspace Model

- **Public CLI Simplified**: User-facing startup flow is now centered on `ccb`, `ccb -s`, `ccb -n`, `ccb kill`, and `ccb kill -f`
- **Explicit Worktree Opt-In**: Compact `ccb.config` entries now default to `workspace_mode='inplace'`; isolated branches require `agent:provider(worktree)`
- **Internal Control Plane Preserved**: `ask`, `ping`, `pend`, and `watch` remain available for model-side orchestration without crowding the main user help

### 🔧 Project State Recovery

- **Reset Rebuilds Cleanly**: `ccb -n` rebuilds project runtime state while preserving `.ccb/ccb.config`
- **Stale Worktree Cleanup**: Startup and reset paths now prune missing registered git worktrees before rematerializing agent workspaces
- **Agent Change Reconciliation**: Adding agents no longer disturbs existing worktrees; removing or renaming worktree agents retires clean branches and blocks on unmerged or dirty ones
- **Kill Warnings**: `ccb kill` now warns clearly when project worktree agents still have unmerged or dirty state that needs user attention

### 🤖 Completion Reliability

- **Gemini Multi-Round Stability**: Gemini completion polling now tracks tool-call activity and no longer treats the first stable planning message as the final answer
- **Detector Reset Safety**: Session rotation clears tool-active state so later turns are evaluated independently

### ✅ Regression Coverage

- Added focused tests for the simplified CLI surface, worktree reconciliation and reset/kill safeguards, and Gemini early-completion regression paths

## v5.2.8 (2026-03-07)

### 📝 Documentation

- **tmux Layout Tip**: Added English and Chinese usage notes explaining that `Ctrl+b` then `Space` cycles tmux layouts and can be pressed repeatedly

## v5.2.7 (2026-03-07)

### 🔧 Stability Fixes

- **Completion Status**: Completion hook now distinguishes `completed`, `cancelled`, `failed`, and `incomplete` instead of reporting every terminal state as completed
- **Cancellation Handling**: Gemini and Claude adapters now consistently honor cancellation and emit a terminal status instead of leaving requests stuck in processing
- **Routing Safety**: Completion routing now keeps parent-project to subdirectory compatibility while preventing nested child sessions from hijacking parent notifications
- **Codex Session Binding**: Bound Codex requests no longer drift to a newer session log in the same worktree
- **askd Startup Guardrails**: `bin/ask` now respects `CCB_ASKD_AUTOSTART=0` and scrubs inherited daemon lifecycle env before spawning askd
- **Claude Session Backfill**: `ccb` startup again backfills `work_dir` and `work_dir_norm` into existing `.claude-session` files
- **Regression Tests**: Added focused tests for completion status handling, caller routing, autostart behavior, cancellation paths, and Codex session binding

## v5.2.5 (2026-02-15)

### 🔧 Bug Fixes

- **Async Guardrail**: Added global mandatory turn-stop rule to `claude-md-ccb.md` to prevent Claude from polling after async `ask` submission
- **Marker Consistency**: `bin/ask` now emits `[CCB_ASYNC_SUBMITTED provider=xxx]` matching all other provider scripts
- **SKILL.md DRY**: Ask skill rules reference global guardrail with local fallback, eliminating duplicate maintenance
- **Command References**: Fixed `/ping` → `/cping` and `ping` → `ccb-ping` in docs

## v5.2.4 (2026-02-11)

### 🔧 Bug Fixes

- **Explicit CCB_CALLER**: `bin/ask` no longer defaults to `"claude"` when `CCB_CALLER` is unset; exits with an error instead
- **SKILL.md template**: Ask skill execution template now explicitly passes `CCB_CALLER=claude`

## v5.2.3 (2026-02-09)

### 🚀 Project-Local History + Legacy Compatibility

- **Local History**: Context exports now save to `./.ccb/history/` per project
- **CWD Scope**: Auto transfer runs only for the current working directory
- **Legacy Migration**: Auto-detect `.ccb_config` and upgrade to `.ccb` when possible
- **Claude /continue**: Attach the latest history file with a single skill

## v5.2.2 (2026-02-04)

### 🚀 Session Switch Capture

- **Old Session Fields**: `.claude-session` now records `old_claude_session_id` / `old_claude_session_path` with `old_updated_at`
- **Auto Context Export**: Previous Claude session is extracted to `./.ccb/history/claude-<timestamp>-<old_id>.md`
- **Transfer Cleanup**: Improved noise filtering while preserving tool-only actions

## v5.1.2 (2026-01-29)

### 🔧 Bug Fixes & Improvements

- **Claude Completion Hook**: Unified askd now triggers completion hook for Claude
- **askd Lifecycle**: askd is bound to CCB lifecycle to avoid stale daemons
- **Mounted Detection**: `ccb-mounted` now uses ping-based detection across all platforms
- **State File Lookup**: `askd_client` falls back to `CCB_RUN_DIR` for daemon state files

## v5.1.1 (2025-01-28)

### 🔧 Bug Fixes & Improvements

- **Unified Daemon**: All providers now use unified askd daemon architecture
- **Install/Uninstall**: Fixed installation and uninstallation bugs
- **Process Management**: Fixed kill/termination issues

### 🔧 ask Foreground Defaults

- `bin/ask`: Foreground mode available via `--foreground`; `--background` forces legacy async
- Managed Codex sessions default to foreground to avoid background cleanup
- Environment overrides: `CCB_ASK_FOREGROUND=1` / `CCB_ASK_BACKGROUND=1`
- Foreground runs sync and suppresses completion hook unless `CCB_COMPLETION_HOOK_ENABLED` is set
- `CCB_CALLER` now defaults to `codex` in Codex sessions when unset

## v5.1.0 (2025-01-26)

### 🚀 Major Changes: Unified Command System

**New unified commands replace provider-specific commands:**

| Old Commands | New Unified Command |
|--------------|---------------------|
| `cask`, `gask`, `oask`, `dask`, `lask` | `ask <provider> <message>` |
| `cping`, `gping`, `oping`, `dping`, `lping` | `ccb-ping <provider>` (skill: `/cping`) |
| `cpend`, `gpend`, `opend`, `dpend`, `lpend` | `pend <provider> [N]` |

**Supported providers:** `gemini`, `codex`, `opencode`, `droid`, `claude`

### 🪟 Windows Backend Direction

- The old native-Windows backend path has been removed from the active codebase
- Current Unix runtime is tmux-only
- Native Windows mux support is being redesigned around `psmux`

### 🔧 Technical Improvements

- `completion_hook.py`: Uses `sys.executable` for cross-platform script execution
- `bin/ask`:
  - Unix: Uses `nohup` for true background execution
  - Windows: Uses PowerShell script + message file to avoid escaping issues
- Added `SKILL.md.powershell` for `cping` and `pend` skills

### 📦 Skills System

New unified skills:
- `/ask <provider> <message>` - Async request to AI provider
- `/cping <provider>` - Test provider connectivity
- `/pend <provider> [N]` - View latest provider reply

### ⚠️ Breaking Changes

- Old provider-specific commands (`cask`, `gask`, etc.) are deprecated
- Old skills (`/cask`, `/gask`, etc.) are removed
- Use new unified commands instead

### 🔄 Migration Guide

```bash
# Old way
cask "What is 1+1?"
gping
cpend

# New way
ask codex "What is 1+1?"
ccb-ping gemini
pend codex
```

---

For older versions, see [CHANGELOG_4.0.md](CHANGELOG_4.0.md)

# CCBD Startup And Supervision Contract

## 1. Purpose

This document defines the non-drifting contract for project-scoped startup, backend ownership, runtime supervision, pane recovery, and kill/shutdown behavior in `ccb_source`.

It is the authoritative design anchor for:

- `ccb` startup behavior
- `ccb` foreground attach behavior
- `ccbd` daemon lifecycle
- project-scoped runtime ownership
- configured-agent mounting
- pane/session/runtime recovery
- `ccb kill` semantics

The repo-local agent memory file [AGENTS.md](/home/bfly/yunwei/ccb_source/AGENTS.md) must always point back to this document rather than duplicating it.

Diagnostics-specific rules live in [docs/ccbd-diagnostics-contract.md](/home/bfly/yunwei/ccb_source/docs/ccbd-diagnostics-contract.md). Startup/shutdown behavior and diagnostics must evolve together.

Startup errors must preserve enough cause detail for the diagnostics contract to be useful. In particular, project tmux namespace preparation failures must not collapse original tmux stderr/stdout into only a generic foreground message such as `failed to prepare tmux server`.

Module/function-level redesign for the project-scoped tmux namespace model lives in [docs/ccbd-project-namespace-lifecycle-plan.md](/home/bfly/yunwei/ccb_source/docs/ccbd-project-namespace-lifecycle-plan.md).

Detailed redesign for pane recovery layering and continuous foreground attach lives in [docs/ccbd-pane-recovery-continuous-attach-plan.md](/home/bfly/yunwei/ccb_source/docs/ccbd-pane-recovery-continuous-attach-plan.md).

Detailed lifecycle-state, keeper-authority, and provider-helper ownership sequencing lives in [docs/ccbd-lifecycle-stability-plan.md](/home/bfly/yunwei/ccb_source/docs/ccbd-lifecycle-stability-plan.md).

User-facing config and tmux layout rules live in [docs/ccb-config-layout-contract.md](/home/bfly/yunwei/ccb_source/docs/ccb-config-layout-contract.md). Startup behavior must honor that layout contract rather than inventing its own pane topology.

Managed Codex conversation isolation rules live in [docs/codex-session-isolation-contract.md](/home/bfly/yunwei/ccb_source/docs/codex-session-isolation-contract.md). Startup behavior must honor that provider-state contract rather than inferring Codex identity from shared `work_dir`.

Managed Claude conversation isolation rules live in [docs/claude-session-isolation-contract.md](/home/bfly/yunwei/ccb_source/docs/claude-session-isolation-contract.md). Startup behavior must honor that provider-state contract rather than inferring Claude identity from shared `work_dir` or global `~/.claude`.

## 2. Problem Statement

The current codebase already contains pieces of the required behavior:

- project-scoped backend ownership via lease/lock
- runtime inspection and pane health checks
- provider-side `ensure_pane()` recovery hooks
- daemon restart-on-next-command behavior
- stop/kill cleanup logic

But those pieces do not currently form a single always-on control-plane contract.

The main failure mode is structural:

- startup authority is split across config, lease, runtime store, provider session files, and tmux facts
- runtime recovery is partially implemented but only executed on some paths
- pane death can mark an agent degraded without triggering a daemon-owned reconciliation loop
- shutdown behavior is split between server-side and CLI fallback logic

This document fixes the contract boundary first, so later implementation does not drift back into scattered patches.

## 3. Scope

In scope:

- one backend per `.ccb` anchor
- daemon startup and takeover rules
- configured-agent desired-state rules
- runtime supervision and recovery rules
- pane death handling
- records under `.ccb/ccbd/`
- `ccb kill` end-to-end semantics
- startup and recovery test matrix

Out of scope:

- provider-specific prompt/protocol details
- completion extraction policy
- mailbox/message semantics except where they depend on runtime liveness

## 4. Terms

- `project anchor`
  - the directory containing `.ccb/`
- `project backend`
  - the unique authoritative `ccbd` process for one project anchor
- `desired agents`
  - the configured agent set defined by `.ccb/ccb.config`
- `authority`
  - the state source allowed to define current project truth
- `evidence`
  - observable facts used for recovery decisions but not allowed to redefine authority
- `residue`
  - stale or extra state from previous runs, renames, or corruption; cleanup input only
- `runtime supervision`
  - the daemon-owned loop that keeps desired agents mounted and healthy
- `keeper`
  - a small watchdog process that restarts `ccbd` after crashes; it is not the project backend

## 5. Hard Contract

### 5.1 Project Scope

- One `.ccb` anchor defines one project control-plane scope.
- The directory that owns `.ccb/` is the only authority root for that project.
- Project lifecycle state must live under that project's `.ccb/` only.
- Startup, supervision, and shutdown must be reasoned per project anchor, never globally.

### 5.2 One Authoritative Backend

- Each project anchor may have at most one authoritative `ccbd` backend.
- each project anchor may also have at most one project-scoped `keeper`; different projects must have independent keepers and independent `ccbd` generations
- keeper is the only authority allowed to advance project lifecycle phase and to spawn a new `ccbd` generation
- CLI commands may express desired lifecycle state and wait for readiness, but must not compete with keeper by directly owning a second backend-start authority
- backend authority is split on purpose:
  - `.ccb/ccbd/lifecycle.json` defines project lifecycle phase and current desired owner generation
  - `.ccb/ccbd/lease.json` defines liveness for the current `ccbd` generation only
  - socket ownership proves readiness for that current generation
- A second `ccbd` may only replace the current one through explicit takeover rules.
- Once takeover has replaced the recorded lease holder, the previous daemon must treat that lease as lost authority:
  - heartbeat refresh must not succeed against a replaced holder
  - backend-local shutdown or unmount must not rewrite a newer holder's lease
  - backend-local socket cleanup must not unlink a newer generation's replacement socket
  - stale control-plane helpers must prefer reading current authority over forcing an unmount write
- Provider-specific background daemons must not become competing project authorities.

### 5.3 Desired Agent Set

- `.ccb/ccb.config` is the only forward authority for the project's desired agent mount set and foreground layout.
- `.ccb/ccb.config` logical names are also the only forward authority for project-namespace pane display names.
- Until a future explicit `enabled` or `desired_state` field exists, all configured agents are desired agents.
- `default_agents` and CLI `requested_agents` do not redefine long-lived backend ownership.
- `requested_agents` may affect foreground behavior or warm-start order only.

### 5.4 Authority Hierarchy

Authority order must be enforced exactly as follows:

1. `.ccb/ccb.config`
2. `.ccb/ccbd/lifecycle.json`
3. `.ccb/ccbd/lease.json`
4. `.ccb/ccbd/start-policy.json`
5. `.ccb/agents/<configured-agent>/runtime.json` for the current daemon generation

Evidence sources:

- provider session files
- tmux pane liveness
- provider-runtime pid files
- runtime-root contents when runtime state is relocated away from the anchor

Residue sources:

- `.ccb/agents/<unknown-agent>/`
- stale session files
- stale runtime files from previous generations
- malformed runtime files

Rules:

- evidence may guide recovery
- residue may guide cleanup
- managed long-lived provider helpers are slot-scoped runtime resources, not independent authority:
  - a helper or bridge process group must belong to one configured agent slot and one runtime generation
  - helper manifests and runtime records may define ownership for cleanup and restart purposes
  - runtime authority and helper ownership must be written from the same agent-authority update path; later outer-layer field patching must not leave helper ownership on an older daemon/runtime generation
  - helper pids, detached parents, or process names alone are evidence only
- configured-agent provider session files are agent-scoped by `.ccb/ccb.config` logical agent name
- provider-base session files such as `.codex-session` or `.claude-session` are legacy or unscoped evidence only:
  - they must not be reinterpreted as a configured agent's identity
  - they may be consulted only when no explicit agent binding is available
- runtime-state relocation markers under either the anchor or the relocated runtime root are evidence only; they must not redefine project authority
- residue such as provider session files or preserved workspaces must not by itself block config bootstrap
- neither evidence nor residue may silently redefine authority
- runtime pid loss is evidence only; for pane-backed runtime it must not preempt pane/session-based recovery checks

Managed Codex session authority rules:

- for a configured Codex agent, the effective managed `CODEX_HOME` belongs to that agent identity, not to the shared `work_dir`
- absent an explicit validated provider-profile runtime home, the default managed Codex home is `.ccb/agents/<agent>/provider-state/codex/home/`
- the effective managed Codex session root is derived from that home as `<codex_home>/sessions`
- startup must set and persist both `CODEX_HOME` and `CODEX_SESSION_ROOT`; `CODEX_SESSION_ROOT` alone is not sufficient managed-provider authority
- startup must also persist Codex provider-route authority for managed explicit
  routes, and a bound Codex session under such a route is reusable only after
  that concrete binding is stamped with matching bound-session authority
- startup must treat the active managed Codex `sessions/` directory as
  reusable authority, not mere residue, because Codex may auto-continue the
  newest conversation found there even without explicit `resume`
- when the managed Codex session namespace authority is missing or incompatible
  with the current route authority, startup must rotate that `sessions/`
  directory out of the active namespace before launch and scrub stale bound
  session fields from project authority
- provider-base workspace files such as `.codex-session` remain unscoped evidence only unless no explicit configured-agent binding exists
- startup and restore must persist and reuse the effective managed `codex_home` and derived `codex_session_root` when available
- restore must not scan or adopt global `~/.codex/sessions` merely because a manual Codex conversation shares the same `work_dir`

Managed Claude session authority rules:

- for a configured Claude agent, the effective managed `HOME` belongs to that agent identity, not to the shared `work_dir`
- absent an explicit validated provider-profile runtime home, the default managed Claude home is `.ccb/agents/<agent>/provider-state/claude/home/`
- the effective managed Claude projects root is derived from that home as `<claude_home>/.claude/projects`
- the effective managed Claude session-env root is derived from that home as `<claude_home>/.claude/session-env`
- startup must set and persist `HOME`, `claude_home`, `claude_projects_root`, and `claude_session_env_root`
- provider-base workspace files such as `.claude-session` remain unscoped evidence only unless no explicit configured-agent binding exists
- startup and restore must persist and reuse the effective managed Claude home and derived roots when available
- restore must not scan or adopt global `~/.claude/projects` merely because a manual Claude conversation shares the same `work_dir`

Managed provider startup mutation rules:

- startup preparation must not create, delete, or rewrite project-level provider dotfiles such as `.claude/settings.json`, `.claude/settings.local.json`, `.gemini/settings.json`, `.codex/*`, or equivalent provider-owned workspace config
- startup may create `.ccb/ccb_memory.md` under the project anchor when it is missing, but must
  treat it as user-editable project memory after creation
- startup must not create, import, or otherwise rely on project-root `CCB.md`
- startup must materialize project memory as an idempotent preparation step
  before launching a managed provider process:
  - source files are `.ccb/ccb_memory.md`, provider-native project memory such as
    `CLAUDE.md` / `AGENTS.md` / `GEMINI.md`, and optional
    `.ccb/agents/<agent>/memory.md`
  - generated seed metadata belongs under
    `<runtime_state_root>/state/memory.seed.json`
  - generated runtime bundles belong under
    `<runtime_state_root>/runtime/memory/<agent>.md`
  - providers that require project-relative memory paths may create generated
    bridge files under `project_root/.ccb/runtime/memory/<agent>.md`
  - unchanged generated content should not be rewritten only to refresh mtime
  - failures to create or refresh project-memory files should degrade with a
    warning unless a provider requires that generated file to start correctly
- `prepare_provider_workspace` is the single writer for generated provider
  memory/config projections during normal pane startup; provider command
  builders should only read the already prepared paths/env and must not refresh
  auth/config/session material as a side effect
- managed provider home projection must receive project root, agent name, and
  workspace path explicitly from the startup context; it must not recover
  project identity by walking up from relocated runtime-state paths
- when `prepare_provider_workspace` asks a launcher to resolve the provider run
  cwd before a pane launch session exists, it must call `resolve_run_cwd` with
  `launch_session_id = None`; providers must not treat that prepare-phase value
  as persisted session authority
- pane-backed provider launchers may declare a `prepare_launch_context` hook
  when command assembly needs project-scoped context:
  - the runtime launcher must call `prepare_runtime`, then
    `prepare_launch_context`, then pass the final `prepared_state` into
    `build_start_cmd`
  - `prepare_launch_context` may add fields such as `project_root`,
    `workspace_path`, and `agent_events_path`; those fields are
    launch-preparation state, not persisted provider session authority
  - providers that require these fields must fail fast when they are absent
    instead of silently inferring project identity from runtime paths
  - `build_session_payload` receives the same final `prepared_state` used by
    command assembly
- provider bootstrap config needed for managed launches must live under `.ccb/agents/<agent>/provider-state/<provider>/` or an explicit validated provider-profile runtime home
- managed OpenCode startup writes `.ccb/agents/<agent>/provider-state/opencode/opencode.json` as a generated `OPENCODE_CONFIG` file; it reads and merges project `opencode.json` without modifying that project file, and it uses project-relative memory instructions through `.ccb/runtime/memory/<agent>.md`
- agent workspaces may still be created or reconciled as workspace mounts, but provider configuration/trust state must remain inside the managed provider boundary rather than the project worktree
- a configured `git-worktree` workspace requires the project root to be a git repository; startup must fail rather than silently copying a non-git project tree
- the project control plane (`ccb`, keeper, `ccbd`) must not inherit provider-runtime session identity or managed-home variables from the caller shell:
  - examples include `CCB_SESSION_ID`, `CCB_SESSION_FILE`, `CCB_CALLER_*`, `CODEX_*`, `CLAUDE_*`, `GEMINI_*`, `OPENCODE_*`, and equivalent provider runtime markers
  - those variables are runtime-local evidence for the currently running managed agent process, not startup authority for a new or existing project backend
  - provider runtime environment must be injected only into the managed provider process being launched, not leaked into project-scoped control-plane subprocesses
- that provider-runtime scrub must still preserve ordinary user-session variables needed for the project command pane to behave like the user's shell:
  - examples include `PATH`, `SHELL`, `DISPLAY`, `WAYLAND_DISPLAY`,
    `DBUS_SESSION_BUS_ADDRESS`, `XAUTHORITY`, and `SSH_AUTH_SOCK`
  - user-session transport variables such as proxy settings, custom CA bundle
    paths, browser/session IPC state, and WSL interop markers must also be
    preserved for control-plane children and explicitly injected into managed
    provider panes
  - examples include `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY`,
    `CODEX_CA_CERTIFICATE`, `SSL_CERT_FILE`, `NODE_EXTRA_CA_CERTS`, `BROWSER`,
    `WSL_INTEROP`, and `WSL_DISTRO_NAME`
  - those variables are user-session transport or shell-usability state, not managed-provider session authority
  - this allowance must not reopen provider runtime authority inheritance;
    managed variables such as `CODEX_HOME`, `CODEX_SESSION_ROOT`,
    `GEMINI_ROOT`, `GEMINI_CLI_HOME`, `CLAUDE_PROJECTS_ROOT`,
    `OPENCODE_*`, `DROID_*`, and `CCB_CALLER_*` remain runtime-local and must
    be injected only by the provider launch path that owns them

Missing-config recovery rules:

- if `.ccb/ccb.config` is missing, startup must use the built-in default project config from code
- bootstrap must not auto-create, reconstruct, or rewrite `.ccb/ccb.config`
- persisted runtime residue, including `.ccb/agents/*/agent.json`, must not be promoted into a reconstructed user config file
- only a user-authored `.ccb/ccb.config` may replace the built-in default project config

Runtime start policy rules:

- `.ccb/ccbd/start-policy.json` records the current project run's recovery startup policy
- `auto_permission` is inherited project runtime policy, not a one-shot pane-local flag
- recovery restore is not inherited from the original CLI invocation; daemon-owned recovery must always use restore semantics
- plain foreground `ccb` without explicit flags is defined as `restore=true` and `auto_permission=true`
- therefore:
  - explicit foreground `ccb` start uses the CLI-provided `restore` flag and `auto_permission` flag
  - daemon-owned recovery mount, pane recovery, namespace reflow, and post-crash remount must always use `restore=true`
  - those same daemon-owned recovery paths must reuse the persisted `auto_permission` policy from `.ccb/ccbd/start-policy.json`
- `ccb kill` / project stop-all must clear `.ccb/ccbd/start-policy.json`
- daemon-owned background maintenance must not proactively create a missing
  runtime from scratch unless persisted `.ccb/ccbd/start-policy.json`
  authority exists for the current project run

### 5.5 Startup Transaction

Startup must be a single project-scoped transaction:

1. inspect anchor state
2. inspect lifecycle state
3. inspect config state
4. inspect backend lease/socket/heartbeat state
5. decide whether the current phase is `unmounted`, `starting`, `mounted`, `stopping`, or `failed`
6. if startup is required, keeper serializes the new generation under `phase=starting`
7. the new backend binds and proves socket readiness before being published as mounted authority
8. ensure project tmux namespace
9. compute desired agents
10. compute recovery/start plan
11. commit startup actions
12. emit startup result and persist startup report

Startup waiter rules:

- lifecycle `phase=mounted` publishes backend control-plane readiness only
- control-plane readiness means:
  - the current authoritative generation bound the project socket
  - the current authoritative generation answers the minimal control-plane readiness probe for that socket
  - the current authoritative generation published the matching current lease authority
- the socket server must keep accepting control-plane connections even when an earlier client connects but does not send a complete request:
  - accepted connections must have a bounded request-read timeout
  - accept and request handling must be decoupled so the kernel listen queue is not consumed by one bad or slow client
  - request handlers and heartbeat/reconcile ticks must still execute serially in one worker lane, preserving current runtime-file write ordering
  - mutating-operation post-request ticks, including the double tick after `submit`, must remain synchronous with the handled request in that worker lane
  - worker-lane heartbeat/reconcile failures must terminate the serving loop and release backend ownership; the server must not remain accept-only with a dead worker lane
- clients may retry transient connect failures such as `ENOENT`, `ECONNREFUSED`, and `EAGAIN` inside the caller's existing RPC timeout budget, but must not retry after a request has been sent
- commands that only need control-plane RPC, including `ccb ask`, `ping`, `pend`, `watch`, `queue`, and similar daemon callers, must stop waiting at control-plane readiness
- those non-foreground callers must not wait for project-namespace attachability or full desired-agent recovery before submitting work
- interactive `ccb` may continue waiting past control-plane readiness for project-namespace/UI readiness and desired-agent recovery
- CLI callers must not own an independent direct-spawn startup path or a separate local "daemon must be ready in N seconds" authority
- instead, CLI callers express desired lifecycle state, observe the keeper-owned `startup_id` / generation transaction, and return as soon as that transaction reaches success or failure
- `startup_transaction_timeout_s` is the maximum budget ceiling for one keeper-owned cold-start transaction:
  - it is not a fixed sleep
  - it is not a generic per-RPC timeout
  - foreground `ccb` startup may use it for the scoped `start` RPC that completes namespace, desired-agent, and startup-report work after control-plane readiness is reached
  - it must return immediately when the relevant transaction reaches success or failure
  - it must not delay ordinary hot-path calls against an already mounted backend
  - stalled startup should also be bounded by a shorter progress-stall policy based on lifecycle startup progress

`ccb` foreground `start_status: ok` is valid only when:

- the project backend is healthy and authoritative
- the project lifecycle phase is `mounted`
- the authoritative mounted generation is the same generation that successfully bound the current project socket
- the project tmux namespace exists at the project-owned socket/session recorded under `.ccb/ccbd/`
- the project tmux namespace has the current session-scoped CCB UI contract applied on that project-owned socket/session
- that project session contains the current namespace window contract:
  - one control window used as the long-lived session anchor
  - one workspace window used as the visible pane layout anchor
- project-generated tmux identifiers must remain tmux-target-safe:
  - project namespace session names must be normalized before use as tmux targets
  - transient workspace reflow operations must address windows by tmux `window_id`, not temporary dotted window names
- config is valid for the current anchor
- desired agents have reached an acceptable mounted state

Acceptable mounted state means one of:

- healthy and attached
- recovering with explicit persisted reason and active reconcile ownership

It must never mean:

- stale binding accepted as success
- missing config silently replaced despite existing project state
- `phase=starting` with only a socket path placeholder but no ready server
- a mounted lease whose socket is not yet ready for live ping
- degraded runtime reported as healthy startup completion

Foreground command split:

- `ccb`
  - ensures backend authority
  - ensures the project tmux namespace
  - ensures desired agents are mounted
  - plain `ccb` is the default interactive start path and implicitly includes `-a -r`
  - release-update advisory checks may read install-scoped cached metadata and schedule background refresh, but they must not join or block the project startup transaction
  - when `ccb` is running in an interactive terminal and will foreground-attach after startup, it should treat that terminal viewport as authoritative startup input and pass the current terminal size into the startup transaction
  - in an interactive terminal, attaches the foreground to the project namespace after the start transaction succeeds
  - foreground attach must tolerate short tmux visibility lag after namespace create/reflow:
    - persisted namespace state may become visible slightly before tmux session/window targets are selectable
    - `ccb` must therefore perform a bounded readiness wait for the authoritative session and workspace window before declaring foreground attach failure
    - this bounded wait must use foreground-attach-specific policy, not the short `rpc_probe_timeout_s` used for daemon compatibility probes
    - the foreground attach RPC budget is allowed to match the stable operational client budget, while daemon config/probe checks must remain fast-fail
    - the foreground attach target-ready budget must remain bounded by the startup transaction budget so namespace/UI lag does not redefine backend startup authority
  - once the tmux client is observed attached, `ccb` should issue a best-effort tmux client refresh so the first attached frame does not depend on a manual user redraw
  - in a non-interactive terminal, reports the start transaction without attaching to tmux
  - startup success and foreground attach success are distinct outcomes; foreground attach failure must not rewrite a successful startup report as failed
  - foreground attach errors must state whether `ccbd` failed to answer the attach ping or whether `ccbd` was responsive but the project namespace was not attachable
- ask-family and other non-foreground daemon commands
  - reuse the same keeper-owned backend startup transaction
  - stop waiting at control-plane readiness
  - must not enter namespace attach waits
  - must not reinterpret a namespace/UI delay as backend startup failure
  - may rely on externally attached actionable runtime authority without first
    forcing daemon-owned provider-session mount authority
- `ccb -n`
  - is an explicit destructive project reset before start
  - must require interactive confirmation
  - must clear and rebuild all project-owned `.ccb` runtime state, logs, sessions, workspaces, and mail/message residue
  - must preserve `.ccb/ccb.config` exactly when it exists
  - if `.ccb/ccb.config` does not exist, startup may bootstrap the default config after reset
  - the same invocation must then continue through the normal `ccb` start transaction rather than using a separate startup implementation
  - that first post-reset startup must force `restore=false` so provider-global history cannot silently reattach old conversations
  - after the fresh post-reset startup completes, later ordinary `ccb` runs return to the default `-a -r` semantics
- removed attach-only commands
  - the foreground attach stage belongs to `ccb`
  - no public command may attach to the namespace without first running the normal `ccb` startup transaction
  - removed command shims may print guidance, but must not enter parser, dispatch, daemon connection, namespace creation, or provider runtime paths

Project namespace compatibility:

- namespace `layout_version` covers visible pane topology and project-socket tmux UI contract, not just split geometry
- project namespace state must also persist the current visible layout signature produced from `.ccb/ccb.config` after foreground pruning
- when stored namespace `layout_version` differs from the current code contract, startup must recreate the project namespace rather than trying to mutate a stale session in place
- when the stored visible layout signature differs from the desired visible layout signature for the current foreground start, startup must recreate the project namespace rather than incrementally splitting an old pane tree
- when startup creates a fresh project namespace session, the root pane must begin as a silent placeholder process rather than an interactive shell
- when startup creates a fresh project namespace session for an interactive foreground `ccb`, the initial tmux session size should come from that foreground terminal-size hint rather than a detached fixed-size default
- for a fresh namespace, the `cmd` pane bootstrap happens only after layout finalization and must replace that silent placeholder in place
- project-namespace bootstrap must treat tmux server warmup and tmux server-policy persistence as separate steps:
  - `prepare_server` warms the server boundary only
  - server-global options that require a live session, such as `destroy-unattached off`, must be applied only after the authoritative project session exists
- project-owned pane mutation commands, including `respawn-pane` used by `cmd` bootstrap and pane-backed runtime launch/relaunch, must use the same shared tmux ready-retry budget as namespace create/reflow rather than a separate shorter timeout
- namespace session liveness on the project-owned tmux socket must treat both `can't find session` and `no server running on <project socket>` as "namespace absent" for create/recreate decisions; startup must not fail that path as a generic tmux inspect error
- startup must not rely on "real shell first, respawn later" behavior for the `cmd` pane, because that leaves stale prompt residue and can surface zsh no-newline `%` markers
- `cmd` bootstrap must directly `exec` the resolved user shell and must not depend on shell-language-specific inline bootstrap snippets that assume the wrapper shell is POSIX-compatible
- `cmd`-anchored projects must treat exact project-namespace pane membership as the reuse gate for pane-backed bindings
- provider-specific live runtime identity proof may further narrow that reuse gate
- for project-namespace reuse, exact membership means:
  - same project-owned tmux socket
  - same authoritative tmux session
  - same logical `slot_key`
  - same current authoritative workspace `window_id`
- for managed Codex agents with a bound `codex_session_id`, exact namespace membership is still not sufficient:
  - startup must also prove that the live pane process is running the bound `resume <codex_session_id>` conversation
  - for explicit managed Codex routes, the persisted bound-session authority
    must also match the current route authority before `resume` is allowed
  - if that proof is unavailable or negative, startup must reject pane reuse and relaunch through the managed start command
- agent-only legacy layouts with `cmd` disabled may reuse instance-scoped provider session evidence when that session file does not explicitly declare a conflicting tmux socket
- that legacy reuse exception is narrow:
  - if the session file explicitly declares a tmux socket and it is not the project socket, startup must reject it
  - if same-socket pane inspection proves the pane belongs to a detached sibling session or foreign project identity, startup must reject it
  - if provider live-identity proof is merely unavailable or `unknown`, startup may still reuse that legacy instance-scoped binding
  - if provider live-identity proof is explicitly `mismatch`, startup must reject it and relaunch
  - inferred default-server socket facts must not override an otherwise valid instance-scoped legacy binding

### 5.6 Runtime Supervision Is A Daemon Responsibility

The project backend must continuously keep desired agents mounted.

When `.ccb/ccb.config` enables `cmd`, the backend must also continuously keep the project-owned `cmd` slot present and healthy inside the authoritative workspace window.

This responsibility belongs to a daemon-owned supervision loop, not to:

- the next CLI command
- the next job start
- an incidental read path like `ps` or `doctor`
- health inspection paths such as `HealthMonitor.check_all()`

The supervision loop must run on backend heartbeat/tick and reconcile every desired agent, regardless of whether there is queued work.

That daemon-owned responsibility is still bounded by runtime authority rules:

- externally attached actionable runtimes are current runtime authority, not an
  implicit request to start a daemon-owned provider-session mount
- daemon authority adoption must not rewrite an `external-attach` runtime into
  `provider-session` only to stamp current daemon generation
- background maintenance may recover or observe an externally attached runtime,
  but missing-runtime proactive mount remains gated by persisted start-policy
  authority

For `cmd`-enabled projects:

- `cmd` is a project-namespace slot, not an entry in `AgentRegistry`
- `cmd` supervision must therefore happen at the namespace layer, not by pretending `cmd` is a provider runtime
- a healthy `cmd` slot means the authoritative workspace root pane still matches:
  - `role=cmd`
  - `slot_key=cmd`
  - `managed_by=ccbd`
  - current authoritative workspace `window_id`

### 5.7 Pane Death Recovery Contract

When a desired agent's pane dies, the daemon must reconcile it in the background using this order:

1. inspect current runtime authority
2. inspect provider session and terminal facts
3. if `ensure_pane()` can recover the pane, rebind runtime authority in place
4. if the original pane target is gone but the current project workspace window is still healthy, local recovery must create the replacement pane inside that current workspace window and immediately rebind it to the same logical `slot_key`
5. otherwise, if the project tmux session is still healthy and namespace-level repair is needed, reflow the workspace window inside that same session and relaunch the configured layout there
6. otherwise, if runtime facts prove session-level corruption and full project-wide reflow is safe, recreate the project namespace and relaunch the configured layout
7. otherwise tear down stale binding authority
8. relaunch runtime through the normal launch path
9. persist recovery result and retry/backoff state

Important rule:

- recovery must happen even if the agent is idle and no new job arrives
- when `cmd` is enabled, pane death or slot drift for `cmd` must also be detected and repaired on heartbeat even if no user command is running in that pane
- `cmd` recovery must first try session-preserving local slot replacement inside the current workspace window before escalating to project reflow
- ordinary `pane-dead` / `pane-missing` recovery must not use project-server destruction as the first-line path
- pane-backed runtime authority must carry `slot_key`, current workspace `window_id`, and `workspace_epoch`; pane id is evidence, not identity
- local replacement must target the authoritative current workspace window for that project session, not whichever tmux target the provider backend would create by default
- if local replacement changes pane id inside a project-owned namespace and project-wide reflow is currently safe, the daemon must immediately continue into session-preserving workspace reflow so the pane returns to canonical layout position
- session-preserving workspace reflow is the first namespace-level escalation for `pane_recovery:*`
- if local replacement cannot restore `cmd`, `cmd` slot recovery must escalate through that same session-preserving `pane_recovery:*` reflow path, with `pane_recovery:cmd` as the canonical reason
- if pane recovery is done by project-namespace reflow, pane position must return to the canonical layout derived from `.ccb/ccb.config`, not whichever slot tmux happens to assign during local recovery
- workspace reflow must preserve the tmux server and tmux session; only the workspace window may be replaced
- transient tmux/server-readiness failures during heartbeat-driven supervision must degrade or retry background maintenance, but must not by themselves crash or unmount the current authoritative `ccbd`
- heartbeat-driven namespace liveness probes must use a short non-blocking readiness budget; if the project tmux server/socket is transiently unavailable, the daemon must defer that maintenance pass instead of spending the full foreground startup timeout inside `has-session` / `list-panes`
- heartbeat-driven mount/reflow attempts that hit transient tmux/server unavailability must preserve current authority, record retry/backoff evidence, and retry later; they must not immediately reinterpret that transient as a stable missing-session signal
- recovery must always use restore semantics even if the original foreground `ccb` invocation did not pass `-r`
- recovery must inherit `auto_permission` from the persisted project start policy rather than falling back to hardcoded defaults

Project-namespace reflow safety rules:

- project-wide full reflow is an escalation path, not the default response to ordinary pane death
- session-preserving workspace reflow is allowed only when the affected runtime belongs to the project-owned tmux socket/session recorded under `.ccb/ccbd/`
- full project reflow is allowed only when the session itself is no longer a trustworthy repair boundary
- only reflow when no other configured agent is currently `BUSY`
- if reflow is not safe, fall back to local provider recovery rather than disrupting unrelated work

Project-socket cleanup rules:

- startup must compute the authoritative active pane set for the current project-owned tmux socket
- same-socket pane/session residue is evidence only; it must not be silently tolerated just because it lives on the project socket
- startup must clean project-owned orphan panes on the project socket during the startup transaction, not wait for a later manual cleanup path
- UNIX-socket cleanup must be identity-safe:
  - a daemon may unlink the project socket path only if the current filesystem entry is still the exact socket inode it bound
  - startup must not blind-unlink an existing project socket path merely because the path exists; it must first prove that the current inode belongs to the same authoritative generation or to a fully invalidated predecessor
  - shutting down an old daemon must never remove a newer daemon's replacement socket path

### 5.8 Daemon Must Not Stay Dead

Strictly satisfying "backend must not die" requires a process outside `ccbd` itself.

Target architecture:

- `ccbd` remains the only authoritative project backend
- a lightweight project-scoped `keeper` process monitors it
- the keeper may restart `ccbd` after crashes
- the keeper is the only authority allowed to initiate a fresh backend generation
- the keeper never owns project runtime authority inside the mounted backend generation
- the keeper must reap exited direct children so crashed `ccbd` pids do not linger as zombie evidence
- forced takeover is allowed only after the lifecycle state and lease inspection together prove that the previous generation has entered a true takeover window:
  - `MISSING`
  - `UNMOUNTED`
  - `STALE`
- `DEGRADED` with a live pid plus fresh heartbeat is observation only, not restart authority, even if the project socket is temporarily unreachable
- therefore temporary UNIX-socket accept stalls during active work must surface as degraded availability, not a keeper-triggered daemon replacement
- config-check or live-ping timeout against a nominally mounted daemon is degraded observation only unless lifecycle state or ownership proof explicitly marks the generation failed
- keeper config-check and graceful-shutdown probes must use the shared short `rpc_probe_timeout_s`; they must not use private shorter literals that make mounted generations look failed during normal startup load
- if takeover does occur, any superseded daemon that wakes up again must fail its next lease refresh and exit rather than continuing to serve against stale authority

If keeper is absent, the system can only provide "restart on next `ccb` command", which is weaker than the target contract.

When `ccb` re-enters a project after an explicit shutdown, startup must first clear prior shutdown intent before keeper/daemon keepalive can resume.

### 5.9 Kill And Shutdown Transaction

`ccb kill` at the project anchor must execute a single shutdown transaction:

1. acquire shutdown intent
2. prevent keeper restart
3. stop new intake
4. terminalize all non-terminal project jobs so no queued/running request survives as restore or retry authority
5. stop running agent executions
6. stop all desired agents
7. destroy the project tmux namespace at the project-owned socket/session
8. terminate surviving provider runtime pids that outlive namespace destruction
9. mark configured-agent runtime authority as stopped
10. unmount backend lease
11. close socket server
12. persist shutdown report

Shutdown must be best-effort toward residue and strict toward authority.

That means:

- malformed or unknown residue must not block kill
- explicit `ccb kill` is a strong management action and must not be blocked merely because the current backend is `DEGRADED` with fresh heartbeat but an unreachable socket
- configured-agent authority must end in a clean stopped/unmounted state
- non-terminal jobs must not survive explicit project stop as active restore or automatic retry authority
- shutdown terminalization must not create fresh provider work while draining existing work; in particular, after-complete hooks such as automatic reply delivery must be suspended once project stop is requested
- once shutdown intent is acquired, the backend must not run any further reconcile/heartbeat tick that could remount desired agents during the same shutdown transaction
- once shutdown intent is acquired, new mutating RPC requests such as `submit`, `start`, `restore`, `retry`, or `attach` must be rejected with a stable lifecycle-level stopping error; clients must not surface raw socket reset errors as the user-visible contract
- local daemon shutdown helpers must not stop at `mark_unmounted()` plus socket close; they must run the same stop-all cleanup transaction first so provider-runtime pid files, namespace state, and configured-agent authority do not survive a backend-local shutdown
- lease writes that transition backend authority to `unmounted` must be holder-safe:
  - daemon-local shutdown paths may only unmount the lease they still own
  - CLI or keeper cleanup paths acting on an inspected lease must not overwrite a newer holder that took over after inspection
- long-lived provider helper groups must also be cleaned as part of the same authoritative shutdown transaction:
  - helper cleanup must be keyed by slot ownership and runtime generation, not by blind global process-name scans
  - helper orphan sweeping is a safety fuse, not the normal meaning of `ccb kill`

## 6. Required Runtime States

At minimum, the supervision model must distinguish these states:

- `unmounted`
- `starting`
- `healthy`
- `recovering`
- `degraded`
- `stopped`
- `failed`

For desired agents, `recovering` and `degraded` are not the same:

- `recovering`
  - daemon currently owns a live reconcile attempt
- `degraded`
  - agent is not healthy and no active recovery has yet succeeded

The current code already records `degraded`, but the target contract requires a distinct supervised recovery state.

## 7. Records Under .ccb

The following records are required.

### 7.1 Backend Authority

Path:

- `.ccb/ccbd/lifecycle.json`
- `.ccb/ccbd/lease.json`
- `.ccb/ccbd/state.json`

Required fields for lifecycle authority:

- `project_id`
- `desired_state`
- `phase`
- `generation`
- `startup_id`
- `keeper_pid`
- `owner_pid`
- `owner_daemon_instance_id`
- `socket_path`
- `config_signature`
- `phase_started_at`
- optional `last_failure_reason`
- optional `shutdown_intent`

Required fields for backend liveness:

- `project_id`
- `ccbd_pid`
- `namespace_epoch`
- `tmux_socket_path`
- `tmux_session_name`
- `socket_path`
- `generation`
- `started_at`
- `last_heartbeat_at`
- `mount_state`
- `config_signature`
- optional `keeper_pid`
- optional `daemon_instance_id`

Write rule:

- `lease.json.socket_path` and lifecycle authority `socket_path` must always record the effective active socket path for the current generation; preferred socket paths are diagnostics only and may live under the project anchor or a relocated runtime root, but they do not redefine authority.

### 7.2 Startup Report

Path:

- `.ccb/ccbd/startup-report.json`

Required purpose:

- capture why startup succeeded, failed, took over, or recovered

Minimum content:

- anchor state
- config state
- daemon inspection
- socket placement decision
  - at minimum preferred/effective socket path, root kind, and fallback reason for both `ccbd` and project tmux socket selection
- desired agents
- actions taken
- final status

### 7.3 Supervision Event Log

Path:

- `.ccb/ccbd/supervision.jsonl`

Required purpose:

- append-only record of pane death detection, relaunch attempts, recovery failures, and success transitions

### 7.4 Agent Runtime Authority

Path:

- `.ccb/agents/<agent>/runtime.json`

Required fields beyond current baseline:

- `daemon_generation`
- `runtime_generation`
- `desired_state`
- `reconcile_state`
- `restart_count`
- `last_reconcile_at`
- `last_failure_reason`
- optional `runtime_owner_pid`
- optional `runtime_owner_pgid`
- optional `tmux_socket_name`
- optional `tmux_socket_path`

Required write semantics:

- `started_at`, `binding_generation`, `runtime_generation`, and `daemon_generation` must advance only when a new runtime authority epoch is created
- a no-op reattach or repeated observation of the same binding within the same daemon generation must not silently bump `binding_generation`
- when daemon generation changes, the resulting runtime authority must remain self-consistent even if the binding facts are otherwise reused
- a supervision mount/recovery attempt must not overwrite a newer runtime authority epoch that was attached or adopted concurrently; once superseded, the older attempt may emit evidence but must not write failed or stale runtime authority back into `runtime.json`
- mount-attempt ownership is represented by `mount_attempt_id` on
  `runtime.json`; daemon-owned mount start, attach, success finalize, and
  failure finalize must all compare against that token before writing authority
- if an external attach supersedes a daemon-owned mount attempt, older attach or
  finalize paths may emit diagnostics evidence but must not retake authority
- runtime authority writes must go through the explicit agent-authority path (`attach` / authority-adopt / authority-mutate equivalents), not through generic outer-layer state patching
- generic runtime state patching may update operational fields such as `state`, `health`, queue/reconcile markers, and last-seen timestamps, but must not mutate epoch/binding ownership fields
- registry persistence must reject non-authority writes that attempt to change authority-owned fields for an existing runtime record

Unknown agent directories under `.ccb/agents/` are residue unless they are present in current config.

### 7.5 Provider Helper Ownership

Path:

- `.ccb/agents/<agent>/helper.json`

Required purpose:

- record long-lived slot-scoped provider helper ownership such as bridge processes
- make helper cleanup generation-safe and slot-safe

Minimum content:

- `agent_name`
- `runtime_generation`
- `helper_kind`
- `leader_pid`
- `pgid`
- `started_at`
- optional `owner_daemon_generation`
- optional `state`

Required write semantics:

- helper ownership must be derived from the final persisted runtime authority for that slot
- `owner_daemon_generation` must match the runtime authority that currently owns that helper group
- helper `started_at` must reflect the current runtime authority epoch, not a superseded slot generation
- helper manifest writes must use canonical persisted `runtime_generation`; they must not silently fall back to `binding_generation`, pane facts, or pid residue

### 7.6 Keeper State

Path:

- `.ccb/ccbd/keeper.json`

Required purpose:

- record the project-scoped keeper process that currently owns daemon keepalive
- make keeper restart attempts and recent failure reason inspectable without treating keeper as backend authority

Minimum content:

- `project_id`
- `keeper_pid`
- `started_at`
- `last_check_at`
- `state`
- `restart_count`
- optional `last_restart_at`
- optional `last_failure_reason`

### 7.7 Shutdown Intent

Path:

- `.ccb/ccbd/shutdown-intent.json`

Required purpose:

- persist explicit shutdown intent so keeper will not restart `ccbd` during or after `ccb kill`

Minimum content:

- `project_id`
- `requested_at`
- `requested_by_pid`
- `reason`

### 7.8 Diagnostics Bundle

Command:

- `ccb doctor --bundle`

Required purpose:

- export a project-scoped support artifact that is sufficient for remote bug triage without interactive shell access

Required content:

- latest startup/shutdown/restore reports
- backend authority files
- backend stdout/stderr logs
- supervision and cleanup event history
- per-agent runtime authority and recent provider/runtime logs
- manifest rows that mark missing or truncated files explicitly

## 8. Implementation Shape

The design should converge toward these domains:

- `startup inspection`
- `startup policy`
- `startup transaction`
- `runtime supervision`
- `shutdown transaction`
- `reporting/read path`

Recommended module split:

- `lib/ccbd/startup/inspection.py`
- `lib/ccbd/startup/policy.py`
- `lib/ccbd/startup/transaction.py`
- `lib/ccbd/supervision/inspector.py`
- `lib/ccbd/supervision/loop.py`
- `lib/ccbd/shutdown/transaction.py`
- `lib/ccbd/reports/startup_report.py`

The key rule is not the exact package name. The key rule is separation:

- inspect first
- decide next
- mutate last

## 9. Current Code Alignment And Gap

The current code already aligns with the contract in some places:

- unique backend ownership is partly enforced by `OwnershipGuard`
- heartbeat and lease refresh exist in `CcbdApp`
- pane/session inspection exists in `HealthMonitor`
- provider recovery hooks exist through `ensure_pane()`
- runtime relaunch support exists in the runtime launch path

But there is one critical gap:

- recovery is not owned by a continuous daemon supervision loop

Current behavior:

- `HealthMonitor` can detect pane death and sometimes repair bindings
- further recovery is mainly attempted when a new job is about to start

Target behavior:

- daemon heartbeat itself must reconcile desired agents continuously

This gap is the main reason the current system can appear to "know how to recover" but still fail to keep idle agents mounted after pane death.

## 10. Phased Delivery

### Phase A: Contract Preservation

- keep one authoritative backend per anchor
- keep config as desired-agent authority
- keep residue from blocking kill
- stop silent authority drift

### Phase B: Runtime Supervision Loop

- add daemon-owned reconcile loop for all desired agents
- recover pane death without waiting for job start
- persist supervision state and retry/backoff

### Phase C: Keeper

- add project-scoped keeper
- restart `ccbd` after crash
- respect shutdown intent so `ccb kill` remains authoritative

### Phase D: Unified Reports

- startup report
- supervision event log
- shutdown report
- read paths consume reports instead of inferring partial truth ad hoc

## 11. Acceptance Matrix

The design is not complete until the following scenarios are automated and green.

Anchor and config:

- `.ccb` missing
- `.ccb` empty
- `.ccb` exists with persisted state but missing config
- config malformed
- config changed while backend is alive

Backend ownership:

- healthy mounted daemon
- stale lease with dead pid
- mounted lease with dead socket
- healthy lease with config mismatch
- backend crash while keeper is active
- explicit `ccb kill` does not trigger keeper restart

Runtime supervision:

- stale binding on startup
- pane dies while agent is idle
- pane dies while agent has queued work
- `ensure_pane()` succeeds
- `ensure_pane()` fails and relaunch succeeds
- repeated relaunch failure enters backoff/recovering state

Shutdown:

- normal `ccb kill`
- forced `ccb kill -f`
- unknown stale agent directories exist
- malformed runtime residue exists
- project-owned panes are removed
- backend lease ends unmounted

## 12. Change Discipline

If future work changes any of the following, this document must be updated in the same patch:

- who owns backend authority
- what defines desired agents
- whether daemon or job path owns runtime recovery
- whether keeper exists and what it is allowed to do
- what `ccb kill` guarantees
- what files under `.ccb/ccbd/` are authoritative

If implementation and this document disagree, the disagreement must be treated as an architecture issue, not hand-waved as an implementation detail.

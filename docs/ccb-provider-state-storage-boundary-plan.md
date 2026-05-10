# CCB Provider State Storage Boundary Plan

## 1. Purpose

This plan defines the code-level and layout-level boundary for storage under
`.ccb/`, especially provider-managed state under:

```text
.ccb/agents/<agent>/provider-state/<provider>/
.ccb/provider-profiles/
.ccb/shared-cache/
```

The immediate goal is not deletion. The goal is to make the storage model
explicit so CCB can later audit, compact, prune, or share cache without touching
conversation authority or breaking `ccbd` / `ask` stability.

This plan complements:

- [docs/ccbd-startup-supervision-contract.md](/home/bfly/yunwei/ccb_source/docs/ccbd-startup-supervision-contract.md)
- [docs/ccb-config-layout-contract.md](/home/bfly/yunwei/ccb_source/docs/ccb-config-layout-contract.md)
- [docs/codex-session-isolation-contract.md](/home/bfly/yunwei/ccb_source/docs/codex-session-isolation-contract.md)
- [docs/claude-session-isolation-contract.md](/home/bfly/yunwei/ccb_source/docs/claude-session-isolation-contract.md)
- [docs/gemini-session-isolation-contract.md](/home/bfly/yunwei/ccb_source/docs/gemini-session-isolation-contract.md)
- [docs/claude-binary-cache-dedup-plan.md](/home/bfly/yunwei/ccb_source/docs/claude-binary-cache-dedup-plan.md)

The provider session isolation contracts remain authoritative for conversation,
auth, config, and restore semantics. This document narrows the storage boundary
problem: what belongs in project/agent authority, what is session evidence, and
what is merely rebuildable cache.

## 2. Current Findings

Observed local `.ccb` shape:

```text
.ccb/ccbd/                         small control-plane ledger
.ccb/agents/<agent>/runtime.json    agent runtime authority
.ccb/agents/<agent>/provider-state  managed provider home/state
.ccb/provider-profiles/             currently may contain profile runtime homes
```

The control-plane portion is not the storage problem. In the observed project,
`.ccb/ccbd` is small, while most disk usage comes from provider-managed homes:

- Claude version binaries under
  `.ccb/agents/<agent>/provider-state/claude/home/.local/share/claude/versions/`
- Codex session/log sqlite data and plugin projections under managed Codex homes
- Gemini npm/node-gyp cache under managed Gemini homes
- Codex runtime home data under `.ccb/provider-profiles/<agent>/codex/`

The current code paths also show structural ambiguity:

- `agents_dir` is rooted at `runtime_state_root`, but `provider_profiles_dir` is
  rooted at the anchor `.ccb`, so WSL relocation can split runtime state from
  provider profile state.
- provider profiles can become runtime homes for Codex when a profile has
  explicit env/home authority, which makes `.ccb/provider-profiles/` hold
  sessions, logs, plugins, and cache rather than only configuration templates.
- provider home materialization copies or projects inherited assets such as
  Codex plugins, Codex skills, Claude skills, Claude commands, and hook assets
  per managed home.
- managed provider `HOME` isolation is necessary for session correctness, but
  third-party tools also write binary/cache artifacts under that same `HOME`.
- diagnostics currently distinguishes secrets mostly by filename/path blacklist,
  not by a shared storage classification model.

## 3. Storage Classes

CCB must classify project storage before it attempts cleanup or deduplication.
Classification must be deterministic: one path has one primary class. If a path
matches multiple rules, the classifier must use this precedence:

```text
SECRET > SESSION > AUTHORITY > STARTUP_AUTHORITY_BUNDLE > RUNTIME_EPHEMERAL > WORKSPACE > USER_CONTENT > PROJECTED_CONFIG > REBUILDABLE_CACHE > RESIDUE > UNKNOWN
```

The classifier may attach secondary metadata such as `provider`, `agent`,
`active`, `reclaimable`, `unsafe_symlink`, or `reason`, but the primary class
must not drift between readers.

### 3.1 Authority

Authority defines current project/backend meaning. It must be preserved by
default and must not be pruned by cache cleanup.

Examples:

- `.ccb/ccb.config`
- `.ccb/ccbd/lifecycle.json`
- `.ccb/ccbd/lease.json`
- `.ccb/ccbd/keeper.json`
- `.ccb/agents/<agent>/agent.json`
- `.ccb/agents/<agent>/runtime.json`
- `.ccb/agents/<agent>/helper.json`
- current mailbox summary records
- runtime relocation marker/ref files

### 3.2 Session Authority And Session Evidence

Session authority binds a managed provider process to a concrete provider
conversation namespace. It is provider-specific and may live inside an
agent-scoped managed home.

Examples:

- Codex managed `CODEX_HOME` and `CODEX_SESSION_ROOT`
- Codex active `sessions/` namespace for the agent
- Codex `.ccb-session-namespace.json` inside the managed home
- Claude managed `HOME`, `.claude/projects/`, and `.claude/session-env/`
- Claude `.claude.json` managed trust/account metadata authority
- Gemini managed `HOME`, `GEMINI_CLI_HOME`, and `GEMINI_ROOT`
- Gemini `<gemini_home>/.gemini/tmp/`
- project-scoped `.codex-<agent>-session`,
  `.claude-<agent>-session`, `.gemini-<agent>-session`

These files may be large, but they are not generic cache. They affect restore
and conversation continuity.

### 3.3 Runtime Ephemeral

Runtime ephemeral files support currently running helpers and panes. They may be
recreated by a fresh launch, but live processes can depend on them.

Examples:

- `.ccb/agents/<agent>/provider-runtime/<provider>/`
- bridge pids, FIFOs, runtime logs, session switch records
- project sockets and heartbeat artifacts

Cleanup must only remove this class during explicit stop/reset/kill flows or
after ownership checks prove the process generation is dead.

### 3.4 Startup Authority Bundle

Startup authority bundles are provider-specific files that are not conversation
identity but still affect launch semantics. They must be preserved atomically as
a unit.

Examples:

- Codex `.tmp/plugins/` plus `.tmp/plugins.sha` when present
- provider startup projection manifests that must match their payload tree

Rules:

- cleanup must not treat these files as ordinary cache
- diagnostics may summarize them but must not split manifest and payload
- sharing is allowed only after content-addressed whole-bundle storage and
  atomic replacement are implemented
- default behavior remains per-agent/per-home storage

### 3.5 Rebuildable Cache

Rebuildable cache does not define project authority or provider conversation
identity. It can be shared, pruned, or regenerated.

Examples:

- Claude `.local/share/claude/versions/`
- Claude `.local/bin/claude` shim/symlink when it only points to a version cache
- Gemini `.npm/_cacache/`
- Gemini `.cache/node-gyp/`
- Gemini `.cache/vscode-ripgrep/`
- provider package manager caches that do not include session/auth state

This class is the primary target for storage optimization. Rebuildable cache
records must include enough metadata for safe decisions, such as
`reachable_from_current_symlink`, `is_active_version`, or `reclaimable=false`
for active tool versions.

### 3.6 Projected Config And Inherited Assets

Projected config is copied or synthesized into managed homes to make isolated
provider startup work.

Examples:

- Codex `config.toml`
- Codex inherited `skills/` and `commands/`
- Claude `.claude/settings.json`
- Claude `.claude/skills/`, `.claude/commands/`, `.claude/CLAUDE.md`
- Gemini `.gemini/settings.json`, `.gemini/trustedFolders.json`

Auth, OAuth, token, and credential files are never `PROJECTED_CONFIG` even when
they were created by a projection step. They must classify as `SECRET`.

### 3.7 Secret

Secret material must not be exported in diagnostics and must not be moved to a
shared cache.

Examples:

- provider auth files
- Codex `auth.json`
- Claude `.claude/.credentials.json`
- Claude `.config/claude-code/auth.json`
- Gemini `.gemini/oauth_creds.json`
- Gemini `.gemini/google_accounts.json`
- API key material
- OAuth credential files
- macOS Keychain-derived Claude credentials
- `.env` files containing provider credentials

Secrets may still live inside managed provider homes, but storage tooling must
handle them through explicit allow/deny classifications.

### 3.8 Workspace

Workspace data is user-visible working-copy state. It may contain uncommitted
changes produced by an agent or by the user and must not be treated as stale
residue.

Examples:

- `.ccb/workspaces/<agent>/`
- git-worktree materializations owned by an agent workspace binding
- copy-mode working directories for non-inplace agents

Cleanup must not remove this class. Git-worktree teardown requires explicit
workspace lifecycle handling, not provider cache cleanup.

### 3.9 User Content

User content is project-local material created to aid handoff, continuation, or
operator workflow. It is not provider conversation state, but it is also not
cache.

Examples:

- `.ccb/history/` handoff/context-transfer documents
- user-authored notes under the project anchor

Cleanup must preserve this class unless a future explicit user-content command
is introduced.

### 3.10 Residue

Residue is old evidence that may guide recovery or diagnostics but must not
redefine current project authority.

Examples:

- unknown `.ccb/agents/<unknown-agent>/` directories
- provider-base session files not scoped to a configured agent
- old provider homes after profile changes
- archived Codex sessions from provider authority rotation

Residue cleanup should be opt-in or tied to explicit reset flows.

## 4. Target Layout

The target layout separates authority, managed session state, and rebuildable
cache.

```text
.ccb/
  ccb.config
  ccbd/
    ...
  agents/
    <agent>/
      agent.json
      runtime.json
      helper.json
      provider-runtime/
        <provider>/
      provider-state/
        <provider>/
          home/
            provider session/config/auth authority
  provider-profiles/
    <profile-or-agent>/
      <provider>/
        profile template/config only
  history/
    user handoff/context-transfer artifacts
  workspaces/
    <agent>/
      agent working copy state
  shared-cache/
    codex/
      startup-bundles/
        content-addressed-only/
    claude/
      bin/
      versions/
    gemini/
      npm/
      node-gyp/
```

Rules:

- `.ccb/agents/<agent>/provider-state/<provider>/home` remains the default
  managed session boundary.
- `.ccb/provider-profiles/` must not silently become a long-lived runtime home
  unless the user explicitly configures that path as an external provider home.
- `.ccb/shared-cache/` contains only rebuildable cache and never conversation
  sessions, mailbox data, runtime authority, auth secrets, or trust authority.
- Codex startup bundles may use shared cache only after content-addressed
  whole-bundle storage and atomic replacement exist; default remains per-agent.
- If runtime state is relocated on WSL-mounted filesystems, profile/runtime
  state that affects startup should follow the same effective runtime state root
  unless the user explicitly opts into an external path.
- macOS Keychain-derived credentials must remain inside agent-scoped managed
  homes and must not be shared.

## 5. Code-Level Changes

### Phase A - Storage Classification API

Add a read-only classifier before cleanup or migration.

Suggested module:

```text
lib/storage_classification/
```

Suggested model:

```text
StorageClass.AUTHORITY
StorageClass.SESSION
StorageClass.RUNTIME_EPHEMERAL
StorageClass.STARTUP_AUTHORITY_BUNDLE
StorageClass.WORKSPACE
StorageClass.USER_CONTENT
StorageClass.REBUILDABLE_CACHE
StorageClass.PROJECTED_CONFIG
StorageClass.SECRET
StorageClass.RESIDUE
StorageClass.UNKNOWN
```

Required behavior:

- classify paths under `.ccb/ccbd`
- classify paths under `.ccb/agents/<agent>`
- classify provider-state subtrees by provider-specific rules
- classify `.ccb/provider-profiles`
- calculate byte totals by class/provider/agent
- return a single primary class per path using the precedence in Section 3
- attach active/cache metadata, including
  `reachable_from_current_symlink` and `is_active_version` when available
- detect symlink loops and out-of-bound symlinks as `UNKNOWN` with a reason
- emit a versioned JSON schema for `doctor storage --json`
- never delete files in this phase

Suggested command surface:

```text
ccb doctor storage
ccb doctor storage --json
```

Exit criteria:

- users can see disk usage by class, provider, and agent
- diagnostics can report cache vs authority without exporting large binaries
- malformed or unknown paths are reported as `UNKNOWN` or `RESIDUE`, not ignored
- Codex session namespace markers, Claude `.claude.json`, and Gemini
  `.gemini/tmp/` do not classify as `UNKNOWN`

### Phase A.5 - Provider Profile Runtime-Home Migration

Before changing provider-profile semantics, migrate existing profile-backed
runtime homes safely.

Required behavior:

- detect `.ccb/provider-profiles/<agent>/codex/` trees that already contain
  sessions, auth, logs, plugin bundles, or other runtime-home data
- move or copy that runtime-home data into
  `.ccb/agents/<agent>/provider-state/codex/home/` only when the target is
  absent or compatible
- update persisted project session fields such as `codex_home`,
  `codex_session_root`, and bound session paths
- if legacy session material exists, validate the persisted Codex session
  authority before moving files; missing, malformed, or non-matching authority
  must abort migration and leave the legacy tree in place
- perform migration before current config/auth/plugin projection, discard any
  migrated plugin projection, then refresh projection from the active
  profile/source home so stale legacy auth or plugin bundles cannot override
  `inherit_auth` or mix with the current plugin bundle
- startup must support one upgrade cycle where it can read the old profile path,
  migrate/fallback safely, and rewrite authority to the new managed home
- never migrate secrets into shared cache
- reject legacy profile runtime homes that contain symlinks instead of partially
  moving data and rewriting authority
- do not migrate while the owning provider runtime is active; non-terminal
  agent runtime authority with a live `pid`/`runtime_pid`, or transitional
  `starting`/`busy`/`stopping` state without usable pid evidence, must leave the
  legacy tree untouched

Exit criteria:

- existing Codex conversations survive the provider-profile boundary change
- old profile-backed homes are classified as `RESIDUE` only after authority has
  been rewritten
- restore does not silently fall back to a fresh bootstrap because a session
  root moved
- after migration, non-explicit Codex profiles resolve to
  `.ccb/agents/<agent>/provider-state/codex/home/`; only explicit
  `provider_profile.home` remains a profile-backed runtime home

### Phase B - Path Boundary Cleanup In Code

Make path ownership explicit.

Required changes:

- introduce `provider_profile_root` and `provider_runtime_home` as separate
  concepts in models and path helpers
- prevent default profile materialization from creating session/log/cache data
  under `.ccb/provider-profiles`
- require explicit config for any profile-backed `runtime_home`; the initial
  allowed explicit runtime-home path is Codex only
- keep Claude and Gemini on managed agent-scoped homes until they have matching
  route/fingerprint rotation semantics for external runtime homes
- validate effective provider homes for all configured agents and hard fail on
  duplicate homes for the same provider
- decide whether default `provider_profiles_dir` should live under
  `runtime_state_root` when runtime state is relocated
- record path class in diagnostics and startup reports where useful

Exit criteria:

- provider profile records are configuration templates by default
- runtime homes are agent-scoped unless explicitly and safely overridden
- duplicate effective `<provider>_home` values fail startup before launch
- WSL relocation no longer leaves part of runtime-critical provider state on
  unsupported project-mounted storage

### Phase C - Provider Cache Cleanup

Implement conservative cache-specific cleanup behind one command surface:
`ccb cleanup`. `ccb doctor storage` remains the inspection path; cleanup itself
does not add dry-run or provider-specific CLI modes.

Required behavior:

- Claude: inspect `.local/share/claude/versions` and current symlink target
- Gemini: inspect `.npm/_cacache`, `.cache/node-gyp`, `.cache/vscode-ripgrep`
- Codex: inspect `.tmp/plugins` and `.tmp/plugins.sha` only as
  `STARTUP_AUTHORITY_BUNDLE`, not as reclaimable cache
- report deleted bytes and skipped paths after cleanup
- refuse unsafe symlink traversal
- hold the same project startup/lifecycle lock used by `ccbd` startup while
  checking state and pruning, so cleanup cannot race a concurrent backend start
- never touch session roots or auth files
- refuse to run while `ccbd` is active or pending/running `ask` jobs exist
- treat malformed or unreadable job JSONL as unknown pending work and refuse
  cleanup rather than crashing or pruning blindly

Suggested command surface:

```text
ccb cleanup
```

Exit criteria:

- `ccb doctor storage` explains cache vs. authority before cleanup
- repeated cleanup is stable and idempotent
- provider startup and ask completion semantics are unchanged
- `ccb cleanup` deletes only safe rebuildable cache and preserves authority,
  sessions, secrets, and startup authority bundles

### Phase D - Shared Cache For Rebuildable Provider Assets

Move selected rebuildable cache out of per-agent managed homes.

Initial candidates:

- Claude version binaries, after Phase C proves safe classification
- Gemini npm/node-gyp cache, only if environment variables can safely redirect
  tool cache without changing auth/session state
- Codex startup bundles only after content-addressed whole-bundle sharing and
  atomic replacement exist; default remains per-agent

Required behavior:

- shared cache must not contain provider conversations or auth secrets
- shared cache must be reference-count safe or content-addressed
- removing one agent must not break another agent
- fallback to per-agent cache if a provider refuses redirected cache paths
- on WSL drvfs anchors without runtime-state relocation, shared cache must be
  disabled and per-agent cache retained
- startup warnings about cache fallback must not fail `ask` jobs

Exit criteria:

- two same-provider agents do not duplicate large rebuildable cache by default
- provider sessions remain isolated
- Linux, macOS, and WSL launches still work

### Phase E - JSONL Retention And Compaction

Control-plane JSONL growth is not the urgent disk issue, but it needs a future
policy.

Required behavior:

- keep append-only semantics for current authority/event readers
- add optional compaction snapshots for old terminal jobs/messages
- preserve enough history for diagnostics and support bundles
- never compact active/running/accepted jobs

Exit criteria:

- long-running projects do not grow unbounded event ledgers
- `pend`, `queue`, `inbox`, `watch`, `doctor`, and restore paths keep their
  current semantics

## 6. Provider-Specific Boundaries

### 6.1 Codex

Must remain agent-isolated:

- `CODEX_HOME`
- `CODEX_SESSION_ROOT`
- active `sessions/`
- explicit provider authority marker
- `.ccb-session-namespace.json`
- project-scoped `.codex-<agent>-session`
- `.tmp/plugins/` plus `.tmp/plugins.sha` as one startup authority bundle

Must remain secret and agent-local:

- `auth.json`

Potential future shared storage:

- inherited skills/commands projection when it can be represented as immutable
  or versioned projection rather than copied tree
- `.tmp/plugins/` plus `.tmp/plugins.sha` only through content-addressed
  whole-bundle storage and atomic replacement

Do not share:

- active sessions
- provider authority markers
- auth files
- plugin tree and sha as separately mutable paths
- per-agent conversation logs

### 6.2 Claude

Must remain agent-isolated:

- managed `HOME`
- `.claude/projects/`
- `.claude/session-env/`
- `.claude/settings.json`
- `.claude.json`

Must remain secret and agent-local:

- `.claude/.credentials.json`
- `.config/claude-code/auth.json`

Candidates for shared/rebuildable cache:

- `.local/share/claude/versions/`
- `.local/bin/claude` shim/symlink

The Claude-specific implementation details live in
[docs/claude-binary-cache-dedup-plan.md](/home/bfly/yunwei/ccb_source/docs/claude-binary-cache-dedup-plan.md).

### 6.3 Gemini

Must remain agent-isolated:

- managed `HOME`
- `GEMINI_CLI_HOME`
- `GEMINI_ROOT`
- `<gemini_home>/.gemini/tmp/`
- `.gemini/settings.json`
- `.gemini/trustedFolders.json`

Must remain secret and agent-local:

- `.gemini/oauth_creds.json`
- `.gemini/google_accounts.json`

Candidates for shared/rebuildable cache:

- `.npm/_cacache`
- `.cache/node-gyp`
- `.cache/vscode-ripgrep`

Do not redirect cache until real launch tests confirm Gemini respects cache env
without changing auth/session identity.

## 7. WSL And macOS Requirements

WSL:

- project anchors on `/mnt/<drive>` must avoid placing Unix sockets or
  runtime-critical mutable state on unsupported filesystems
- provider profile/runtime state must not be split across anchor and relocated
  root in a way that breaks startup or cleanup
- shared cache may live under relocated runtime state or user cache, not under
  an unsafe mounted-drive path by default
- if the project anchor is on drvfs and runtime-state relocation is not active,
  Phase D shared cache must be disabled and per-agent cache retained
- `ccb doctor storage` must report that relocation is required before shared
  provider cache can be enabled on drvfs

macOS:

- Claude Keychain-derived credentials must remain per managed home
- shared binary/cache logic must not move or export Keychain-derived auth files
- cleanup must handle symlink metadata conservatively

Linux:

- default behavior should continue to use project-local `.ccb` when safe
- user-level cache is acceptable only for rebuildable cache, not authority

## 8. Diagnostics Contract Changes

Diagnostics should stop treating provider-state as an undifferentiated tree.

Required changes:

- `doctor` should surface storage class totals
- diagnostics bundle should include cache manifests but not large cache payloads
- secret filtering should use storage classification plus provider-specific
  rules, not only filename blacklists
- unknown provider-state paths should be visible as unknown/residue
- the classifier must return one primary class per path; conflict precedence is
  defined in Section 3
- cache summaries should include active/reclaimable metadata and a reason when
  a path is not safe to prune

Bundle export rule:

- authority and small session evidence may be copied according to existing
  diagnostics policy
- rebuildable cache should be summarized by path, size, provider, and class
- startup authority bundles should be summarized as a unit and not split across
  manifest/payload files
- secrets must never be copied
- diagnostic bundles must include `generated/storage-summary.json` so skipped
  cache/startup-bundle payloads remain visible as summaries

## 9. Tests

Required unit tests:

- classify `.ccb/ccbd` authority vs events
- classify agent runtime files as authority/runtime
- classify Codex session roots as session authority
- classify Codex `.ccb-session-namespace.json` as session authority
- classify Codex plugin projection plus sha as `STARTUP_AUTHORITY_BUNDLE`
- classify Claude versions as rebuildable cache and active version separately
- classify Claude `.claude.json` as managed trust/session authority
- classify Gemini npm/node-gyp cache as rebuildable cache
- classify Gemini `.gemini/tmp/` as session
- classify provider auth files as secret
- provider profile default path does not become runtime home
- explicit Codex provider profile home remains allowed and visible as explicit
- duplicate effective provider homes fail validation
- cleanup refuses to run while ccbd or ask jobs are active
- unsafe symlinks classify as `UNKNOWN` with a reason

Required integration tests:

- Linux storage audit on a multi-provider project
- WSL relocated runtime-state project storage audit
- WSL drvfs project without relocation reports shared-cache disabled
- macOS Claude storage audit with Keychain-compatible managed home
- `ccb ask` still completes after storage audit
- `ccbd` restart still restores managed provider sessions
- cleanup preserves provider sessions/auth and is idempotent
- provider-profile Codex migration preserves bound session authority

Required real tests:

- multi-agent Codex ask/reply loop
- Claude managed launch with version cache present
- Gemini managed launch with npm cache present
- two same-provider agents remain session-isolated after cache inspection
- WSL project on mounted drive starts and asks successfully
- macOS project starts and asks successfully

## 10. Recommended Implementation Order

1. Implement Phase A storage classification and `doctor storage --json`.
2. Add diagnostics bundle cache summaries and secret-safe classification.
3. Implement Phase A.5 provider-profile Codex runtime-home migration.
4. Fix provider profile/runtime-home path boundary so default profiles do not
   accumulate runtime sessions/log/cache.
5. Implement `ccb cleanup` as the single conservative provider-cache cleanup
   command.
6. Keep `ccb doctor storage` as the only cleanup preview/audit surface.
7. Evaluate Codex startup-bundle sharing only after content-addressed
   whole-bundle atomic replacement exists.
8. Evaluate Claude shared binary cache only after Linux/macOS/WSL real launch
   verification.
9. Evaluate Gemini npm/node-gyp cache redirection after real launch
   verification.
10. Add JSONL retention/compaction after provider-state size is under control.

## 11. Non-Goals

- Do not weaken managed provider session isolation.
- Do not make `.ccb/agents/<agent>/provider-state` globally shared.
- Do not delete cache as part of `doctor`.
- Do not treat unknown files as safe to remove.
- Do not share auth, trust, session roots, mailbox records, runtime authority,
  or active provider logs.
- Do not make cleanup part of normal `ask` critical path.
- Do not run destructive `ccb cleanup` concurrently with an active backend:
  cleanup must acquire the project startup/lifecycle guard, confirm `ccbd` is
  stopped inside that guard, and refuse to prune while pending `ask` jobs exist.

## 12. First Concrete Slice

The first implementation slice should be read-only:

- add storage classification models
- add provider-specific classifiers for Codex, Claude, and Gemini
- add `ccb doctor storage --json`
- add human render for `ccb doctor storage`
- include `schema_version`, primary class, provider, agent, size, active flags,
  reclaimability, and reason fields in JSON output
- add tests with synthetic `.ccb` trees

This slice directly addresses the current ambiguity without risking data loss.
Only after the classifier is trusted should cleanup or shared-cache behavior be
implemented.

## 13. Current Implementation Status

Implemented:

- Phase A storage classification API exists under `lib/storage_classification/`.
- `ccb doctor storage` and `ccb doctor storage --json` expose storage totals and
  per-entry class/provider/agent/size metadata.
- `ccb doctor storage` reports `shared_cache_status=disabled` and a disabled
  reason while Phase D shared-cache redirection remains unimplemented.
- Provider auth/OAuth files classify as `SECRET`, not `PROJECTED_CONFIG`.
- Codex `.tmp/plugins/` plus `.tmp/plugins.sha` classify as
  `STARTUP_AUTHORITY_BUNDLE`, not rebuildable cache.
- Codex `.ccb-session-namespace.json`, Claude `.claude.json`, and Gemini
  `.gemini/tmp/` classify as session authority/evidence.
- Claude version-cache entries include active-version metadata:
  `active`, `is_active_version`, `reachable_from_current_symlink`,
  `reclaimable`, and `reason`.
- `.ccb/history/` classifies as `USER_CONTENT`, not provider session state.
- `.ccb/workspaces/` classifies as `WORKSPACE`, not residue.
- Non-Codex `provider_profile.home` is rejected at config load and materializer
  boundaries. Claude/Gemini runtime homes remain managed
  `.ccb/agents/<agent>/provider-state/<provider>/home` paths.
- Phase A.5 Codex migration moves old default
  `.ccb/provider-profiles/<agent>/codex/` runtime-home data into
  `.ccb/agents/<agent>/provider-state/codex/home/` only after session
  authority preflight passes, merges without overwriting existing managed data,
  and rewrites persisted `codex_home`, `codex_session_root`,
  `codex_session_path`, `start_cmd`, and `codex_start_cmd` authority fields.
  Command fields are rewritten with path-boundary checks so unrelated strings
  that merely share the legacy path prefix are preserved.
- Non-explicit Codex provider profiles now materialize config/auth/plugin
  projection into the agent-scoped managed Codex home. Explicit
  `provider_profile.home` remains the only profile-backed Codex runtime-home
  override.
- Non-explicit Codex resolved profile records leave `profile_root` unset so
  persisted provider-profile metadata does not point at the removed legacy
  `.ccb/provider-profiles/<agent>/codex/` runtime-home path.
- Codex migration runs before profile projection, and projection then refreshes
  config/auth/plugins from the active source home/profile after discarding any
  migrated plugin tree, so legacy auth files or plugin trees do not bypass
  current `inherit_auth` or mix bundle versions.
- Codex migration is skipped when agent runtime authority still points at a
  live non-terminal provider runtime process, while stale `idle`/`degraded`
  records without a live pid do not block upgrade migration.
- Codex legacy profile migration writes a best-effort
  `codex_profile_migration` event to `agents/<agent>/events.jsonl` on migrated
  or skipped outcomes so upgrade diagnostics can explain why a legacy tree
  remained in place.
- Claude/Gemini launchers ignore older persisted `runtime_home` values in
  provider profile records.
- Startup preparation rejects duplicate effective provider runtime homes before
  provider launch.
- `ccb config validate` rejects duplicate effective provider runtime homes
  before startup as well.
- `ccb cleanup` is implemented as the single cleanup entrypoint. It refuses to
  run while `ccbd` is active or ask jobs are pending/running, prunes old Claude
  version caches while keeping current plus one rollback version, and removes
  Gemini rebuildable npm/node-gyp/ripgrep caches.
- `ccb cleanup` holds the project `startup.lock` while re-checking backend/job
  state and pruning; malformed job JSONL blocks cleanup conservatively.
- cleanup reports symlinked Claude `versions/` directories and skips
  out-of-bounds Gemini cache paths instead of traversing them.
- diagnostics bundle export writes `generated/storage-summary.json` and uses
  `StorageClass` to exclude `SECRET`, `REBUILDABLE_CACHE`, and
  `STARTUP_AUTHORITY_BUNDLE` provider payloads from the archive.
- diagnostics bundle provider-state walking does not follow symlinks and
  hard-excludes Codex plugin bundles, Claude version caches, and Gemini/npm
  rebuildable caches even if storage classification fails.
- storage diagnostics include explicit shared-cache disabled status/reason so
  users do not mistake Phase C cache cleanup for Phase D shared-cache
  redirection.
- Linux real validation passed with the current Phase A-C implementation:
  - full unit suite: `1738 passed`
  - communication matrix: `test/system_comm_matrix.sh` passed, covering mixed
    providers, same-provider dual agents, cross-project isolation, `watch`,
    `pend`, and kill cleanup
  - fastpath stress: `test/system_fastpath_stress.sh` passed with 60 asks,
    submit p95 `220ms`, max `240ms`
  - shortened Linux soak after the shutdown reply-delivery fix:
    `CCB_LINUX_SOAK_SECONDS=180 CCB_LINUX_SOAK_KILL_EVERY=3
    test/system_linux_soak.sh` passed with 14 iterations, repeated
    kill/restart, submit p95 `212ms`, max `212ms`
  - real cleanup validation on the soak project passed after injecting Claude
    and Gemini cache residue: no pending jobs remained, `ccb cleanup` removed
    old Claude version cache plus Gemini npm/node-gyp caches while preserving
    Claude current/rollback versions and Gemini `.gemini/tmp` session state
- During Linux cleanup validation, an accepted reply-delivery residue was found
  from shutdown-time after-complete scheduling. The shutdown contract now
  suspends automatic reply-delivery creation once project stop is requested, so
  stop-all terminalization cannot create replacement provider work while
  draining existing jobs.
- The real-platform GitHub Actions workflow
  `.github/workflows/ccbd-real-platform.yml` now includes macOS and WSL
  `ccb doctor storage --json` plus `ccb cleanup` smoke steps. Those steps
  inject Claude version-cache and Gemini npm/node-gyp cache residue through the
  effective `PathLayout`, then assert cleanup removes only rebuildable cache and
  preserves Claude current/rollback binaries plus Gemini `.gemini/tmp` session
  state. WSL also accepts either pre-relocation or relocated shared-cache
  disabled reasons.
- Remote macOS and WSL validation passed on GitHub Actions run
  `25632010275` for commit `d693004`:
  <https://github.com/SeemSeam/claude_codex_bridge/actions/runs/25632010275>
  - macOS real ccbd/ask smoke passed in `5m27s`, including lifecycle smoke,
    communication matrix, short soak, fastpath stress, and storage cleanup
    smoke.
  - WSL mounted-drive ccbd/ask smoke passed in `8m40s`, including lifecycle
    smoke, WSL path/relocation tests, communication matrix, short soak,
    fastpath stress, and storage cleanup smoke.

Not implemented yet:

- Claude shared binary cache, Gemini cache redirection, and Codex
  content-addressed startup-bundle sharing.
- JSONL retention and compaction.

Next recommended work:

1. Evaluate shared-cache redirection only after repeated Linux/macOS/WSL cleanup
   validation proves stable.
2. Keep `ccb cleanup` conservative until Phase D has content-addressed or
   provider-supported shared-cache semantics.

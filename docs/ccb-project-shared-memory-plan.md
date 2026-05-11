# CCB Project Shared Memory Plan

## Purpose

CCB should provide a small project-level shared memory file that helps all
configured agents understand they are part of the same visible CCB agent team.

The primary purpose is agent awareness and agent-to-agent communication:

- agents should know that other configured project agents may exist
- agents should prefer CCB `ask` for visible cross-agent collaboration
- agents should avoid silently defaulting to provider-native hidden subagents
  when the work belongs to another CCB-managed project agent

This feature is not a full user manual, not a provider configuration system,
and not a replacement for provider-native memory files.

## Goals

- Create a project-level shared memory source at `project_root/.ccb/ccb_memory.md`.
- Keep the default `.ccb/ccb_memory.md` template minimal and English-only.
- Materialize shared memory into each managed agent on every startup.
- Preserve provider isolation and avoid mutating user global provider state.
- Work correctly when an agent workspace is not the original project root.
- Keep `.ccb` generated state and private memory out of git by default.

## Non-Goals

- Do not inject long CLI command documentation into agent memory.
- Do not automatically edit `project_root/CLAUDE.md`, `project_root/AGENTS.md`,
  `project_root/GEMINI.md`, or other user-authored provider memory files.
- Do not edit `~/.claude`, `~/.codex`, `~/.gemini`, or OpenCode global config
  as part of this feature.
- Do not promise a universal provider-internal memory load order. CCB only
  controls the generated bundle content and provider-specific projection path.

## Project Files

Recommended project layout:

```text
project_root/
  .ccb/
    ccb_memory.md
    agents/
      agent1/
        memory.md
        provider-state/
          claude/
          codex/
          gemini/
          opencode/
<runtime_state_root>/
  state/
    memory.seed.json
  runtime/
    memory/
      agent1.md
      agent2.md
```

### User-Editable Files

- `.ccb/ccb_memory.md`
  - shared CCB project memory
  - safe to whitelist and commit when the team wants common agent collaboration rules
  - created automatically only when missing

- `.ccb/agents/<agent>/memory.md`
  - optional agent-private memory
  - user data, but local/private by default
  - anchored under the project `.ccb/` directory, not relocated runtime state
  - never deleted or rewritten automatically by normal startup

### Generated Files

- `<runtime_state_root>/state/memory.seed.json`
  - records template version and seed hash for the original generated `.ccb/ccb_memory.md`

- `<runtime_state_root>/runtime/memory/<agent>.md`
  - generated bundle for providers that need a stable project-relative memory
    path, especially OpenCode

- `.ccb/agents/<agent>/provider-state/<provider>/...`
  - managed provider projection files
  - generated runtime state, not user-editable source

## Git Ignore Policy

`.ccb` should be ignored by default because it contains runtime state,
provider-state, generated bundles, local config, session data, auth/config
projections, and optional agent-private memory.

Recommended default:

```gitignore
.ccb/*
```

`.ccb/ccb_memory.md` is local by default under the project anchor. Teams that
want to share it can whitelist that specific file.

If a team explicitly wants to share `.ccb/ccb.config`, they can add their own
project-specific whitelist:

```gitignore
.ccb/*
!.ccb/
!.ccb/ccb_memory.md
!.ccb/ccb.config
```

CCB should not force this whitelist because `.ccb/ccb.config` may contain local
provider routing, model, URL, or key material.

## .ccb/ccb_memory.md Creation Semantics

Startup may create `project_root/.ccb/ccb_memory.md` only when the file is missing.

Requirements:

- Use atomic create-if-missing semantics.
- Do not create, import, or otherwise rely on project-root `CCB.md`.
- Never overwrite a user-edited `.ccb/ccb_memory.md`.
- Record seed metadata in `<runtime_state_root>/state/memory.seed.json`.
- If a future template version changes and the current `.ccb/ccb_memory.md` still matches
  the original seed hash, CCB may update it.
- If a future template version changes and the user has edited `.ccb/ccb_memory.md`, CCB
  should write `.ccb/ccb_memory.md.new` or emit a diagnostic notice instead of overwriting.
- If the project root is read-only, startup should continue without shared
  memory and record a warning.

## Minimal .ccb/ccb_memory.md Template

The default template should stay focused on agent awareness and CCB `ask`
communication.

````md
# CCB Project Memory

This project is managed by CCB as a visible multi-agent workspace.

## Agent Awareness

- You are one agent in a CCB-managed project team.
- Other configured agents may be available in the same project.
- When work should be handled, reviewed, or cross-checked by another visible
  project agent, use CCB `ask`.
- Prefer CCB `ask` over provider-native hidden subagents for project-level
  collaboration.
- When delegating, include the goal, relevant files, current assumptions, and
  expected output.
- When replying to another agent, be concrete: include findings, changed files,
  blockers, and verification results.

## Ask Communication

Use one of these forms when available:

```text
/ask <agent> <message>
ask <agent> "<message>"
```

For CCB CLI help, run `ccb -h`.
````

## Memory Bundle Model

CCB should generate a provider-facing memory bundle per agent. The bundle is a
single markdown document with explicit source sections.

CCB should not claim that every provider loads memory in the same order.
Instead, CCB controls the generated bundle order:

```md
# CCB Managed Agent Memory

<!-- generated by ccb; do not edit this file directly -->

## CCB Shared Project Memory
source: project_root/.ccb/ccb_memory.md

## Provider-Native Project Memory
source: project_root/CLAUDE.md, AGENTS.md, GEMINI.md, or equivalent

## Agent Private Memory
source: .ccb/agents/<agent>/memory.md
```

The provider/system/account memory layer remains provider-owned and outside
this generated bundle unless explicitly inherited through a provider profile
field.

## Source Resolution

Memory source resolution must use `project_root`, not the agent workspace, for
project-level memory files.

This matters because configured agents may run in:

- `project_root`
- a copy workspace
- a git worktree
- a custom workspace root

Therefore, CCB must explicitly read:

- `project_root/.ccb/ccb_memory.md`
- `project_root/CLAUDE.md` for Claude when applicable
- `project_root/AGENTS.md` for Codex/OpenCode when applicable
- `project_root/GEMINI.md` for Gemini when applicable
- `project_root/.ccb/agents/<agent>/memory.md`

Provider-native project memory should not be discovered only from the agent
runtime cwd.

Agent-private memory is anchored at `project_root/.ccb/agents/<agent>/memory.md`
even when provider runtime state is relocated. This intentionally separates
user-editable memory from generated provider runtime directories.

## Provider Strategy

### Claude Code

Claude Code should receive the generated bundle through the managed Claude home:

```text
.ccb/agents/<agent>/provider-state/claude/home/.claude/CLAUDE.md
```

The existing path that syncs `source_home/.claude/CLAUDE.md` into the same
managed file must be merged into the new memory pipeline or disabled for memory
projection. Otherwise, two startup steps can write the same target file and the
last writer wins.

Recommended profile model:

- add `inherit_memory`, default `true`
- keep `inherit_memory` independent from `inherit_skills`
- keep skill and command projection behavior unchanged

### Codex

Codex should receive the generated bundle through its managed `CODEX_HOME`:

```text
.ccb/agents/<agent>/provider-state/codex/home/AGENTS.md
```

Do not rely on workspace discovery alone because the agent workspace may not be
the original project root.

If the project has `project_root/AGENTS.md`, include it in the generated bundle
from `project_root`. Avoid copying another duplicate into the workspace.

Codex launcher integration must mirror Claude's launch-context contract:
declare `prepare_launch_context`, put `project_root`, `workspace_path`, and
`agent_events_path` into `prepared_state`, and read those values during memory
projection instead of inferring project identity from provider runtime paths.

Codex startup must write `codex_memory_projection_{ok,skipped,failed}` events
with the same marker-dedup semantics as Claude. Missing launch context is a
startup contract violation and should fail fast before launching the provider.

### Gemini

Gemini should receive the generated bundle through its managed Gemini home:

```text
.ccb/agents/<agent>/provider-state/gemini/home/.gemini/GEMINI.md
```

The implementation uses the managed `.gemini/settings.json` `contextFileName`
field to point Gemini at `GEMINI.md`. `inherit_memory = false` removes the
generated file and clears that managed `contextFileName` value. Gemini CLI
0.41.2 was smoke-tested with `HOME`, `GEMINI_CLI_HOME`, and `GEMINI_ROOT`
pointing at the managed home; a token present only in managed
`.gemini/GEMINI.md` was available to `gemini --prompt`. Re-run this smoke when
upgrading Gemini CLI versions so the loading mechanism does not drift.

### OpenCode

OpenCode should use its config `instructions` mechanism. CCB must not modify
`project_root/AGENTS.md` or `project_root/opencode.json`.

Generate the canonical runtime memory bundle under runtime state, then expose a
project-relative bridge path for OpenCode versions that resolve instructions
relative to the project:

```text
<runtime_state_root>/runtime/memory/<agent>.md
project_root/.ccb/runtime/memory/<agent>.md
```

Generate an agent-local OpenCode config:

```text
.ccb/agents/<agent>/provider-state/opencode/opencode.json
```

Example:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "instructions": [
    ".ccb/runtime/memory/agent3.md"
  ]
}
```

Launch OpenCode with an absolute `OPENCODE_CONFIG` pointing to the generated
config file. The generated config must merge `project_root/opencode.json` when
present:

- user keys win for all fields except `instructions`
- `instructions` is a stable union of user entries plus the CCB bridge entry
- invalid project config degrades by writing the minimal CCB config and
  recording `opencode_config_merge_failed`

This avoids treating `OPENCODE_CONFIG` as a replacement that silently discards
project provider, model, MCP, permission, or instruction settings.

## Runtime Integration

Recommended new module:

```text
lib/project_memory/
  template.py
  loader.py
  renderer.py
  materializer.py
```

Responsibilities:

- ensure `.ccb/ccb_memory.md` exists when safe
- load shared, provider-native, and agent-private memory sources
- render deterministic generated bundles
- materialize provider-specific memory files/config
- report path, hash, mtime, source list, and warnings for diagnostics

The startup flow should call project memory materialization before launching the
provider process and after the provider runtime directory/home is known.
`prepare_provider_workspace` is the preferred single writer for generated
provider memory/config projections; command builders should read prepared
paths/env only unless a provider explicitly documents a different lifecycle.

Memory materialization should be idempotent. Failure to write generated memory
should not prevent agent startup unless the provider requires the generated file
to start correctly. Prefer warning and degraded startup.

## Diagnostics

Diagnostics should include metadata, not memory body text:

- shared memory path
- generated bundle path
- provider projection path
- sha256
- mtime
- source files
- missing-source warnings
- read/write warnings

Support bundles must avoid exporting sensitive generated provider-state content
unless the diagnostics policy explicitly allows a redacted form.

## Cleanup Semantics

- `.ccb/ccb_memory.md` is user data and must not be deleted automatically.
- `.ccb/agents/<agent>/memory.md` is user data and must not be deleted by normal
  startup.
- `.ccb/runtime/memory/<agent>.md` is generated runtime state and may be removed
  during runtime cleanup.
- Provider-state memory projections are generated runtime state and may be
  removed with the corresponding provider-state.

## Contract Updates Required

Implementation should update these documents in the same patch set:

- `docs/ccb-config-layout-contract.md`
  - define `.ccb/ccb_memory.md` and `.ccb/agents/<agent>/memory.md`
  - state that `.ccb` is ignored/local by default

- `docs/ccbd-startup-supervision-contract.md`
  - add project memory materialization as an idempotent startup step
  - define failure downgrade behavior

- `docs/claude-session-isolation-contract.md`
  - define managed `.claude/CLAUDE.md` as a CCB-generated projection
  - clarify `inherit_memory` versus `inherit_skills`

- `docs/codex-session-isolation-contract.md`
  - define managed `CODEX_HOME/AGENTS.md` projection

- `docs/gemini-session-isolation-contract.md`
  - define managed `.gemini/GEMINI.md` projection and loading mechanism

- OpenCode contract coverage
  - update `docs/opencode-completion-contract.md` only if completion behavior is
    affected
  - otherwise add or update an OpenCode isolation/config contract for generated
    `opencode.json`

## Tests Required

- Missing `.ccb/ccb_memory.md` is created once.
- Edited `.ccb/ccb_memory.md` is not overwritten.
- Read-only project root degrades with a warning.
- Concurrent startup does not corrupt `.ccb/ccb_memory.md`.
- Claude has no double-write conflict for managed `.claude/CLAUDE.md`.
- Codex receives `CODEX_HOME/AGENTS.md`.
- Gemini generated memory is actually loaded by the current CLI mechanism.
- OpenCode receives generated `opencode.json` and project-relative
  `instructions`.
- Copy workspace and git-worktree agents still inherit `project_root/.ccb/ccb_memory.md`.
- Agent-private memory enters the generated bundle.
- Diagnostics expose metadata only, not memory body text.

## Implementation Sequence

1. Add `inherit_memory` to provider profile models, defaulting to `true`.
2. Add project memory template, seed metadata, loader, renderer, and diagnostics
   metadata.
3. Integrate Claude first and remove the existing double-write risk.
4. Integrate Codex.
5. Verify and integrate Gemini memory loading.
6. Verify and integrate OpenCode config instructions.
7. Update contracts and diagnostics.
8. Add focused regression tests for startup, workspace isolation, and generated
   provider projections.

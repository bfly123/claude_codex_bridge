# Managed Provider Completion Reliability Plan

## 1. Document Role

This document defines the architecture plan for reliable completion detection and terminalization for managed pane-backed providers.

Primary trigger incidents:

- GitHub issue `#180`
  - managed Codex on macOS accepts work but never converges the job out of `running`
- GitHub issue `#181`
  - managed Gemini on macOS leaves jobs in `running` when `AfterAgent` misfires, fires on the wrong turn, or never fires after provider-side failure / long-thinking state

This document is intentionally broader than "mac bugfix notes".

The current incidents were surfaced on macOS, but the design defect is not mac-only:

- provider completion authority is too dependent on one fragile provider-specific signal
- runtime artifact contracts are not validated as a coherent system
- `ccbd` has no generic completion-timeout closure when a provider never emits its expected terminal artifact

This plan applies to:

- managed `codex`
- managed `claude`
- managed `gemini`

in pane-backed mode only.

This document does not replace:

- `docs/ccbd-startup-supervision-contract.md`
- `docs/ccbd-diagnostics-contract.md`
- `docs/codex-session-isolation-contract.md`
- `docs/claude-session-isolation-contract.md`
- `docs/gemini-session-isolation-contract.md`
- `docs/opencode-completion-contract.md`

`opencode` already has its own completion contract and should not be silently folded into the changes below.

## 2. Current Problem

### 2.1 Surface Symptoms

Issue `#180` shows:

- Codex pane finishes visible work
- job remains `running`
- `ccb kill -f` is the only way to clear the execution
- runtime file layout is inconsistent:
  - session payload advertises `bridge_output.log`
  - bridge runtime writes `bridge.log`
  - `completion/` is not guaranteed to exist

Issue `#181` shows:

- Gemini hook is registered correctly
- hook artifact may be written for the wrong request id
- hook may emit `completed` with empty reply for an auth / info banner turn
- hook may never emit for the actual request after provider-side API failure or long-thinking stall
- job remains `running` forever because no alternate closure path exists

### 2.2 Shared Structural Root Cause

The shared problem is not "mac has weird timing".

The shared problem is:

```text
provider completion authority
  = split across provider-specific artifact assumptions
  + no unified runtime bootstrap validation
  + no generic no-terminal-evidence timeout
  + weak request-turn attribution for hook-driven providers
```

Current behavior by family:

- Codex
  - modeled as `PROTOCOL_TURN`
  - depends on Codex log/session reading
  - runtime layout contract is duplicated across launcher/session payload/bridge code
- Claude
  - modeled as `SESSION_BOUNDARY`
  - may use observed session events plus hook shortcut
- Gemini
  - modeled as `ANCHORED_SESSION_STABILITY`
  - currently treats hook artifact as the decisive exact terminal source when present

All three families currently lack a single reliability boundary that answers:

- what runtime artifacts must exist before the provider is considered launch-ready
- what the primary completion source is
- what alternative evidence may be used when the primary source is absent or misattributed
- how long a job may remain `running` without new reliable completion evidence
- how `ccbd` should converge the job when the provider stays alive but never emits a valid terminal signal

## 3. Architectural Diagnosis

### 3.1 Missing Completion Reliability Plane

Today the stack is:

- provider adapter emits items / terminal decision
- execution service persists whatever the provider emits
- dispatcher terminalizes the job only when the provider emitted a terminal decision

This means:

- if a provider returns `None` forever, the job remains `running` forever
- `ccbd` has no cross-provider closure authority for "provider alive but completion evidence missing"

That is the central design defect.

### 3.2 Missing Runtime Artifact Contract

Managed pane-backed providers also lack a strict runtime bootstrap contract.

Example from Codex:

- launcher payload says `tmux_log = runtime_dir/bridge_output.log`
- bridge env exports `CODEX_TMUX_LOG = runtime_dir/bridge_output.log`
- bridge runtime writes to `runtime_dir/bridge.log`

This is a direct contract split.

As long as file paths are duplicated across:

- launcher
- bridge runtime
- session payload
- readers

the system will continue to accumulate platform-sensitive residue bugs.

### 3.3 Weak Turn Attribution For Hook Providers

Current Gemini / Claude hook handling is too weakly bound to the active request turn.

Current artifact model:

- one file per `req_id`
- hook script extracts request id from prompt or transcript
- `load_event()` reads a single terminal event file

Problems:

- a hook may fire for an auth / info / retry side turn
- extracted `req_id` may refer to the last visible request marker, not the currently intended answer turn
- empty reply can still be terminalized as `completed`

This is not a mere parser issue.

It is a missing turn-identity contract.

### 3.4 No Generic No-Evidence Timeout

A managed request can currently get stuck in this bad state:

- pane is alive
- provider is still attached
- request was accepted and started
- partial or unrelated completion items may have been observed
- no valid terminal artifact arrives
- no provider adapter emits terminal decision
- execution stays active forever

That must not be legal.

## 4. Design Goals

The target architecture is:

```text
managed pane-backed request
  = one declared primary completion source
  + one validated runtime artifact contract
  + optional secondary degraded evidence sources
  + one control-plane-owned timeout closure path
```

Required outcomes:

- no managed job may stay `running` forever only because the provider never emitted a valid terminal artifact
- runtime artifact path mismatches must fail fast during startup, not surface later as zombie jobs
- hook-driven providers must not burn a job id on an unrelated auth/info turn
- diagnostics must show which completion source was expected, which one was observed, and why the job terminalized
- the design must preserve provider-family differences without scattering reliability logic across random call sites

## 5. Non-Goals

This plan does not:

- change keeper / `ccbd` lifecycle authority
- redefine `.ccb` startup authority
- replace provider-family-specific readers with one universal parser
- add native Windows support
- change `opencode` completion semantics

## 6. New Boundary: Completion Reliability Contract

Add a new provider/runtime-scoped contract layer:

- `CompletionReliabilityManifest`

This belongs beside existing completion manifests, but serves a different purpose.

Existing manifest answers:

- what completion family the provider belongs to
- what selector family / source kind is expected

New reliability manifest answers:

- what runtime artifacts must exist
- what the primary authority source is
- what secondary evidence sources may be consulted
- whether empty-reply terminalization is allowed
- what no-progress / no-terminal deadlines apply
- what degraded terminal reason to emit when primary completion authority never arrives

### 6.1 Suggested Fields

- `provider`
- `runtime_mode`
- `primary_authority`
  - `protocol_log`
  - `hook_artifact`
  - `session_event_log`
- `required_runtime_artifacts`
  - directories/files expected immediately after launch
- `optional_secondary_sources`
  - `session_log`
  - `pane_capture`
  - `hook_artifact`
  - `protocol_log`
- `allow_empty_terminal_reply`
- `empty_reply_requires_secondary_evidence`
- `no_progress_timeout_s`
- `no_terminal_timeout_s`
- `timeout_terminal_status`
  - usually `incomplete`
- `timeout_terminal_reason`
  - for example `completion_timeout`
- `supports_degraded_pane_capture`

The manifest must be provider-owned data, not inferred ad hoc in CLI code.

## 7. New Boundary: Completion Reliability Monitor

Add a control-plane-owned component in the execution layer:

- `CompletionReliabilityMonitor`

This component must live with provider execution, not in CLI, and not in generic dispatcher routing.

### 7.1 Responsibility

For each active submission, it tracks:

- when the job started
- when runtime bootstrap was confirmed
- when the last progress evidence arrived
- when the last primary-authority evidence arrived
- whether the latest evidence is exact / observed / degraded
- whether the request is past no-progress or no-terminal deadlines

It does not parse provider-specific logs itself.

Instead:

- provider adapters keep parsing provider-native streams
- the monitor evaluates reliability state and closure policy using normalized evidence facts

### 7.2 State Model

Each active submission should expose reliability facts in runtime state:

- `completion_bootstrap_state`
  - `pending`
  - `ready`
  - `failed`
- `completion_primary_state`
  - `waiting`
  - `observed`
  - `terminal`
  - `missing`
- `completion_last_progress_at`
- `completion_last_primary_evidence_at`
- `completion_last_secondary_evidence_at`
- `completion_timeout_deadline_at`
- `completion_reliability_reason`

### 7.3 Terminalization Rule

New hard rule:

- a managed pane-backed submission may not remain active indefinitely after `no_terminal_timeout_s` without valid primary authority

When that deadline is exceeded, the monitor must produce a terminal decision.
Provider-native cursor movement, polling timestamps, rescan offsets, and other
reader bookkeeping are not progress evidence and must not extend the deadline.
Only semantic evidence such as request anchor observation, assistant reply text,
terminal artifacts, or provider turn binding should refresh progress.
Session snapshot/rotation bookkeeping is observable state, but it is not
completion progress by itself.

Default degraded closure:

- `status = incomplete`
- `reason = completion_timeout`
- `confidence = degraded`

If a provider-specific secondary source supports extracting a best-effort reply safely, that reply may be attached with clear degraded diagnostics.

Running-job heartbeat is a separate no-progress guard:

- heartbeat observations remain internal diagnostics/events rather than caller-visible replies
- after three consecutive heartbeat intervals without progress, the job must terminalize once with `status = incomplete`, `reason = heartbeat_timeout`, and a caller-facing recommendation to send a small communication test before another large task
- a real terminal provider reply before that threshold remains the only normal caller-facing reply

## 8. New Boundary: Runtime Artifact Layout Contract

Provider launchers must no longer hand-roll runtime file names in multiple places.

Introduce one canonical artifact-layout helper per provider runtime.

### 8.1 Codex

Add a canonical helper such as:

- `codex_runtime_artifact_layout(runtime_dir)`

It must own all runtime paths:

- `input.fifo`
- `output.fifo`
- `bridge.pid`
- `bridge.stdout.log`
- `bridge.stderr.log`
- canonical bridge terminal log
- `completion/`

All of these must be consumed from that helper by:

- launcher payload builder
- bridge env builder
- bridge runtime state
- diagnostics renderers

String literals for these names must not be duplicated across modules.

### 8.2 Hook Providers

Add equivalent helpers for:

- `gemini`
- `claude`

The helper must own:

- `completion/`
- `completion/events/`
- optional auxiliary diagnostics files if introduced later

### 8.3 Boot Validation

Provider startup must assert declared artifacts exist immediately after launch preparation.

Failure mode must be:

- runtime launch degraded / failed

not:

- accept jobs and wait forever

## 9. New Boundary: Turn-Scoped Hook Evidence

Single-file terminal overwrite is too weak for hook-driven providers.

Replace the hook completion model with an append-oriented turn evidence model.

### 9.1 Current Weakness

Current file:

- `completion/events/<req_id>.json`

stores only the latest terminal interpretation.

That loses:

- whether the hook fired multiple times
- whether an empty-reply artifact arrived before a later real reply
- whether the artifact belonged to an auth/info turn versus the request answer turn

### 9.2 Target Model

Use an append-only per-request ledger, for example:

- `completion/events/<req_id>.jsonl`

Each record should include:

- `event_kind`
  - `hook_seen`
  - `hook_empty_reply`
  - `hook_failure`
  - `hook_completed`
  - `hook_cancelled`
- `req_id`
- `provider_turn_ref`
- `session_id`
- `session_path`
- `reply`
- `reply_text_present`
- `hook_event_name`
- `diagnostics`
- `timestamp`

The poller may still synthesize one terminal decision, but the authority read path must be able to distinguish:

- empty informational hook
- wrong-turn hook
- genuine answer completion

## 10. Provider-Specific Repair Plan

### 10.1 Codex

Codex does not need to be forced into the Gemini/Claude hook model.

Its design should remain:

- primary authority = protocol/session log

But reliability must be fixed in two places.

#### 10.1.1 Fix Runtime Layout Split

Current split:

- launcher/session payload uses `bridge_output.log`
- bridge runtime writes `bridge.log`

This must be unified by canonical layout helper.

Phase 1 chooses:

- canonical Codex bridge terminal log = `bridge.log`

Backward-compatible migration:

- choose one canonical file name
- optionally preserve the old name as a symlink or compatibility alias for one release cycle

#### 10.1.2 Create Declared Runtime Artifacts Up Front

Ensure startup explicitly creates:

- `completion/`
- canonical bridge log path
- other declared runtime files/directories

even if Codex completion does not primarily consume hook artifacts.

This keeps diagnostics and contract shape coherent.

#### 10.1.3 Add Bootstrap Self-Test

Immediately after bridge spawn, validate:

- bridge pid file exists
- bridge log path exists or is writable
- declared runtime artifacts exist

If not:

- mark startup degraded / failed
- do not accept async jobs silently

### 10.2 Gemini

Gemini currently has the most fragile turn attribution.

#### 10.2.1 Strengthen Req-ID Ownership

Hook processing must not infer `completed` merely from "some request id was present in prompt text".

Required conditions for exact completion:

- artifact req_id matches the active request anchor
- hook event is associated with the current provider turn
- reply is non-empty, or provider diagnostics explicitly declare a valid empty terminal turn

If these are not all true:

- do not emit exact `completed`
- record degraded hook evidence instead

#### 10.2.2 Empty Reply Must Not Burn The Job

Current `reply = "[no response text]"` style terminalization should be demoted unless positively proven valid.

Default rule:

- empty reply + no assistant-visible content = `incomplete`, not `completed`

#### 10.2.3 API Failure And Long-Thinking Need Closure

If Gemini shows:

- transport/API failure
- long-thinking stall
- hook absence beyond timeout

then the reliability monitor must terminalize with:

- `status = incomplete`
- `reason = completion_timeout` or `api_error`

depending on observed diagnostics

This must happen without requiring `ccb kill -f`.

### 10.3 Claude

Claude should adopt the same reliability plane as Gemini, even if the current public issue is narrower.

Required:

- same append-only hook evidence model
- same empty-terminal guard
- same timeout closure
- same diagnostics surface

Claude-specific session-boundary logic may still provide stronger observed completion than Gemini, but must no longer rely on hook exactness alone.

## 11. Placement In Code

### 11.1 Completion Manifest Layer

Add reliability manifest data near provider manifest / completion manifest definitions.

Likely modules:

- `lib/completion/`
- `lib/provider_core/`
- provider-specific `manifest.py`

### 11.2 Execution Layer

Add reliability monitor in provider execution service path.

Likely modules:

- `lib/provider_execution/service.py`
- `lib/provider_execution/service_runtime/`

This is the correct layer because it already owns:

- active submissions
- polling cadence
- persisted execution state

### 11.3 Provider-Specific Readers

Provider readers remain provider-owned.

Likely modules:

- `lib/provider_backends/codex/execution_runtime/`
- `lib/provider_backends/gemini/execution_runtime/`
- `lib/provider_backends/claude/execution_runtime/`
- `bin/ccb-provider-finish-hook`
- `lib/provider_hooks/artifacts_runtime/`

### 11.4 Diagnostics Layer

Expose reliability state in:

- `ccb ping <agent>`
- `ccb doctor`
- support bundle artifacts

Useful fields:

- `completion_primary_authority`
- `completion_primary_state`
- `completion_bootstrap_state`
- `completion_last_progress_at`
- `completion_timeout_deadline_at`
- `completion_reliability_reason`
- `completion_fallback_source`

## 12. Testing Strategy

### 12.1 Codex

Add tests for:

- canonical runtime artifact layout is consistent across launcher / bridge / session payload
- declared `completion/` and bridge log path exist after startup
- startup fails clearly if canonical artifact path cannot be provisioned

### 12.2 Gemini

Add tests for:

- hook event with wrong `req_id` does not terminalize another job
- empty reply hook produces degraded / incomplete, not completed
- no hook after API failure converges to timeout terminal decision
- long-thinking without hook converges to timeout terminal decision

### 12.3 Claude

Add tests for:

- empty hook reply does not burn job
- session-boundary and hook evidence merge correctly
- timeout closure works when hook never arrives

### 12.4 Cross-Provider Reliability

Add execution-layer tests for:

- active job cannot remain `running` forever without primary completion evidence
- reliability timeout is provider-manifest-driven
- degraded fallback decision is persisted and restorable

## 13. Rollout Phases

### Phase 1

- introduce document and reliability boundary
- fix Codex runtime artifact layout split
- add bootstrap assertions for declared runtime artifacts

### Phase 2

- add reliability manifest and execution-layer monitor
- add no-terminal timeout closure

### Phase 3

- migrate Gemini / Claude hook artifacts from one-shot terminal file to append-oriented evidence
- strengthen req-id / turn attribution

### Phase 4

- expose diagnostics
- run macOS end-to-end validation

## 14. Immediate Design Conclusions

The correct architectural reading of issues `#180` and `#181` is:

- they are not identical provider bugs
- they are the same reliability-class bug

More precisely:

```text
#180 = runtime artifact contract split
#181 = hook-turn attribution and no-terminal-timeout gap
shared parent = missing managed-provider completion reliability plane
```

Therefore the repair plan must not be:

- "patch Codex log filename here"
- "patch Gemini hook parser there"
- "add one more mac-only timeout in CLI"

The repair plan must be:

- define one reliability contract
- validate runtime artifacts at launch
- preserve provider-specific completion families
- add one control-plane-owned timeout closure path
- make hook evidence turn-scoped instead of blindly terminal

## 15. Callback Ask Continuations

Nested synchronous `ask` is not a supported completion model. When agent A is
running an active mailbox request, a normal child ask to agent B can complete
and queue a `TASK_REPLY` back to A, but that reply cannot be delivered while
A's active request is still the mailbox head. Agents must not wait or poll for
that child reply inside the same turn.

`ccb ask --callback <target>` provides the stable handoff for this case:

- it is valid only from an agent that currently owns an active parent job
- the child request is recorded with a durable callback edge
- the parent job may complete as delegated and suppress normal reply delivery
- the parent message remains open until a continuation attempt produces the
  final reply
- the child result is recorded as a `ReplyRecord` but is not delivered as a
  normal `TASK_REPLY` to the parent agent
- when the child logical message reaches a terminal reply, CCB submits a normal
  `callback_continuation` `TASK_REQUEST` back to the parent agent
- the continuation uses the original caller as `from_actor`, preserving the
  normal final reply routing path

While an agent owns an active parent job, CCB rejects plain nested `ask`
submissions unless they are explicitly `--callback` or `--silence`. This guard
keeps accidental nested dependencies from completing into an undeliverable
`TASK_REPLY`; `--callback` is for needed child results, and `--silence` is for
independent no-result-needed work.

The first supported callback model is intentionally narrow:

- one outstanding callback child per parent job
- no inline provider-pane injection
- no mailbox FIFO bypass
- no fan-out / fan-in aggregation
- nested callback chains are supported because each level is a normal
  delegated parent plus later continuation

Durability is owned by callback edge records under the ccbd mailbox state. A
callback edge records the parent job/message, child job/message, original
caller, callback target, child reply id/status, continuation job/message, and
state. Dispatcher maintenance must repair the crash window where the child
reply was recorded and the continuation was not yet submitted. Repair is
idempotent: an edge with an existing continuation job is not submitted again.

Callback edge state is also the backend safety boundary for nested delegation.
Edges must carry a timeout deadline, and dispatcher maintenance must transition
expired pending edges to a terminal timeout state, persist a failed reply on the
parent message, and deliver that failure to the original caller when the caller
owns a mailbox. Callback submission must enforce a bounded chain depth and
reject actor cycles before creating the child job. If continuation submission
fails after the child has completed, the edge must transition to a terminal
failed state and the parent message must not remain indefinitely running.

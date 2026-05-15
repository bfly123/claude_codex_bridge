from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from agents.models import (
    AgentRuntime,
    AgentSpec,
    AgentState,
    PermissionMode,
    ProjectConfig,
    QueuePolicy,
    RestoreMode,
    RuntimeMode,
    WorkspaceMode,
)
from ccbd.api_models import DeliveryScope, JobStatus, MessageEnvelope
from ccbd.services.dispatcher import JobDispatcher
from ccbd.services.dispatcher_runtime.reply_delivery import prepare_reply_deliveries
from ccbd.services.job_heartbeat import JobHeartbeatService
from ccbd.services.registry import AgentRegistry
from completion.models import (
    CompletionConfidence,
    CompletionCursor,
    CompletionDecision,
    CompletionItem,
    CompletionItemKind,
    CompletionSourceKind,
    CompletionStatus,
)
from completion.tracker import CompletionTrackerService
from heartbeat import HeartbeatPolicy, HeartbeatStateStore
from mailbox_kernel import (
    InboundEventRecord,
    InboundEventStatus,
    InboundEventStore,
    InboundEventType,
    MailboxState,
    MailboxStore,
)
from message_bureau import AttemptState, AttemptStore, MessageState, MessageStore, ReplyStore, ReplyTerminalStatus
from message_bureau.reply_payloads import delivery_job_id_from_payload
from project.ids import compute_project_id
from project.resolver import ProjectContext
from provider_core.catalog import build_default_provider_catalog
from provider_execution.base import ProviderSubmission
from provider_execution.registry import build_default_execution_registry
from provider_execution.service import ExecutionService
from provider_execution.service_runtime.models import ExecutionUpdate
from storage.paths import PathLayout


def _bootstrap_test_project(project_root: Path) -> ProjectContext:
    project_root.mkdir()
    config_dir = project_root / '.ccb'
    config_dir.mkdir(exist_ok=True)
    (config_dir / 'ccb.config').write_text('cmd; demo:fake\n', encoding='utf-8')
    return ProjectContext(
        cwd=project_root,
        project_root=project_root,
        config_dir=config_dir,
        project_id=compute_project_id(project_root),
        source='test',
    )


def _runtime(agent_name: str, *, project_id: str, layout: PathLayout, pid: int) -> AgentRuntime:
    return AgentRuntime(
        agent_name=agent_name,
        state=AgentState.IDLE,
        pid=pid,
        started_at='2026-03-30T00:00:00Z',
        last_seen_at='2026-03-30T00:00:00Z',
        runtime_ref=f'{agent_name}-runtime',
        session_ref=f'{agent_name}-session',
        workspace_path=str(layout.workspace_path(agent_name)),
        project_id=project_id,
        backend_type='tmux',
        queue_depth=0,
        socket_path=None,
        health='healthy',
    )


def _decision(*, status: CompletionStatus = CompletionStatus.COMPLETED, reply: str = 'done') -> CompletionDecision:
    return CompletionDecision(
        terminal=True,
        status=status,
        reason='task_complete' if status is CompletionStatus.COMPLETED else status.value,
        confidence=CompletionConfidence.EXACT,
        reply=reply,
        anchor_seen=True,
        reply_started=True,
        reply_stable=True,
        provider_turn_ref='turn-1',
        source_cursor=None,
        finished_at='2026-03-30T00:00:10Z',
        diagnostics={},
    )


def _failed_decision(*, reason: str = 'api_error', diagnostics: dict[str, object] | None = None) -> CompletionDecision:
    payload = dict(diagnostics or {})
    if reason == 'api_error' and 'error_type' not in payload:
        payload['error_type'] = 'provider_api_error'
    return CompletionDecision(
        terminal=True,
        status=CompletionStatus.FAILED,
        reason=reason,
        confidence=CompletionConfidence.OBSERVED,
        reply='',
        anchor_seen=True,
        reply_started=False,
        reply_stable=False,
        provider_turn_ref='turn-failed',
        source_cursor=None,
        finished_at='2026-03-30T00:00:10Z',
        diagnostics=payload,
    )


class ActiveReplyDeliveryExecutionService:
    def __init__(self) -> None:
        self.started: list[str] = []
        self.finished: list[str] = []
        self._state_store = None

    def start(self, job, *, runtime_context=None):
        del runtime_context
        self.started.append(job.job_id)
        return ProviderSubmission(
            job_id=job.job_id,
            agent_name=job.agent_name,
            provider=job.provider,
            accepted_at='2026-03-30T00:00:00Z',
            ready_at='2026-03-30T00:00:00Z',
            source_kind=CompletionSourceKind.SESSION_EVENT_LOG,
            reply='',
            diagnostics={'provider': job.provider, 'mode': 'active'},
            runtime_state={'mode': 'active', 'request_anchor': job.job_id},
        )

    def cancel(self, job_id: str) -> None:
        del job_id

    def finish(self, job_id: str) -> None:
        self.finished.append(job_id)

    def poll(self):
        return ()


class DeferredReplyDeliveryExecutionService:
    def __init__(self) -> None:
        self.started: list[str] = []
        self.finished: list[str] = []
        self._state_store = None
        self._active: dict[str, ProviderSubmission] = {}
        self._pending_replays: dict[str, tuple] = {}

    def start(self, job, *, runtime_context=None):
        del runtime_context
        self.started.append(job.job_id)
        submission = ProviderSubmission(
            job_id=job.job_id,
            agent_name=job.agent_name,
            provider=job.provider,
            accepted_at='2026-03-30T00:00:00Z',
            ready_at='2026-03-30T00:00:00Z',
            source_kind=CompletionSourceKind.SESSION_EVENT_LOG,
            reply='',
            diagnostics={'provider': job.provider, 'mode': 'active'},
            runtime_state={
                'mode': 'active',
                'request_anchor': job.job_id,
                'reply_delivery_complete_on_dispatch': True,
                'prompt_sent': False,
            },
        )
        self._active[job.job_id] = submission
        return submission

    def cancel(self, job_id: str) -> None:
        self._active.pop(job_id, None)

    def finish(self, job_id: str) -> None:
        self.finished.append(job_id)
        self._active.pop(job_id, None)

    def poll(self):
        return ()


def _provider_config(*providers: str) -> ProjectConfig:
    agents: dict[str, AgentSpec] = {}
    for provider in providers:
        agents[provider] = AgentSpec(
            name=provider,
            provider=provider,
            target='.',
            workspace_mode=WorkspaceMode.GIT_WORKTREE,
            workspace_root=None,
            runtime_mode=RuntimeMode.PANE_BACKED,
            restore_default=RestoreMode.AUTO,
            permission_default=PermissionMode.MANUAL,
            queue_policy=QueuePolicy.SERIAL_PER_AGENT,
        )
    return ProjectConfig(version=2, default_agents=tuple(providers), agents=agents, cmd_enabled=True)


def test_dispatcher_mirrors_single_job_into_message_bureau_records(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-bureau'
    ctx = _bootstrap_test_project(project_root)
    layout = PathLayout(project_root)
    base_config = _provider_config('codex', 'claude', 'gemini')
    config = ProjectConfig(
        version=base_config.version,
        default_agents=base_config.default_agents,
        agents={
            **base_config.agents,
            'gemini': AgentSpec(
                name='gemini',
                provider='gemini',
                target='.',
                workspace_mode=WorkspaceMode.GIT_WORKTREE,
                workspace_root=None,
                runtime_mode=RuntimeMode.PANE_BACKED,
                restore_default=RestoreMode.AUTO,
                permission_default=PermissionMode.MANUAL,
                queue_policy=QueuePolicy.SERIAL_PER_AGENT,
            ),
        },
        cmd_enabled=base_config.cmd_enabled,
    )
    registry = AgentRegistry(layout, config)
    registry.upsert(_runtime('codex', project_id=ctx.project_id, layout=layout, pid=101))
    dispatcher = JobDispatcher(layout, config, registry, clock=lambda: '2026-03-30T00:00:00Z')

    receipt = dispatcher.submit(
        MessageEnvelope(
            project_id=ctx.project_id,
            to_agent='codex',
            from_actor='user',
            body='hello',
            task_id='task-1',
            reply_to=None,
            message_type='ask',
            delivery_scope=DeliveryScope.SINGLE,
        )
    )
    job_id = receipt.jobs[0].job_id
    dispatcher.tick()
    dispatcher.complete(job_id, _decision())

    message_store = MessageStore(layout)
    attempt_store = AttemptStore(layout)
    reply_store = ReplyStore(layout)
    inbox_store = InboundEventStore(layout)
    mailbox_store = MailboxStore(layout)

    message = message_store.list_all()[-1]
    assert message.target_agents == ('codex',)
    assert message.message_state is MessageState.COMPLETED

    attempt = attempt_store.get_latest_by_job_id(job_id)
    assert attempt is not None
    assert attempt.attempt_state is AttemptState.COMPLETED

    replies = reply_store.list_message(message.message_id)
    assert len(replies) == 1
    assert replies[0].terminal_status is ReplyTerminalStatus.COMPLETED
    assert replies[0].reply == 'done'

    inbound = inbox_store.get_latest_for_attempt('codex', attempt.attempt_id)
    assert inbound is not None
    assert inbound.event_type is InboundEventType.TASK_REQUEST
    assert inbound.status is InboundEventStatus.CONSUMED

    mailbox = mailbox_store.load('codex')
    assert mailbox is not None
    assert mailbox.mailbox_state is MailboxState.IDLE
    assert mailbox.queue_depth == 0
    assert mailbox.pending_reply_count == 0


def test_dispatcher_routes_reply_into_registered_caller_mailbox(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-registered-caller'
    ctx = _bootstrap_test_project(project_root)
    layout = PathLayout(project_root)
    config = _provider_config('codex', 'claude', 'gemini')
    registry = AgentRegistry(layout, config)
    registry.upsert(_runtime('codex', project_id=ctx.project_id, layout=layout, pid=101))
    registry.upsert(_runtime('claude', project_id=ctx.project_id, layout=layout, pid=102))
    dispatcher = JobDispatcher(layout, config, registry, clock=lambda: '2026-03-30T00:00:00Z')

    receipt = dispatcher.submit(
        MessageEnvelope(
            project_id=ctx.project_id,
            to_agent='codex',
            from_actor='Claude',
            body='hello',
            task_id='task-2',
            reply_to=None,
            message_type='ask',
            delivery_scope=DeliveryScope.SINGLE,
        )
    )
    job_id = receipt.jobs[0].job_id
    dispatcher.tick()
    dispatcher.complete(job_id, _decision(reply='done from codex'))

    message = MessageStore(layout).list_all()[-1]
    replies = ReplyStore(layout).list_message(message.message_id)
    assert len(replies) == 1
    assert replies[0].agent_name == 'codex'

    inbox_store = InboundEventStore(layout)
    claude_events = inbox_store.list_agent('claude')
    assert len(claude_events) == 1
    assert claude_events[0].event_type is InboundEventType.TASK_REPLY
    assert claude_events[0].status is InboundEventStatus.QUEUED

    mailbox = MailboxStore(layout).load('claude')
    assert mailbox is not None
    assert mailbox.mailbox_state is MailboxState.BLOCKED
    assert mailbox.queue_depth == 1
    assert mailbox.pending_reply_count == 1
    queue_summary = dispatcher.queue('claude')
    assert queue_summary['target'] == 'claude'
    assert queue_summary['agent']['queue_depth'] == 1
    assert queue_summary['agent']['pending_reply_count'] == 1
    assert 'queued_events' not in queue_summary['agent']


def test_dispatcher_silence_hides_success_reply_body_for_caller_mailbox(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-silence-success'
    ctx = _bootstrap_test_project(project_root)
    layout = PathLayout(project_root)
    config = _provider_config('codex', 'claude')
    registry = AgentRegistry(layout, config)
    registry.upsert(_runtime('codex', project_id=ctx.project_id, layout=layout, pid=101))
    registry.upsert(_runtime('claude', project_id=ctx.project_id, layout=layout, pid=102))
    dispatcher = JobDispatcher(layout, config, registry, clock=lambda: '2026-03-30T00:00:00Z')

    receipt = dispatcher.submit(
        MessageEnvelope(
            project_id=ctx.project_id,
            to_agent='codex',
            from_actor='claude',
            body='hello',
            task_id='task-silent',
            reply_to=None,
            message_type='ask',
            delivery_scope=DeliveryScope.SINGLE,
            silence_on_success=True,
        )
    )
    job_id = receipt.jobs[0].job_id
    dispatcher.tick()
    dispatcher.complete(job_id, _decision(reply='done from codex'))

    message = MessageStore(layout).list_all()[-1]
    replies = ReplyStore(layout).list_message(message.message_id)
    assert len(replies) == 1
    assert replies[0].terminal_status is ReplyTerminalStatus.COMPLETED
    assert replies[0].reply == (
        'CCB_COMPLETE from=codex status=completed job='
        f'{job_id} task=task-silent result=hidden'
    )
    assert replies[0].diagnostics.get('silence_on_success') is True


def test_dispatcher_silence_does_not_hide_failure_reply_body(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-silence-failure'
    ctx = _bootstrap_test_project(project_root)
    layout = PathLayout(project_root)
    config = _provider_config('codex', 'claude')
    registry = AgentRegistry(layout, config)
    registry.upsert(_runtime('codex', project_id=ctx.project_id, layout=layout, pid=101))
    registry.upsert(_runtime('claude', project_id=ctx.project_id, layout=layout, pid=102))
    dispatcher = JobDispatcher(layout, config, registry, clock=lambda: '2026-03-30T00:00:00Z')

    receipt = dispatcher.submit(
        MessageEnvelope(
            project_id=ctx.project_id,
            to_agent='codex',
            from_actor='claude',
            body='hello',
            task_id='task-silent-fail',
            reply_to=None,
            message_type='ask',
            delivery_scope=DeliveryScope.SINGLE,
            silence_on_success=True,
        )
    )
    job_id = receipt.jobs[0].job_id
    dispatcher.tick()
    dispatcher.complete(
        job_id,
        replace(
            _failed_decision(
                reason='api_error',
                diagnostics={
                    'error_type': 'provider_api_error',
                    'error_code': 'unauthorized',
                    'error_message': 'login required',
                },
            ),
            reply='raw failure body',
        ),
    )

    message = MessageStore(layout).list_all()[-1]
    replies = ReplyStore(layout).list_message(message.message_id)
    assert len(replies) == 1
    assert replies[0].terminal_status is ReplyTerminalStatus.FAILED
    assert replies[0].reply
    assert 'result=hidden' not in replies[0].reply
    assert replies[0].diagnostics.get('silence_on_success') is True


def test_dispatcher_rejects_cmd_sender(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-cmd-caller'
    ctx = _bootstrap_test_project(project_root)
    layout = PathLayout(project_root)
    config = _provider_config('codex', 'claude', 'gemini')
    registry = AgentRegistry(layout, config)
    registry.upsert(_runtime('codex', project_id=ctx.project_id, layout=layout, pid=101))
    dispatcher = JobDispatcher(layout, config, registry, clock=lambda: '2026-03-30T00:00:00Z')

    with pytest.raises(Exception, match='unknown sender agent: cmd'):
        dispatcher.submit(
            MessageEnvelope(
                project_id=ctx.project_id,
                to_agent='codex',
                from_actor='cmd',
                body='hello from cmd',
                task_id='task-cmd-1',
                reply_to=None,
                message_type='ask',
                delivery_scope=DeliveryScope.SINGLE,
            )
        )


def test_dispatcher_queue_summary_reflects_mailbox_state_and_pending_reply(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-queue-summary'
    ctx = _bootstrap_test_project(project_root)
    layout = PathLayout(project_root)
    config = _provider_config('codex', 'claude', 'gemini')
    registry = AgentRegistry(layout, config)
    registry.upsert(_runtime('codex', project_id=ctx.project_id, layout=layout, pid=101))
    registry.upsert(_runtime('claude', project_id=ctx.project_id, layout=layout, pid=102))
    dispatcher = JobDispatcher(layout, config, registry, clock=lambda: '2026-03-30T00:00:00Z')

    receipt = dispatcher.submit(
        MessageEnvelope(
            project_id=ctx.project_id,
            to_agent='codex',
            from_actor='claude',
            body='hello',
            task_id='task-3',
            reply_to=None,
            message_type='ask',
            delivery_scope=DeliveryScope.SINGLE,
        )
    )
    job_id = receipt.jobs[0].job_id
    dispatcher.tick()

    queue_running = dispatcher.queue('codex', detail=True)
    agent_running = queue_running['agent']
    assert agent_running['agent_name'] == 'codex'
    assert agent_running['mailbox_state'] == 'delivering'
    assert agent_running['runtime_state'] == 'busy'
    assert agent_running['runtime_health'] == 'healthy'
    assert agent_running['queue_depth'] == 1
    assert agent_running['active']['job_id'] == job_id
    assert agent_running['active']['event_type'] == 'task_request'

    dispatcher.complete(job_id, _decision(reply='reply for claude'))

    queue_reply = dispatcher.queue('claude', detail=True)
    agent_reply = queue_reply['agent']
    assert agent_reply['agent_name'] == 'claude'
    assert agent_reply['mailbox_state'] == 'blocked'
    assert agent_reply['runtime_state'] == 'idle'
    assert agent_reply['runtime_health'] == 'healthy'
    assert agent_reply['queue_depth'] == 1
    assert agent_reply['pending_reply_count'] == 1
    assert agent_reply['queued_events'][0]['event_type'] == 'task_reply'

    queue_all = dispatcher.queue('all')
    assert queue_all['target'] == 'all'
    assert queue_all['total_queue_depth'] == 1
    assert queue_all['queued_agent_count'] == 1
    assert {item['runtime_state'] for item in queue_all['agents']} == {'idle', 'stopped'}
    assert {item['runtime_health'] for item in queue_all['agents']} == {'healthy', 'stopped'}


def test_dispatcher_queue_summary_ignores_stale_cmd_mailbox_residue(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-cmd-queue-summary'
    ctx = _bootstrap_test_project(project_root)
    layout = PathLayout(project_root)
    config = _provider_config('codex', 'claude', 'gemini')
    registry = AgentRegistry(layout, config)
    registry.upsert(_runtime('codex', project_id=ctx.project_id, layout=layout, pid=101))
    dispatcher = JobDispatcher(layout, config, registry, clock=lambda: '2026-03-30T00:00:00Z')

    stale_mailbox_path = layout.ccbd_mailboxes_dir / 'cmd' / 'mailbox.json'
    stale_mailbox_path.parent.mkdir(parents=True, exist_ok=True)
    stale_mailbox_path.write_text(
        json.dumps(
            {
                'schema_version': 1,
                'record_type': 'mailbox_record',
                'mailbox_id': 'mbx_cmd',
                'agent_name': 'cmd',
                'active_inbound_event_id': 'iev_cmd',
                'queue_depth': 1,
                'pending_reply_count': 1,
                'last_inbound_started_at': None,
                'last_inbound_finished_at': None,
                'mailbox_state': 'blocked',
                'lease_version': 1,
                'updated_at': '2026-03-30T00:00:00Z',
            }
        ),
        encoding='utf-8',
    )
    stale_inbox_path = layout.ccbd_mailboxes_dir / 'cmd' / 'inbox.jsonl'
    stale_inbox_path.parent.mkdir(parents=True, exist_ok=True)
    stale_inbox_path.write_text(
        json.dumps(
            {
                'schema_version': 1,
                'record_type': 'inbound_event_record',
                'inbound_event_id': 'iev_cmd',
                'agent_name': 'cmd',
                'event_type': 'task_reply',
                'message_id': 'msg_cmd',
                'attempt_id': 'att_cmd',
                'payload_ref': 'reply:rep_cmd',
                'priority': 10,
                'status': 'queued',
                'created_at': '2026-03-30T00:00:00Z',
                'started_at': None,
                'finished_at': None,
            }
        )
        + '\n',
        encoding='utf-8',
    )

    with pytest.raises(ValueError, match='unknown mailbox target: cmd'):
        dispatcher.queue('cmd')

    queue_all = dispatcher.queue('all')
    assert {item['agent_name'] for item in queue_all['agents']} == {'claude', 'codex', 'gemini'}


def test_dispatcher_trace_submission_returns_message_attempt_reply_job_chain(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-trace-submission'
    ctx = _bootstrap_test_project(project_root)
    layout = PathLayout(project_root)
    config = _provider_config('codex', 'claude', 'gemini')
    registry = AgentRegistry(layout, config)
    registry.upsert(_runtime('codex', project_id=ctx.project_id, layout=layout, pid=101))
    registry.upsert(_runtime('claude', project_id=ctx.project_id, layout=layout, pid=102))
    dispatcher = JobDispatcher(layout, config, registry, clock=lambda: '2026-03-30T00:00:00Z')

    receipt = dispatcher.submit(
        MessageEnvelope(
            project_id=ctx.project_id,
            to_agent='all',
            from_actor='user',
            body='hello everyone',
            task_id='task-trace-sub',
            reply_to=None,
            message_type='ask',
            delivery_scope=DeliveryScope.BROADCAST,
        )
    )
    assert receipt.submission_id is not None

    dispatcher.tick()
    for accepted in receipt.jobs:
        dispatcher.complete(accepted.job_id, _decision(reply=f'done for {accepted.agent_name}'))

    payload = dispatcher.trace(receipt.submission_id)

    assert payload['target'] == receipt.submission_id
    assert payload['resolved_kind'] == 'submission'
    assert payload['submission_id'] == receipt.submission_id
    assert payload['message_count'] == 1
    assert payload['attempt_count'] == 2
    assert payload['reply_count'] == 2
    assert payload['event_count'] == 2
    assert payload['job_count'] == 2
    assert payload['messages'][0]['target_agents'] == ['claude', 'codex']
    assert {item['job_id'] for item in payload['attempts']} == {job.job_id for job in receipt.jobs}
    assert {item['terminal_status'] for item in payload['replies']} == {'completed'}
    assert {item['event_type'] for item in payload['events']} == {'task_request'}
    assert {item['agent_name'] for item in payload['jobs']} == {'claude', 'codex'}


def test_dispatcher_resubmit_creates_new_message_with_origin_lineage(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-resubmit-lineage'
    ctx = _bootstrap_test_project(project_root)
    layout = PathLayout(project_root)
    config = _provider_config('codex', 'claude', 'gemini')
    registry = AgentRegistry(layout, config)
    registry.upsert(_runtime('codex', project_id=ctx.project_id, layout=layout, pid=101))
    dispatcher = JobDispatcher(layout, config, registry, clock=lambda: '2026-03-30T00:00:00Z')

    receipt = dispatcher.submit(
        MessageEnvelope(
            project_id=ctx.project_id,
            to_agent='codex',
            from_actor='user',
            body='hello',
            task_id='task-resubmit',
            reply_to=None,
            message_type='ask',
            delivery_scope=DeliveryScope.SINGLE,
        )
    )
    original_job_id = receipt.jobs[0].job_id
    dispatcher.tick()
    dispatcher.complete(original_job_id, _decision(status=CompletionStatus.INCOMPLETE, reply='need retry'))

    original_message = MessageStore(layout).list_all()[-1]
    payload = dispatcher.resubmit(original_message.message_id)

    assert payload['original_message_id'] == original_message.message_id
    assert str(payload['message_id']).startswith('msg_')
    assert payload['message_id'] != original_message.message_id
    assert len(payload['jobs']) == 1
    assert payload['jobs'][0]['agent_name'] == 'codex'

    new_message = MessageStore(layout).get_latest(payload['message_id'])
    assert new_message is not None
    assert new_message.origin_message_id == original_message.message_id
    assert new_message.message_state is MessageState.QUEUED

    attempts = AttemptStore(layout).list_message(payload['message_id'])
    assert len(attempts) == 1
    assert attempts[0].retry_index == 0
    assert attempts[0].attempt_state is AttemptState.PENDING

    codex_events = InboundEventStore(layout).list_agent('codex')
    assert codex_events[-1].message_id == payload['message_id']
    assert codex_events[-1].event_type is InboundEventType.TASK_REQUEST
    assert codex_events[-1].status is InboundEventStatus.QUEUED


def test_dispatcher_resubmit_rejects_message_with_active_attempts(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-resubmit-active'
    ctx = _bootstrap_test_project(project_root)
    layout = PathLayout(project_root)
    config = _provider_config('codex', 'claude', 'gemini')
    registry = AgentRegistry(layout, config)
    registry.upsert(_runtime('codex', project_id=ctx.project_id, layout=layout, pid=101))
    dispatcher = JobDispatcher(layout, config, registry, clock=lambda: '2026-03-30T00:00:00Z')

    receipt = dispatcher.submit(
        MessageEnvelope(
            project_id=ctx.project_id,
            to_agent='codex',
            from_actor='user',
            body='hello',
            task_id='task-resubmit-active',
            reply_to=None,
            message_type='ask',
            delivery_scope=DeliveryScope.SINGLE,
        )
    )
    dispatcher.tick()
    original_message = MessageStore(layout).list_all()[-1]

    try:
        dispatcher.resubmit(original_message.message_id)
    except Exception as exc:
        assert 'active attempts' in str(exc)
    else:
        raise AssertionError('expected resubmit to reject active attempts')


def test_dispatcher_retry_creates_new_attempt_under_same_message(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-retry-lineage'
    ctx = _bootstrap_test_project(project_root)
    layout = PathLayout(project_root)
    config = _provider_config('codex', 'claude', 'gemini')
    registry = AgentRegistry(layout, config)
    registry.upsert(_runtime('codex', project_id=ctx.project_id, layout=layout, pid=101))
    dispatcher = JobDispatcher(layout, config, registry, clock=lambda: '2026-03-30T00:00:00Z')

    receipt = dispatcher.submit(
        MessageEnvelope(
            project_id=ctx.project_id,
            to_agent='codex',
            from_actor='user',
            body='hello',
            task_id='task-retry',
            reply_to=None,
            message_type='ask',
            delivery_scope=DeliveryScope.SINGLE,
        )
    )
    original_job_id = receipt.jobs[0].job_id
    dispatcher.tick()
    dispatcher.complete(original_job_id, _decision(status=CompletionStatus.INCOMPLETE, reply='need retry'))

    original_attempt = AttemptStore(layout).get_latest_by_job_id(original_job_id)
    assert original_attempt is not None

    payload = dispatcher.retry(original_job_id)

    assert payload['target'] == original_job_id
    assert payload['message_id'] == original_attempt.message_id
    assert payload['original_attempt_id'] == original_attempt.attempt_id
    assert str(payload['attempt_id']).startswith('att_')
    assert payload['attempt_id'] != original_attempt.attempt_id
    assert str(payload['job_id']).startswith('job_')
    assert payload['job_id'] != original_job_id
    assert payload['agent_name'] == 'codex'
    assert payload['status'] == 'accepted'

    message = MessageStore(layout).get_latest(original_attempt.message_id)
    assert message is not None
    assert message.message_state is MessageState.QUEUED

    attempts = AttemptStore(layout).list_message(original_attempt.message_id)
    assert len(attempts) == 4
    latest_attempt = AttemptStore(layout).get_latest(payload['attempt_id'])
    assert latest_attempt is not None
    assert latest_attempt.retry_index == 1
    assert latest_attempt.attempt_state is AttemptState.PENDING
    assert latest_attempt.job_id == payload['job_id']

    codex_events = InboundEventStore(layout).list_agent('codex')
    assert codex_events[-1].message_id == original_attempt.message_id
    assert codex_events[-1].attempt_id == payload['attempt_id']
    assert codex_events[-1].event_type is InboundEventType.TASK_REQUEST
    assert codex_events[-1].status is InboundEventStatus.QUEUED


def test_dispatcher_retry_rejects_completed_attempt(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-retry-completed'
    ctx = _bootstrap_test_project(project_root)
    layout = PathLayout(project_root)
    config = _provider_config('codex', 'claude', 'gemini')
    registry = AgentRegistry(layout, config)
    registry.upsert(_runtime('codex', project_id=ctx.project_id, layout=layout, pid=101))
    dispatcher = JobDispatcher(layout, config, registry, clock=lambda: '2026-03-30T00:00:00Z')

    receipt = dispatcher.submit(
        MessageEnvelope(
            project_id=ctx.project_id,
            to_agent='codex',
            from_actor='user',
            body='hello',
            task_id='task-retry-completed',
            reply_to=None,
            message_type='ask',
            delivery_scope=DeliveryScope.SINGLE,
        )
    )
    job_id = receipt.jobs[0].job_id
    dispatcher.tick()
    dispatcher.complete(job_id, _decision(status=CompletionStatus.COMPLETED, reply='done'))

    try:
        dispatcher.retry(job_id)
    except Exception as exc:
        assert 'completed attempts' in str(exc)
    else:
        raise AssertionError('expected retry to reject completed attempt')


def test_dispatcher_auto_retries_retryable_api_failures_before_delivering_failed_reply(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-auto-retry-api'
    ctx = _bootstrap_test_project(project_root)
    layout = PathLayout(project_root)
    config = _provider_config('codex', 'claude', 'gemini')
    registry = AgentRegistry(layout, config)
    registry.upsert(_runtime('codex', project_id=ctx.project_id, layout=layout, pid=101))
    registry.upsert(_runtime('claude', project_id=ctx.project_id, layout=layout, pid=102))
    dispatcher = JobDispatcher(layout, config, registry, clock=lambda: '2026-03-30T00:00:00Z')

    receipt = dispatcher.submit(
        MessageEnvelope(
            project_id=ctx.project_id,
            to_agent='codex',
            from_actor='claude',
            body='retryable api failure test',
            task_id='task-auto-retry-api',
            reply_to=None,
            message_type='ask',
            delivery_scope=DeliveryScope.SINGLE,
        )
    )
    message = MessageStore(layout).list_all()[-1]
    job_id = receipt.jobs[0].job_id

    for expected_retry_index in (1, 2):
        dispatcher.tick()
        dispatcher.complete(job_id, _failed_decision())

        claude_inbox = dispatcher.inbox('claude')
        assert claude_inbox['item_count'] == 0

        latest_attempts = {}
        for record in AttemptStore(layout).list_message(message.message_id):
            latest_attempts[record.attempt_id] = record
        pending_retry = next(
            attempt
            for attempt in latest_attempts.values()
            if attempt.retry_index == expected_retry_index and attempt.attempt_state is AttemptState.PENDING
        )
        job_id = pending_retry.job_id

    dispatcher.tick()
    dispatcher.complete(job_id, _failed_decision())

    claude_inbox = dispatcher.inbox('claude')
    assert claude_inbox['item_count'] == 1
    assert claude_inbox['head']['event_type'] == 'task_reply'

    latest_attempts = {}
    for record in AttemptStore(layout).list_message(message.message_id):
        latest_attempts[record.attempt_id] = record
    assert len(latest_attempts) == 3
    assert {attempt.retry_index for attempt in latest_attempts.values()} == {0, 1, 2}
    assert {attempt.attempt_state for attempt in latest_attempts.values()} == {AttemptState.FAILED}

    replies = ReplyStore(layout).list_message(message.message_id)
    assert len(replies) == 1
    assert replies[0].terminal_status is ReplyTerminalStatus.FAILED
    assert 'failed after 3 attempts' in replies[0].reply
    assert 'another healthy registered agent' in replies[0].reply

    ack = dispatcher.ack_reply('claude')
    assert ack['reply_terminal_status'] == 'failed'
    assert 'failed after 3 attempts' in ack['reply']


def test_dispatcher_auto_retries_resumable_pane_failures_before_delivering_failed_reply(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-auto-retry-runtime-pane'
    ctx = _bootstrap_test_project(project_root)
    layout = PathLayout(project_root)
    config = _provider_config('codex', 'claude', 'gemini')
    registry = AgentRegistry(layout, config)
    registry.upsert(_runtime('codex', project_id=ctx.project_id, layout=layout, pid=101))
    registry.upsert(_runtime('claude', project_id=ctx.project_id, layout=layout, pid=102))
    dispatcher = JobDispatcher(layout, config, registry, clock=lambda: '2026-03-30T00:00:00Z')

    receipt = dispatcher.submit(
        MessageEnvelope(
            project_id=ctx.project_id,
            to_agent='codex',
            from_actor='claude',
            body='retryable pane failure test',
            task_id='task-auto-retry-pane',
            reply_to=None,
            message_type='ask',
            delivery_scope=DeliveryScope.SINGLE,
        )
    )
    message = MessageStore(layout).list_all()[-1]
    job_id = receipt.jobs[0].job_id

    for expected_retry_index in (1, 2):
        dispatcher.tick()
        dispatcher.complete(job_id, _failed_decision(reason='pane_dead'))

        claude_inbox = dispatcher.inbox('claude')
        assert claude_inbox['item_count'] == 0

        latest_attempts = {}
        for record in AttemptStore(layout).list_message(message.message_id):
            latest_attempts[record.attempt_id] = record
        pending_retry = next(
            attempt
            for attempt in latest_attempts.values()
            if attempt.retry_index == expected_retry_index and attempt.attempt_state is AttemptState.PENDING
        )
        job_id = pending_retry.job_id

    dispatcher.tick()
    dispatcher.complete(job_id, _failed_decision(reason='pane_dead'))

    claude_inbox = dispatcher.inbox('claude')
    assert claude_inbox['item_count'] == 1
    assert claude_inbox['head']['event_type'] == 'task_reply'

    latest_attempts = {}
    for record in AttemptStore(layout).list_message(message.message_id):
        latest_attempts[record.attempt_id] = record
    assert len(latest_attempts) == 3
    assert {attempt.retry_index for attempt in latest_attempts.values()} == {0, 1, 2}
    assert {attempt.attempt_state for attempt in latest_attempts.values()} == {AttemptState.FAILED}

    replies = ReplyStore(layout).list_message(message.message_id)
    assert len(replies) == 1
    assert replies[0].terminal_status is ReplyTerminalStatus.FAILED
    assert 'runtime/pane could not be recovered' in replies[0].reply
    assert 'another healthy registered agent' in replies[0].reply

    ack = dispatcher.ack_reply('claude')
    assert ack['reply_terminal_status'] == 'failed'
    assert 'runtime/pane could not be recovered' in ack['reply']


def test_dispatcher_auto_retry_uses_continue_after_attempt_entered_context(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-auto-retry-continue'
    ctx = _bootstrap_test_project(project_root)
    layout = PathLayout(project_root)
    config = _provider_config('codex', 'claude')
    registry = AgentRegistry(layout, config)
    registry.upsert(_runtime('codex', project_id=ctx.project_id, layout=layout, pid=101))
    registry.upsert(_runtime('claude', project_id=ctx.project_id, layout=layout, pid=102))
    dispatcher = JobDispatcher(layout, config, registry, clock=lambda: '2026-03-30T00:00:00Z')

    receipt = dispatcher.submit(
        MessageEnvelope(
            project_id=ctx.project_id,
            to_agent='codex',
            from_actor='claude',
            body='keep the full original request body',
            task_id='task-auto-retry-continue',
            reply_to=None,
            message_type='ask',
            delivery_scope=DeliveryScope.SINGLE,
        )
    )
    message = MessageStore(layout).list_all()[-1]
    job_id = receipt.jobs[0].job_id

    dispatcher.tick()
    dispatcher.complete(job_id, _failed_decision(reason='pane_dead'))

    latest_attempts = {record.attempt_id: record for record in AttemptStore(layout).list_message(message.message_id)}
    retry_attempt = next(attempt for attempt in latest_attempts.values() if attempt.retry_index == 1)
    retry_job = dispatcher.get(retry_attempt.job_id)

    assert retry_job is not None
    assert retry_job.request.body == 'continue'
    assert retry_job.provider_options['retry_delivery_mode'] == 'continue'
    assert retry_job.provider_options['retry_source_job_id'] == job_id


def test_dispatcher_auto_retry_replays_original_request_when_attempt_never_entered_context(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-auto-retry-original'
    ctx = _bootstrap_test_project(project_root)
    layout = PathLayout(project_root)
    config = _provider_config('codex', 'claude')
    registry = AgentRegistry(layout, config)
    registry.upsert(_runtime('codex', project_id=ctx.project_id, layout=layout, pid=101))
    registry.upsert(_runtime('claude', project_id=ctx.project_id, layout=layout, pid=102))
    dispatcher = JobDispatcher(layout, config, registry, clock=lambda: '2026-03-30T00:00:00Z')

    receipt = dispatcher.submit(
        MessageEnvelope(
            project_id=ctx.project_id,
            to_agent='codex',
            from_actor='claude',
            body='original request body must be preserved',
            task_id='task-auto-retry-original',
            reply_to=None,
            message_type='ask',
            delivery_scope=DeliveryScope.SINGLE,
        )
    )
    message = MessageStore(layout).list_all()[-1]
    job_id = receipt.jobs[0].job_id

    dispatcher.tick()
    dispatcher.complete(
        job_id,
        replace(
            _failed_decision(reason='pane_unavailable'),
            anchor_seen=False,
            reply_started=False,
            reply_stable=False,
        ),
    )

    latest_attempts = {record.attempt_id: record for record in AttemptStore(layout).list_message(message.message_id)}
    retry_attempt = next(attempt for attempt in latest_attempts.values() if attempt.retry_index == 1)
    retry_job = dispatcher.get(retry_attempt.job_id)

    assert retry_job is not None
    assert retry_job.request.body == 'original request body must be preserved'
    assert retry_job.provider_options.get('retry_delivery_mode') != 'continue'
    assert retry_job.provider_options['retry_source_job_id'] == job_id


def test_dispatcher_timeout_delivers_inspection_notice_to_caller(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-timeout-notice'
    ctx = _bootstrap_test_project(project_root)
    layout = PathLayout(project_root)
    config = _provider_config('codex', 'claude')
    registry = AgentRegistry(layout, config)
    registry.upsert(_runtime('codex', project_id=ctx.project_id, layout=layout, pid=101))
    registry.upsert(_runtime('claude', project_id=ctx.project_id, layout=layout, pid=102))

    class StepClock:
        def __init__(self, *values: str) -> None:
            self._values = list(values)
            self._index = 0
            self._last = values[-1] if values else '2026-03-30T00:00:00Z'

        def __call__(self) -> str:
            if self._index < len(self._values):
                self._last = self._values[self._index]
                self._index += 1
            return self._last

    class SilentExecutionService:
        def start(self, job, *, runtime_context=None) -> None:
            del job, runtime_context

        def cancel(self, job_id: str) -> None:
            del job_id

        def finish(self, job_id: str) -> None:
            del job_id

        def acknowledge(self, job_id: str) -> None:
            del job_id

        def acknowledge_item(self, job_id: str, *, event_seq: int | None) -> None:
            del job_id, event_seq

        def poll(self):
            return ()

    clock = StepClock(
        '2026-03-30T00:00:00Z',
        '2026-03-30T00:00:00Z',
        '2026-03-30T00:00:00Z',
        '2026-03-30T00:00:00Z',
        '2026-03-30T00:00:02Z',
        '2026-03-30T00:00:02Z',
    )
    provider_catalog = build_default_provider_catalog()
    dispatcher = JobDispatcher(
        layout,
        config,
        registry,
        execution_service=SilentExecutionService(),
        completion_tracker=CompletionTrackerService(config, provider_catalog, request_timeout_s=1.0),
        provider_catalog=provider_catalog,
        clock=clock,
    )

    receipt = dispatcher.submit(
        MessageEnvelope(
            project_id=ctx.project_id,
            to_agent='codex',
            from_actor='claude',
            body='this task may legitimately run for a long time',
            task_id='task-timeout-notice',
            reply_to=None,
            message_type='ask',
            delivery_scope=DeliveryScope.SINGLE,
        )
    )
    message = MessageStore(layout).list_all()[-1]
    job_id = receipt.jobs[0].job_id

    started = dispatcher.tick()
    assert len(started) == 1
    assert started[0].job_id == job_id

    completed = dispatcher.poll_completions()
    assert len(completed) == 1
    assert completed[0].job_id == job_id

    replies = ReplyStore(layout).list_message(message.message_id)
    assert len(replies) == 1
    assert replies[0].terminal_status is ReplyTerminalStatus.INCOMPLETE
    assert 'timed out before a confirmed terminal reply' in replies[0].reply
    assert job_id in replies[0].reply

    ack = dispatcher.ack_reply('claude')
    assert ack['reply_terminal_status'] == 'incomplete'
    assert 'timed out before a confirmed terminal reply' in ack['reply']


def test_job_heartbeat_delivers_progress_notice_and_preserves_terminal_message_state(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-job-heartbeat'
    ctx = _bootstrap_test_project(project_root)
    layout = PathLayout(project_root)
    config = _provider_config('codex', 'claude')
    registry = AgentRegistry(layout, config)
    registry.upsert(_runtime('codex', project_id=ctx.project_id, layout=layout, pid=101))
    registry.upsert(_runtime('claude', project_id=ctx.project_id, layout=layout, pid=102))

    class SilentExecutionService:
        def start(self, job, *, runtime_context=None) -> None:
            del job, runtime_context

        def cancel(self, job_id: str) -> None:
            del job_id

        def finish(self, job_id: str) -> None:
            del job_id

        def acknowledge(self, job_id: str) -> None:
            del job_id

        def acknowledge_item(self, job_id: str, *, event_seq: int | None) -> None:
            del job_id, event_seq

        def poll(self):
            return ()

    class StepClock:
        def __init__(self, *values: str) -> None:
            self._values = list(values)
            self._index = 0
            self._last = values[-1] if values else '2026-03-30T00:00:00Z'

        def __call__(self) -> str:
            if self._index < len(self._values):
                self._last = self._values[self._index]
                self._index += 1
            return self._last

    provider_catalog = build_default_provider_catalog()
    dispatcher = JobDispatcher(
        layout,
        config,
        registry,
        execution_service=SilentExecutionService(),
        completion_tracker=CompletionTrackerService(config, provider_catalog, request_timeout_s=0.0),
        provider_catalog=provider_catalog,
        clock=lambda: '2026-03-30T00:00:00Z',
    )
    heartbeat_clock = StepClock(
        '2026-03-30T00:09:59Z',
        '2026-03-30T00:10:00Z',
        '2026-03-30T00:15:00Z',
        '2026-03-30T00:20:00Z',
        '2026-03-30T00:21:00Z',
    )
    heartbeats = JobHeartbeatService(
        layout,
        policy=HeartbeatPolicy(silence_start_after_s=600.0, repeat_interval_s=600.0),
        store=HeartbeatStateStore(layout),
        clock=heartbeat_clock,
    )

    receipt = dispatcher.submit(
        MessageEnvelope(
            project_id=ctx.project_id,
            to_agent='codex',
            from_actor='claude',
            body='long running task',
            task_id='task-job-heartbeat',
            reply_to=None,
            message_type='ask',
            delivery_scope=DeliveryScope.SINGLE,
        )
    )
    message = MessageStore(layout).list_all()[-1]
    job_id = receipt.jobs[0].job_id
    heartbeat_path = layout.heartbeat_subject_path('job_progress', job_id)

    started = dispatcher.tick()
    assert len(started) == 1
    assert started[0].job_id == job_id

    heartbeats.tick(dispatcher)
    replies = ReplyStore(layout).list_message(message.message_id)
    assert replies == []
    assert heartbeat_path.exists() is False

    heartbeats.tick(dispatcher)
    replies = ReplyStore(layout).list_message(message.message_id)
    assert len(replies) == 1
    assert replies[0].terminal_status is ReplyTerminalStatus.INCOMPLETE
    assert replies[0].diagnostics.get('notice_kind') == 'heartbeat'
    assert 'CCB_HEARTBEAT ' in replies[0].reply
    assert MessageStore(layout).list_all()[-1].message_state is MessageState.PARTIALLY_REPLIED
    assert heartbeat_path.exists()

    heartbeats.tick(dispatcher)
    assert len(ReplyStore(layout).list_message(message.message_id)) == 1

    heartbeats.tick(dispatcher)
    replies = ReplyStore(layout).list_message(message.message_id)
    assert len(replies) == 2
    assert all(reply.diagnostics.get('notice_kind') == 'heartbeat' for reply in replies)

    dispatcher.complete(
        job_id,
        replace(
            _decision(reply='final answer'),
            finished_at='2026-03-30T00:21:00Z',
        ),
    )
    heartbeats.tick(dispatcher)

    replies = ReplyStore(layout).list_message(message.message_id)
    assert len(replies) == 3
    assert replies[-1].terminal_status is ReplyTerminalStatus.COMPLETED
    assert replies[-1].reply == 'final answer'
    assert MessageStore(layout).list_all()[-1].message_state is MessageState.COMPLETED
    assert heartbeat_path.exists() is False


def test_dispatcher_delivers_failed_reply_to_sender_when_claude_hits_pre_anchor_api_error(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from provider_execution import claude as claude_adapter_module

    project_root = tmp_path / 'repo-claude-pre-anchor-api-error'
    ctx = _bootstrap_test_project(project_root)
    layout = PathLayout(project_root)
    config = _provider_config('codex', 'claude', 'gemini')
    registry = AgentRegistry(layout, config)
    registry.upsert(_runtime('codex', project_id=ctx.project_id, layout=layout, pid=101))
    registry.upsert(_runtime('claude', project_id=ctx.project_id, layout=layout, pid=102))

    class FakeBackend:
        def send_text(self, pane_id: str, text: str) -> None:
            del pane_id, text

        def is_alive(self, pane_id: str) -> bool:
            return pane_id == '%2'

    class FakeSession:
        data = {}
        claude_session_path = str(tmp_path / 'claude-session.jsonl')
        claude_projects_root = None
        work_dir = str(layout.workspace_path('claude'))

        def ensure_pane(self):
            return True, '%2'

    class FakeReader:
        def __init__(self, *args, **kwargs) -> None:
            del args, kwargs
            self._events = [
                {
                    'role': 'system',
                    'text': '',
                    'entry_type': 'system',
                    'subtype': 'api_error',
                    'entry': {
                        'type': 'system',
                        'subtype': 'api_error',
                        'timestamp': '2026-03-30T00:00:02Z',
                        'retryAttempt': 3,
                        'maxRetries': 3,
                        'cause': {
                            'code': 'Unauthorized',
                            'path': 'https://api.anthropic.com/v1/messages',
                        },
                    },
                },
            ]

        def set_preferred_session(self, session_path) -> None:
            del session_path

        def capture_state(self):
            return {'session_path': str(tmp_path / 'claude-session.jsonl'), 'offset': 0}

        def try_get_entries(self, state):
            index = int(state.get('index', 0))
            if index >= len(self._events):
                return [], state
            return [self._events[index]], {**state, 'index': index + 1}

    monkeypatch.setattr(claude_adapter_module, 'load_project_session', lambda work_dir, instance=None: FakeSession())
    monkeypatch.setattr(claude_adapter_module, 'get_backend_for_session', lambda data: FakeBackend())
    monkeypatch.setattr(claude_adapter_module, 'ClaudeLogReader', FakeReader)

    execution_service = ExecutionService(build_default_execution_registry(), clock=lambda: '2026-03-30T00:00:00Z')
    dispatcher = JobDispatcher(
        layout,
        config,
        registry,
        execution_service=execution_service,
        clock=lambda: '2026-03-30T00:00:00Z',
    )

    receipt = dispatcher.submit(
        MessageEnvelope(
            project_id=ctx.project_id,
            to_agent='claude',
            from_actor='codex',
            body='please handle this',
            task_id='task-claude-auth-fail',
            reply_to=None,
            message_type='ask',
            delivery_scope=DeliveryScope.SINGLE,
        )
    )
    message = MessageStore(layout).list_all()[-1]
    job_id = receipt.jobs[0].job_id

    started = dispatcher.tick()
    assert len(started) == 1
    assert started[0].job_id == job_id
    completed = dispatcher.poll_completions()
    assert len(completed) == 1
    assert completed[0].job_id == job_id

    codex_inbox = dispatcher.inbox('codex')
    assert codex_inbox['item_count'] == 1
    assert codex_inbox['head']['event_type'] == 'task_reply'

    latest_attempts = {record.attempt_id: record for record in AttemptStore(layout).list_message(message.message_id)}
    assert len(latest_attempts) == 1
    assert {attempt.retry_index for attempt in latest_attempts.values()} == {0}
    assert {attempt.attempt_state for attempt in latest_attempts.values()} == {AttemptState.FAILED}

    replies = ReplyStore(layout).list_message(message.message_id)
    assert len(replies) == 1
    assert replies[0].terminal_status is ReplyTerminalStatus.FAILED
    assert 'failed after 3 attempts' not in replies[0].reply
    assert 'authentication/login error' in replies[0].reply
    assert 'error_code=Unauthorized' in replies[0].reply

    ack = dispatcher.ack_reply('codex')
    assert ack['reply_terminal_status'] == 'failed'
    assert 'authentication/login error' in ack['reply']


def test_dispatcher_does_not_auto_retry_nonretryable_quota_api_failures(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-no-auto-retry-api-quota'
    ctx = _bootstrap_test_project(project_root)
    layout = PathLayout(project_root)
    config = _provider_config('codex', 'claude', 'gemini')
    registry = AgentRegistry(layout, config)
    registry.upsert(_runtime('codex', project_id=ctx.project_id, layout=layout, pid=101))
    registry.upsert(_runtime('claude', project_id=ctx.project_id, layout=layout, pid=102))
    dispatcher = JobDispatcher(layout, config, registry, clock=lambda: '2026-03-30T00:00:00Z')

    receipt = dispatcher.submit(
        MessageEnvelope(
            project_id=ctx.project_id,
            to_agent='codex',
            from_actor='claude',
            body='quota failures should not retry',
            task_id='task-no-auto-retry-api-quota',
            reply_to=None,
            message_type='ask',
            delivery_scope=DeliveryScope.SINGLE,
        )
    )
    message = MessageStore(layout).list_all()[-1]
    job_id = receipt.jobs[0].job_id

    dispatcher.tick()
    dispatcher.complete(
        job_id,
        _failed_decision(
            diagnostics={
                'error_type': 'provider_api_error',
                'error_code': 'InsufficientQuota',
            }
        ),
    )

    claude_inbox = dispatcher.inbox('claude')
    assert claude_inbox['item_count'] == 1
    assert claude_inbox['head']['event_type'] == 'task_reply'

    latest_attempts = {record.attempt_id: record for record in AttemptStore(layout).list_message(message.message_id)}
    assert len(latest_attempts) == 1
    only_attempt = next(iter(latest_attempts.values()))
    assert only_attempt.retry_index == 0
    assert only_attempt.attempt_state is AttemptState.FAILED

    replies = ReplyStore(layout).list_message(message.message_id)
    assert len(replies) == 1
    assert replies[0].terminal_status is ReplyTerminalStatus.FAILED
    assert 'failed after 3 attempts' not in replies[0].reply
    assert 'quota/billing error' in replies[0].reply
    assert 'error_code=InsufficientQuota' in replies[0].reply

    ack = dispatcher.ack_reply('claude')
    assert ack['reply_terminal_status'] == 'failed'
    assert 'quota/billing error' in ack['reply']


def test_dispatcher_does_not_auto_retry_gemini_hook_login_failures(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-no-auto-retry-gemini-login'
    ctx = _bootstrap_test_project(project_root)
    layout = PathLayout(project_root)
    base_config = _provider_config('codex', 'claude', 'gemini')
    config = ProjectConfig(
        version=base_config.version,
        default_agents=base_config.default_agents,
        agents={
            **base_config.agents,
            'gemini': AgentSpec(
                name='gemini',
                provider='gemini',
                target='.',
                workspace_mode=WorkspaceMode.GIT_WORKTREE,
                workspace_root=None,
                runtime_mode=RuntimeMode.PANE_BACKED,
                restore_default=RestoreMode.AUTO,
                permission_default=PermissionMode.MANUAL,
                queue_policy=QueuePolicy.SERIAL_PER_AGENT,
            ),
        },
        cmd_enabled=base_config.cmd_enabled,
    )
    registry = AgentRegistry(layout, config)
    registry.upsert(_runtime('gemini', project_id=ctx.project_id, layout=layout, pid=101))
    registry.upsert(_runtime('claude', project_id=ctx.project_id, layout=layout, pid=102))
    failure_text = (
        'Code Assist login required.\n'
        'Attempting to open authentication page in your browser.'
    )

    class FakeExecutionService:
        def __init__(self) -> None:
            self._job = None
            self._emitted = False

        def start(self, job, *, runtime_context=None) -> None:
            del runtime_context
            self._job = job
            self._emitted = False

        def cancel(self, job_id: str) -> None:
            del job_id

        def finish(self, job_id: str) -> None:
            del job_id

        def acknowledge(self, job_id: str) -> None:
            del job_id

        def acknowledge_item(self, job_id: str, *, event_seq: int | None) -> None:
            del job_id, event_seq

        def poll(self):
            if self._job is None or self._emitted:
                return ()
            self._emitted = True
            return (
                ExecutionUpdate(
                    job_id=self._job.job_id,
                    items=(
                        CompletionItem(
                            kind=CompletionItemKind.ASSISTANT_FINAL,
                            timestamp='2026-03-30T00:00:02Z',
                            cursor=CompletionCursor(
                                source_kind=CompletionSourceKind.SESSION_SNAPSHOT,
                                event_seq=1,
                                updated_at='2026-03-30T00:00:02Z',
                            ),
                            provider='gemini',
                            agent_name='gemini',
                            req_id=self._job.job_id,
                            payload={
                                'reply': failure_text,
                                'text': failure_text,
                                'status': 'failed',
                                'completion_source': 'hook_artifact',
                                'hook_event_name': 'AfterAgent',
                                'error_type': 'provider_api_error',
                                'error_code': 'LoginRequired',
                                'error_message': failure_text,
                            },
                        ),
                    ),
                    decision=CompletionDecision(
                        terminal=True,
                        status=CompletionStatus.FAILED,
                        reason='api_error',
                        confidence=CompletionConfidence.EXACT,
                        reply=failure_text,
                        anchor_seen=False,
                        reply_started=True,
                        reply_stable=True,
                        provider_turn_ref='gemini-session-id',
                        source_cursor=CompletionCursor(
                            source_kind=CompletionSourceKind.SESSION_SNAPSHOT,
                            event_seq=1,
                            updated_at='2026-03-30T00:00:02Z',
                        ),
                        finished_at='2026-03-30T00:00:02Z',
                        diagnostics={
                            'completion_source': 'hook_artifact',
                            'hook_event_name': 'AfterAgent',
                            'error_type': 'provider_api_error',
                            'error_code': 'LoginRequired',
                            'error_message': failure_text,
                        },
                    ),
                ),
            )

    dispatcher = JobDispatcher(
        layout,
        config,
        registry,
        execution_service=FakeExecutionService(),
        clock=lambda: '2026-03-30T00:00:00Z',
    )

    receipt = dispatcher.submit(
        MessageEnvelope(
            project_id=ctx.project_id,
            to_agent='gemini',
            from_actor='claude',
            body='gemini login failures should not retry',
            task_id='task-no-auto-retry-gemini-login',
            reply_to=None,
            message_type='ask',
            delivery_scope=DeliveryScope.SINGLE,
        )
    )
    message = MessageStore(layout).list_all()[-1]
    job_id = receipt.jobs[0].job_id

    started = dispatcher.tick()
    assert len(started) == 1
    assert started[0].job_id == job_id

    completed = dispatcher.poll_completions()
    assert len(completed) == 1
    assert completed[0].job_id == job_id

    claude_inbox = dispatcher.inbox('claude')
    assert claude_inbox['item_count'] == 1
    assert claude_inbox['head']['event_type'] == 'task_reply'

    latest_attempts = {record.attempt_id: record for record in AttemptStore(layout).list_message(message.message_id)}
    assert len(latest_attempts) == 1
    only_attempt = next(iter(latest_attempts.values()))
    assert only_attempt.retry_index == 0
    assert only_attempt.attempt_state is AttemptState.FAILED

    replies = ReplyStore(layout).list_message(message.message_id)
    assert len(replies) == 1
    assert replies[0].terminal_status is ReplyTerminalStatus.FAILED
    assert 'failed after 3 attempts' not in replies[0].reply
    assert 'authentication/login error' in replies[0].reply
    assert 'LoginRequired' in replies[0].reply

    ack = dispatcher.ack_reply('claude')
    assert ack['reply_terminal_status'] == 'failed'
    assert 'authentication/login error' in ack['reply']


def test_dispatcher_does_not_auto_retry_codex_abort_login_failures_from_tracker(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-no-auto-retry-codex-login'
    ctx = _bootstrap_test_project(project_root)
    layout = PathLayout(project_root)
    config = _provider_config('codex', 'claude', 'gemini')
    registry = AgentRegistry(layout, config)
    registry.upsert(_runtime('codex', project_id=ctx.project_id, layout=layout, pid=101))
    registry.upsert(_runtime('claude', project_id=ctx.project_id, layout=layout, pid=102))

    class FakeExecutionService:
        def __init__(self) -> None:
            self._job = None
            self._emitted = False

        def start(self, job, *, runtime_context=None) -> None:
            del runtime_context
            self._job = job
            self._emitted = False

        def cancel(self, job_id: str) -> None:
            del job_id

        def finish(self, job_id: str) -> None:
            del job_id

        def acknowledge(self, job_id: str) -> None:
            del job_id

        def acknowledge_item(self, job_id: str, *, event_seq: int | None) -> None:
            del job_id, event_seq

        def poll(self):
            if self._job is None or self._emitted:
                return ()
            self._emitted = True
            return (
                ExecutionUpdate(
                    job_id=self._job.job_id,
                    items=(
                        CompletionItem(
                            kind=CompletionItemKind.TURN_ABORTED,
                            timestamp='2026-03-30T00:00:02Z',
                            cursor=CompletionCursor(
                                source_kind=CompletionSourceKind.PROTOCOL_EVENT_STREAM,
                                event_seq=1,
                                updated_at='2026-03-30T00:00:02Z',
                            ),
                            provider='codex',
                            agent_name='codex',
                            req_id=self._job.job_id,
                            payload={
                                'reason': 'turn_aborted',
                                'status': 'failed',
                                'text': 'Login required. Please run codex login.',
                                'error_message': 'Login required. Please run codex login.',
                            },
                        ),
                    ),
                    decision=None,
                ),
            )

    provider_catalog = build_default_provider_catalog()
    dispatcher = JobDispatcher(
        layout,
        config,
        registry,
        execution_service=FakeExecutionService(),
        completion_tracker=CompletionTrackerService(config, provider_catalog),
        provider_catalog=provider_catalog,
        clock=lambda: '2026-03-30T00:00:00Z',
    )

    receipt = dispatcher.submit(
        MessageEnvelope(
            project_id=ctx.project_id,
            to_agent='codex',
            from_actor='claude',
            body='codex login failures should not retry',
            task_id='task-no-auto-retry-codex-login',
            reply_to=None,
            message_type='ask',
            delivery_scope=DeliveryScope.SINGLE,
        )
    )
    message = MessageStore(layout).list_all()[-1]
    job_id = receipt.jobs[0].job_id

    started = dispatcher.tick()
    assert len(started) == 1
    assert started[0].job_id == job_id

    completed = dispatcher.poll_completions()
    assert len(completed) == 1
    assert completed[0].job_id == job_id

    claude_inbox = dispatcher.inbox('claude')
    assert claude_inbox['item_count'] == 1
    assert claude_inbox['head']['event_type'] == 'task_reply'

    latest_attempts = {record.attempt_id: record for record in AttemptStore(layout).list_message(message.message_id)}
    assert len(latest_attempts) == 1
    only_attempt = next(iter(latest_attempts.values()))
    assert only_attempt.retry_index == 0
    assert only_attempt.attempt_state is AttemptState.FAILED

    replies = ReplyStore(layout).list_message(message.message_id)
    assert len(replies) == 1
    assert replies[0].terminal_status is ReplyTerminalStatus.FAILED
    assert 'failed after 3 attempts' not in replies[0].reply
    assert 'authentication/login error' in replies[0].reply
    assert 'run codex login' in replies[0].reply.lower()

    ack = dispatcher.ack_reply('claude')
    assert ack['reply_terminal_status'] == 'failed'
    assert 'authentication/login error' in ack['reply']


def test_dispatcher_does_not_auto_retry_non_retryable_runtime_failures(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-no-auto-retry-runtime'
    ctx = _bootstrap_test_project(project_root)
    layout = PathLayout(project_root)
    config = ProjectConfig(
        version=2,
        default_agents=('opencode', 'claude'),
        agents={
            'opencode': AgentSpec(
                name='opencode',
                provider='opencode',
                target='.',
                workspace_mode=WorkspaceMode.GIT_WORKTREE,
                workspace_root=None,
                runtime_mode=RuntimeMode.PANE_BACKED,
                restore_default=RestoreMode.AUTO,
                permission_default=PermissionMode.MANUAL,
                queue_policy=QueuePolicy.SERIAL_PER_AGENT,
            ),
            'claude': AgentSpec(
                name='claude',
                provider='claude',
                target='.',
                workspace_mode=WorkspaceMode.GIT_WORKTREE,
                workspace_root=None,
                runtime_mode=RuntimeMode.PANE_BACKED,
                restore_default=RestoreMode.AUTO,
                permission_default=PermissionMode.MANUAL,
                queue_policy=QueuePolicy.SERIAL_PER_AGENT,
            ),
        },
        cmd_enabled=False,
    )
    registry = AgentRegistry(layout, config)
    registry.upsert(_runtime('opencode', project_id=ctx.project_id, layout=layout, pid=101))
    registry.upsert(_runtime('claude', project_id=ctx.project_id, layout=layout, pid=102))
    dispatcher = JobDispatcher(layout, config, registry, clock=lambda: '2026-03-30T00:00:00Z')

    receipt = dispatcher.submit(
        MessageEnvelope(
            project_id=ctx.project_id,
            to_agent='opencode',
            from_actor='claude',
            body='pane dead should not retry',
            task_id='task-no-auto-retry-runtime',
            reply_to=None,
            message_type='ask',
            delivery_scope=DeliveryScope.SINGLE,
        )
    )
    message = MessageStore(layout).list_all()[-1]
    job_id = receipt.jobs[0].job_id

    dispatcher.tick()
    dispatcher.complete(job_id, _failed_decision(reason='pane_dead'))

    claude_inbox = dispatcher.inbox('claude')
    assert claude_inbox['item_count'] == 1
    assert claude_inbox['head']['event_type'] == 'task_reply'

    latest_attempts = {}
    for record in AttemptStore(layout).list_message(message.message_id):
        latest_attempts[record.attempt_id] = record
    assert len(latest_attempts) == 1
    only_attempt = next(iter(latest_attempts.values()))
    assert only_attempt.retry_index == 0
    assert only_attempt.attempt_state is AttemptState.FAILED

    replies = ReplyStore(layout).list_message(message.message_id)
    assert len(replies) == 1
    assert 'failed after 3 attempts' not in replies[0].reply


def test_dispatcher_tick_keeps_degraded_agent_queued_until_recovered(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-degraded-queue'
    ctx = _bootstrap_test_project(project_root)
    layout = PathLayout(project_root)
    config = _provider_config('codex', 'claude', 'gemini')
    registry = AgentRegistry(layout, config)
    degraded_runtime = replace(
        _runtime('codex', project_id=ctx.project_id, layout=layout, pid=101),
        state=AgentState.DEGRADED,
        health='pane-dead',
        runtime_ref=None,
        session_ref=None,
    )
    registry.upsert(degraded_runtime)
    dispatcher = JobDispatcher(layout, config, registry, clock=lambda: '2026-03-30T00:00:00Z')

    receipt = dispatcher.submit(
        MessageEnvelope(
            project_id=ctx.project_id,
            to_agent='codex',
            from_actor='user',
            body='hello',
            task_id='task-degraded-queue',
            reply_to=None,
            message_type='ask',
            delivery_scope=DeliveryScope.SINGLE,
        )
    )
    job_id = receipt.jobs[0].job_id

    assert dispatcher.tick() == ()
    accepted = dispatcher.get(job_id)
    assert accepted is not None
    assert accepted.status.value == 'accepted'

    recovered_runtime = replace(
        degraded_runtime,
        state=AgentState.IDLE,
        health='healthy',
        runtime_ref='tmux:%1',
        session_ref='/tmp/codex-session.json',
    )
    registry.upsert_authority(recovered_runtime)
    dispatcher.reconcile_runtime_views()

    started = dispatcher.tick()
    assert len(started) == 1
    assert started[0].job_id == job_id


def test_dispatcher_tick_keeps_recoverable_agent_queued_without_runtime_service(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-degraded-recovery-start'
    ctx = _bootstrap_test_project(project_root)
    layout = PathLayout(project_root)
    config = _provider_config('codex', 'claude', 'gemini')
    registry = AgentRegistry(layout, config)
    degraded_runtime = replace(
        _runtime('codex', project_id=ctx.project_id, layout=layout, pid=101),
        state=AgentState.DEGRADED,
        health='pane-dead',
        runtime_ref=None,
        session_ref=None,
    )
    registry.upsert(degraded_runtime)

    started_jobs: list[tuple[str, str | None]] = []

    class FakeExecutionService:
        def start(self, job, *, runtime_context=None) -> None:
            started_jobs.append((job.job_id, runtime_context.runtime_health if runtime_context is not None else None))

    dispatcher = JobDispatcher(
        layout,
        config,
        registry,
        execution_service=FakeExecutionService(),
        clock=lambda: '2026-03-30T00:00:00Z',
    )

    receipt = dispatcher.submit(
        MessageEnvelope(
            project_id=ctx.project_id,
            to_agent='codex',
            from_actor='user',
            body='recover if possible',
            task_id='task-degraded-recovery-start',
            reply_to=None,
            message_type='ask',
            delivery_scope=DeliveryScope.SINGLE,
        )
    )
    job_id = receipt.jobs[0].job_id

    started = dispatcher.tick()
    assert started == ()
    accepted = dispatcher.get(job_id)
    assert accepted is not None
    assert accepted.status.value == 'accepted'
    assert started_jobs == []


def test_dispatcher_tick_uses_mailbox_claimable_requests_as_start_source(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-mailbox-source'
    ctx = _bootstrap_test_project(project_root)
    layout = PathLayout(project_root)
    config = _provider_config('codex', 'claude', 'gemini')
    registry = AgentRegistry(layout, config)
    registry.upsert(_runtime('codex', project_id=ctx.project_id, layout=layout, pid=101))
    dispatcher = JobDispatcher(layout, config, registry, clock=lambda: '2026-03-30T00:00:00Z')

    receipt = dispatcher.submit(
        MessageEnvelope(
            project_id=ctx.project_id,
            to_agent='codex',
            from_actor='user',
            body='hello',
            task_id='task-mailbox-source',
            reply_to=None,
            message_type='ask',
            delivery_scope=DeliveryScope.SINGLE,
        )
    )
    job_id = receipt.jobs[0].job_id
    attempt = AttemptStore(layout).get_latest_by_job_id(job_id)
    assert attempt is not None
    inbox_store = InboundEventStore(layout)
    inbound = inbox_store.get_latest_for_attempt('codex', attempt.attempt_id)
    assert inbound is not None

    inbox_store.append(
        InboundEventRecord(
            inbound_event_id=inbound.inbound_event_id,
            agent_name=inbound.agent_name,
            event_type=inbound.event_type,
            message_id=inbound.message_id,
            attempt_id=inbound.attempt_id,
            payload_ref=inbound.payload_ref,
            priority=inbound.priority,
            status=InboundEventStatus.ABANDONED,
            created_at=inbound.created_at,
            started_at=inbound.started_at,
            finished_at='2026-03-30T00:00:01Z',
        )
    )

    started = dispatcher.tick()

    assert started == ()
    current = dispatcher.get(job_id)
    assert current is not None
    assert current.status.value == 'accepted'


def test_dispatcher_does_not_start_task_request_behind_pending_reply_head(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-mailbox-head-block'
    ctx = _bootstrap_test_project(project_root)
    layout = PathLayout(project_root)
    config = _provider_config('codex', 'claude', 'gemini')
    registry = AgentRegistry(layout, config)
    registry.upsert(_runtime('codex', project_id=ctx.project_id, layout=layout, pid=101))
    registry.upsert(_runtime('claude', project_id=ctx.project_id, layout=layout, pid=102))
    dispatcher = JobDispatcher(layout, config, registry, clock=lambda: '2026-03-30T00:00:00Z')

    reply_receipt = dispatcher.submit(
        MessageEnvelope(
            project_id=ctx.project_id,
            to_agent='codex',
            from_actor='claude',
            body='hello from claude',
            task_id='task-reply-head',
            reply_to=None,
            message_type='ask',
            delivery_scope=DeliveryScope.SINGLE,
        )
    )
    reply_job_id = reply_receipt.jobs[0].job_id
    dispatcher.tick()
    dispatcher.complete(reply_job_id, _decision(reply='reply for claude'))

    blocked_receipt = dispatcher.submit(
        MessageEnvelope(
            project_id=ctx.project_id,
            to_agent='claude',
            from_actor='user',
            body='should stay queued',
            task_id='task-behind-reply',
            reply_to=None,
            message_type='ask',
            delivery_scope=DeliveryScope.SINGLE,
        )
    )
    blocked_job_id = blocked_receipt.jobs[0].job_id

    started = dispatcher.tick()

    assert len(started) == 1
    assert started[0].request.message_type == 'reply_delivery'
    current = dispatcher.get(blocked_job_id)
    assert current is not None
    assert current.status.value == 'accepted'

    queue = dispatcher.queue('claude', detail=True)
    agent = queue['agent']
    assert agent['queue_depth'] == 2
    assert agent['queued_events'][0]['event_type'] == 'task_reply'
    assert agent['queued_events'][1]['job_id'] == blocked_job_id


def test_dispatcher_inbox_exposes_head_reply_body_and_ack_drains_mailbox(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-inbox-ack'
    ctx = _bootstrap_test_project(project_root)
    layout = PathLayout(project_root)
    config = _provider_config('codex', 'claude', 'gemini')
    registry = AgentRegistry(layout, config)
    registry.upsert(_runtime('codex', project_id=ctx.project_id, layout=layout, pid=101))
    registry.upsert(_runtime('claude', project_id=ctx.project_id, layout=layout, pid=102))
    dispatcher = JobDispatcher(layout, config, registry, clock=lambda: '2026-03-30T00:00:00Z')

    receipt = dispatcher.submit(
        MessageEnvelope(
            project_id=ctx.project_id,
            to_agent='codex',
            from_actor='claude',
            body='hello inbox',
            task_id='task-inbox',
            reply_to=None,
            message_type='ask',
            delivery_scope=DeliveryScope.SINGLE,
        )
    )
    job_id = receipt.jobs[0].job_id
    dispatcher.tick()
    dispatcher.complete(job_id, _decision(reply='done for inbox'))

    inbox = dispatcher.inbox('claude')

    assert inbox['target'] == 'claude'
    assert inbox['item_count'] == 1
    assert inbox['head']['event_type'] == 'task_reply'
    assert inbox['head']['reply'] == 'done for inbox'
    assert inbox['items'] == []

    inbox_detail = dispatcher.inbox('claude', detail=True)
    assert inbox_detail['items'][0]['reply_preview'] == 'done for inbox'

    acked = dispatcher.ack_reply('claude')

    assert acked['acknowledged_inbound_event_id'] == inbox['head']['inbound_event_id']
    assert acked['reply'] == 'done for inbox'
    queue = dispatcher.queue('claude', detail=True)
    assert queue['agent']['mailbox_state'] == 'idle'
    assert queue['agent']['queue_depth'] == 0
    assert queue['agent']['pending_reply_count'] == 0


def test_dispatcher_ack_reply_unblocks_next_task_request_after_tick(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-ack-unblock'
    ctx = _bootstrap_test_project(project_root)
    layout = PathLayout(project_root)
    config = _provider_config('codex', 'claude', 'gemini')
    registry = AgentRegistry(layout, config)
    registry.upsert(_runtime('codex', project_id=ctx.project_id, layout=layout, pid=101))
    registry.upsert(_runtime('claude', project_id=ctx.project_id, layout=layout, pid=102))
    dispatcher = JobDispatcher(layout, config, registry, clock=lambda: '2026-03-30T00:00:00Z')

    reply_receipt = dispatcher.submit(
        MessageEnvelope(
            project_id=ctx.project_id,
            to_agent='codex',
            from_actor='claude',
            body='reply first',
            task_id='task-reply-first',
            reply_to=None,
            message_type='ask',
            delivery_scope=DeliveryScope.SINGLE,
        )
    )
    reply_job_id = reply_receipt.jobs[0].job_id
    dispatcher.tick()
    dispatcher.complete(reply_job_id, _decision(reply='reply for claude'))

    blocked_receipt = dispatcher.submit(
        MessageEnvelope(
            project_id=ctx.project_id,
            to_agent='claude',
            from_actor='user',
            body='run after ack',
            task_id='task-run-after-ack',
            reply_to=None,
            message_type='ask',
            delivery_scope=DeliveryScope.SINGLE,
        )
    )
    blocked_job_id = blocked_receipt.jobs[0].job_id

    dispatcher.ack_reply('claude')
    started = dispatcher.tick()

    assert len(started) == 1
    assert started[0].job_id == blocked_job_id
    queue = dispatcher.queue('claude', detail=True)
    assert queue['agent']['mailbox_state'] == 'delivering'
    assert queue['agent']['active']['job_id'] == blocked_job_id


def test_dispatcher_ack_clears_terminal_task_request_head(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-ack-terminal-task-request'
    ctx = _bootstrap_test_project(project_root)
    layout = PathLayout(project_root)
    config = _provider_config('codex', 'claude')
    registry = AgentRegistry(layout, config)
    registry.upsert(_runtime('claude', project_id=ctx.project_id, layout=layout, pid=102))
    dispatcher = JobDispatcher(layout, config, registry, clock=lambda: '2026-03-30T00:00:00Z')

    receipt = dispatcher.submit(
        MessageEnvelope(
            project_id=ctx.project_id,
            to_agent='claude',
            from_actor='user',
            body='stale task request',
            task_id='task-stale-request',
            reply_to=None,
            message_type='ask',
            delivery_scope=DeliveryScope.SINGLE,
        )
    )
    job_id = receipt.jobs[0].job_id
    dispatcher.tick()
    attempt = dispatcher._message_bureau._attempt_store.get_latest_by_job_id(job_id)
    assert attempt is not None
    dispatcher._message_bureau._attempt_store.append(
        replace(attempt, attempt_state=AttemptState.INCOMPLETE, updated_at='2026-03-30T00:00:05Z')
    )

    acked = dispatcher.ack_reply('claude')

    assert acked['acknowledged_event_type'] == 'task_request'
    assert acked['attempt_state'] == 'incomplete'
    assert acked['job_id'] == job_id
    queue = dispatcher.queue('claude', detail=True)
    assert queue['agent']['mailbox_state'] == 'idle'
    assert queue['agent']['queue_depth'] == 0
    assert queue['agent']['active_inbound_event_id'] is None
    latest = InboundEventStore(layout).get_latest_for_attempt('claude', attempt.attempt_id)
    assert latest is not None
    assert latest.status is InboundEventStatus.CONSUMED


def test_dispatcher_queue_summary_discards_stale_terminal_task_request_head(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-discard-terminal-task-request'
    ctx = _bootstrap_test_project(project_root)
    layout = PathLayout(project_root)
    config = _provider_config('codex', 'claude')
    registry = AgentRegistry(layout, config)
    registry.upsert(_runtime('claude', project_id=ctx.project_id, layout=layout, pid=102))
    dispatcher = JobDispatcher(layout, config, registry, clock=lambda: '2026-03-30T00:00:00Z')

    receipt = dispatcher.submit(
        MessageEnvelope(
            project_id=ctx.project_id,
            to_agent='claude',
            from_actor='user',
            body='auto discard stale request',
            task_id='task-auto-discard',
            reply_to=None,
            message_type='ask',
            delivery_scope=DeliveryScope.SINGLE,
        )
    )
    job_id = receipt.jobs[0].job_id
    dispatcher.tick()
    attempt = dispatcher._message_bureau._attempt_store.get_latest_by_job_id(job_id)
    assert attempt is not None
    dispatcher._message_bureau._attempt_store.append(
        replace(attempt, attempt_state=AttemptState.INCOMPLETE, updated_at='2026-03-30T00:00:05Z')
    )

    queue = dispatcher.queue('claude', detail=True)

    assert queue['agent']['mailbox_state'] == 'idle'
    assert queue['agent']['queue_depth'] == 0
    assert queue['agent']['active_inbound_event_id'] is None
    latest = InboundEventStore(layout).get_latest_for_attempt('claude', attempt.attempt_id)
    assert latest is not None
    assert latest.status is InboundEventStatus.ABANDONED


def test_dispatcher_pending_reply_on_one_agent_does_not_block_other_agent_start(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-multi-agent-mailbox-isolation'
    ctx = _bootstrap_test_project(project_root)
    layout = PathLayout(project_root)
    config = _provider_config('codex', 'claude')
    registry = AgentRegistry(layout, config)
    registry.upsert(_runtime('codex', project_id=ctx.project_id, layout=layout, pid=101))
    registry.upsert(_runtime('claude', project_id=ctx.project_id, layout=layout, pid=102))
    dispatcher = JobDispatcher(layout, config, registry, clock=lambda: '2026-03-30T00:00:00Z')

    reply_receipt = dispatcher.submit(
        MessageEnvelope(
            project_id=ctx.project_id,
            to_agent='codex',
            from_actor='claude',
            body='question for codex',
            task_id='task-mailbox-isolation-reply',
            reply_to=None,
            message_type='ask',
            delivery_scope=DeliveryScope.SINGLE,
        )
    )
    reply_job_id = reply_receipt.jobs[0].job_id
    dispatcher.tick()
    dispatcher.complete(reply_job_id, _decision(reply='reply for claude'))

    blocked_receipt = dispatcher.submit(
        MessageEnvelope(
            project_id=ctx.project_id,
            to_agent='claude',
            from_actor='user',
            body='should stay queued behind mailbox head',
            task_id='task-mailbox-isolation-blocked',
            reply_to=None,
            message_type='ask',
            delivery_scope=DeliveryScope.SINGLE,
        )
    )
    blocked_job_id = blocked_receipt.jobs[0].job_id
    codex_receipt = dispatcher.submit(
        MessageEnvelope(
            project_id=ctx.project_id,
            to_agent='codex',
            from_actor='user',
            body='codex should still run',
            task_id='task-mailbox-isolation-codex',
            reply_to=None,
            message_type='ask',
            delivery_scope=DeliveryScope.SINGLE,
        )
    )
    codex_job_id = codex_receipt.jobs[0].job_id

    started = dispatcher.tick()

    started_ids = {job.job_id for job in started}
    assert codex_job_id in started_ids
    assert any(job.request.message_type == 'reply_delivery' and job.agent_name == 'claude' for job in started)
    blocked_state = dispatcher.get(blocked_job_id)
    codex_state = dispatcher.get(codex_job_id)
    assert blocked_state is not None and blocked_state.status.value == 'accepted'
    assert codex_state is not None and codex_state.status.value == 'running'

    claude_queue = dispatcher.queue('claude', detail=True)
    assert claude_queue['agent']['queue_depth'] == 2
    assert claude_queue['agent']['queued_events'][0]['event_type'] == 'task_reply'
    assert claude_queue['agent']['queued_events'][1]['job_id'] == blocked_job_id


def test_dispatcher_tick_promotes_head_reply_into_tracked_delivery_before_queued_requests(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-reply-delivery-order'
    ctx = _bootstrap_test_project(project_root)
    layout = PathLayout(project_root)
    config = _provider_config('codex', 'claude')
    registry = AgentRegistry(layout, config)
    registry.upsert(_runtime('codex', project_id=ctx.project_id, layout=layout, pid=101))
    registry.upsert(_runtime('claude', project_id=ctx.project_id, layout=layout, pid=102))
    dispatcher = JobDispatcher(layout, config, registry, clock=lambda: '2026-03-30T00:00:00Z')

    reply_receipt = dispatcher.submit(
        MessageEnvelope(
            project_id=ctx.project_id,
            to_agent='codex',
            from_actor='claude',
            body='question for codex',
            task_id='task-reply-order',
            reply_to=None,
            message_type='ask',
            delivery_scope=DeliveryScope.SINGLE,
        )
    )
    reply_job_id = reply_receipt.jobs[0].job_id
    dispatcher.tick()
    dispatcher.complete(reply_job_id, _decision(reply='reply for claude'))

    queued_receipt = dispatcher.submit(
        MessageEnvelope(
            project_id=ctx.project_id,
            to_agent='claude',
            from_actor='user',
            body='real work queued behind reply',
            task_id='task-behind-reply',
            reply_to=None,
            message_type='ask',
            delivery_scope=DeliveryScope.SINGLE,
        )
    )
    queued_job_id = queued_receipt.jobs[0].job_id

    started = dispatcher.tick()

    assert len(started) == 1
    delivery_job = started[0]
    assert delivery_job.job_id != queued_job_id
    assert delivery_job.request.message_type == 'reply_delivery'
    assert delivery_job.provider_options['no_wrap'] is True
    assert delivery_job.request.body.startswith('CCB_REPLY from=codex ')
    assert 'status=completed' in delivery_job.request.body
    assert 'reply for claude' in delivery_job.request.body
    assert dispatcher.get(queued_job_id).status.value == 'accepted'

    inbox = dispatcher.inbox('claude')
    assert inbox['head']['event_type'] == 'task_reply'
    head_record = InboundEventStore(layout).get_latest('claude', inbox['head']['inbound_event_id'])
    assert head_record is not None
    assert delivery_job_id_from_payload(head_record.payload_ref) == delivery_job.job_id
    mailbox = MailboxStore(layout).load('claude')
    assert mailbox is not None
    assert mailbox.summary_source == 'transition-claim'
    assert mailbox.head_status == 'delivering'
    assert delivery_job_id_from_payload(mailbox.head_payload_ref) == delivery_job.job_id

    dispatcher.complete(delivery_job.job_id, _decision(reply='reply delivered'))

    queue_after = dispatcher.queue('claude', detail=True)
    assert queue_after['agent']['mailbox_state'] == 'blocked'
    assert queue_after['agent']['queue_depth'] == 1
    assert queue_after['agent']['queued_events'][0]['event_type'] == 'task_request'

    started_after = dispatcher.tick()
    assert len(started_after) == 1
    assert started_after[0].job_id == queued_job_id


def test_dispatcher_failed_reply_delivery_requeues_original_reply_head(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-reply-delivery-failure'
    ctx = _bootstrap_test_project(project_root)
    layout = PathLayout(project_root)
    config = _provider_config('codex', 'claude')
    registry = AgentRegistry(layout, config)
    registry.upsert(_runtime('codex', project_id=ctx.project_id, layout=layout, pid=101))
    registry.upsert(_runtime('claude', project_id=ctx.project_id, layout=layout, pid=102))
    dispatcher = JobDispatcher(layout, config, registry, clock=lambda: '2026-03-30T00:00:00Z')

    reply_receipt = dispatcher.submit(
        MessageEnvelope(
            project_id=ctx.project_id,
            to_agent='codex',
            from_actor='claude',
            body='question for codex',
            task_id='task-reply-failure',
            reply_to=None,
            message_type='ask',
            delivery_scope=DeliveryScope.SINGLE,
        )
    )
    reply_job_id = reply_receipt.jobs[0].job_id
    dispatcher.tick()
    dispatcher.complete(reply_job_id, _decision(reply='reply that should stay queued'))

    started = dispatcher.tick()
    assert len(started) == 1
    delivery_job = started[0]
    assert delivery_job.request.message_type == 'reply_delivery'

    dispatcher.complete(
        delivery_job.job_id,
        CompletionDecision(
            terminal=True,
            status=CompletionStatus.FAILED,
            reason='runtime_error',
            confidence=CompletionConfidence.DEGRADED,
            reply='',
            anchor_seen=True,
            reply_started=False,
            reply_stable=False,
            provider_turn_ref='turn-reply-delivery-failed',
            source_cursor=None,
            finished_at='2026-03-30T00:00:10Z',
            diagnostics={'error_type': 'runtime_error'},
        ),
    )

    inbox = dispatcher.inbox('claude')
    assert inbox['head']['event_type'] == 'task_reply'
    assert inbox['head']['reply'] == 'reply that should stay queued'
    head_record = InboundEventStore(layout).get_latest('claude', inbox['head']['inbound_event_id'])
    assert head_record is not None
    assert delivery_job_id_from_payload(head_record.payload_ref) is None
    mailbox = MailboxStore(layout).load('claude')
    assert mailbox is not None
    assert mailbox.summary_source == 'transition-rewrite-head'
    assert delivery_job_id_from_payload(mailbox.head_payload_ref) is None


def test_dispatcher_ack_rejects_reply_after_auto_delivery_is_scheduled(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-reply-delivery-ack-reject'
    ctx = _bootstrap_test_project(project_root)
    layout = PathLayout(project_root)
    config = _provider_config('codex', 'claude')
    registry = AgentRegistry(layout, config)
    registry.upsert(_runtime('codex', project_id=ctx.project_id, layout=layout, pid=101))
    registry.upsert(_runtime('claude', project_id=ctx.project_id, layout=layout, pid=102))
    dispatcher = JobDispatcher(layout, config, registry, clock=lambda: '2026-03-30T00:00:00Z')

    reply_receipt = dispatcher.submit(
        MessageEnvelope(
            project_id=ctx.project_id,
            to_agent='codex',
            from_actor='claude',
            body='question for codex',
            task_id='task-reply-ack-reject',
            reply_to=None,
            message_type='ask',
            delivery_scope=DeliveryScope.SINGLE,
        )
    )
    reply_job_id = reply_receipt.jobs[0].job_id
    dispatcher.tick()
    dispatcher.complete(reply_job_id, _decision(reply='reply for claude'))

    dispatcher.tick()

    with pytest.raises(ValueError, match='automatic reply delivery has been scheduled'):
        dispatcher.ack_reply('claude')


def test_dispatcher_tick_auto_consumes_reply_delivery_head_with_execution_service(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-reply-delivery-autocomplete'
    ctx = _bootstrap_test_project(project_root)
    layout = PathLayout(project_root)
    config = _provider_config('codex', 'claude')
    registry = AgentRegistry(layout, config)
    registry.upsert(_runtime('codex', project_id=ctx.project_id, layout=layout, pid=101))
    registry.upsert(_runtime('claude', project_id=ctx.project_id, layout=layout, pid=102))
    execution_service = ActiveReplyDeliveryExecutionService()
    dispatcher = JobDispatcher(
        layout,
        config,
        registry,
        execution_service=execution_service,
        clock=lambda: '2026-03-30T00:00:00Z',
    )

    reply_receipt = dispatcher.submit(
        MessageEnvelope(
            project_id=ctx.project_id,
            to_agent='codex',
            from_actor='claude',
            body='question for codex',
            task_id='task-reply-autocomplete',
            reply_to=None,
            message_type='ask',
            delivery_scope=DeliveryScope.SINGLE,
        )
    )
    reply_job_id = reply_receipt.jobs[0].job_id
    dispatcher.tick()
    dispatcher.complete(reply_job_id, _decision(reply='reply for claude'))

    queued_receipt = dispatcher.submit(
        MessageEnvelope(
            project_id=ctx.project_id,
            to_agent='claude',
            from_actor='user',
            body='real work queued behind reply',
            task_id='task-behind-reply-autocomplete',
            reply_to=None,
            message_type='ask',
            delivery_scope=DeliveryScope.SINGLE,
        )
    )
    queued_job_id = queued_receipt.jobs[0].job_id

    started = dispatcher.tick()

    assert len(started) == 1
    delivery_job = started[0]
    assert delivery_job.request.message_type == 'reply_delivery'
    assert delivery_job.status.value == 'completed'
    assert delivery_job.job_id in execution_service.started
    assert delivery_job.job_id in execution_service.finished
    inbox_after = dispatcher.inbox('claude')
    assert inbox_after['item_count'] == 1
    assert inbox_after['head']['event_type'] == 'task_request'

    queue_after = dispatcher.queue('claude', detail=True)
    assert queue_after['agent']['mailbox_state'] == 'blocked'
    assert queue_after['agent']['queue_depth'] == 1
    assert queue_after['agent']['queued_events'][0]['event_type'] == 'task_request'
    assert dispatcher.get(queued_job_id).status.value == 'accepted'

    started_after = dispatcher.tick()
    assert len(started_after) == 1
    assert started_after[0].job_id == queued_job_id


def test_dispatcher_tick_keeps_live_running_reply_delivery_head_with_execution_service(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-reply-delivery-live-running'
    ctx = _bootstrap_test_project(project_root)
    layout = PathLayout(project_root)
    config = _provider_config('codex', 'claude')
    registry = AgentRegistry(layout, config)
    registry.upsert(_runtime('codex', project_id=ctx.project_id, layout=layout, pid=101))
    registry.upsert(_runtime('claude', project_id=ctx.project_id, layout=layout, pid=102))
    execution_service = DeferredReplyDeliveryExecutionService()
    dispatcher = JobDispatcher(
        layout,
        config,
        registry,
        execution_service=execution_service,
        clock=lambda: '2026-03-30T00:00:00Z',
    )

    reply_receipt = dispatcher.submit(
        MessageEnvelope(
            project_id=ctx.project_id,
            to_agent='codex',
            from_actor='claude',
            body='question for codex',
            task_id='task-reply-live-running',
            reply_to=None,
            message_type='ask',
            delivery_scope=DeliveryScope.SINGLE,
        )
    )
    reply_job_id = reply_receipt.jobs[0].job_id
    dispatcher.tick()
    dispatcher.complete(reply_job_id, _decision(reply='reply for claude'))

    started = dispatcher.tick()

    assert len(started) == 1
    delivery_job = started[0]
    assert delivery_job.request.message_type == 'reply_delivery'
    assert delivery_job.status.value == 'running'
    assert delivery_job.job_id in execution_service.started
    assert delivery_job.job_id in execution_service._active

    repaired = dispatcher.tick()

    assert repaired == ()
    still_running = dispatcher.get(delivery_job.job_id)
    assert still_running is not None
    assert still_running.status.value == 'running'
    assert dispatcher.inbox('claude')['item_count'] == 1


def test_dispatcher_tick_repairs_stale_running_reply_delivery_head_with_execution_service(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-reply-delivery-repair'
    ctx = _bootstrap_test_project(project_root)
    layout = PathLayout(project_root)
    config = _provider_config('codex', 'claude')
    registry = AgentRegistry(layout, config)
    registry.upsert(_runtime('codex', project_id=ctx.project_id, layout=layout, pid=101))
    registry.upsert(_runtime('claude', project_id=ctx.project_id, layout=layout, pid=102))
    execution_service = ActiveReplyDeliveryExecutionService()
    dispatcher = JobDispatcher(
        layout,
        config,
        registry,
        execution_service=execution_service,
        clock=lambda: '2026-03-30T00:00:00Z',
    )

    reply_receipt = dispatcher.submit(
        MessageEnvelope(
            project_id=ctx.project_id,
            to_agent='codex',
            from_actor='claude',
            body='question for codex',
            task_id='task-reply-repair',
            reply_to=None,
            message_type='ask',
            delivery_scope=DeliveryScope.SINGLE,
        )
    )
    reply_job_id = reply_receipt.jobs[0].job_id
    dispatcher.tick()
    dispatcher.complete(reply_job_id, _decision(reply='reply for claude'))

    created = prepare_reply_deliveries(dispatcher)
    assert len(created) == 1
    delivery_job = created[0]
    inbox = dispatcher.inbox('claude')
    assert inbox['head'] is not None
    head_record = InboundEventStore(layout).get_latest('claude', inbox['head']['inbound_event_id'])
    assert head_record is not None
    assert delivery_job_id_from_payload(head_record.payload_ref) == delivery_job.job_id

    dispatcher._state.remove_queued('claude', delivery_job.job_id)
    dispatcher._state.mark_active('claude', delivery_job.job_id)
    dispatcher._append_job(replace(delivery_job, status=JobStatus.RUNNING, updated_at='2026-03-30T00:00:20Z'))

    repaired = dispatcher.tick()

    stale = dispatcher.get(delivery_job.job_id)
    assert stale is not None
    assert stale.status.value == 'incomplete'
    assert any(job.request.message_type == 'reply_delivery' and job.status.value == 'completed' for job in repaired)
    assert dispatcher.inbox('claude')['item_count'] == 0


def test_dispatcher_shutdown_terminalizes_reply_delivery_without_spawning_replacement(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-reply-delivery-shutdown'
    ctx = _bootstrap_test_project(project_root)
    layout = PathLayout(project_root)
    config = _provider_config('codex', 'claude')
    registry = AgentRegistry(layout, config)
    registry.upsert(_runtime('codex', project_id=ctx.project_id, layout=layout, pid=101))
    registry.upsert(_runtime('claude', project_id=ctx.project_id, layout=layout, pid=102))
    execution_service = DeferredReplyDeliveryExecutionService()
    dispatcher = JobDispatcher(
        layout,
        config,
        registry,
        execution_service=execution_service,
        auto_reply_delivery_on_complete=True,
        clock=lambda: '2026-03-30T00:00:00Z',
    )

    reply_receipt = dispatcher.submit(
        MessageEnvelope(
            project_id=ctx.project_id,
            to_agent='codex',
            from_actor='claude',
            body='question for codex',
            task_id='task-reply-shutdown',
            reply_to=None,
            message_type='ask',
            delivery_scope=DeliveryScope.SINGLE,
        )
    )
    reply_job_id = reply_receipt.jobs[0].job_id
    dispatcher.tick()
    dispatcher.complete(reply_job_id, _decision(reply='reply for claude'))

    started = dispatcher.tick()
    assert len(started) == 1
    delivery_job = started[0]
    assert delivery_job.request.message_type == 'reply_delivery'
    assert delivery_job.status.value == 'running'

    dispatcher.disable_auto_reply_delivery()
    terminated = dispatcher.terminate_nonterminal_jobs(shutdown_reason='stop_all', forced=False)

    assert len(terminated) == 1
    terminal = dispatcher.get(delivery_job.job_id)
    assert terminal is not None
    assert terminal.status is JobStatus.INCOMPLETE
    assert terminal.terminal_decision is not None
    assert terminal.terminal_decision['reason'] == 'project_shutdown'
    latest_by_job = {
        record.job_id: record
        for record in dispatcher._job_store.list_agent('claude')
    }
    reply_delivery_jobs = [
        record
        for record in latest_by_job.values()
        if record.request.message_type == 'reply_delivery'
    ]
    pending_delivery_jobs = [
        record
        for record in reply_delivery_jobs
        if record.status in {JobStatus.ACCEPTED, JobStatus.QUEUED, JobStatus.RUNNING}
    ]
    assert [record.job_id for record in reply_delivery_jobs] == [delivery_job.job_id]
    assert pending_delivery_jobs == []
    inbox = dispatcher.inbox('claude')
    assert inbox['head'] is not None
    head = InboundEventStore(layout).get_latest('claude', inbox['head']['inbound_event_id'])
    assert head is not None
    assert head.status is InboundEventStatus.QUEUED
    assert delivery_job_id_from_payload(head.payload_ref) is None

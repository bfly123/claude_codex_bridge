from __future__ import annotations

from datetime import timedelta
from dataclasses import replace

from ccbd.api_models import DeliveryScope, JobRecord, JobStatus, MessageEnvelope, TargetKind
from ccbd.system import parse_utc_timestamp
from completion.models import CompletionDecision
from mailbox_runtime.targets import NON_AGENT_ACTORS
from message_bureau import CallbackEdgeRecord, CallbackEdgeState, MessageState, ReplyTerminalStatus

from .records import append_event, append_job, get_job
from .runtime_state import sync_runtime

CALLBACK_ROUTE_MODE = 'callback'
CALLBACK_CONTINUATION_MESSAGE_TYPE = 'callback_continuation'
DEFAULT_CALLBACK_TIMEOUT_S = 30 * 60
DEFAULT_MAX_CALLBACK_DEPTH = 5
_TERMINAL_CALLBACK_STATES = frozenset(
    {
        CallbackEdgeState.CONTINUATION_SUBMITTED,
        CallbackEdgeState.DONE,
        CallbackEdgeState.FAILED,
        CallbackEdgeState.TIMED_OUT,
    }
)


def request_callback_route(request: MessageEnvelope) -> bool:
    options = dict(getattr(request, 'route_options', None) or {})
    return str(options.get('mode') or '').strip().lower() == CALLBACK_ROUTE_MODE


def validate_nested_ask_request(dispatcher, request: MessageEnvelope) -> None:
    if not _is_plain_ask(request):
        return
    if bool(getattr(request, 'silence_on_success', False)):
        return
    parent = _active_parent_job(dispatcher, request.from_actor)
    if parent is None:
        return
    raise dispatcher._dispatch_error(
        'plain ask from an active CCB task requires --callback when the child result is needed, '
        'or --silence for independent fire-and-forget work'
    )


def register_callback_edge(dispatcher, *, request: MessageEnvelope, jobs: tuple, message_id: str, accepted_at: str) -> None:
    validate_callback_request(dispatcher, request)
    if not request_callback_route(request):
        return
    if len(jobs) != 1:
        raise dispatcher._dispatch_error('ask --callback supports exactly one target agent')
    parent = _active_parent_job(dispatcher, request.from_actor)
    parent_message = _message_for_job(dispatcher, parent)
    child = jobs[0]
    edge = CallbackEdgeRecord(
        edge_id=dispatcher._new_id('cb'),
        parent_job_id=parent.job_id,
        parent_message_id=parent_message.message_id,
        parent_agent=parent.agent_name,
        child_job_id=child.job_id,
        child_message_id=message_id,
        callback_target_agent=parent.agent_name,
        original_caller=parent.request.from_actor,
        original_task_id=parent.request.task_id or parent_message.message_id,
        state=CallbackEdgeState.PENDING,
        timeout_at=_callback_timeout_at(dispatcher, accepted_at),
        created_at=accepted_at,
        updated_at=accepted_at,
        diagnostics={
            'route_mode': CALLBACK_ROUTE_MODE,
            'child_agent': child.agent_name,
            'parent_body': _strip_ccb_guidance(parent.request.body),
            'child_body': _strip_ccb_guidance(child.request.body),
        },
    )
    dispatcher._message_bureau.record_callback_edge(edge)
    append_event(
        dispatcher,
        child,
        'callback_edge_created',
        {
            'edge_id': edge.edge_id,
            'parent_job_id': edge.parent_job_id,
            'parent_message_id': edge.parent_message_id,
            'callback_target_agent': edge.callback_target_agent,
            'original_caller': edge.original_caller,
        },
        timestamp=accepted_at,
    )


def validate_callback_request(dispatcher, request: MessageEnvelope) -> None:
    if not request_callback_route(request):
        validate_nested_ask_request(dispatcher, request)
        return
    if dispatcher._message_bureau is None:
        raise dispatcher._dispatch_error('ask --callback requires message bureau support')
    if request.delivery_scope is not DeliveryScope.SINGLE:
        raise dispatcher._dispatch_error('ask --callback supports exactly one target agent')
    parent = _active_parent_job(dispatcher, request.from_actor)
    if parent is None:
        raise dispatcher._dispatch_error('ask --callback requires an active parent job for the sender')
    if _message_for_job(dispatcher, parent) is None:
        raise dispatcher._dispatch_error('ask --callback could not resolve parent message')
    if dispatcher._message_bureau.callback_edge_for_parent_job(parent.job_id) is not None:
        raise dispatcher._dispatch_error('ask --callback allows one outstanding callback per parent job')
    _validate_callback_chain(dispatcher, parent=parent, child_agent=request.to_agent)


def _is_plain_ask(request: MessageEnvelope) -> bool:
    if str(request.message_type or '').strip().lower() != 'ask':
        return False
    return not request_callback_route(request)


def delegated_parent_edge(dispatcher, job) -> CallbackEdgeRecord | None:
    if dispatcher._message_bureau is None:
        return None
    return dispatcher._message_bureau.callback_edge_for_parent_job(job.job_id)


def callback_child_edge(dispatcher, job) -> CallbackEdgeRecord | None:
    if dispatcher._message_bureau is None:
        return None
    edge = dispatcher._message_bureau.callback_edge_for_child_job(job.job_id)
    if edge is not None:
        return edge
    message = _message_for_job(dispatcher, job)
    if message is None:
        return None
    return dispatcher._message_bureau.callback_edge_for_child_message(message.message_id)


def submit_callback_continuation(
    dispatcher,
    edge: CallbackEdgeRecord,
    *,
    child_job,
    child_reply_id: str | None,
    decision: CompletionDecision,
    finished_at: str,
) -> CallbackEdgeRecord:
    latest = dispatcher._message_bureau.callback_edge_for_child_job(child_job.job_id) or edge
    if latest.state in _TERMINAL_CALLBACK_STATES:
        return latest
    existing_continuation = _existing_continuation_job(dispatcher, latest)
    if existing_continuation is not None:
        persisted_reply = _latest_child_reply(dispatcher, latest)
        state = (
            CallbackEdgeState.DONE
            if existing_continuation.status in dispatcher._terminal_event_by_status
            else CallbackEdgeState.CONTINUATION_SUBMITTED
        )
        return dispatcher._message_bureau.update_callback_edge(
            latest,
            state=state,
            child_reply_id=child_reply_id or latest.child_reply_id or (persisted_reply.reply_id if persisted_reply else None),
            child_status=child_job.status.value,
            continuation_job_id=existing_continuation.job_id,
            continuation_message_id=latest.parent_message_id,
            updated_at=finished_at,
        )
    updated = dispatcher._message_bureau.update_callback_edge(
        latest,
        state=CallbackEdgeState.CHILD_COMPLETED,
        child_reply_id=child_reply_id,
        child_status=child_job.status.value,
        updated_at=finished_at,
    )
    try:
        continuation_job_id, continuation_message_id = _submit_continuation_job(
            dispatcher,
            request=_continuation_request(edge=updated, child_job=child_job, decision=decision),
            parent_message_id=updated.parent_message_id,
            accepted_at=finished_at,
        )
    except Exception as exc:
        return fail_callback_edge(
            dispatcher,
            updated,
            reason='callback_continuation_submit_failed',
            detail=str(exc),
            updated_at=finished_at,
        )
    final = dispatcher._message_bureau.update_callback_edge(
        updated,
        state=CallbackEdgeState.CONTINUATION_SUBMITTED,
        continuation_job_id=continuation_job_id,
        continuation_message_id=continuation_message_id,
        updated_at=finished_at,
    )
    append_event(
        dispatcher,
        child_job,
        'callback_continuation_submitted',
        {
            'edge_id': final.edge_id,
            'continuation_job_id': continuation_job_id,
            'continuation_message_id': continuation_message_id,
            'callback_target_agent': final.callback_target_agent,
        },
        timestamp=finished_at,
    )
    return final


def repair_callback_edges(dispatcher) -> tuple[CallbackEdgeRecord, ...]:
    if dispatcher._message_bureau is None:
        return ()
    repaired: list[CallbackEdgeRecord] = []
    repaired.extend(sweep_callback_timeouts(dispatcher))
    for edge in dispatcher._message_bureau.pending_callback_edges():
        latest = dispatcher._message_bureau.callback_edge(edge.edge_id) or edge
        if latest.state in _TERMINAL_CALLBACK_STATES:
            continue
        if _callback_edge_expired(latest, dispatcher._clock()):
            continue
        if latest.continuation_job_id:
            continue
        existing_continuation = _existing_continuation_job(dispatcher, latest)
        if existing_continuation is not None:
            reply = _latest_child_reply(dispatcher, latest)
            reply_job = _job_for_reply(dispatcher, reply)
            repaired.append(
                dispatcher._message_bureau.update_callback_edge(
                    latest,
                    state=CallbackEdgeState.CONTINUATION_SUBMITTED,
                    child_reply_id=latest.child_reply_id or (reply.reply_id if reply else None),
                    child_status=latest.child_status or (reply_job.status.value if reply_job else None),
                    continuation_job_id=existing_continuation.job_id,
                    continuation_message_id=latest.parent_message_id,
                    updated_at=latest.updated_at,
                )
            )
            continue
        reply = _latest_child_reply(dispatcher, latest)
        child_job = _job_for_reply(dispatcher, reply) or get_job(dispatcher, latest.child_job_id)
        decision = _decision_from_reply(reply, child_job=child_job, fallback_finished_at=latest.updated_at)
        if reply is None or child_job is None or decision is None:
            continue
        repaired.append(
            submit_callback_continuation(
                dispatcher,
                latest,
                child_job=child_job,
                child_reply_id=reply.reply_id,
                decision=decision,
                finished_at=latest.updated_at or reply.finished_at,
            )
        )
    return tuple(repaired)


def sweep_callback_timeouts(dispatcher) -> tuple[CallbackEdgeRecord, ...]:
    if dispatcher._message_bureau is None:
        return ()
    edges = dispatcher._message_bureau.pending_callback_edges()
    if not edges:
        return ()
    now = dispatcher._clock()
    expired: list[CallbackEdgeRecord] = []
    for edge in edges:
        latest = dispatcher._message_bureau.callback_edge(edge.edge_id) or edge
        if latest.state in _TERMINAL_CALLBACK_STATES:
            continue
        if not _callback_edge_expired(latest, now):
            continue
        expired.append(
            fail_callback_edge(
                dispatcher,
                latest,
                reason='callback_timeout',
                detail='callback child did not produce a continuation before timeout',
                updated_at=now,
                state=CallbackEdgeState.TIMED_OUT,
            )
        )
    return tuple(expired)


def fail_callback_edge(
    dispatcher,
    edge: CallbackEdgeRecord,
    *,
    reason: str,
    detail: str,
    updated_at: str,
    state: CallbackEdgeState = CallbackEdgeState.FAILED,
) -> CallbackEdgeRecord:
    latest = dispatcher._message_bureau.callback_edge(edge.edge_id) or edge
    if latest.state in _TERMINAL_CALLBACK_STATES:
        return latest
    failed = dispatcher._message_bureau.update_callback_edge(
        latest,
        state=state,
        child_status=latest.child_status or state.value,
        updated_at=updated_at,
        diagnostics={
            **dict(latest.diagnostics or {}),
            'failure_reason': reason,
            'failure_detail': detail,
        },
    )
    _record_callback_failure_notice(
        dispatcher,
        failed,
        reason=reason,
        detail=detail,
        updated_at=updated_at,
    )
    return failed


def mark_callback_done(dispatcher, job, *, finished_at: str) -> None:
    options = dict(getattr(job.request, 'route_options', None) or {})
    edge_id = str(options.get('callback_edge_id') or '').strip()
    if not edge_id or dispatcher._message_bureau is None:
        return
    edge = dispatcher._message_bureau.callback_edge(edge_id)
    if edge is None or edge.state in {CallbackEdgeState.DONE, CallbackEdgeState.FAILED, CallbackEdgeState.TIMED_OUT}:
        return
    dispatcher._message_bureau.update_callback_edge(
        edge,
        state=CallbackEdgeState.DONE,
        updated_at=finished_at,
    )


def mark_parent_message_waiting(dispatcher, edge: CallbackEdgeRecord, *, updated_at: str) -> None:
    if edge.state in {CallbackEdgeState.FAILED, CallbackEdgeState.TIMED_OUT, CallbackEdgeState.DONE}:
        return
    dispatcher._message_bureau.set_message_state(edge.parent_message_id, MessageState.RUNNING, updated_at=updated_at)


def delegated_terminal_job(job, edge: CallbackEdgeRecord):
    return replace(
        job,
        terminal_decision={
            **dict(job.terminal_decision or {}),
            'delegated': True,
            'suppress_reply': True,
            'callback_edge_id': edge.edge_id,
            'callback_child_job_id': edge.child_job_id,
        },
    )


def persist_delegated_terminal_job(dispatcher, job, edge: CallbackEdgeRecord, *, finished_at: str):
    delegated = delegated_terminal_job(job, edge)
    append_job(dispatcher, delegated)
    append_event(
        dispatcher,
        delegated,
        'job_delegated_callback',
        {
            'edge_id': edge.edge_id,
            'callback_child_job_id': edge.child_job_id,
            'callback_target_agent': edge.callback_target_agent,
        },
        timestamp=finished_at,
    )
    return delegated


def _submit_continuation_job(dispatcher, *, request: MessageEnvelope, parent_message_id: str, accepted_at: str) -> tuple[str, str]:
    dispatcher._registry.spec_for(request.to_agent)
    dispatcher._validate_targets_available((request.to_agent,))
    spec = dispatcher._registry.spec_for(request.to_agent)
    job_id = dispatcher._new_id('job')
    status = JobStatus.QUEUED if dispatcher._state.has_outstanding_for(TargetKind.AGENT, request.to_agent) else JobStatus.ACCEPTED
    job = JobRecord(
        job_id=job_id,
        submission_id=None,
        agent_name=request.to_agent,
        provider=spec.provider,
        provider_instance=None,
        provider_options={},
        workspace_path=None,
        target_kind=TargetKind.AGENT,
        target_name=request.to_agent,
        request=request,
        status=status,
        terminal_decision=None,
        cancel_requested_at=None,
        created_at=accepted_at,
        updated_at=accepted_at,
    )
    append_job(dispatcher, job)
    append_event(
        dispatcher,
        job,
        'job_accepted' if status is JobStatus.ACCEPTED else 'job_queued',
        {'status': status.value, 'callback_continuation': True},
        timestamp=accepted_at,
    )
    dispatcher._state.enqueue_for(job.target_kind, job.target_name, job.job_id)
    sync_runtime(dispatcher, job.agent_name)
    dispatcher._message_bureau.record_retry_attempt(parent_message_id, job, accepted_at=accepted_at)
    parent_message = dispatcher._message_bureau._message_store.get_latest(parent_message_id)
    if parent_message is not None:
        _append_submission_job(dispatcher, parent_message.submission_id, job_id=job.job_id, updated_at=accepted_at)
    return job.job_id, parent_message_id


def _append_submission_job(dispatcher, submission_id: str | None, *, job_id: str, updated_at: str) -> None:
    if not submission_id:
        return
    current = dispatcher._submission_store.get_latest(submission_id)
    if current is None:
        return
    job_ids = list(current.job_ids)
    if job_id not in job_ids:
        job_ids.append(job_id)
    dispatcher._submission_store.append(
        replace(
            current,
            job_ids=job_ids,
            updated_at=updated_at,
        )
    )


def _existing_continuation_job(dispatcher, edge: CallbackEdgeRecord):
    for job in reversed(dispatcher._job_store.list_agent(edge.callback_target_agent)):
        options = dict(getattr(job.request, 'route_options', None) or {})
        if str(options.get('callback_edge_id') or '').strip() == edge.edge_id:
            return job
    return None


def _latest_child_reply(dispatcher, edge: CallbackEdgeRecord):
    if edge.child_reply_id:
        reply = dispatcher._message_bureau._reply_store.get_latest(edge.child_reply_id)
        if reply is not None:
            return reply
    for reply in reversed(dispatcher._message_bureau._reply_store.list_message(edge.child_message_id)):
        if not bool(reply.diagnostics.get('notice')):
            return reply
    return None


def _job_for_reply(dispatcher, reply):
    if reply is None:
        return None
    attempt = dispatcher._message_bureau._attempt_store.get_latest(reply.attempt_id)
    if attempt is None:
        return None
    return get_job(dispatcher, attempt.job_id)


def _active_parent_job(dispatcher, actor: str):
    normalized = str(actor or '').strip().lower()
    if not normalized or normalized in NON_AGENT_ACTORS:
        return None
    if normalized not in dispatcher._config.agents:
        return None
    parent_job_id = dispatcher._state.active_job(normalized)
    if not parent_job_id:
        return None
    return get_job(dispatcher, parent_job_id)


def _message_for_job(dispatcher, job):
    attempt = dispatcher._message_bureau._attempt_store.get_latest_by_job_id(job.job_id)
    if attempt is None:
        return None
    return dispatcher._message_bureau._message_store.get_latest(attempt.message_id)


def _validate_callback_chain(dispatcher, *, parent, child_agent: str) -> None:
    parent_message = _message_for_job(dispatcher, parent)
    if parent_message is None:
        raise dispatcher._dispatch_error('ask --callback could not resolve parent message')
    chain = _callback_chain_for_parent(dispatcher, parent_message.message_id)
    max_depth = _max_callback_depth(dispatcher)
    next_depth = len(chain) + 1
    if next_depth > max_depth:
        raise dispatcher._dispatch_error(f'ask --callback exceeds max callback depth {max_depth}')
    actors = {str(edge.parent_agent or '').strip().lower() for edge in chain}
    actors.update(_callback_child_agent(edge) for edge in chain)
    actors.add(parent.agent_name)
    target = str(child_agent or '').strip().lower()
    if target in actors:
        raise dispatcher._dispatch_error('ask --callback cycle detected')


def _callback_chain_for_parent(dispatcher, parent_message_id: str) -> tuple[CallbackEdgeRecord, ...]:
    chain: list[CallbackEdgeRecord] = []
    seen: set[str] = set()
    message_id = parent_message_id
    while message_id and message_id not in seen:
        seen.add(message_id)
        edge = dispatcher._message_bureau.callback_edge_for_child_message(message_id)
        if edge is None:
            break
        chain.append(edge)
        message_id = edge.parent_message_id
    return tuple(chain)


def _record_callback_failure_notice(
    dispatcher,
    edge: CallbackEdgeRecord,
    *,
    reason: str,
    detail: str,
    updated_at: str,
) -> None:
    parent_job = get_job(dispatcher, edge.parent_job_id)
    if parent_job is None:
        dispatcher._message_bureau.set_message_state(edge.parent_message_id, MessageState.FAILED, updated_at=updated_at)
        return
    dispatcher._message_bureau.record_notice(
        parent_job,
        reply=_callback_failure_reply(edge=edge, reason=reason, detail=detail),
        diagnostics={
            'notice': True,
            'callback_edge_id': edge.edge_id,
            'callback_failure': True,
            'reason': reason,
            'detail': detail,
        },
        finished_at=updated_at,
        terminal_status=ReplyTerminalStatus.FAILED,
        deliver_to_actor=edge.original_caller,
    )


def _callback_failure_reply(*, edge: CallbackEdgeRecord, reason: str, detail: str) -> str:
    suffix = f': {detail}' if detail else ''
    return (
        f'CCB callback failed for delegated task {edge.child_job_id} '
        f'while continuing parent job {edge.parent_job_id}. Reason: {reason}{suffix}'
    )


def _callback_timeout_at(dispatcher, accepted_at: str) -> str:
    timeout_s = _callback_timeout_s(dispatcher)
    try:
        return (
            parse_utc_timestamp(accepted_at) + timedelta(seconds=max(0.0, timeout_s))
        ).isoformat().replace('+00:00', 'Z')
    except Exception:
        return accepted_at


def _callback_edge_expired(edge: CallbackEdgeRecord, now: str) -> bool:
    if not edge.timeout_at:
        return False
    try:
        return parse_utc_timestamp(now) >= parse_utc_timestamp(edge.timeout_at)
    except Exception:
        return False


def _callback_timeout_s(dispatcher) -> float:
    value = getattr(dispatcher._config, 'callback_timeout_s', DEFAULT_CALLBACK_TIMEOUT_S)
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return float(DEFAULT_CALLBACK_TIMEOUT_S)


def _max_callback_depth(dispatcher) -> int:
    value = getattr(dispatcher._config, 'max_callback_depth', DEFAULT_MAX_CALLBACK_DEPTH)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return DEFAULT_MAX_CALLBACK_DEPTH


def _callback_child_agent(edge: CallbackEdgeRecord) -> str:
    return str(edge.diagnostics.get('child_agent') or '').strip().lower()


def _continuation_request(*, edge: CallbackEdgeRecord, child_job, decision: CompletionDecision) -> MessageEnvelope:
    return MessageEnvelope(
        project_id=child_job.request.project_id,
        to_agent=edge.callback_target_agent,
        from_actor=edge.original_caller,
        body=_continuation_body(edge=edge, child_job=child_job, decision=decision),
        task_id=edge.original_task_id,
        reply_to=edge.parent_message_id,
        message_type=CALLBACK_CONTINUATION_MESSAGE_TYPE,
        delivery_scope=DeliveryScope.SINGLE,
        silence_on_success=False,
        route_options={
            'mode': 'callback_continuation',
            'callback_edge_id': edge.edge_id,
            'callback_parent_job_id': edge.parent_job_id,
            'callback_child_job_id': edge.child_job_id,
            'callback_child_message_id': edge.child_message_id,
        },
    )


def _continuation_body(*, edge: CallbackEdgeRecord, child_job, decision: CompletionDecision) -> str:
    original = str(edge.diagnostics.get('parent_body') or '').rstrip()
    child_task = str(edge.diagnostics.get('child_body') or '').rstrip()
    child_reply = decision.reply or ''
    parts = [
        'CCB callback continuation.',
        '',
        f'Original caller: {edge.original_caller}',
        f'Parent job: {edge.parent_job_id}',
        f'Child job: {child_job.job_id}',
        f'Child agent: {child_job.agent_name}',
        f'Child status: {child_job.status.value}',
    ]
    if original:
        parts.extend(['', 'Original task context:', original])
    if child_task:
        parts.extend(['', 'Delegated child task:', child_task])
    parts.extend(
        [
            '',
            'Child result:',
            child_reply or '(no reply body)',
            '',
            'Continue the original task using the child result. Reply to the original caller with the final result.',
        ]
    )
    return '\n'.join(parts)


def _decision_from_reply(reply, *, child_job, fallback_finished_at: str | None):
    if reply is None or child_job is None or child_job.terminal_decision is None:
        return None
    from completion.models import CompletionConfidence, CompletionStatus

    terminal = dict(child_job.terminal_decision or {})
    status = CompletionStatus(terminal.get('status') or child_job.status.value)
    confidence = CompletionConfidence(terminal.get('confidence') or 'degraded')
    return CompletionDecision(
        terminal=True,
        status=status,
        reason=terminal.get('reason') or child_job.status.value,
        confidence=confidence,
        reply=reply.reply,
        anchor_seen=bool(terminal.get('anchor_seen')),
        reply_started=bool(terminal.get('reply_started')),
        reply_stable=bool(terminal.get('reply_stable')),
        provider_turn_ref=terminal.get('provider_turn_ref'),
        source_cursor=None,
        finished_at=terminal.get('finished_at') or reply.finished_at or fallback_finished_at,
        diagnostics=dict(terminal.get('diagnostics') or {}),
    )


def _strip_ccb_guidance(body: str) -> str:
    marker = '\n\nCCB reply guidance:'
    if marker not in body:
        return body
    return body.split(marker, 1)[0].rstrip()


__all__ = [
    'CALLBACK_CONTINUATION_MESSAGE_TYPE',
    'CALLBACK_ROUTE_MODE',
    'callback_child_edge',
    'delegated_parent_edge',
    'delegated_terminal_job',
    'mark_parent_message_waiting',
    'mark_callback_done',
    'persist_delegated_terminal_job',
    'repair_callback_edges',
    'register_callback_edge',
    'request_callback_route',
    'sweep_callback_timeouts',
    'submit_callback_continuation',
    'validate_nested_ask_request',
    'validate_callback_request',
]

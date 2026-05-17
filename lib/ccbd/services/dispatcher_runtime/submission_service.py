from __future__ import annotations

from agents.models import AgentState
from ccbd.api_models import DeliveryScope, JobRecord, MessageEnvelope, TargetKind
from message_bureau import AttemptState, AttemptStore, MessageStore

from .callbacks import validate_callback_request
from .submission_models import _JobDraft, _message_for_agent, _SubmissionPlan

_TERMINAL_ATTEMPT_STATES = frozenset(
    {
        AttemptState.COMPLETED,
        AttemptState.INCOMPLETE,
        AttemptState.FAILED,
        AttemptState.CANCELLED,
        AttemptState.SUPERSEDED,
        AttemptState.DEAD_LETTER,
    }
)


def _plan_agent_submission(dispatcher, request: MessageEnvelope) -> _SubmissionPlan:
    dispatcher._validate_sender(request.from_actor)
    validate_callback_request(dispatcher, request)
    targets = dispatcher._resolve_targets(request)
    if not targets:
        raise dispatcher._dispatch_error('no eligible target agents are alive for this request')
    dispatcher._validate_targets_available(targets)
    submission_id = dispatcher._new_id('sub') if request.delivery_scope is DeliveryScope.BROADCAST else None
    drafts = _drafts_for_agents(dispatcher, request, targets)
    return _SubmissionPlan(
        project_id=request.project_id,
        from_actor=request.from_actor,
        request=request,
        task_id=request.task_id,
        drafts=tuple(drafts),
        submission_id=submission_id,
        target_scope='all' if submission_id is not None else None,
    )


def _plan_message_resubmission(dispatcher, message_id: str) -> _SubmissionPlan:
    original_message = _require_original_message(dispatcher, message_id)
    latest_attempts = _require_attempt_lineage(dispatcher, message_id, original_message.target_agents)
    _ensure_no_active_attempts(dispatcher, latest_attempts)
    jobs = _jobs_for_resubmission(dispatcher, original_message.target_agents, latest_attempts)

    request = _resubmission_request(original_message, jobs)
    dispatcher._validate_sender(request.from_actor)
    dispatcher._validate_targets_available(original_message.target_agents)

    submission_id = dispatcher._new_id('sub') if request.delivery_scope is DeliveryScope.BROADCAST else None
    return _SubmissionPlan(
        project_id=request.project_id,
        from_actor=request.from_actor,
        request=request,
        task_id=request.task_id,
        drafts=tuple(_drafts_for_agents(dispatcher, request, original_message.target_agents)),
        submission_id=submission_id,
        target_scope='all' if submission_id is not None else None,
        origin_message_id=message_id,
    )


def _resolve_retry_attempt(dispatcher, target: str):
    attempt_store = AttemptStore(dispatcher._layout)
    attempt = attempt_store.get_latest(target)
    if attempt is not None:
        return attempt
    attempt = attempt_store.get_latest_by_job_id(target)
    if attempt is not None:
        return attempt
    raise dispatcher._dispatch_error(f'retry target not found: {target}')


def _latest_attempts_by_agent(dispatcher, message_id: str) -> dict[str, object]:
    attempt_store = AttemptStore(dispatcher._layout)
    latest_by_attempt_id: dict[str, object] = {}
    for record in attempt_store.list_message(message_id):
        latest_by_attempt_id[record.attempt_id] = record
    latest_by_agent: dict[str, object] = {}
    for record in latest_by_attempt_id.values():
        current = latest_by_agent.get(record.agent_name)
        if current is None or _attempt_sort_key(record) > _attempt_sort_key(current):
            latest_by_agent[record.agent_name] = record
    return latest_by_agent


def _ensure_agent_target_ready(dispatcher, agent_name: str) -> None:
    dispatcher._registry.spec_for(agent_name)


def _drafts_for_agents(dispatcher, request: MessageEnvelope, targets) -> list[_JobDraft]:
    drafts: list[_JobDraft] = []
    for agent_name in targets:
        spec = dispatcher._registry.spec_for(agent_name)
        drafts.append(
            _JobDraft(
                agent_name=agent_name,
                provider=spec.provider,
                request=_message_for_agent(request, agent_name=agent_name),
                target_kind=TargetKind.AGENT,
                target_name=agent_name,
            )
        )
    return drafts


def _require_original_message(dispatcher, message_id: str):
    original_message = MessageStore(dispatcher._layout).get_latest(message_id)
    if original_message is None:
        raise dispatcher._dispatch_error(f'message not found: {message_id}')
    return original_message


def _require_attempt_lineage(dispatcher, message_id: str, target_agents) -> dict[str, object]:
    latest_attempts = _latest_attempts_by_agent(dispatcher, message_id)
    if not latest_attempts:
        raise dispatcher._dispatch_error(f'message has no attempts to resubmit: {message_id}')
    missing_agents = [agent_name for agent_name in target_agents if agent_name not in latest_attempts]
    if missing_agents:
        raise dispatcher._dispatch_error(f'message is missing attempt lineage for agents: {", ".join(missing_agents)}')
    return latest_attempts


def _ensure_no_active_attempts(dispatcher, latest_attempts: dict[str, object]) -> None:
    active_agents = sorted(
        agent_name
        for agent_name, attempt in latest_attempts.items()
        if attempt.attempt_state not in _TERMINAL_ATTEMPT_STATES
    )
    if active_agents:
        raise dispatcher._dispatch_error(f'message still has active attempts: {", ".join(active_agents)}')


def _jobs_for_resubmission(dispatcher, target_agents, latest_attempts: dict[str, object]) -> list[JobRecord]:
    jobs: list[JobRecord] = []
    for agent_name in target_agents:
        _ensure_agent_target_ready(dispatcher, agent_name)
        attempt = latest_attempts[agent_name]
        job = dispatcher._job_store.get_latest(agent_name, attempt.job_id)
        if job is None:
            raise dispatcher._dispatch_error(f'job not found for attempt: {attempt.attempt_id}')
        jobs.append(job)
    return jobs


def _resubmission_request(original_message, jobs: list[JobRecord]) -> MessageEnvelope:
    source = jobs[0].request
    delivery_scope = DeliveryScope.BROADCAST if len(original_message.target_agents) > 1 else DeliveryScope.SINGLE
    return MessageEnvelope(
        project_id=source.project_id,
        to_agent='all' if delivery_scope is DeliveryScope.BROADCAST else original_message.target_agents[0],
        from_actor=original_message.from_actor,
        body=source.body,
        task_id=source.task_id,
        reply_to=source.reply_to,
        message_type=source.message_type,
        delivery_scope=delivery_scope,
        silence_on_success=source.silence_on_success,
        route_options=dict(source.route_options or {}),
    )


def _attempt_sort_key(record) -> tuple:
    return (record.retry_index, record.updated_at, record.attempt_id)


__all__ = [
    '_ensure_agent_target_ready',
    '_latest_attempts_by_agent',
    '_plan_agent_submission',
    '_plan_message_resubmission',
    '_resolve_retry_attempt',
]

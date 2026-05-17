from __future__ import annotations

from collections.abc import Callable, Collection

from agents.models import AgentValidationError
from ccbd.api_models import DeliveryScope, MessageEnvelope
from mailbox_runtime.targets import NON_AGENT_ACTORS, normalize_actor_name

from .models import AskSummary

_DEFAULT_REPLY_GUIDANCE = """CCB reply guidance:
- Choose the shortest reply that still preserves the key information needed for this ask.
- Keep conclusions, blockers, risks, evidence, and next actions when they are relevant.
- For simple status checks, prefer a short status answer.
- Avoid full logs, raw output, and broad background unless the ask explicitly requires them."""

_NESTED_ASK_GUIDANCE = (
    'CCB nested ask routing: inside an active CCB task, use `ask --callback` when a child result is needed, '
    '`ask --silence` for independent no-result-needed work, and never plain nested `ask`.'
)

_COMPACT_REPLY_GUIDANCE = """CCB reply guidance:
- Actively distill the reply while preserving the key information needed for this ask.
- Decide the right compression level from the request context; do not use a fixed length target.
- Lead with the answer and omit empty or report-style sections.
- Keep blockers, decisions, risks, evidence, changed files, verification, and next actions only when they matter.
- Avoid background, raw logs, and repeated context unless they are essential to understand the result."""

_SILENT_REPLY_GUIDANCE = """CCB reply guidance:
- The caller requested silent-on-success delivery.
- Prefer the shortest useful success/failure status.
- Include details only when they are needed to explain a failure, blocker, or required next action."""

_GUIDANCE_MARKER = 'CCB reply guidance:'
_EXPLICIT_OUTPUT_HINTS = (
    'output requirements',
    'reply format',
    'response format',
    'format:',
    'only reply',
    'reply only',
    'full report',
    'detailed report',
    'verbatim',
    'do not summarize',
    'do not abbreviate',
    '完整输出',
    '不要总结',
    '不要压缩',
    '不要精简',
    '不要省略',
    '逐字返回',
    '逐字',
    '原样返回',
    '保留原文',
    '完整日志',
    '完整报告',
    '详细报告',
    '全文',
)


def submit_ask(
    context,
    command,
    *,
    load_project_config_fn: Callable,
    resolve_ask_sender_fn: Callable,
    invoke_mounted_daemon_fn: Callable,
) -> AskSummary:
    config = load_project_config_fn(context.project.project_root).config
    normalized_target = _normalize_target(command.target)
    _validate_target(normalized_target, config.agents)
    sender = resolve_ask_sender_fn(context, command.sender)
    normalized_sender = _normalize_sender(sender)
    _validate_sender(normalized_sender, config.agents)
    payload = invoke_mounted_daemon_fn(
        context,
        allow_restart_stale=True,
        request_fn=lambda client: client.submit(
            MessageEnvelope(
                project_id=context.project.project_id,
                to_agent=normalized_target,
                from_actor=normalized_sender,
                body=message_with_reply_guidance(
                    command.message,
                    message_type=command.mode or 'ask',
                    compact=bool(getattr(command, 'compact', False)),
                    silence_on_success=command.silence,
                ),
                task_id=command.task_id,
                reply_to=command.reply_to,
                message_type=command.mode or 'ask',
                delivery_scope=_delivery_scope(command.target),
                silence_on_success=command.silence,
                route_options=_route_options(command),
            )
        )
    )
    return _summary_from_payload(context.project.project_id, payload)


def _route_options(command) -> dict[str, object]:
    if not bool(getattr(command, 'callback', False)):
        return {}
    return {'mode': 'callback'}


def message_with_reply_guidance(
    message: str,
    *,
    message_type: str,
    compact: bool = False,
    silence_on_success: bool = False,
) -> str:
    if str(message_type or '').strip().lower() != 'ask':
        return message
    if _has_explicit_output_guidance(message):
        return message
    if silence_on_success:
        guidance = _SILENT_REPLY_GUIDANCE
    elif compact:
        guidance = _COMPACT_REPLY_GUIDANCE
    else:
        guidance = _DEFAULT_REPLY_GUIDANCE
    return f'{str(message).rstrip()}\n\n{guidance}\n\n{_NESTED_ASK_GUIDANCE}'


def _has_explicit_output_guidance(message: str) -> bool:
    text = str(message or '')
    lowered = text.lower()
    if _GUIDANCE_MARKER.lower() in lowered:
        return True
    return any(hint in lowered for hint in _EXPLICIT_OUTPUT_HINTS)


def _normalize_sender(value: str | None) -> str:
    try:
        return normalize_actor_name(value)
    except AgentValidationError as exc:
        raise ValueError(str(exc)) from exc


def _normalize_target(value: str | None) -> str:
    normalized = str(value or '').strip().lower()
    if normalized == 'all':
        return normalized
    return _normalize_sender(normalized)


def _validate_target(target: str, configured_agents: Collection[str]) -> None:
    if target != 'all' and target not in configured_agents:
        raise ValueError(f'unknown agent: {target}')


def _validate_sender(sender: str, configured_agents: Collection[str]) -> None:
    if sender in NON_AGENT_ACTORS:
        if sender == 'cmd':
            raise ValueError(f'unknown sender agent: {sender}')
        return
    if sender in configured_agents:
        return
    raise ValueError(f'unknown sender agent: {sender}')


def _delivery_scope(target: str | None) -> DeliveryScope:
    return DeliveryScope.BROADCAST if _normalize_target(target) == 'all' else DeliveryScope.SINGLE


def _summary_from_payload(project_id: str, payload: dict) -> AskSummary:
    if 'job_id' in payload:
        jobs = (
            {
                'job_id': payload['job_id'],
                'agent_name': payload['agent_name'],
                'target_kind': payload.get('target_kind', 'agent'),
                'target_name': payload.get('target_name', payload['agent_name']),
                'provider_instance': payload.get('provider_instance'),
                'status': payload['status'],
            },
        )
        submission_id = None
    else:
        jobs = tuple(payload.get('jobs', ()))
        submission_id = payload.get('submission_id')
    return AskSummary(project_id=project_id, submission_id=submission_id, jobs=jobs)


__all__ = ['message_with_reply_guidance', 'submit_ask']

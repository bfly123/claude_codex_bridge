from __future__ import annotations

from mailbox_kernel import InboundEventStatus, InboundEventType
from message_bureau.models import AttemptState
from message_bureau.reply_metadata import (
    reply_heartbeat_silence_seconds,
    reply_last_progress_at,
    reply_notice,
    reply_notice_kind,
)
from message_bureau.reply_payloads import reply_id_from_payload

from .common import preview_text

TERMINAL_EVENT_STATES = frozenset(
    {
        InboundEventStatus.CONSUMED,
        InboundEventStatus.SUPERSEDED,
        InboundEventStatus.ABANDONED,
    }
)
TERMINAL_ATTEMPT_STATES = frozenset(
    {
        AttemptState.COMPLETED,
        AttemptState.INCOMPLETE,
        AttemptState.FAILED,
        AttemptState.CANCELLED,
        AttemptState.SUPERSEDED,
        AttemptState.DEAD_LETTER,
    }
)


def pending_event_records(service, agent_name: str) -> list:
    _discard_stale_head_events(service, agent_name)
    latest_by_id: dict[str, object] = {}
    order: list[str] = []
    for record in service._inbound_store.list_agent(agent_name):
        if record.inbound_event_id not in latest_by_id:
            order.append(record.inbound_event_id)
        latest_by_id[record.inbound_event_id] = record
    return [
        latest_by_id[inbound_event_id]
        for inbound_event_id in order
        if latest_by_id[inbound_event_id].status not in TERMINAL_EVENT_STATES
        and _event_is_live(service, latest_by_id[inbound_event_id])
    ]


def reply_for_event(service, event):
    if event.event_type is not InboundEventType.TASK_REPLY:
        return None
    reply_id = reply_id_from_payload(event.payload_ref)
    if not reply_id:
        return None
    return service._reply_store.get_latest(reply_id)


def _discard_stale_head_events(service, agent_name: str) -> None:
    abandon = getattr(service._mailbox_kernel, 'abandon', None)
    if abandon is None:
        return
    while True:
        head = service._mailbox_kernel.head_pending_event(agent_name)
        if head is None or _event_is_live(service, head):
            return
        abandon(agent_name, head.inbound_event_id, finished_at=service._clock())


def _event_is_live(service, event) -> bool:
    message = service._message_store.get_latest(event.message_id)
    if message is None:
        return False
    attempt = service._attempt_store.get_latest(event.attempt_id) if event.attempt_id else None
    if event.attempt_id and attempt is None:
        return False
    if event.event_type is InboundEventType.TASK_REQUEST and attempt is not None:
        return attempt.attempt_state not in TERMINAL_ATTEMPT_STATES
    if event.event_type is InboundEventType.TASK_REPLY and reply_for_event(service, event) is None:
        return False
    return True


def pending_events(service, agent_name: str) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for position, record in enumerate(pending_event_records(service, agent_name), start=1):
        attempt = service._attempt_store.get_latest(record.attempt_id) if record.attempt_id else None
        message = service._message_store.get_latest(record.message_id)
        replies = service._reply_store.list_message(record.message_id)
        events.append(
            {
                'position': position,
                'inbound_event_id': record.inbound_event_id,
                'event_type': record.event_type.value,
                'status': record.status.value,
                'priority': record.priority,
                'message_id': record.message_id,
                'message_state': message.message_state.value if message is not None else None,
                'attempt_id': record.attempt_id,
                'attempt_state': attempt.attempt_state.value if attempt is not None else None,
                'job_id': attempt.job_id if attempt is not None else None,
                'reply_count': len(replies),
                'created_at': record.created_at,
                'started_at': record.started_at,
                'finished_at': record.finished_at,
            }
        )
    return events


def inbox_item_summary(service, event, *, position: int) -> dict[str, object]:
    attempt = service._attempt_store.get_latest(event.attempt_id) if event.attempt_id else None
    message = service._message_store.get_latest(event.message_id)
    reply = reply_for_event(service, event)
    item = {
        'position': position,
        'inbound_event_id': event.inbound_event_id,
        'event_type': event.event_type.value,
        'status': event.status.value,
        'priority': event.priority,
        'message_id': event.message_id,
        'message_state': message.message_state.value if message is not None else None,
        'attempt_id': event.attempt_id,
        'attempt_state': attempt.attempt_state.value if attempt is not None else None,
        'job_id': attempt.job_id if attempt is not None else None,
        'source_actor': reply.agent_name if reply is not None else (message.from_actor if message is not None else None),
        'created_at': event.created_at,
        'started_at': event.started_at,
        'finished_at': event.finished_at,
    }
    if reply is not None:
        item.update(
            {
                'reply_id': reply.reply_id,
                'reply_terminal_status': reply.terminal_status.value,
                'reply_finished_at': reply.finished_at,
                'reply_preview': preview_text(reply.reply),
                'reply_notice': reply_notice(reply),
                'reply_notice_kind': reply_notice_kind(reply),
                'reply_last_progress_at': reply_last_progress_at(reply),
                'reply_heartbeat_silence_seconds': reply_heartbeat_silence_seconds(reply),
            }
        )
        if position == 1:
            item['reply'] = reply.reply
    return item


__all__ = [
    'TERMINAL_EVENT_STATES',
    'inbox_item_summary',
    'pending_event_records',
    'pending_events',
    'reply_for_event',
]

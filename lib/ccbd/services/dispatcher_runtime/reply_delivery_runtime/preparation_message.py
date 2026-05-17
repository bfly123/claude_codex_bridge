from __future__ import annotations

from ccbd.api_models import DeliveryScope, MessageEnvelope, TargetKind
from mailbox_kernel import InboundEventStatus
from message_bureau.models import AttemptRecord, AttemptState, MessageRecord, MessageState

from ..records import append_event
from ..submission_models import _JobDraft
from ..submission_recording import _build_job_record, _enqueue_submitted_job
from .constants import (
    REPLY_DELIVERY_INBOUND_EVENT_OPTION,
    REPLY_DELIVERY_MESSAGE_TYPE,
    REPLY_DELIVERY_PROVIDER_OPTION,
    REPLY_DELIVERY_REPLY_ID_OPTION,
)
from .formatting import format_reply_delivery_body
from .head import rewrite_reply_head


def resolve_workspace_path(dispatcher, agent_name: str, runtime) -> str:
    if runtime is not None and runtime.workspace_path:
        return runtime.workspace_path
    return str(dispatcher._layout.workspace_path(agent_name))


def build_reply_delivery_request(dispatcher, *, reply, project_id: str, agent_name: str) -> MessageEnvelope:
    return MessageEnvelope(
        project_id=project_id,
        to_agent=agent_name,
        from_actor='system',
        body=format_reply_delivery_body(dispatcher, reply),
        task_id=f'reply:{reply.reply_id}',
        reply_to=None,
        message_type=REPLY_DELIVERY_MESSAGE_TYPE,
        delivery_scope=DeliveryScope.SINGLE,
        route_options={},
    )


def append_reply_delivery_message(dispatcher, *, reply, agent_name: str, accepted_at: str, spec, job_id: str) -> None:
    message_id = dispatcher._new_id('msg')
    attempt_id = dispatcher._new_id('att')
    dispatcher._message_bureau._message_store.append(
        MessageRecord(
            message_id=message_id,
            origin_message_id=reply.message_id,
            from_actor='system',
            target_scope='single',
            target_agents=(agent_name,),
            message_class=REPLY_DELIVERY_MESSAGE_TYPE,
            reply_policy={'mode': 'none', 'expected_reply_count': 0},
            retry_policy={'mode': 'manual'},
            priority=10,
            payload_ref=f'reply:{reply.reply_id}',
            submission_id=None,
            created_at=accepted_at,
            updated_at=accepted_at,
            message_state=MessageState.QUEUED,
        )
    )
    dispatcher._message_bureau._attempt_store.append(
        AttemptRecord(
            attempt_id=attempt_id,
            message_id=message_id,
            agent_name=agent_name,
            provider=spec.provider,
            job_id=job_id,
            retry_index=0,
            health_snapshot_ref=None,
            started_at=accepted_at,
            updated_at=accepted_at,
            attempt_state=AttemptState.PENDING,
        )
    )


def record_reply_delivery_scheduled(dispatcher, job, *, inbound_event_id: str, reply_id: str, accepted_at: str) -> None:
    append_event(
        dispatcher,
        job,
        'reply_delivery_scheduled',
        {
            'inbound_event_id': inbound_event_id,
            'reply_id': reply_id,
        },
        timestamp=accepted_at,
    )


def build_reply_delivery_job(dispatcher, *, agent_name: str, head, reply, accepted_at: str, project_id: str):
    spec = dispatcher._registry.spec_for(agent_name)
    runtime = dispatcher._registry.get(agent_name)
    workspace_path = resolve_workspace_path(dispatcher, agent_name, runtime)
    request = build_reply_delivery_request(
        dispatcher,
        reply=reply,
        project_id=project_id,
        agent_name=agent_name,
    )
    job_id = dispatcher._new_id('job')
    draft = _JobDraft(
        agent_name=agent_name,
        provider=spec.provider,
        request=request,
        target_kind=TargetKind.AGENT,
        target_name=agent_name,
        provider_options={
            'no_wrap': True,
            REPLY_DELIVERY_PROVIDER_OPTION: True,
            REPLY_DELIVERY_INBOUND_EVENT_OPTION: head.inbound_event_id,
            REPLY_DELIVERY_REPLY_ID_OPTION: reply.reply_id,
        },
        workspace_path=workspace_path,
    )
    job, status = _build_job_record(
        dispatcher,
        draft,
        job_id=job_id,
        submission_id=None,
        accepted_at=accepted_at,
    )
    _enqueue_submitted_job(dispatcher, job, status=status, accepted_at=accepted_at)
    append_reply_delivery_message(
        dispatcher,
        reply=reply,
        agent_name=agent_name,
        accepted_at=accepted_at,
        spec=spec,
        job_id=job_id,
    )
    rewrite_reply_head(
        dispatcher,
        head,
        reply_id=reply.reply_id,
        delivery_job_id=job_id,
        status=InboundEventStatus.QUEUED,
        updated_at=accepted_at,
        clear_progress=True,
    )
    record_reply_delivery_scheduled(
        dispatcher,
        job,
        inbound_event_id=head.inbound_event_id,
        reply_id=reply.reply_id,
        accepted_at=accepted_at,
    )
    return job


__all__ = [
    'build_reply_delivery_job',
]

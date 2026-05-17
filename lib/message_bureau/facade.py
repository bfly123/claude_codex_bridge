from __future__ import annotations

from ccbd.api_models import JobRecord, MessageEnvelope
from completion.models import CompletionDecision
from mailbox_runtime.targets import known_mailbox_targets
from mailbox_kernel import (
    DeliveryLeaseStore,
    InboundEventStore,
    MailboxKernelService,
    MailboxStore,
)
from storage.paths import PathLayout

from .callback_edges import CallbackEdgeRecord, CallbackEdgeState, CallbackEdgeStore
from .facade_recording import (
    claimable_request_job_ids as _claimable_request_job_ids_impl,
    mark_attempt_started as _mark_attempt_started_impl,
    record_notice as _record_notice_impl,
    record_attempt_terminal as _record_attempt_terminal_impl,
    record_reply as _record_reply_impl,
    record_retry_attempt as _record_retry_attempt_impl,
    record_submission as _record_submission_impl,
    record_terminal as _record_terminal_impl,
)
from .models import ReplyTerminalStatus
from .service_state import MessageBureauFacadeRuntimeState, MessageBureauFacadeStateMixin
from .store import AttemptStore, MessageStore, ReplyStore


class MessageBureauFacade(MessageBureauFacadeStateMixin):
    def __init__(
        self,
        layout: PathLayout,
        *,
        config=None,
        clock,
        message_store: MessageStore | None = None,
        attempt_store: AttemptStore | None = None,
        reply_store: ReplyStore | None = None,
        callback_edge_store: CallbackEdgeStore | None = None,
        mailbox_store: MailboxStore | None = None,
        inbound_store: InboundEventStore | None = None,
        lease_store: DeliveryLeaseStore | None = None,
        mailbox_kernel: MailboxKernelService | None = None,
    ) -> None:
        message_store = message_store or MessageStore(layout)
        attempt_store = attempt_store or AttemptStore(layout)
        reply_store = reply_store or ReplyStore(layout)
        callback_edge_store = callback_edge_store or CallbackEdgeStore(layout)
        mailbox_store = mailbox_store or MailboxStore(layout)
        inbound_store = inbound_store or InboundEventStore(layout)
        lease_store = lease_store or DeliveryLeaseStore(layout)
        self._runtime_state = MessageBureauFacadeRuntimeState(
            layout=layout,
            clock=clock,
            known_agents=frozenset(getattr(config, 'agents', {}).keys()),
            known_mailboxes=known_mailbox_targets(config),
            message_store=message_store,
            attempt_store=attempt_store,
            reply_store=reply_store,
            callback_edge_store=callback_edge_store,
            mailbox_store=mailbox_store,
            inbound_store=inbound_store,
            lease_store=lease_store,
            mailbox_kernel=mailbox_kernel or MailboxKernelService(
                layout,
                clock=clock,
                mailbox_store=mailbox_store,
                inbound_store=inbound_store,
                lease_store=lease_store,
            ),
        )

    def record_submission(
        self,
        request: MessageEnvelope,
        jobs: tuple[JobRecord, ...],
        *,
        submission_id: str | None,
        accepted_at: str,
        origin_message_id: str | None = None,
    ) -> str | None:
        return _record_submission_impl(
            self,
            request,
            jobs,
            submission_id=submission_id,
            accepted_at=accepted_at,
            origin_message_id=origin_message_id,
        )

    def claimable_request_job_ids(self, agent_name: str) -> tuple[str, ...]:
        return _claimable_request_job_ids_impl(self, agent_name)

    def mark_attempt_started(self, job: JobRecord, *, started_at: str) -> None:
        _mark_attempt_started_impl(self, job, started_at=started_at)

    def record_attempt_terminal(self, job: JobRecord, decision: CompletionDecision, *, finished_at: str) -> None:
        _record_attempt_terminal_impl(self, job, decision, finished_at=finished_at)

    def record_reply(
        self,
        job: JobRecord,
        decision: CompletionDecision,
        *,
        finished_at: str,
        deliver_to_caller: bool = True,
    ) -> str | None:
        return _record_reply_impl(
            self,
            job,
            decision,
            finished_at=finished_at,
            deliver_to_caller=deliver_to_caller,
        )

    def record_notice(
        self,
        job: JobRecord,
        *,
        reply: str,
        diagnostics: dict[str, object] | None,
        finished_at: str,
        terminal_status: ReplyTerminalStatus = ReplyTerminalStatus.INCOMPLETE,
        deliver_to_actor: str | None = None,
    ) -> str | None:
        return _record_notice_impl(
            self,
            job,
            reply=reply,
            diagnostics=diagnostics,
            finished_at=finished_at,
            terminal_status=terminal_status,
            deliver_to_actor=deliver_to_actor,
        )

    def record_terminal(
        self,
        job: JobRecord,
        decision: CompletionDecision,
        *,
        finished_at: str,
        deliver_to_caller: bool = True,
        record_reply: bool = True,
    ) -> str | None:
        return _record_terminal_impl(
            self,
            job,
            decision,
            finished_at=finished_at,
            deliver_to_caller=deliver_to_caller,
            record_reply_enabled=record_reply,
        )

    def record_retry_attempt(self, message_id: str, job: JobRecord, *, accepted_at: str) -> str:
        return _record_retry_attempt_impl(self, message_id, job, accepted_at=accepted_at)

    def set_message_state(self, message_id: str, next_state, *, updated_at: str) -> None:
        from .facade_state import set_message_state

        set_message_state(self, message_id, next_state, updated_at=updated_at)

    def record_callback_edge(self, edge: CallbackEdgeRecord) -> None:
        self._callback_edge_store.append(edge)

    def callback_edge_for_child_job(self, child_job_id: str) -> CallbackEdgeRecord | None:
        return self._callback_edge_store.get_latest_for_child_job(child_job_id)

    def callback_edge_for_child_message(self, child_message_id: str) -> CallbackEdgeRecord | None:
        return self._callback_edge_store.get_latest_for_child_message(child_message_id)

    def callback_edge_for_parent_job(self, parent_job_id: str) -> CallbackEdgeRecord | None:
        return self._callback_edge_store.get_latest_for_parent_job(parent_job_id)

    def update_callback_edge(self, edge: CallbackEdgeRecord, **changes) -> CallbackEdgeRecord:
        return self._callback_edge_store.update(edge, **changes)

    def callback_edge(self, edge_id: str) -> CallbackEdgeRecord | None:
        return self._callback_edge_store.get_latest(edge_id)

    def pending_callback_edges(self) -> tuple[CallbackEdgeRecord, ...]:
        latest: dict[str, CallbackEdgeRecord] = {}
        for edge in self._callback_edge_store.list_all():
            latest[edge.edge_id] = edge
        return tuple(
            edge
            for edge in latest.values()
            if edge.state in {CallbackEdgeState.PENDING, CallbackEdgeState.CHILD_COMPLETED}
        )


__all__ = ['MessageBureauFacade']

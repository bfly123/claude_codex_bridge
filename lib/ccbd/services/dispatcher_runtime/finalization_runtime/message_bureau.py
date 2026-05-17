from __future__ import annotations

from dataclasses import replace

from completion.models import CompletionDecision
from message_bureau import CallbackEdgeState

from ..callbacks import (
    callback_child_edge,
    delegated_parent_edge,
    mark_callback_done,
    mark_parent_message_waiting,
    persist_delegated_terminal_job,
    submit_callback_continuation,
)
from ..reply_delivery import is_reply_delivery_job
from .message_bureau_persistence import persist_reply_decision
from .message_bureau_retry import reply_decision_without_automatic_retry, schedule_automatic_retry


def record_message_bureau_completion(
    dispatcher,
    current,
    terminal,
    decision: CompletionDecision,
    *,
    finished_at: str,
    prior_snapshot,
) -> tuple[object, CompletionDecision, bool]:
    reply_decision = decision
    if dispatcher._message_bureau is None:
        return terminal, reply_decision, False

    dispatcher._message_bureau.record_attempt_terminal(terminal, decision, finished_at=finished_at)
    if is_reply_delivery_job(current):
        return terminal, reply_decision, False
    parent_edge = delegated_parent_edge(dispatcher, terminal)
    if parent_edge is not None and parent_edge.state not in {
        CallbackEdgeState.FAILED,
        CallbackEdgeState.TIMED_OUT,
        CallbackEdgeState.DONE,
    }:
        terminal = persist_delegated_terminal_job(dispatcher, terminal, parent_edge, finished_at=finished_at)
        mark_parent_message_waiting(dispatcher, parent_edge, updated_at=finished_at)
        return terminal, reply_decision, False
    reply_decision, retry_scheduled = schedule_automatic_retry(
        dispatcher,
        current,
        terminal,
        decision,
        finished_at=finished_at,
    )
    if retry_scheduled:
        return terminal, decision, True
    if reply_decision is decision:
        reply_decision = reply_decision_without_automatic_retry(
            dispatcher,
            current,
            terminal,
            decision,
            finished_at=finished_at,
        )
    if reply_decision is not decision:
        terminal = persist_reply_decision(
            dispatcher,
            current,
            terminal,
            reply_decision,
            prior_snapshot=prior_snapshot,
            finished_at=finished_at,
        )
    child_edge = callback_child_edge(dispatcher, terminal)
    if child_edge is not None:
        reply_id = dispatcher._message_bureau.record_reply(
            _job_with_unsilenced_reply(terminal),
            reply_decision,
            finished_at=finished_at,
            deliver_to_caller=False,
        )
        submit_callback_continuation(
            dispatcher,
            child_edge,
            child_job=terminal,
            child_reply_id=reply_id,
            decision=reply_decision,
            finished_at=finished_at,
        )
        mark_callback_done(dispatcher, terminal, finished_at=finished_at)
        return terminal, reply_decision, False
    dispatcher._message_bureau.record_reply(terminal, reply_decision, finished_at=finished_at)
    mark_callback_done(dispatcher, terminal, finished_at=finished_at)
    return terminal, reply_decision, False


def _job_with_unsilenced_reply(job):
    if not bool(getattr(job.request, 'silence_on_success', False)):
        return job
    return replace(job, request=replace(job.request, silence_on_success=False))


__all__ = ['record_message_bureau_completion']

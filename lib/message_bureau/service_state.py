from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MessageBureauFacadeRuntimeState:
    layout: object
    clock: object
    known_agents: frozenset[str]
    known_mailboxes: object
    message_store: object
    attempt_store: object
    reply_store: object
    callback_edge_store: object
    mailbox_store: object
    inbound_store: object
    lease_store: object
    mailbox_kernel: object


class MessageBureauFacadeStateMixin:
    @property
    def _layout(self):
        return self._runtime_state.layout

    @property
    def _clock(self):
        return self._runtime_state.clock

    @property
    def _known_agents(self):
        return self._runtime_state.known_agents

    @property
    def _known_mailboxes(self):
        return self._runtime_state.known_mailboxes

    @property
    def _message_store(self):
        return self._runtime_state.message_store

    @property
    def _attempt_store(self):
        return self._runtime_state.attempt_store

    @property
    def _reply_store(self):
        return self._runtime_state.reply_store

    @property
    def _callback_edge_store(self):
        return self._runtime_state.callback_edge_store

    @property
    def _mailbox_store(self):
        return self._runtime_state.mailbox_store

    @property
    def _inbound_store(self):
        return self._runtime_state.inbound_store

    @property
    def _lease_store(self):
        return self._runtime_state.lease_store

    @property
    def _mailbox_kernel(self):
        return self._runtime_state.mailbox_kernel


@dataclass
class MessageBureauControlRuntimeState:
    layout: object
    config: object
    known_mailboxes: object
    clock: object
    mailbox_store: object
    inbound_store: object
    lease_store: object
    message_store: object
    attempt_store: object
    reply_store: object
    job_store: object
    submission_store: object
    mailbox_kernel: object


class MessageBureauControlStateMixin:
    @property
    def _layout(self):
        return self._runtime_state.layout

    @property
    def _config(self):
        return self._runtime_state.config

    @property
    def _known_mailboxes(self):
        return self._runtime_state.known_mailboxes

    @property
    def _clock(self):
        return self._runtime_state.clock

    @property
    def _mailbox_store(self):
        return self._runtime_state.mailbox_store

    @property
    def _inbound_store(self):
        return self._runtime_state.inbound_store

    @property
    def _lease_store(self):
        return self._runtime_state.lease_store

    @property
    def _message_store(self):
        return self._runtime_state.message_store

    @property
    def _attempt_store(self):
        return self._runtime_state.attempt_store

    @property
    def _reply_store(self):
        return self._runtime_state.reply_store

    @property
    def _job_store(self):
        return self._runtime_state.job_store

    @property
    def _submission_store(self):
        return self._runtime_state.submission_store

    @property
    def _mailbox_kernel(self):
        return self._runtime_state.mailbox_kernel


__all__ = [
    'MessageBureauControlRuntimeState',
    'MessageBureauControlStateMixin',
    'MessageBureauFacadeRuntimeState',
    'MessageBureauFacadeStateMixin',
]

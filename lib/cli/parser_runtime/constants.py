from __future__ import annotations

SUBCOMMANDS = {
    'ask',
    'cancel',
    'cleanup',
    'kill',
    'ps',
    'ping',
    'watch',
    'pend',
    'queue',
    'trace',
    'resubmit',
    'retry',
    'wait-any',
    'wait-all',
    'wait-quorum',
    'inbox',
    'ack',
    'logs',
    'doctor',
    'repair',
    'config',
    'fault',
}

ASK_OPTIONS_WITH_VALUES = {'--task-id', '--reply-to', '--mode'}
ASK_FLAG_OPTIONS = {'--callback', '--compact', '--silence'}
WAIT_COMMAND_TO_MODE = {
    'wait-any': 'any',
    'wait-all': 'all',
    'wait-quorum': 'quorum',
}
ASK_JOB_ACTIONS = {'get', 'cancel'}


__all__ = [
    'ASK_FLAG_OPTIONS',
    'ASK_JOB_ACTIONS',
    'ASK_OPTIONS_WITH_VALUES',
    'SUBCOMMANDS',
    'WAIT_COMMAND_TO_MODE',
]

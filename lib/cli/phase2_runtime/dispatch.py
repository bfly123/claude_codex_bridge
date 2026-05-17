from __future__ import annotations

from .handlers_ask import handle_ask
from .handlers_mailbox import (
    handle_ack,
    handle_cancel,
    handle_inbox,
    handle_pend,
    handle_ping,
    handle_queue,
    handle_resubmit,
    handle_retry,
    handle_trace,
    handle_wait,
    handle_watch,
)
from .handlers_ops import (
    handle_cleanup,
    handle_doctor,
    handle_fault_arm,
    handle_fault_clear,
    handle_fault_list,
    handle_kill,
    handle_logs,
    handle_ps,
)
from .handlers_start import handle_config_validate, handle_start


_HANDLERS = {
    'ack': handle_ack,
    'ask': handle_ask,
    'cancel': handle_cancel,
    'cleanup': handle_cleanup,
    'config-validate': handle_config_validate,
    'doctor': handle_doctor,
    'fault-arm': handle_fault_arm,
    'fault-clear': handle_fault_clear,
    'fault-list': handle_fault_list,
    'inbox': handle_inbox,
    'kill': handle_kill,
    'logs': handle_logs,
    'pend': handle_pend,
    'ping': handle_ping,
    'ps': handle_ps,
    'queue': handle_queue,
    'resubmit': handle_resubmit,
    'retry': handle_retry,
    'start': handle_start,
    'trace': handle_trace,
    'wait': handle_wait,
    'watch': handle_watch,
}


def dispatch(context, command, out, services) -> int:
    handler = _HANDLERS.get(command.kind)
    if handler is None:
        print(f'command_status: unsupported\nerror: unsupported v2 command: {command.kind}', file=out)
        return 2
    return handler(context, command, out, services)


__all__ = ['dispatch']

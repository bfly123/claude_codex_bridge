from __future__ import annotations

from typing import Union

from .models_faults import ParsedFaultArmCommand, ParsedFaultClearCommand, ParsedFaultListCommand
from .models_mailbox import (
    ParsedAckCommand,
    ParsedAskCommand,
    ParsedCancelCommand,
    ParsedInboxCommand,
    ParsedPendCommand,
    ParsedQueueCommand,
    ParsedResubmitCommand,
    ParsedRetryCommand,
    ParsedTraceCommand,
    ParsedWaitCommand,
    ParsedWatchCommand,
)
from .models_start import (
    ParsedCleanupCommand,
    ParsedConfigValidateCommand,
    ParsedDoctorCommand,
    ParsedKillCommand,
    ParsedLogsCommand,
    ParsedPingCommand,
    ParsedPsCommand,
    ParsedStartCommand,
)


ParsedCommand = Union[
    ParsedAckCommand,
    ParsedAskCommand,
    ParsedCancelCommand,
    ParsedCleanupCommand,
    ParsedConfigValidateCommand,
    ParsedDoctorCommand,
    ParsedFaultArmCommand,
    ParsedFaultClearCommand,
    ParsedFaultListCommand,
    ParsedInboxCommand,
    ParsedKillCommand,
    ParsedLogsCommand,
    ParsedPendCommand,
    ParsedPingCommand,
    ParsedPsCommand,
    ParsedQueueCommand,
    ParsedResubmitCommand,
    ParsedRetryCommand,
    ParsedStartCommand,
    ParsedTraceCommand,
    ParsedWaitCommand,
    ParsedWatchCommand,
]

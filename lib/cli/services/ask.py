from __future__ import annotations

import time
from pathlib import Path
from typing import TextIO
import os

from agents.config_loader import load_project_config
from ccbd.socket_client import CcbdClientError
from cli.ask_sender import resolve_ask_sender
from cli.render import render_watch_batch, write_lines

from .ask_runtime import AskSummary, exit_code_for_ask_status, write_ask_output
from .ask_runtime.submission import submit_ask as _submit_ask_impl
from .ask_runtime.watch import watch_ask_job as _watch_ask_job_impl
from .daemon import CcbdServiceError, connect_mounted_daemon, invoke_mounted_daemon


def watch_timeout_seconds() -> float:
    raw = str(os.environ.get("CCB_WATCH_TIMEOUT_S") or "3600").strip()
    try:
        return float(raw)
    except ValueError:
        return 3600.0


def watch_poll_interval_seconds() -> float:
    raw = str(os.environ.get("CCB_WATCH_POLL_INTERVAL_S") or "0.1").strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 0.1


def submit_ask(context, command) -> AskSummary:
    return _submit_ask_impl(
        context,
        command,
        load_project_config_fn=load_project_config,
        resolve_ask_sender_fn=resolve_ask_sender,
        invoke_mounted_daemon_fn=invoke_mounted_daemon,
    )


def watch_ask_job(
    context,
    job_id: str,
    out: TextIO,
    *,
    timeout: float | None,
    emit_output: bool,
):
    return _watch_ask_job_impl(
        context,
        job_id,
        out,
        timeout=timeout,
        emit_output=emit_output,
        connect_mounted_daemon_fn=connect_mounted_daemon,
        reconnect_error_classes=(CcbdClientError, CcbdServiceError),
        monotonic_fn=time.monotonic,
        sleep_fn=time.sleep,
        poll_interval_seconds_fn=watch_poll_interval_seconds,
        timeout_seconds_fn=watch_timeout_seconds,
        render_watch_batch_fn=render_watch_batch,
        write_lines_fn=write_lines,
    )


__all__ = [
    'AskSummary',
    'exit_code_for_ask_status',
    'submit_ask',
    'watch_ask_job',
    'watch_poll_interval_seconds',
    'watch_timeout_seconds',
    'write_ask_output',
]

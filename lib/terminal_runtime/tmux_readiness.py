from __future__ import annotations

import os
import shlex

from terminal_runtime.env import env_float as _env_float_impl
from terminal_runtime.tmux import tmux_base

_TMUX_TRANSIENT_SERVER_ERROR_MARKERS = (
    'fork failed',
    'no server running',
    'server exited unexpectedly',
)
_TMUX_ABSENT_SERVER_ERROR_MARKERS = (
    'no server running',
)
_TMUX_MISSING_SESSION_ERROR_MARKERS = (
    "can't find session",
    'session not found',
)
_TMUX_OBJECT_READY_TIMEOUT_S = 3.0
_TMUX_OBJECT_READY_POLL_INTERVAL_S = 0.05


class TmuxTransientServerUnavailable(RuntimeError):
    """tmux server/socket exists as authority, but is not ready for control-plane work yet."""

    def __init__(
        self,
        message: str,
        *,
        args: list[str] | tuple[str, ...] | None = None,
        detail: str | None = None,
        socket_path: str | None = None,
        command: list[str] | tuple[str, ...] | None = None,
    ) -> None:
        self.message = str(message or '').strip() or 'tmux server unavailable'
        self.tmux_args = tuple(str(item) for item in (args or ()))
        self.detail = str(detail or '').strip()
        self.socket_path = str(socket_path or '').strip() or None
        self.command = tuple(str(item) for item in (command or ()))
        if self.detail or self.socket_path or self.command or self.tmux_args:
            super().__init__(
                tmux_command_failure_message(
                    self.message,
                    args=self.tmux_args,
                    detail=self.detail,
                    socket_path=self.socket_path,
                    command=self.command,
                )
            )
        else:
            super().__init__(self.message)


class TmuxCommandError(RuntimeError):
    """A tmux command failed with command/socket context preserved for diagnostics."""

    def __init__(
        self,
        message: str,
        *,
        args: list[str] | tuple[str, ...] | None = None,
        detail: str | None = None,
        socket_path: str | None = None,
        command: list[str] | tuple[str, ...] | None = None,
    ) -> None:
        self.message = str(message or '').strip() or 'tmux command failed'
        self.tmux_args = tuple(str(item) for item in (args or ()))
        self.detail = str(detail or '').strip()
        self.socket_path = str(socket_path or '').strip() or None
        self.command = tuple(str(item) for item in (command or ()))
        super().__init__(
            tmux_command_failure_message(
                self.message,
                args=self.tmux_args,
                detail=self.detail,
                socket_path=self.socket_path,
                command=self.command,
            )
        )


def tmux_failure_detail(cp: object, args: list[str] | tuple[str, ...] | None = None) -> str:
    stderr = str(getattr(cp, 'stderr', '') or '').strip()
    stdout = str(getattr(cp, 'stdout', '') or '').strip()
    if stderr or stdout:
        return stderr or stdout
    if args:
        return f'tmux command failed: {" ".join(str(item) for item in args)}'
    return 'tmux command failed'


def tmux_command_failure_message(
    message: str,
    *,
    args: list[str] | tuple[str, ...] | None = None,
    detail: str | None = None,
    socket_path: str | None = None,
    command: list[str] | tuple[str, ...] | None = None,
) -> str:
    base = str(message or '').strip() or 'tmux command failed'
    parts = [base]
    socket_text = str(socket_path or '').strip()
    if socket_text:
        parts.append(f'tmux_socket_path={socket_text}')
        parts.append(f'tmux_socket_path_bytes={len(os.fsencode(socket_text))}')
    command_text = _tmux_command_text(args=args, socket_path=socket_text or None, command=command)
    if command_text:
        parts.append(f'tmux_command={command_text!r}')
    detail_text = _single_line_detail(detail)
    if detail_text and detail_text not in base:
        parts.append(f'tmux_detail={detail_text!r}')
    return '; '.join(parts)


def _tmux_command_text(
    *,
    args: list[str] | tuple[str, ...] | None,
    socket_path: str | None,
    command: list[str] | tuple[str, ...] | None,
) -> str:
    if command:
        items = [str(item) for item in command]
    else:
        items = tmux_base(socket_path=socket_path)
        items.extend(str(item) for item in (args or ()))
    return shlex.join(items) if items else ''


def _single_line_detail(detail: str | None) -> str:
    lines = [line.strip() for line in str(detail or '').splitlines() if line.strip()]
    return ' | '.join(lines)


def is_tmux_transient_server_error_text(text: str) -> bool:
    normalized = str(text or '').strip().lower()
    if not normalized:
        return False
    return any(marker in normalized for marker in _TMUX_TRANSIENT_SERVER_ERROR_MARKERS)


def is_tmux_transient_server_error(exc: BaseException) -> bool:
    if isinstance(exc, TmuxTransientServerUnavailable):
        return True
    return is_tmux_transient_server_error_text(str(exc))


def is_tmux_absent_server_text(text: str) -> bool:
    normalized = str(text or '').strip().lower()
    if not normalized:
        return False
    return any(marker in normalized for marker in _TMUX_ABSENT_SERVER_ERROR_MARKERS)


def is_tmux_missing_session_text(text: str) -> bool:
    normalized = str(text or '').strip().lower()
    if not normalized:
        return False
    return any(marker in normalized for marker in _TMUX_MISSING_SESSION_ERROR_MARKERS)


def tmux_object_ready_timeout_s(timeout_s: float | None = None) -> float:
    if timeout_s is not None:
        return max(0.0, float(timeout_s))
    return _env_float_impl('CCB_TMUX_OBJECT_READY_TIMEOUT_S', _TMUX_OBJECT_READY_TIMEOUT_S)


def tmux_object_ready_poll_interval_s() -> float:
    return max(0.0, _env_float_impl('CCB_TMUX_OBJECT_READY_POLL_INTERVAL_S', _TMUX_OBJECT_READY_POLL_INTERVAL_S))


__all__ = [
    'is_tmux_absent_server_text',
    'TmuxCommandError',
    'TmuxTransientServerUnavailable',
    'is_tmux_missing_session_text',
    'is_tmux_transient_server_error',
    'is_tmux_transient_server_error_text',
    'tmux_command_failure_message',
    'tmux_object_ready_poll_interval_s',
    'tmux_object_ready_timeout_s',
    'tmux_failure_detail',
]

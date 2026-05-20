from __future__ import annotations

from dataclasses import dataclass
import os
import shutil
import subprocess
import time

from cli.context import CliContext
from ccbd.socket_client import CcbdClient, CcbdClientError
from terminal_runtime.tmux import tmux_base
from .daemon_runtime.policy import (
    FOREGROUND_ATTACH_RPC_TIMEOUT_S,
    FOREGROUND_ATTACH_TARGET_READY_TIMEOUT_S,
)

_ATTACH_ESTABLISH_TIMEOUT_S = 1.5
_ATTACH_ESTABLISH_POLL_INTERVAL_S = 0.05
_ATTACH_TARGET_READY_TIMEOUT_S = FOREGROUND_ATTACH_TARGET_READY_TIMEOUT_S
_ATTACH_TARGET_READY_POLL_INTERVAL_S = 0.05
_MIN_ATTACH_RPC_TIMEOUT_S = 0.1


@dataclass(frozen=True)
class ForegroundAttachSummary:
    project_id: str
    tmux_socket_path: str
    tmux_session_name: str


class ForegroundAttachError(RuntimeError):
    pass


def attach_started_project_namespace(context: CliContext) -> ForegroundAttachSummary:
    if shutil.which('tmux') is None:
        raise ForegroundAttachError('tmux is required for interactive `ccb`')
    client = _foreground_attach_client(context)
    env = _attach_env()
    payload = _wait_for_attach_target(client, env=env)
    tmux_socket_path = str(payload.get('namespace_tmux_socket_path') or '').strip()
    tmux_session_name = str(payload.get('namespace_tmux_session_name') or '').strip()
    summary = ForegroundAttachSummary(
        project_id=context.project.project_id,
        tmux_socket_path=tmux_socket_path,
        tmux_session_name=tmux_session_name,
    )
    attach = subprocess.Popen(
        _tmux_cmd(tmux_socket_path, 'attach-session', '-t', tmux_session_name),
        env=env,
    )
    attached = _wait_for_attach_established(
        attach,
        tmux_socket_path=tmux_socket_path,
        tmux_session_name=tmux_session_name,
        env=env,
    )
    if attached:
        _best_effort_refresh_attached_client(
            tmux_socket_path,
            tmux_session_name,
            client_pid=attach.pid,
            env=env,
        )
    returncode = attach.wait()
    if attached:
        return summary
    if returncode != 0 and not _tmux_has_session(tmux_socket_path, tmux_session_name, env=env):
        raise ForegroundAttachError('project namespace session exited before foreground attach completed')
    raise ForegroundAttachError('failed to attach project namespace after successful `ccb` start')


def _wait_for_attach_established(
    attach: subprocess.Popen[bytes] | subprocess.Popen[str],
    *,
    tmux_socket_path: str,
    tmux_session_name: str,
    env: dict[str, str],
) -> bool:
    deadline = time.monotonic() + _ATTACH_ESTABLISH_TIMEOUT_S
    while True:
        if _tmux_client_pid_attached(
            tmux_socket_path,
            tmux_session_name,
            client_pid=attach.pid,
            env=env,
        ):
            return True
        if attach.poll() is not None:
            return False
        if time.monotonic() >= deadline:
            return True
        time.sleep(_ATTACH_ESTABLISH_POLL_INTERVAL_S)


def _tmux_client_pid_attached(
    tmux_socket_path: str,
    tmux_session_name: str,
    *,
    client_pid: int,
    env: dict[str, str],
) -> bool:
    return client_pid in _tmux_list_client_pids(
        tmux_socket_path,
        tmux_session_name,
        env=env,
    )


def _wait_for_attach_target(client, *, env: dict[str, str]) -> dict[str, object]:
    deadline = time.monotonic() + _ATTACH_TARGET_READY_TIMEOUT_S
    attempts = 0
    ping_successes = 0
    last_error = _attach_target_unavailable_error(
        attempts=attempts,
        timeout_s=_ATTACH_TARGET_READY_TIMEOUT_S,
    )
    while True:
        remaining_s = deadline - time.monotonic()
        if remaining_s < _MIN_ATTACH_RPC_TIMEOUT_S:
            raise ForegroundAttachError(last_error)
        attempt_timeout_s = min(FOREGROUND_ATTACH_RPC_TIMEOUT_S, remaining_s)
        try:
            attempts += 1
            payload = _client_for_attach_attempt(client, timeout_s=attempt_timeout_s).ping('ccbd')
        except CcbdClientError as exc:
            last_error = _attach_ping_timeout_error(
                exc,
                attempts=attempts,
                timeout_s=_ATTACH_TARGET_READY_TIMEOUT_S,
                rpc_timeout_s=attempt_timeout_s,
            )
        else:
            ping_successes += 1
            ready, error = _attach_target_ready(payload, env=env)
            if ready:
                return payload
            last_error = _attach_namespace_timeout_error(
                error,
                attempts=attempts,
                ping_successes=ping_successes,
                timeout_s=_ATTACH_TARGET_READY_TIMEOUT_S,
            )
        if time.monotonic() >= deadline:
            raise ForegroundAttachError(last_error)
        time.sleep(min(_ATTACH_TARGET_READY_POLL_INTERVAL_S, max(0.0, deadline - time.monotonic())))


def _attach_target_ready(payload: dict[str, object], *, env: dict[str, str]) -> tuple[bool, str]:
    tmux_socket_path = str(payload.get('namespace_tmux_socket_path') or '').strip()
    tmux_session_name = str(payload.get('namespace_tmux_session_name') or '').strip()
    workspace_window_name = str(payload.get('namespace_workspace_window_name') or '').strip()
    ui_attachable = bool(payload.get('namespace_ui_attachable'))
    if not tmux_socket_path or not tmux_session_name or not ui_attachable:
        return False, 'project namespace is not attachable after successful `ccb` start'
    if not _tmux_has_session(tmux_socket_path, tmux_session_name, env=env):
        return False, 'project namespace session is missing after successful `ccb` start'
    if workspace_window_name and not _tmux_select_window(
        tmux_socket_path,
        f'{tmux_session_name}:{workspace_window_name}',
        env=env,
    ):
        return False, 'project namespace workspace window is missing after successful `ccb` start'
    return True, ''


def _client_for_attach_attempt(client, *, timeout_s: float):
    with_timeout = getattr(client, 'with_timeout', None)
    if callable(with_timeout):
        return with_timeout(timeout_s)
    return client


def _attach_target_unavailable_error(*, attempts: int, timeout_s: float) -> str:
    return (
        'foreground attach timed out: project namespace did not become '
        f'attachable within {timeout_s:.1f}s after successful `ccb` start '
        f'(attempts={attempts})'
    )


def _attach_ping_timeout_error(
    exc: Exception,
    *,
    attempts: int,
    timeout_s: float,
    rpc_timeout_s: float,
) -> str:
    detail = str(exc or '').strip() or type(exc).__name__
    return (
        'foreground attach timed out: ccbd did not respond to ping '
        f'within {timeout_s:.1f}s after successful `ccb` start '
        f'(rpc_timeout={rpc_timeout_s:.1f}s, attempts={attempts}, last_error={detail})'
    )


def _attach_namespace_timeout_error(
    error: str,
    *,
    attempts: int,
    ping_successes: int,
    timeout_s: float,
) -> str:
    detail = str(error or '').strip() or 'project namespace is not attachable'
    return (
        'foreground attach timed out: ccbd is responsive but project namespace '
        f'was not attachable within {timeout_s:.1f}s after successful `ccb` start '
        f'(attempts={attempts}, ping_successes={ping_successes}, last_error={detail})'
    )


def _tmux_list_client_pids(
    tmux_socket_path: str,
    tmux_session_name: str,
    *,
    env: dict[str, str],
) -> tuple[int, ...]:
    probe = subprocess.run(
        _tmux_cmd(tmux_socket_path, 'list-clients', '-t', tmux_session_name, '-F', '#{client_pid}'),
        check=False,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    if probe.returncode != 0:
        return ()
    client_pids: list[int] = []
    for line in (probe.stdout or '').splitlines():
        value = line.strip()
        if not value:
            continue
        try:
            client_pids.append(int(value))
        except ValueError:
            continue
    return tuple(client_pids)


def _tmux_client_tty(
    tmux_socket_path: str,
    tmux_session_name: str,
    *,
    client_pid: int,
    env: dict[str, str],
) -> str | None:
    probe = subprocess.run(
        _tmux_cmd(tmux_socket_path, 'list-clients', '-t', tmux_session_name, '-F', '#{client_pid}\t#{client_tty}'),
        check=False,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    if probe.returncode != 0:
        return None
    for line in (probe.stdout or '').splitlines():
        pid_text, _sep, tty_text = line.partition('\t')
        try:
            listed_pid = int(pid_text.strip())
        except ValueError:
            continue
        if listed_pid != client_pid:
            continue
        tty = tty_text.strip()
        return tty or None
    return None


def _best_effort_refresh_attached_client(
    tmux_socket_path: str,
    tmux_session_name: str,
    *,
    client_pid: int,
    env: dict[str, str],
) -> None:
    client_tty = _tmux_client_tty(
        tmux_socket_path,
        tmux_session_name,
        client_pid=client_pid,
        env=env,
    )
    if not client_tty:
        return
    try:
        subprocess.run(
            _tmux_cmd(tmux_socket_path, 'refresh-client', '-t', client_tty),
            check=False,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return


def _foreground_attach_client(context: CliContext):
    try:
        return _build_foreground_attach_client(context.paths.ccbd_socket_path)
    except CcbdClientError as exc:
        raise ForegroundAttachError(
            'foreground attach failed: ccbd client is unavailable '
            f'after successful `ccb` start: {exc}'
        ) from exc


def _build_foreground_attach_client(socket_path):
    return CcbdClient(socket_path, timeout_s=FOREGROUND_ATTACH_RPC_TIMEOUT_S)


def _attach_env() -> dict[str, str]:
    env = dict(os.environ)
    env.pop('TMUX', None)
    env.pop('TMUX_PANE', None)
    return env


def _tmux_cmd(tmux_socket_path: str, *args: str) -> list[str]:
    return [*tmux_base(socket_path=tmux_socket_path), *args]


def _tmux_has_session(tmux_socket_path: str, tmux_session_name: str, *, env: dict[str, str]) -> bool:
    probe = subprocess.run(
        _tmux_cmd(tmux_socket_path, 'has-session', '-t', tmux_session_name),
        check=False,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return probe.returncode == 0


def _tmux_select_window(tmux_socket_path: str, target: str, *, env: dict[str, str]) -> bool:
    probe = subprocess.run(
        _tmux_cmd(tmux_socket_path, 'select-window', '-t', target),
        check=False,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return probe.returncode == 0


__all__ = [
    'ForegroundAttachError',
    'ForegroundAttachSummary',
    'attach_started_project_namespace',
]

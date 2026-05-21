from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable

from terminal_runtime.tmux_readiness import (
    TmuxCommandError,
    TmuxTransientServerUnavailable,
    is_tmux_absent_server_text,
    is_tmux_missing_session_text,
    is_tmux_transient_server_error_text,
    tmux_command_failure_message,
    tmux_object_ready_poll_interval_s,
    tmux_object_ready_timeout_s,
    tmux_failure_detail,
)
from terminal_runtime.placeholders import pane_placeholder_argv


@dataclass(frozen=True)
class TmuxWindowRecord:
    window_id: str | None
    window_name: str
    active: bool = False


def build_backend(backend_factory, *, socket_path: str):
    try:
        return backend_factory(socket_path=socket_path)
    except TypeError:
        return backend_factory()


def prepare_server(backend, *, timeout_s: float | None = None) -> None:
    _tmux_run_ready(
        backend,
        ['start-server'],
        failure_message='failed to prepare tmux server',
        timeout_s=timeout_s,
    )


def ensure_server_policy(backend, *, timeout_s: float | None = None) -> None:
    policies = [
        (
            ['set-option', '-g', 'destroy-unattached', 'off'],
            'failed to persist tmux destroy-unattached policy',
        ),
        (
            ['set-option', '-g', 'mouse', 'on'],
            'failed to enable tmux mouse support',
        ),
        (
            ['set-window-option', '-g', 'mode-keys', 'vi'],
            'failed to enable vi copy-mode keys',
        ),
        (
            ['set-option', '-g', 'history-limit', '50000'],
            'failed to set tmux history limit',
        ),
    ]
    for args, failure_message in policies:
        _tmux_run_ready(
            backend,
            args,
            failure_message=failure_message,
            timeout_s=timeout_s,
        )


def create_session(
    backend,
    *,
    session_name: str,
    project_root,
    window_name: str | None = None,
    terminal_size: tuple[int, int] | None = None,
    timeout_s: float | None = None,
) -> None:
    width, height = _resolved_session_size(terminal_size)
    args = [
        'new-session',
        '-d',
        '-x',
        str(width),
        '-y',
        str(height),
        '-s',
        session_name,
    ]
    if str(window_name or '').strip():
        args.extend(['-n', str(window_name).strip()])
    args.extend(
        [
            '-c',
            str(project_root),
            *pane_placeholder_argv(),
        ]
    )
    _tmux_run_ready(
        backend,
        args,
        failure_message=f'failed to create tmux session {session_name!r}',
        timeout_s=timeout_s,
    )


def _resolved_session_size(terminal_size: tuple[int, int] | None) -> tuple[int, int]:
    default = (160, 48)
    if terminal_size is None:
        return default
    try:
        width = int(terminal_size[0])
        height = int(terminal_size[1])
    except Exception:
        return default
    if width <= 0 or height <= 0:
        return default
    return width, height


def session_window_target(session_name: str, window_name: str | None = None) -> str:
    session_text = str(session_name or '').strip()
    window_text = str(window_name or '').strip()
    if not session_text:
        raise ValueError('session_name cannot be empty')
    if not window_text:
        return session_text
    return f'{session_text}:{window_text}'


def list_windows(backend, session_name: str, *, timeout_s: float | None = None) -> tuple[TmuxWindowRecord, ...]:
    result = _tmux_run_ready(
        backend,
        ['list-windows', '-t', session_name, '-F', '#{window_id}\t#{window_name}\t#{window_active}'],
        failure_message=f'failed to list tmux windows for session {session_name!r}',
        timeout_s=timeout_s,
    )
    windows: list[TmuxWindowRecord] = []
    for line in (result.stdout or '').splitlines():
        parts = line.split('\t')
        if len(parts) != 3:
            continue
        window_id = (parts[0] or '').strip() or None
        window_name = (parts[1] or '').strip()
        if not window_name:
            continue
        windows.append(
            TmuxWindowRecord(
                window_id=window_id,
                window_name=window_name,
                active=(parts[2] or '').strip() in {'1', 'true', 'True'},
            )
        )
    return tuple(windows)


def find_window(backend, *, session_name: str, window_name: str, timeout_s: float | None = None) -> TmuxWindowRecord | None:
    target_name = str(window_name or '').strip()
    if not target_name:
        return None
    if timeout_s is not None:
        for record in list_windows(backend, session_name, timeout_s=timeout_s):
            if record.window_name == target_name:
                return record
        return None
    for record in list_windows(backend, session_name):
        if record.window_name == target_name:
            return record
    return None


def create_window(backend, *, session_name: str, window_name: str, project_root, select: bool = False, timeout_s: float | None = None) -> TmuxWindowRecord:
    _tmux_run_ready(
        backend,
        [
            'new-window',
            '-d',
            '-t',
            session_name,
            '-n',
            window_name,
            '-c',
            str(project_root),
            *pane_placeholder_argv(),
        ],
        failure_message=f'failed to create tmux window {window_name!r} for session {session_name!r}',
        timeout_s=timeout_s,
    )
    record = wait_for_window(backend, session_name=session_name, window_name=window_name, timeout_s=timeout_s)
    if record is None:
        raise RuntimeError(f'failed to resolve tmux window {window_name!r} for session {session_name!r}')
    if select:
        select_window(
            backend,
            target=session_window_target(session_name, record.window_id or window_name),
        )
    return record


def ensure_window(backend, *, session_name: str, window_name: str, project_root, select: bool = False, timeout_s: float | None = None) -> TmuxWindowRecord:
    record = find_window(backend, session_name=session_name, window_name=window_name, timeout_s=timeout_s)
    if record is None:
        record = create_window(
            backend,
            session_name=session_name,
            window_name=window_name,
            project_root=project_root,
            select=select,
            timeout_s=timeout_s,
        )
    elif select:
        select_window(
            backend,
            target=session_window_target(session_name, record.window_id or window_name),
        )
    return record


def rename_window(backend, *, target: str, new_name: str, timeout_s: float | None = None) -> None:
    _tmux_run_ready(
        backend,
        ['rename-window', '-t', target, new_name],
        failure_message=f'failed to rename tmux window target {target!r} to {new_name!r}',
        timeout_s=timeout_s,
    )
    session_name, _sep, _old_name = target.partition(':')
    resolved_session_name = session_name.strip()
    if resolved_session_name and wait_for_window(backend, session_name=resolved_session_name, window_name=new_name, timeout_s=timeout_s) is None:
        raise RuntimeError(f'failed to observe renamed tmux window {new_name!r} for session {resolved_session_name!r}')


def kill_window(backend, *, target: str, timeout_s: float | None = None) -> None:
    _tmux_run_ready(
        backend,
        ['kill-window', '-t', target],
        failure_message=f'failed to kill tmux window target {target!r}',
        timeout_s=timeout_s,
    )


def session_alive(backend, session_name: str, *, timeout_s: float | None = None) -> bool:
    runner = getattr(backend, '_tmux_run', None)
    if not callable(runner):
        checker = getattr(backend, 'is_alive', None)
        if not callable(checker):
            return False
        try:
            return bool(checker(session_name))
        except Exception:
            return False
    return bool(
        _wait_until_ready(
            lambda: _session_alive_once(backend, session_name),
            failure_message=f'failed to inspect tmux session {session_name!r}',
            timeout_s=timeout_s,
        )
    )


def session_root_pane(backend, session_name: str, *, timeout_s: float | None = None) -> str:
    return window_root_pane(backend, target_window=session_name, timeout_s=timeout_s)


def window_root_pane(backend, *, target_window: str, timeout_s: float | None = None) -> str:
    pane_id = wait_for_root_pane(backend, target_window=target_window, timeout_s=timeout_s)
    if not pane_id.startswith('%'):
        raise RuntimeError(f'failed to resolve root pane for tmux target {target_window!r}')
    return pane_id


def kill_server(backend) -> bool:
    try:
        backend._tmux_run(['kill-server'], check=False, capture=True)  # type: ignore[attr-defined]
        return True
    except Exception:
        return False


def wait_for_window(
    backend,
    *,
    session_name: str,
    window_name: str,
    timeout_s: float | None = None,
) -> TmuxWindowRecord | None:
    return _wait_until(
        lambda: find_window(backend, session_name=session_name, window_name=window_name, timeout_s=None),
        timeout_s=timeout_s,
        failure_message=f'failed to observe tmux window {window_name!r} for session {session_name!r}',
    )


def select_window(backend, *, target: str) -> None:
    _wait_until_ready(
        lambda: _tmux_run_ready(
            backend,
            ['select-window', '-t', target],
            failure_message=f'failed to select tmux window target {target!r}',
            timeout_s=0.0,
        ),
        failure_message=f'failed to select tmux window target {target!r}',
    )


def wait_for_root_pane(backend, *, target_window: str, timeout_s: float | None = None) -> str:
    pane_id = _wait_until(
        lambda: _root_pane_once(backend, target_window=target_window),
        timeout_s=timeout_s,
        failure_message=f'failed to resolve root pane for tmux target {target_window!r}',
    )
    if pane_id is None:
        raise RuntimeError(f'failed to resolve root pane for tmux target {target_window!r}')
    return pane_id


def _root_pane_once(backend, *, target_window: str) -> str | None:
    result = _tmux_run_once(
        backend,
        ['list-panes', '-t', target_window, '-F', '#{pane_id}'],
    )
    if result is None:
        return None
    pane_id = ((result.stdout or '').splitlines() or [''])[0].strip()
    return pane_id or None


def _tmux_run_ready(
    backend,
    args: list[str],
    *,
    failure_message: str,
    timeout_s: float | None = None,
):
    return _wait_until_ready(
        lambda: _tmux_run_checked(backend, args),
        failure_message=failure_message,
        timeout_s=timeout_s,
    )


def _tmux_run_once(backend, args: list[str]):
    try:
        return _tmux_run_checked(backend, args)
    except TmuxTransientServerUnavailable:
        raise
    except Exception:
        return None


def _tmux_run_checked(backend, args: list[str]):
    result = backend._tmux_run(args, check=False, capture=True)  # type: ignore[attr-defined]
    if int(getattr(result, 'returncode', 1) or 0) == 0:
        return result
    detail = tmux_failure_detail(result, args)
    socket_path = str(getattr(backend, '_socket_path', '') or getattr(backend, 'socket_path', '') or '').strip() or None
    command = None
    tmux_base = getattr(backend, '_tmux_base', None)
    if callable(tmux_base):
        try:
            command = [*tmux_base(), *args]
        except Exception:
            command = None
    if is_tmux_transient_server_error_text(detail):
        raise TmuxTransientServerUnavailable(
            'tmux server unavailable',
            args=args,
            detail=detail,
            socket_path=socket_path,
            command=command,
        )
    raise TmuxCommandError(
        detail,
        args=args,
        detail=detail,
        socket_path=socket_path,
        command=command,
    )


def _wait_until(
    probe: Callable[[], object | None],
    *,
    timeout_s: float | None = None,
    failure_message: str | None = None,
):
    deadline = time.monotonic() + _tmux_object_ready_timeout_s(timeout_s)
    last_transient: TmuxTransientServerUnavailable | None = None
    while True:
        try:
            value = probe()
        except TmuxTransientServerUnavailable as exc:
            last_transient = exc
            value = None
        if value is not None:
            return value
        if time.monotonic() >= deadline:
            if last_transient is not None and failure_message:
                raise TmuxTransientServerUnavailable(failure_message) from last_transient
            return None
        time.sleep(_tmux_object_ready_poll_interval_s())


def _wait_until_ready(action: Callable[[], object], *, failure_message: str, timeout_s: float | None = None) -> object:
    deadline = time.monotonic() + _tmux_object_ready_timeout_s(timeout_s)
    last_error: Exception | None = None
    while True:
        try:
            return action()
        except Exception as exc:
            last_error = exc
        if time.monotonic() >= deadline:
            break
        time.sleep(_tmux_object_ready_poll_interval_s())
    if last_error is not None:
        detail = getattr(last_error, 'detail', None) or str(last_error)
        if isinstance(last_error, TmuxTransientServerUnavailable):
            raise TmuxTransientServerUnavailable(
                failure_message,
                detail=detail,
                socket_path=getattr(last_error, 'socket_path', None),
                command=getattr(last_error, 'command', None),
                args=getattr(last_error, 'tmux_args', None),
            ) from last_error
        raise RuntimeError(
            tmux_command_failure_message(
                failure_message,
                detail=detail,
                socket_path=getattr(last_error, 'socket_path', None),
                command=getattr(last_error, 'command', None),
                args=getattr(last_error, 'tmux_args', None),
            )
        ) from last_error
    raise RuntimeError(failure_message)


def _session_alive_once(backend, session_name: str) -> bool:
    result = backend._tmux_run(  # type: ignore[attr-defined]
        ['has-session', '-t', session_name],
        check=False,
        capture=True,
    )
    if int(getattr(result, 'returncode', 1) or 0) == 0:
        return True
    stderr = str(getattr(result, 'stderr', '') or '').strip()
    stdout = str(getattr(result, 'stdout', '') or '').strip()
    detail = stderr or stdout
    if is_tmux_absent_server_text(detail):
        return False
    if is_tmux_transient_server_error_text(detail):
        raise TmuxTransientServerUnavailable(detail)
    if not detail or is_tmux_missing_session_text(detail):
        return False
    raise RuntimeError(detail)


def _tmux_object_ready_timeout_s(timeout_s: float | None = None) -> float:
    return tmux_object_ready_timeout_s(timeout_s)


def _tmux_object_ready_poll_interval_s() -> float:
    return tmux_object_ready_poll_interval_s()


__all__ = [
    'build_backend',
    'create_session',
    'create_window',
    'ensure_server_policy',
    'ensure_window',
    'find_window',
    'kill_window',
    'kill_server',
    'list_windows',
    'prepare_server',
    'rename_window',
    'session_alive',
    'session_root_pane',
    'session_window_target',
    'select_window',
    'TmuxCommandError',
    'TmuxTransientServerUnavailable',
    'TmuxWindowRecord',
    'wait_for_root_pane',
    'wait_for_window',
    'window_root_pane',
]

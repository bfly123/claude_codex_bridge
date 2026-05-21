from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ccbd.services.project_namespace_runtime.backend import (
    create_window,
    create_session,
    ensure_server_policy,
    ensure_window,
    find_window,
    list_windows,
    prepare_server,
    session_alive,
    wait_for_root_pane,
)
from terminal_runtime.tmux_readiness import TmuxTransientServerUnavailable


class _FlakyBackend:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self._remaining_failures: dict[tuple[str, ...], int] = {}
        self.session_created = False
        self.require_session_for_server_policy = False
        self.missing_session_stderr: str | None = None

    def fail_once(self, *args: str) -> None:
        self._remaining_failures[tuple(args)] = 1

    def _tmux_run(self, args, *, check=False, capture=False, timeout=None):
        del check, capture, timeout
        key = tuple(str(item) for item in args)
        self.calls.append(key)
        if key[:1] == ('new-session',):
            self.session_created = True
        remaining = int(self._remaining_failures.get(key, 0))
        if remaining > 0:
            self._remaining_failures[key] = remaining - 1
            return subprocess.CompletedProcess(
                ['tmux', *key],
                1,
                stdout='',
                stderr='no server running on /tmp/ccb-runtime/test.sock\n',
            )
        if key == ('set-option', '-g', 'destroy-unattached', 'off') and self.require_session_for_server_policy and not self.session_created:
            return subprocess.CompletedProcess(
                ['tmux', *key],
                1,
                stdout='',
                stderr='no server running on /tmp/ccb-runtime/test.sock\n',
            )
        if key[:1] == ('list-windows',):
            return subprocess.CompletedProcess(
                ['tmux', *key],
                0,
                stdout='@1\tcmd\t1\n@2\tworkspace\t0\n',
                stderr='',
            )
        if key[:2] == ('has-session', '-t'):
            missing_stderr = self.missing_session_stderr or f"can't find session: {key[2]}\n"
            return subprocess.CompletedProcess(
                ['tmux', *key],
                0 if self.session_created else 1,
                stdout='',
                stderr='' if self.session_created else missing_stderr,
            )
        if key[:2] == ('list-panes', '-t'):
            return subprocess.CompletedProcess(
                ['tmux', *key],
                0,
                stdout='%7\n',
                stderr='',
            )
        return subprocess.CompletedProcess(['tmux', *key], 0, stdout='', stderr='')


def test_prepare_server_then_create_session_and_server_policy_retry_transient_tmux_failures(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv('CCB_TMUX_OBJECT_READY_POLL_INTERVAL_S', '0')
    backend = _FlakyBackend()
    backend.fail_once('start-server')
    backend.fail_once('set-option', '-g', 'destroy-unattached', 'off')
    backend.fail_once(
        'new-session',
        '-d',
        '-x',
        '160',
        '-y',
        '48',
        '-s',
        'ccb-proj',
        '-n',
        'cmd',
        '-c',
        str(tmp_path),
        'sh',
        '-lc',
        'while :; do sleep 3600; done',
    )

    prepare_server(backend)
    create_session(backend, session_name='ccb-proj', project_root=tmp_path, window_name='cmd')
    ensure_server_policy(backend)

    assert backend.calls.count(('start-server',)) == 2
    assert backend.calls.count(('set-option', '-g', 'destroy-unattached', 'off')) == 2
    assert backend.calls.count(
        (
            'new-session',
            '-d',
            '-x',
            '160',
            '-y',
            '48',
            '-s',
            'ccb-proj',
            '-n',
            'cmd',
            '-c',
            str(tmp_path),
            'sh',
            '-lc',
            'while :; do sleep 3600; done',
        )
    ) == 2


def test_ensure_server_policy_applies_interactive_tmux_defaults(monkeypatch) -> None:
    monkeypatch.setenv('CCB_TMUX_OBJECT_READY_POLL_INTERVAL_S', '0')
    backend = _FlakyBackend()

    ensure_server_policy(backend)

    assert ('set-option', '-g', 'destroy-unattached', 'off') in backend.calls
    assert ('set-option', '-g', 'mouse', 'on') in backend.calls
    assert ('set-window-option', '-g', 'mode-keys', 'vi') in backend.calls
    assert ('set-option', '-g', 'history-limit', '50000') in backend.calls


def test_prepare_server_accepts_fast_probe_timeout(monkeypatch) -> None:
    monkeypatch.setenv('CCB_TMUX_OBJECT_READY_POLL_INTERVAL_S', '0')
    backend = _FlakyBackend()

    prepare_server(backend, timeout_s=0.0)

    assert backend.calls == [('start-server',)]


def test_prepare_server_does_not_require_server_policy_before_session_exists(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv('CCB_TMUX_OBJECT_READY_POLL_INTERVAL_S', '0')
    backend = _FlakyBackend()
    backend.require_session_for_server_policy = True

    prepare_server(backend)
    create_session(backend, session_name='ccb-proj', project_root=tmp_path, window_name='cmd')
    ensure_server_policy(backend)

    assert backend.calls[0] == ('start-server',)
    assert ('set-option', '-g', 'destroy-unattached', 'off') not in backend.calls[:2]
    assert backend.calls[-4:] == [
        ('set-option', '-g', 'destroy-unattached', 'off'),
        ('set-option', '-g', 'mouse', 'on'),
        ('set-window-option', '-g', 'mode-keys', 'vi'),
        ('set-option', '-g', 'history-limit', '50000'),
    ]


def test_list_windows_retries_transient_tmux_failures(monkeypatch) -> None:
    monkeypatch.setenv('CCB_TMUX_OBJECT_READY_POLL_INTERVAL_S', '0')
    backend = _FlakyBackend()
    backend.fail_once('list-windows', '-t', 'ccb-proj', '-F', '#{window_id}\t#{window_name}\t#{window_active}')

    windows = list_windows(backend, 'ccb-proj')

    assert [(window.window_id, window.window_name, window.active) for window in windows] == [
        ('@1', 'cmd', True),
        ('@2', 'workspace', False),
    ]
    assert backend.calls.count(('list-windows', '-t', 'ccb-proj', '-F', '#{window_id}\t#{window_name}\t#{window_active}')) == 2


def test_session_alive_retries_transient_tmux_failures(monkeypatch) -> None:
    monkeypatch.setenv('CCB_TMUX_OBJECT_READY_POLL_INTERVAL_S', '0')
    backend = _FlakyBackend()
    backend.session_created = True

    original_tmux_run = backend._tmux_run
    state = {'remaining': 1}

    def _tmux_run(args, *, check=False, capture=False, timeout=None):
        if tuple(str(item) for item in args) == ('has-session', '-t', 'ccb-proj') and state['remaining'] > 0:
            state['remaining'] -= 1
            backend.calls.append(tuple(str(item) for item in args))
            return subprocess.CompletedProcess(
                ['tmux', *args],
                1,
                stdout='',
                stderr='fork failed: resource temporarily unavailable\n',
            )
        return original_tmux_run(args, check=check, capture=capture, timeout=timeout)

    backend._tmux_run = _tmux_run  # type: ignore[method-assign]

    assert session_alive(backend, 'ccb-proj') is True
    assert backend.calls.count(('has-session', '-t', 'ccb-proj')) == 2


def test_session_alive_treats_absent_project_server_as_missing_namespace(monkeypatch) -> None:
    monkeypatch.setenv('CCB_TMUX_OBJECT_READY_POLL_INTERVAL_S', '0')
    backend = _FlakyBackend()
    backend.missing_session_stderr = 'no server running on /tmp/ccb-runtime/test.sock\n'

    assert session_alive(backend, 'ccb-proj') is False
    assert backend.calls.count(('has-session', '-t', 'ccb-proj')) == 1


def test_wait_for_root_pane_raises_transient_unavailable_for_fast_probe(monkeypatch) -> None:
    monkeypatch.setenv('CCB_TMUX_OBJECT_READY_POLL_INTERVAL_S', '0')
    backend = _FlakyBackend()
    backend.fail_once('list-panes', '-t', 'ccb-proj:workspace', '-F', '#{pane_id}')

    with pytest.raises(TmuxTransientServerUnavailable):
        wait_for_root_pane(backend, target_window='ccb-proj:workspace', timeout_s=0.0)


def test_find_window_uses_fast_probe_timeout_when_provided(monkeypatch) -> None:
    monkeypatch.setenv('CCB_TMUX_OBJECT_READY_POLL_INTERVAL_S', '0')
    backend = _FlakyBackend()
    backend.fail_once('list-windows', '-t', 'ccb-proj', '-F', '#{window_id}\t#{window_name}\t#{window_active}')

    with pytest.raises(TmuxTransientServerUnavailable):
        find_window(backend, session_name='ccb-proj', window_name='workspace', timeout_s=0.0)
    assert backend.calls.count(('list-windows', '-t', 'ccb-proj', '-F', '#{window_id}\t#{window_name}\t#{window_active}')) == 1


def test_create_window_uses_fast_probe_timeout_when_provided(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv('CCB_TMUX_OBJECT_READY_POLL_INTERVAL_S', '0')
    backend = _FlakyBackend()
    backend.fail_once('list-windows', '-t', 'ccb-proj', '-F', '#{window_id}\t#{window_name}\t#{window_active}')

    record = create_window(
        backend,
        session_name='ccb-proj',
        window_name='workspace',
        project_root=tmp_path,
        timeout_s=0.0,
    )
    assert record.window_name == 'workspace'
    assert backend.calls.count(('list-windows', '-t', 'ccb-proj', '-F', '#{window_id}\t#{window_name}\t#{window_active}')) == 2


def test_ensure_window_uses_fast_probe_timeout_when_provided(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv('CCB_TMUX_OBJECT_READY_POLL_INTERVAL_S', '0')
    backend = _FlakyBackend()
    backend.fail_once('list-windows', '-t', 'ccb-proj', '-F', '#{window_id}\t#{window_name}\t#{window_active}')

    with pytest.raises(TmuxTransientServerUnavailable):
        ensure_window(
            backend,
            session_name='ccb-proj',
            window_name='workspace',
            project_root=tmp_path,
            timeout_s=0.0,
        )
    assert backend.calls.count(('list-windows', '-t', 'ccb-proj', '-F', '#{window_id}\t#{window_name}\t#{window_active}')) == 1


def test_create_session_uses_terminal_size_hint_when_provided(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv('CCB_TMUX_OBJECT_READY_POLL_INTERVAL_S', '0')
    backend = _FlakyBackend()

    create_session(
        backend,
        session_name='ccb-proj',
        project_root=tmp_path,
        window_name='cmd',
        terminal_size=(233, 61),
    )

    assert backend.calls == [
        (
            'new-session',
            '-d',
            '-x',
            '233',
            '-y',
            '61',
            '-s',
            'ccb-proj',
            '-n',
            'cmd',
            '-c',
            str(tmp_path),
            'sh',
            '-lc',
            'while :; do sleep 3600; done',
        )
    ]


def test_create_session_accepts_fast_probe_timeout(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv('CCB_TMUX_OBJECT_READY_POLL_INTERVAL_S', '0')
    backend = _FlakyBackend()

    create_session(
        backend,
        session_name='ccb-proj',
        project_root=tmp_path,
        window_name='cmd',
        timeout_s=0.0,
    )

    assert backend.calls[0][:2] == ('new-session', '-d')


def test_ensure_server_policy_accepts_fast_probe_timeout(monkeypatch) -> None:
    monkeypatch.setenv('CCB_TMUX_OBJECT_READY_POLL_INTERVAL_S', '0')
    backend = _FlakyBackend()

    ensure_server_policy(backend, timeout_s=0.0)

    assert backend.calls == [
        ('set-option', '-g', 'destroy-unattached', 'off'),
        ('set-option', '-g', 'mouse', 'on'),
        ('set-window-option', '-g', 'mode-keys', 'vi'),
        ('set-option', '-g', 'history-limit', '50000'),
    ]


def test_kill_window_accepts_fast_probe_timeout(monkeypatch) -> None:
    monkeypatch.setenv('CCB_TMUX_OBJECT_READY_POLL_INTERVAL_S', '0')
    backend = _FlakyBackend()

    from ccbd.services.project_namespace_runtime.backend import kill_window

    kill_window(backend, target='ccb-proj:@1', timeout_s=0.0)

    assert backend.calls == [('kill-window', '-t', 'ccb-proj:@1')]

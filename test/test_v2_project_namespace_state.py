from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

from ccbd.services.project_namespace import ProjectNamespaceController
from ccbd.services.project_namespace_runtime.backend import prepare_server
from ccbd.services.project_namespace_state import (
    ProjectNamespaceEvent,
    ProjectNamespaceEventStore,
    ProjectNamespaceState,
    ProjectNamespaceStateStore,
)
from storage.paths import PathLayout


def test_project_namespace_state_store_round_trip(tmp_path: Path) -> None:
    layout = PathLayout(tmp_path / 'repo')
    state = ProjectNamespaceState(
        project_id='proj-1',
        namespace_epoch=3,
        tmux_socket_path=str(layout.ccbd_tmux_socket_path),
        tmux_session_name=layout.ccbd_tmux_session_name,
        layout_version=3,
        layout_signature='cmd; agent1:codex',
        control_window_name=layout.ccbd_tmux_control_window_name,
        control_window_id='@1',
        workspace_window_name=layout.ccbd_tmux_workspace_window_name,
        workspace_window_id='@2',
        workspace_epoch=4,
        ui_attachable=True,
        last_started_at='2026-04-03T01:00:00Z',
        last_destroyed_at='2026-04-03T00:55:00Z',
        last_destroy_reason='kill',
    )

    store = ProjectNamespaceStateStore(layout)
    store.save(state)
    loaded = store.load()

    assert loaded == state
    assert loaded is not None
    assert loaded.summary_fields()['namespace_tmux_socket_path'] == str(layout.ccbd_tmux_socket_path)


def test_path_layout_normalizes_tmux_session_name_for_tmux_targets(tmp_path: Path) -> None:
    layout = PathLayout(tmp_path / 'repo.with.dots')

    assert layout.ccbd_tmux_session_name.startswith('ccb-')
    assert '.' not in layout.ccbd_tmux_session_name


@dataclass
class _FakeTmuxBackend:
    socket_path: str | None = None
    sessions: dict[str, list[dict[str, object]]] = field(default_factory=dict)
    active_windows: dict[str, str] = field(default_factory=dict)
    pane_titles: dict[str, str] = field(default_factory=dict)
    pane_options: dict[str, dict[str, str]] = field(default_factory=dict)
    session_options: dict[str, dict[str, str]] = field(default_factory=dict)
    window_options: dict[str, dict[str, str]] = field(default_factory=dict)
    global_options: dict[str, str] = field(default_factory=dict)
    global_window_options: dict[str, str] = field(default_factory=dict)
    hooks: dict[str, dict[str, str]] = field(default_factory=dict)
    tmux_calls: list[tuple[list[str], bool]] = field(default_factory=list)
    window_visibility_lag: dict[str, int] = field(default_factory=dict)
    pane_visibility_lag: dict[str, int] = field(default_factory=dict)
    pane_counter: int = 0
    window_counter: int = 0
    server_killed: bool = False

    def _alloc_pane(self) -> str:
        self.pane_counter += 1
        return f'%{self.pane_counter}'

    def _alloc_window(self) -> str:
        self.window_counter += 1
        return f'@{self.window_counter}'

    def _session_windows(self, session_name: str) -> list[dict[str, object]]:
        return self.sessions.setdefault(session_name, [])

    def _create_window(self, session_name: str, window_name: str) -> dict[str, object]:
        pane_id = self._alloc_pane()
        record = {
            'id': self._alloc_window(),
            'name': window_name,
            'panes': [pane_id],
        }
        self._session_windows(session_name).append(record)
        self.active_windows.setdefault(session_name, window_name)
        return record

    def _window_record(self, target: str) -> dict[str, object] | None:
        session_name, _, maybe_window = target.partition(':')
        windows = self.sessions.get(session_name, [])
        if not maybe_window:
            active_name = self.active_windows.get(session_name)
            for record in windows:
                if record['name'] == active_name:
                    return record
            return windows[0] if windows else None
        for record in windows:
            if record['name'] == maybe_window or record['id'] == maybe_window:
                return record
        return None

    def _window_visible(self, session_name: str, window_name: str) -> bool:
        key = f'{session_name}:{window_name}'
        remaining = int(self.window_visibility_lag.get(key, 0))
        if remaining <= 0:
            return True
        self.window_visibility_lag[key] = remaining - 1
        return False

    def _panes_visible(self, target: str, record: dict[str, object] | None) -> bool:
        candidates = [target]
        if record is not None:
            session_name, _, maybe_window = target.partition(':')
            candidates.append(f'{session_name}:{record["name"]}')
            candidates.append(f'{session_name}:{record["id"]}')
            if maybe_window:
                candidates.append(maybe_window)
        for key in candidates:
            remaining = int(self.pane_visibility_lag.get(key, 0))
            if remaining <= 0:
                continue
            self.pane_visibility_lag[key] = remaining - 1
            return False
        return True

    def drop_session(self, session_name: str) -> None:
        self.sessions.pop(session_name, None)
        self.active_windows.pop(session_name, None)

    def _tmux_run(
        self,
        args: list[str],
        *,
        check: bool = False,
        capture: bool = False,
        input_bytes: bytes | None = None,
        timeout: float | None = None,
    ):
        del check, input_bytes, timeout
        self.tmux_calls.append((list(args), capture))
        if args[:1] == ['start-server']:
            return SimpleNamespace(returncode=0, stdout='', stderr='')
        if len(args) >= 4 and args[:2] == ['set-option', '-g']:
            self.global_options[args[2]] = args[3]
            return SimpleNamespace(returncode=0, stdout='', stderr='')
        if len(args) >= 4 and args[:2] == ['set-window-option', '-g']:
            self.global_window_options[args[2]] = args[3]
            return SimpleNamespace(returncode=0, stdout='', stderr='')
        if len(args) >= 3 and args[:2] == ['has-session', '-t']:
            return SimpleNamespace(returncode=0 if args[2] in self.sessions else 1, stdout='', stderr='')
        if len(args) >= 9 and args[:2] == ['new-session', '-d']:
            session_name = args[7]
            if '-n' in args:
                window_name = args[args.index('-n') + 1]
            else:
                window_name = session_name
            self.sessions[session_name] = []
            self.active_windows[session_name] = window_name
            self._create_window(session_name, window_name)
            return SimpleNamespace(returncode=0, stdout='', stderr='')
        if len(args) >= 7 and args[:2] == ['new-window', '-d']:
            session_name = args[args.index('-t') + 1]
            window_name = args[args.index('-n') + 1]
            self._create_window(session_name, window_name)
            return SimpleNamespace(returncode=0, stdout='', stderr='')
        if len(args) >= 4 and args[:2] == ['list-windows', '-t']:
            session_name = args[2]
            rows = []
            for record in self.sessions.get(session_name, []):
                if not self._window_visible(session_name, str(record['name'])):
                    continue
                active = '1' if self.active_windows.get(session_name) == record['name'] else '0'
                rows.append(f"{record['id']}\t{record['name']}\t{active}")
            return SimpleNamespace(returncode=0, stdout='\n'.join(rows), stderr='')
        if len(args) >= 4 and args[:2] == ['list-panes', '-t']:
            window = self._window_record(args[2])
            panes = list(window['panes']) if window is not None and self._panes_visible(args[2], window) else []
            if capture and len(args) >= 5 and args[4] == '#{?pane_active,#{pane_id},}':
                active = panes[0] if panes else ''
                return SimpleNamespace(returncode=0, stdout=f'{active}\n', stderr='')
            return SimpleNamespace(returncode=0, stdout='\n'.join(panes), stderr='')
        if len(args) >= 3 and args[:2] == ['select-window', '-t']:
            target = args[2]
            session_name, _, maybe_window = target.partition(':')
            if maybe_window:
                window = self._window_record(target)
                if window is not None:
                    self.active_windows[session_name] = str(window['name'])
            return SimpleNamespace(returncode=0, stdout='', stderr='')
        if len(args) >= 4 and args[:2] == ['rename-window', '-t']:
            target = args[2]
            new_name = args[3]
            window = self._window_record(target)
            if window is not None:
                session_name, _, _ = target.partition(':')
                previous_name = str(window['name'])
                window['name'] = new_name
                if self.active_windows.get(session_name) == previous_name:
                    self.active_windows[session_name] = new_name
            return SimpleNamespace(returncode=0, stdout='', stderr='')
        if len(args) >= 3 and args[:2] == ['kill-window', '-t']:
            target = args[2]
            session_name, _, _ = target.partition(':')
            window = self._window_record(target)
            if window is not None:
                windows = self.sessions.get(session_name, [])
                self.sessions[session_name] = [record for record in windows if record is not window]
                if self.active_windows.get(session_name) == window['name']:
                    next_windows = self.sessions.get(session_name, [])
                    self.active_windows[session_name] = str(next_windows[0]['name']) if next_windows else ''
            return SimpleNamespace(returncode=0, stdout='', stderr='')
        if len(args) >= 5 and args[:2] == ['set-option', '-t']:
            self.session_options.setdefault(args[2], {})[args[3]] = args[4]
            return SimpleNamespace(returncode=0, stdout='', stderr='')
        if len(args) >= 5 and args[:2] == ['set-window-option', '-t']:
            self.window_options.setdefault(args[2], {})[args[3]] = args[4]
            return SimpleNamespace(returncode=0, stdout='', stderr='')
        if len(args) >= 5 and args[:2] == ['set-hook', '-t']:
            self.hooks.setdefault(args[2], {})[args[3]] = args[4]
            return SimpleNamespace(returncode=0, stdout='', stderr='')
        if len(args) >= 6 and args[:3] == ['set-option', '-p', '-t']:
            self.pane_options.setdefault(args[3], {})[args[4]] = args[5]
            return SimpleNamespace(returncode=0, stdout='', stderr='')
        if len(args) >= 5 and args[:3] == ['display-message', '-p', '-t']:
            pane_id = args[3]
            fmt = args[4]
            if fmt == '#{@ccb_active_border_style}':
                value = self.pane_options.get(pane_id, {}).get('@ccb_active_border_style', '')
                return SimpleNamespace(returncode=0, stdout=f'{value}\n', stderr='')
            if fmt == '#{@ccb_border_style}':
                value = self.pane_options.get(pane_id, {}).get('@ccb_border_style', '')
                return SimpleNamespace(returncode=0, stdout=f'{value}\n', stderr='')
            return SimpleNamespace(returncode=0, stdout='', stderr='')
        if args[:1] == ['kill-server']:
            self.server_killed = True
            self.sessions.clear()
            self.active_windows.clear()
            return SimpleNamespace(returncode=0, stdout='', stderr='')
        raise AssertionError(f'unexpected tmux args: {args}')

    def is_alive(self, session_name: str) -> bool:
        return session_name in self.sessions

    def set_pane_title(self, pane_id: str, title: str) -> None:
        self.pane_titles[pane_id] = title

    def set_pane_user_option(self, pane_id: str, name: str, value: str) -> None:
        self.pane_options.setdefault(pane_id, {})[name] = value

    def set_pane_style(
        self,
        pane_id: str,
        *,
        border_style: str | None = None,
        active_border_style: str | None = None,
    ) -> None:
        options = self.pane_options.setdefault(pane_id, {})
        if border_style:
            options['pane-border-style'] = border_style
        if active_border_style:
            options['pane-active-border-style'] = active_border_style


def test_project_namespace_controller_creates_state_and_lifecycle_event(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo'
    layout = PathLayout(project_root)
    backend = _FakeTmuxBackend()
    controller = ProjectNamespaceController(
        layout,
        'proj-1',
        clock=lambda: '2026-04-03T02:00:00Z',
        backend_factory=lambda socket_path=None: backend,
    )

    namespace = controller.ensure()
    state = ProjectNamespaceStateStore(layout).load()
    latest_event = ProjectNamespaceEventStore(layout).load_latest()

    assert namespace.project_id == 'proj-1'
    assert namespace.namespace_epoch == 1
    assert state is not None
    assert state.tmux_socket_path == str(layout.ccbd_tmux_socket_path)
    assert state.tmux_session_name == layout.ccbd_tmux_session_name
    assert state.control_window_name == layout.ccbd_tmux_control_window_name
    assert state.workspace_window_name == layout.ccbd_tmux_workspace_window_name
    assert state.workspace_epoch == 1
    assert backend.active_windows[layout.ccbd_tmux_session_name] == layout.ccbd_tmux_workspace_window_name
    assert backend.pane_titles['%2'] == 'cmd'
    assert backend.pane_options['%2']['@ccb_slot'] == 'cmd'
    assert backend.pane_options['%2']['@ccb_namespace_epoch'] == '1'
    assert backend.pane_options['%2']['@ccb_managed_by'] == 'ccbd'
    assert backend.window_options[layout.ccbd_tmux_session_name]['pane-border-status'] == 'top'
    assert 'after-select-pane' in backend.hooks[layout.ccbd_tmux_session_name]
    assert latest_event is not None
    assert latest_event.event_kind == 'namespace_created'
    assert latest_event.details['recreated'] is False
    assert latest_event.details['reason'] == 'initial_create'


def test_prepare_server_preserves_tmux_failure_detail_for_diagnostics(tmp_path: Path) -> None:
    socket_path = tmp_path / 'repo' / '.ccb' / 'ccbd' / 'tmux.sock'

    class _FailingStartServerBackend(_FakeTmuxBackend):
        def __init__(self) -> None:
            super().__init__(socket_path=str(socket_path))
            self._socket_path = str(socket_path)

        def _tmux_base(self) -> list[str]:
            return ['tmux', '-f', '/dev/null', '-S', self._socket_path]

        def _tmux_run(
            self,
            args: list[str],
            *,
            check: bool = False,
            capture: bool = False,
            input_bytes: bytes | None = None,
            timeout: float | None = None,
        ):
            del check, capture, input_bytes, timeout
            if args[:1] == ['start-server']:
                return SimpleNamespace(
                    returncode=1,
                    stdout='',
                    stderr='error connecting to /private/tmp/tmux-501/default (No such file or directory)\n',
                )
            return super()._tmux_run(args, check=False, capture=True)

    try:
        prepare_server(_FailingStartServerBackend())
    except RuntimeError as exc:
        text = str(exc)
    else:
        raise AssertionError('expected prepare_server to fail')

    assert 'failed to prepare tmux server' in text
    assert f'tmux_socket_path={socket_path}' in text
    assert 'tmux_socket_path_bytes=' in text
    assert "tmux_command='tmux -f /dev/null -S" in text
    assert 'start-server' in text
    assert 'No such file or directory' in text


def test_project_namespace_controller_recreates_missing_session_with_new_epoch(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-recreate'
    layout = PathLayout(project_root)
    backend = _FakeTmuxBackend()
    controller = ProjectNamespaceController(
        layout,
        'proj-2',
        clock=lambda: '2026-04-03T03:00:00Z',
        backend_factory=lambda socket_path=None: backend,
    )

    first = controller.ensure()
    backend.drop_session(layout.ccbd_tmux_session_name)
    second = controller.ensure()
    latest_event = ProjectNamespaceEventStore(layout).load_latest()

    assert first.namespace_epoch == 1
    assert second.namespace_epoch == 2
    assert latest_event is not None
    assert latest_event.event_kind == 'namespace_created'
    assert latest_event.namespace_epoch == 2
    assert latest_event.details['recreated'] is True
    assert latest_event.details['reason'] == 'missing_session'


def test_project_namespace_controller_recreates_after_kill_when_has_session_reports_no_server_running(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-recreate-no-server'
    layout = PathLayout(project_root)

    class _NoServerWhenAbsentBackend(_FakeTmuxBackend):
        def _tmux_run(
            self,
            args: list[str],
            *,
            check: bool = False,
            capture: bool = False,
            input_bytes: bytes | None = None,
            timeout: float | None = None,
        ):
            if len(args) >= 3 and args[:2] == ['has-session', '-t'] and args[2] not in self.sessions:
                self.tmux_calls.append((list(args), capture))
                return SimpleNamespace(
                    returncode=1,
                    stdout='',
                    stderr=f'no server running on {layout.ccbd_tmux_socket_path}\n',
                )
            return super()._tmux_run(
                args,
                check=check,
                capture=capture,
                input_bytes=input_bytes,
                timeout=timeout,
            )

    backend = _NoServerWhenAbsentBackend()
    controller = ProjectNamespaceController(
        layout,
        'proj-2b',
        clock=lambda: '2026-04-03T03:30:00Z',
        backend_factory=lambda socket_path=None: backend,
    )

    first = controller.ensure()
    controller.destroy(reason='kill')
    second = controller.ensure()
    latest_event = ProjectNamespaceEventStore(layout).load_latest()

    assert first.namespace_epoch == 1
    assert second.namespace_epoch == 2
    assert second.ui_attachable is True
    assert layout.ccbd_tmux_session_name in backend.sessions
    assert latest_event is not None
    assert latest_event.event_kind == 'namespace_created'
    assert latest_event.namespace_epoch == 2
    assert latest_event.details['reason'] == 'missing_session'


def test_project_namespace_controller_recreates_session_when_layout_version_changes(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-layout-upgrade'
    layout = PathLayout(project_root)
    backend = _FakeTmuxBackend()
    state_store = ProjectNamespaceStateStore(layout)
    state_store.save(
        ProjectNamespaceState(
            project_id='proj-5',
            namespace_epoch=4,
            tmux_socket_path=str(layout.ccbd_tmux_socket_path),
            tmux_session_name=layout.ccbd_tmux_session_name,
            layout_version=1,
            layout_signature='cmd; agent1:codex',
            ui_attachable=True,
        )
    )
    backend.sessions[layout.ccbd_tmux_session_name] = [{'id': '@8', 'name': layout.ccbd_tmux_workspace_window_name, 'panes': ['%8']}]
    backend.active_windows[layout.ccbd_tmux_session_name] = layout.ccbd_tmux_workspace_window_name
    controller = ProjectNamespaceController(
        layout,
        'proj-5',
        clock=lambda: '2026-04-03T06:00:00Z',
        backend_factory=lambda socket_path=None: backend,
        layout_version=3,
    )

    namespace = controller.ensure()
    latest_event = ProjectNamespaceEventStore(layout).load_latest()

    assert namespace.namespace_epoch == 5
    assert backend.server_killed is True
    assert backend.pane_titles['%2'] == 'cmd'
    assert latest_event is not None
    assert latest_event.details['reason'] == 'layout_version_changed'


def test_project_namespace_controller_recreates_session_when_layout_signature_changes(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-layout-signature-upgrade'
    layout = PathLayout(project_root)
    backend = _FakeTmuxBackend()
    state_store = ProjectNamespaceStateStore(layout)
    state_store.save(
        ProjectNamespaceState(
            project_id='proj-6',
            namespace_epoch=7,
            tmux_socket_path=str(layout.ccbd_tmux_socket_path),
            tmux_session_name=layout.ccbd_tmux_session_name,
            layout_version=3,
            layout_signature='cmd; agent1:codex',
            ui_attachable=True,
        )
    )
    backend.sessions[layout.ccbd_tmux_session_name] = [{'id': '@9', 'name': layout.ccbd_tmux_workspace_window_name, 'panes': ['%9']}]
    backend.active_windows[layout.ccbd_tmux_session_name] = layout.ccbd_tmux_workspace_window_name
    controller = ProjectNamespaceController(
        layout,
        'proj-6',
        clock=lambda: '2026-04-03T07:00:00Z',
        backend_factory=lambda socket_path=None: backend,
        layout_version=3,
    )

    namespace = controller.ensure(layout_signature='cmd, agent1:codex; agent2:claude')
    latest_event = ProjectNamespaceEventStore(layout).load_latest()

    assert namespace.namespace_epoch == 8
    assert namespace.layout_signature == 'cmd, agent1:codex; agent2:claude'
    assert backend.server_killed is True
    assert backend.pane_titles['%2'] == 'cmd'
    assert latest_event is not None
    assert latest_event.details['reason'] == 'layout_signature_changed'


def test_project_namespace_controller_waits_for_delayed_window_and_pane_visibility(
    tmp_path: Path, monkeypatch
) -> None:
    project_root = tmp_path / 'repo-delayed-namespace-visibility'
    layout = PathLayout(project_root)
    backend = _FakeTmuxBackend()
    backend.window_visibility_lag[f'{layout.ccbd_tmux_session_name}:{layout.ccbd_tmux_workspace_window_name}'] = 2
    backend.pane_visibility_lag[f'{layout.ccbd_tmux_session_name}:{layout.ccbd_tmux_workspace_window_name}'] = 2
    controller = ProjectNamespaceController(
        layout,
        'proj-delay-1',
        clock=lambda: '2026-04-03T07:30:00Z',
        backend_factory=lambda socket_path=None: backend,
    )
    monkeypatch.setenv('CCB_TMUX_OBJECT_READY_TIMEOUT_S', '0.2')
    monkeypatch.setenv('CCB_TMUX_OBJECT_READY_POLL_INTERVAL_S', '0')

    namespace = controller.ensure()
    state = ProjectNamespaceStateStore(layout).load()

    assert namespace.workspace_window_name == layout.ccbd_tmux_workspace_window_name
    assert state is not None
    assert state.workspace_window_name == layout.ccbd_tmux_workspace_window_name
    assert backend.pane_titles['%2'] == 'cmd'


def test_project_namespace_controller_destroy_marks_state_and_event(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-destroy'
    layout = PathLayout(project_root)
    backend = _FakeTmuxBackend()
    controller = ProjectNamespaceController(
        layout,
        'proj-3',
        clock=lambda: '2026-04-03T04:00:00Z',
        backend_factory=lambda socket_path=None: backend,
    )

    controller.ensure()
    summary = controller.destroy(reason='kill')
    state = ProjectNamespaceStateStore(layout).load()
    latest_event = ProjectNamespaceEventStore(layout).load_latest()

    assert summary.destroyed is True
    assert summary.reason == 'kill'
    assert backend.server_killed is True
    assert state is not None
    assert state.ui_attachable is False
    assert state.last_destroy_reason == 'kill'
    assert latest_event is not None
    assert latest_event.event_kind == 'namespace_destroyed'
    assert latest_event.details['reason'] == 'kill'


def test_project_namespace_controller_reflows_workspace_without_killing_server(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-reflow-workspace'
    layout = PathLayout(project_root)
    backend = _FakeTmuxBackend()
    controller = ProjectNamespaceController(
        layout,
        'proj-7',
        clock=lambda: '2026-04-03T08:00:00Z',
        backend_factory=lambda socket_path=None: backend,
    )

    first = controller.ensure()
    namespace = controller.reflow_workspace(
        layout_signature='cmd; agent1:codex',
        reason='pane_recovery:agent1',
    )
    state = ProjectNamespaceStateStore(layout).load()
    latest_event = ProjectNamespaceEventStore(layout).load_latest()

    assert first.namespace_epoch == 1
    assert namespace.namespace_epoch == 1
    assert namespace.workspace_epoch == 2
    assert namespace.workspace_recreated_this_call is True
    assert backend.server_killed is False
    assert state is not None
    assert state.control_window_id == '@1'
    assert state.workspace_window_id == '@3'
    assert backend.active_windows[layout.ccbd_tmux_session_name] == layout.ccbd_tmux_workspace_window_name
    assert backend.pane_titles['%3'] == 'cmd'
    assert latest_event is not None
    assert latest_event.event_kind == 'workspace_reflowed'
    assert latest_event.details['reason'] == 'pane_recovery:agent1'


def test_project_namespace_controller_reflow_waits_for_renamed_workspace_visibility(
    tmp_path: Path, monkeypatch
) -> None:
    project_root = tmp_path / 'repo-reflow-delayed-visibility'
    layout = PathLayout(project_root)
    backend = _FakeTmuxBackend()
    controller = ProjectNamespaceController(
        layout,
        'proj-reflow-delay',
        clock=lambda: '2026-04-03T08:30:00Z',
        backend_factory=lambda socket_path=None: backend,
    )
    controller.ensure()
    backend.window_visibility_lag[f'{layout.ccbd_tmux_session_name}:{layout.ccbd_tmux_workspace_window_name}'] = 2
    monkeypatch.setenv('CCB_TMUX_OBJECT_READY_TIMEOUT_S', '0.2')
    monkeypatch.setenv('CCB_TMUX_OBJECT_READY_POLL_INTERVAL_S', '0')

    namespace = controller.reflow_workspace(
        layout_signature='cmd; agent1:codex',
        reason='pane_recovery:agent1',
    )

    assert namespace.workspace_epoch == 2
    assert backend.active_windows[layout.ccbd_tmux_session_name] == layout.ccbd_tmux_workspace_window_name


def test_project_namespace_reflow_targets_transient_window_by_id(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-reflow-targets'
    layout = PathLayout(project_root)
    backend = _FakeTmuxBackend()
    controller = ProjectNamespaceController(
        layout,
        'proj-8',
        clock=lambda: '2026-04-03T09:00:00Z',
        backend_factory=lambda socket_path=None: backend,
    )

    controller.ensure()
    backend.tmux_calls.clear()

    controller.reflow_workspace(
        layout_signature='cmd; agent1:codex',
        reason='pane_recovery:agent1',
    )

    targeted = [
        args
        for args, _capture in backend.tmux_calls
        if args[:1] and args[0] in {'select-window', 'rename-window', 'kill-window'}
    ]

    assert targeted
    for args in targeted:
        target = args[2]
        assert '.__reflow__.' not in target
        assert target.startswith(f'{layout.ccbd_tmux_session_name}:@')


def test_project_namespace_controller_uses_silent_server_commands(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-silent'
    layout = PathLayout(project_root)
    backend = _FakeTmuxBackend()
    controller = ProjectNamespaceController(
        layout,
        'proj-4',
        clock=lambda: '2026-04-03T05:00:00Z',
        backend_factory=lambda socket_path=None: backend,
    )

    controller.ensure()
    controller.destroy(reason='kill')

    new_session_calls = [args for args, _capture in backend.tmux_calls if args[:2] == ['new-session', '-d']]
    assert len(new_session_calls) == 1
    assert new_session_calls[0][-3:] == ['sh', '-lc', 'while :; do sleep 3600; done']
    assert (['start-server'], True) in backend.tmux_calls
    assert (['set-option', '-g', 'destroy-unattached', 'off'], True) in backend.tmux_calls
    assert (['set-option', '-g', 'mouse', 'on'], True) in backend.tmux_calls
    assert (['set-window-option', '-g', 'mode-keys', 'vi'], True) in backend.tmux_calls
    assert (['set-option', '-g', 'history-limit', '50000'], True) in backend.tmux_calls
    assert (['kill-server'], True) in backend.tmux_calls

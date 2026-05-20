from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from agents.config_identity import project_config_identity_payload
from agents.config_loader import load_project_config
from ccbd.keeper import KeeperState, KeeperStateStore, ProjectKeeper, ShutdownIntent, ShutdownIntentStore
from ccbd.models import CcbdLease, LeaseHealth, LeaseInspection, MountState
from ccbd.services.lifecycle import CcbdLifecycleStore, build_lifecycle
from ccbd.services.project_namespace_state import ProjectNamespaceState, ProjectNamespaceStateStore
from cli.context import CliContext
from cli.models import ParsedStartCommand
import cli.services.daemon as daemon_service
import ccbd.keeper as keeper_module
import ccbd.keeper_runtime.loop as keeper_loop
from project.resolver import bootstrap_project
from storage.paths import PathLayout


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def _context(project_root: Path, config_text: str) -> CliContext:
    project_root.mkdir(parents=True, exist_ok=True)
    _write(project_root / '.ccb' / 'ccb.config', config_text)
    project = bootstrap_project(project_root)
    command = ParsedStartCommand(project=None, agent_names=(), restore=False, auto_permission=False)
    return CliContext(command=command, cwd=project_root, project=project, paths=PathLayout(project_root))


def _inspection(
    context: CliContext,
    *,
    health: LeaseHealth,
    socket_connectable: bool,
    pid_alive: bool,
    heartbeat_fresh: bool,
    mount_state: MountState = MountState.MOUNTED,
    reason: str,
) -> LeaseInspection:
    lease = None
    if health is not LeaseHealth.MISSING:
        lease = CcbdLease(
            project_id=context.project.project_id,
            ccbd_pid=321,
            socket_path=str(context.paths.ccbd_socket_path),
            owner_uid=1000,
            boot_id='boot-id',
            started_at='2026-04-02T00:00:00Z',
            last_heartbeat_at='2026-04-02T00:00:00Z',
            mount_state=mount_state,
            generation=1,
        )
    return LeaseInspection(
        lease=lease,
        health=health,
        pid_alive=pid_alive,
        socket_connectable=socket_connectable,
        heartbeat_fresh=heartbeat_fresh,
        takeover_allowed=health in {LeaseHealth.MISSING, LeaseHealth.UNMOUNTED, LeaseHealth.STALE},
        reason=reason,
    )


def _repeat_last_inspection(inspections):
    items = tuple(inspections)
    assert items
    iterator = iter(items)
    last = items[-1]

    def _inspect(context):
        del context
        try:
            current = next(iterator)
        except StopIteration:
            current = last
        return None, None, current

    return _inspect


def test_keeper_state_store_roundtrip(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-state'
    _write(project_root / '.ccb' / 'ccb.config', 'agent1:codex\n')
    layout = PathLayout(project_root)
    state = KeeperState(
        project_id='project-1',
        keeper_pid=555,
        started_at='2026-04-02T00:00:00Z',
        last_check_at='2026-04-02T00:00:00Z',
        state='running',
        restart_count=2,
        last_restart_at='2026-04-02T00:00:10Z',
        last_failure_reason='socket_unreachable',
    )

    KeeperStateStore(layout).save(state)
    loaded = KeeperStateStore(layout).load()

    assert loaded == state


def test_project_keeper_spawns_missing_daemon(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-missing'
    ctx = _context(project_root, 'agent1:codex\n')
    spawn_calls: list[dict] = []
    keeper = ProjectKeeper(
        project_root,
        pid=777,
        spawn_ccbd_process_fn=lambda **kwargs: spawn_calls.append(dict(kwargs)),
    )
    keeper._ownership_guard = SimpleNamespace(
        inspect=lambda: _inspection(
            ctx,
            health=LeaseHealth.MISSING,
            socket_connectable=False,
            pid_alive=False,
            heartbeat_fresh=False,
            reason='lease_missing',
        )
    )
    CcbdLifecycleStore(keeper.paths).save(
        build_lifecycle(
            project_id=ctx.project.project_id,
            occurred_at='2026-04-02T00:00:00Z',
            desired_state='running',
            phase='unmounted',
            generation=0,
            keeper_pid=777,
            socket_path=ctx.paths.ccbd_socket_path,
        )
    )
    state = KeeperState(
        project_id=ctx.project.project_id,
        keeper_pid=777,
        started_at='2026-04-02T00:00:00Z',
        last_check_at='2026-04-02T00:00:00Z',
        state='running',
    )

    next_state = keeper._reconcile_once(state=state, start_timeout_s=0.1)

    assert len(spawn_calls) == 1
    assert spawn_calls[0]['project_root'] == project_root
    assert spawn_calls[0]['keeper_pid'] == 777
    assert next_state.restart_count == 1
    assert next_state.last_failure_reason is None


def test_project_keeper_does_not_restart_degraded_unreachable_daemon_with_fresh_heartbeat(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root = tmp_path / 'repo-crash'
    ctx = _context(project_root, 'agent1:codex\n')
    spawn_calls: list[dict] = []
    terminated: list[int] = []
    keeper = ProjectKeeper(
        project_root,
        pid=888,
        process_exists_fn=lambda pid: pid == 321,
        spawn_ccbd_process_fn=lambda **kwargs: spawn_calls.append(dict(kwargs)),
    )
    keeper._ownership_guard = SimpleNamespace(
        inspect=lambda: _inspection(
            ctx,
            health=LeaseHealth.DEGRADED,
            socket_connectable=False,
            pid_alive=True,
            heartbeat_fresh=True,
            reason='socket_unreachable',
        )
    )
    monkeypatch.setattr(
        keeper_module,
        'terminate_pid_tree',
        lambda pid, timeout_s, is_pid_alive_fn: terminated.append(pid) or True,
    )
    state = KeeperState(
        project_id=ctx.project.project_id,
        keeper_pid=888,
        started_at='2026-04-02T00:00:00Z',
        last_check_at='2026-04-02T00:00:00Z',
        state='running',
    )

    next_state = keeper._reconcile_once(state=state, start_timeout_s=0.1)

    assert next_state == state
    assert terminated == []
    assert spawn_calls == []


def test_project_keeper_restarts_stale_unreachable_daemon(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / 'repo-stale'
    ctx = _context(project_root, 'agent1:codex\n')
    spawn_calls: list[dict] = []
    terminated: list[int] = []
    keeper = ProjectKeeper(
        project_root,
        pid=889,
        process_exists_fn=lambda pid: pid == 321,
        spawn_ccbd_process_fn=lambda **kwargs: spawn_calls.append(dict(kwargs)),
    )
    keeper._ownership_guard = SimpleNamespace(
        inspect=lambda: _inspection(
            ctx,
            health=LeaseHealth.STALE,
            socket_connectable=False,
            pid_alive=True,
            heartbeat_fresh=False,
            reason='heartbeat_stale,socket_unreachable',
        )
    )
    monkeypatch.setattr(
        keeper_module,
        'terminate_pid_tree',
        lambda pid, timeout_s, is_pid_alive_fn: terminated.append(pid) or True,
    )
    state = KeeperState(
        project_id=ctx.project.project_id,
        keeper_pid=889,
        started_at='2026-04-02T00:00:00Z',
        last_check_at='2026-04-02T00:00:00Z',
        state='running',
    )

    next_state = keeper._reconcile_once(state=state, start_timeout_s=0.1)

    assert terminated == [321]
    assert len(spawn_calls) == 1
    assert next_state.restart_count == 1
    assert next_state.last_failure_reason is None


def test_project_keeper_preserves_namespace_epoch_when_confirming_mounted_daemon(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / 'repo-mounted-namespace'
    ctx = _context(project_root, 'agent1:codex\n')
    keeper = ProjectKeeper(project_root, pid=890)
    keeper._ownership_guard = SimpleNamespace(
        inspect=lambda: _inspection(
            ctx,
            health=LeaseHealth.HEALTHY,
            socket_connectable=True,
            pid_alive=True,
            heartbeat_fresh=True,
            reason='healthy',
        )
    )
    ProjectNamespaceStateStore(keeper.paths).save(
        ProjectNamespaceState(
            project_id=ctx.project.project_id,
            namespace_epoch=6,
            tmux_socket_path=str(ctx.paths.ccbd_tmux_socket_path),
            tmux_session_name=ctx.paths.ccbd_tmux_session_name,
            layout_version=3,
            control_window_name='__ccb_ctl',
            control_window_id='@0',
            workspace_window_name='ccb',
            workspace_window_id='@1',
            workspace_epoch=1,
            ui_attachable=True,
            last_started_at='2026-04-22T00:00:00Z',
        )
    )
    lifecycle_store = CcbdLifecycleStore(keeper.paths)
    lifecycle_store.save(
        build_lifecycle(
            project_id=ctx.project.project_id,
            occurred_at='2026-04-22T00:00:00Z',
            desired_state='running',
            phase='starting',
            generation=1,
            keeper_pid=890,
            socket_path=ctx.paths.ccbd_socket_path,
            namespace_epoch=None,
        )
    )
    monkeypatch.setattr('ccbd.keeper_runtime.loop.daemon_matches_project_config', lambda app: True)
    state = KeeperState(
        project_id=ctx.project.project_id,
        keeper_pid=890,
        started_at='2026-04-22T00:00:00Z',
        last_check_at='2026-04-22T00:00:00Z',
        state='running',
    )

    next_state = keeper._reconcile_once(state=state, start_timeout_s=0.1)
    lifecycle = lifecycle_store.load()

    assert next_state.last_failure_reason is None
    assert lifecycle is not None
    assert lifecycle.phase == 'mounted'
    assert lifecycle.namespace_epoch == 6


def test_project_keeper_keeps_mounted_phase_when_config_check_times_out(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / 'repo-mounted-config-check-timeout'
    ctx = _context(project_root, 'agent1:codex\n')
    keeper = ProjectKeeper(project_root, pid=891)
    keeper._ownership_guard = SimpleNamespace(
        inspect=lambda: _inspection(
            ctx,
            health=LeaseHealth.HEALTHY,
            socket_connectable=True,
            pid_alive=True,
            heartbeat_fresh=True,
            reason='healthy',
        )
    )
    lifecycle_store = CcbdLifecycleStore(keeper.paths)
    lifecycle_store.save(
        build_lifecycle(
            project_id=ctx.project.project_id,
            occurred_at='2026-04-22T00:00:00Z',
            desired_state='running',
            phase='mounted',
            generation=1,
            keeper_pid=891,
            owner_pid=321,
            socket_path=ctx.paths.ccbd_socket_path,
        )
    )
    monkeypatch.setattr(
        'ccbd.keeper_runtime.loop.daemon_matches_project_config',
        lambda app: (_ for _ in ()).throw(TimeoutError('ping timeout')),
    )
    state = KeeperState(
        project_id=ctx.project.project_id,
        keeper_pid=891,
        started_at='2026-04-22T00:00:00Z',
        last_check_at='2026-04-22T00:00:00Z',
        state='running',
    )

    next_state = keeper._reconcile_once(state=state, start_timeout_s=0.1)
    lifecycle = lifecycle_store.load()

    assert next_state.last_failure_reason == 'config_check_failed:ping timeout'
    assert lifecycle is not None
    assert lifecycle.phase == 'mounted'
    assert lifecycle.desired_state == 'running'
    assert lifecycle.last_failure_reason == 'config_check_failed:ping timeout'


def test_project_keeper_config_probe_uses_shared_control_plane_timeout(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / 'repo-keeper-probe-timeout'
    ctx = _context(project_root, 'agent1:codex\n')
    expected = project_config_identity_payload(load_project_config(project_root).config)
    captured: list[float | None] = []

    class _FakeClient:
        def __init__(self, socket_path, *, timeout_s=None) -> None:
            assert socket_path == ctx.paths.ccbd_socket_path
            captured.append(timeout_s)

        def ping(self, target: str) -> dict[str, object]:
            assert target == 'ccbd'
            return {'config_signature': expected['config_signature']}

        def stop_all(self, *, force: bool = False) -> dict[str, object]:
            assert force is False
            return {'ok': True}

    keeper = ProjectKeeper(project_root, pid=892)
    monkeypatch.setattr(keeper_loop, 'CcbdClient', _FakeClient)

    assert keeper_loop.daemon_matches_project_config(keeper) is True
    keeper_loop.request_shutdown(keeper)

    assert captured == [
        keeper_loop.CONTROL_PLANE_RPC_TIMEOUT_S,
        keeper_loop.CONTROL_PLANE_RPC_TIMEOUT_S,
    ]


def test_project_keeper_stops_when_shutdown_intent_exists(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-stop'
    ctx = _context(project_root, 'agent1:codex\n')
    layout = PathLayout(project_root)
    ShutdownIntentStore(layout).save(
        ShutdownIntent(
            project_id=ctx.project.project_id,
            requested_at='2026-04-02T00:00:00Z',
            requested_by_pid=1,
            reason='kill',
        )
    )
    keeper = ProjectKeeper(
        project_root,
        pid=999,
        sleep_fn=lambda _seconds: (_ for _ in ()).throw(AssertionError('keeper should not sleep')),
        spawn_ccbd_process_fn=lambda **kwargs: (_ for _ in ()).throw(AssertionError('keeper should not spawn')),
    )

    code = keeper.run_forever(poll_interval=0.1, start_timeout_s=0.1)
    state = KeeperStateStore(layout).load()

    assert code == 0
    assert state is not None
    assert state.state == 'stopped'


def test_project_keeper_uses_builtin_default_when_config_missing(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / 'repo-missing-config'
    monkeypatch.setenv('HOME', str(tmp_path / 'empty-home'))
    _context(project_root, 'agent1:codex\n')
    config_path = project_root / '.ccb' / 'ccb.config'
    config_path.unlink()
    ctx = CliContext(
        command=ParsedStartCommand(project=None, agent_names=(), restore=False, auto_permission=False),
        cwd=project_root,
        project=bootstrap_project(project_root),
        paths=PathLayout(project_root),
    )
    spawn_calls: list[dict] = []

    keeper = ProjectKeeper(
        project_root,
        pid=1001,
        spawn_ccbd_process_fn=lambda **kwargs: spawn_calls.append(dict(kwargs)),
    )
    keeper._ownership_guard = SimpleNamespace(
        inspect=lambda: _inspection(
            ctx,
            health=LeaseHealth.MISSING,
            socket_connectable=False,
            pid_alive=False,
            heartbeat_fresh=False,
            reason='lease_missing',
        )
    )
    CcbdLifecycleStore(keeper.paths).save(
        build_lifecycle(
            project_id=ctx.project.project_id,
            occurred_at='2026-04-02T00:00:00Z',
            desired_state='running',
            phase='unmounted',
            generation=0,
            keeper_pid=1001,
            socket_path=ctx.paths.ccbd_socket_path,
        )
    )
    state = KeeperState(
        project_id=ctx.project.project_id,
        keeper_pid=1001,
        started_at='2026-04-02T00:00:00Z',
        last_check_at='2026-04-02T00:00:00Z',
        state='running',
    )

    next_state = keeper._reconcile_once(state=state, start_timeout_s=0.1)

    loaded_config = load_project_config(project_root)
    assert loaded_config.source_path is None
    assert loaded_config.used_default is True
    assert (project_root / '.ccb' / 'ccb.config').exists() is False
    assert len(spawn_calls) == 1
    assert spawn_calls[0]['project_root'] == project_root
    assert spawn_calls[0]['keeper_pid'] == 1001
    assert next_state.restart_count == 1
    assert next_state.last_failure_reason is None


def test_reap_child_processes_drains_exited_children() -> None:
    seen: list[tuple[int, int]] = []
    responses = iter(((321, 0), (654, 0), (0, 0)))
    original = keeper_module._reap_child_processes

    reaped = original(waitpid_fn=lambda pid, flags: seen.append((pid, flags)) or next(responses))

    assert reaped == (321, 654)
    assert seen == [(-1, keeper_module.os.WNOHANG)] * 3


def test_ensure_daemon_started_waits_for_keeper_started_backend(monkeypatch, tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-keeper-start'
    ctx = _context(project_root, 'agent1:codex\n')
    expected = project_config_identity_payload(load_project_config(project_root).config)
    inspections = iter(
        [
            _inspection(
                ctx,
                health=LeaseHealth.MISSING,
                socket_connectable=False,
                pid_alive=False,
                heartbeat_fresh=False,
                reason='lease_missing',
            ),
            _inspection(
                ctx,
                health=LeaseHealth.MISSING,
                socket_connectable=False,
                pid_alive=False,
                heartbeat_fresh=False,
                reason='lease_missing',
            ),
            _inspection(
                ctx,
                health=LeaseHealth.HEALTHY,
                socket_connectable=True,
                pid_alive=True,
                heartbeat_fresh=True,
                reason='healthy',
            ),
        ]
    )
    running_intents: list[str] = []

    class FakeClient:
        def __init__(self, socket_path, *, timeout_s=None) -> None:
            del socket_path, timeout_s

        def ping(self, target: str = 'ccbd') -> dict:
            assert target == 'ccbd'
            return {
                'known_agents': list(expected['known_agents']),
                'config_signature': expected['config_signature'],
            }

    monkeypatch.setattr(daemon_service, 'inspect_daemon', _repeat_last_inspection(inspections))
    monkeypatch.setattr(daemon_service, 'CcbdClient', FakeClient)
    monkeypatch.setattr(daemon_service, '_record_running_intent', lambda context: running_intents.append(context.project.project_id))
    monkeypatch.setattr(daemon_service, '_ensure_keeper_started', lambda context: True)

    handle = daemon_service.ensure_daemon_started(ctx)

    assert handle.started is True
    assert running_intents == [ctx.project.project_id]


def test_shutdown_daemon_records_intent_and_terminates_keeper(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / 'repo-kill-keeper'
    ctx = _context(project_root, 'agent1:codex\n')
    layout = PathLayout(project_root)
    KeeperStateStore(layout).save(
        KeeperState(
            project_id=ctx.project.project_id,
            keeper_pid=654,
            started_at='2026-04-02T00:00:00Z',
            last_check_at='2026-04-02T00:00:00Z',
            state='running',
        )
    )
    lease = SimpleNamespace(
        mount_state=SimpleNamespace(value='unmounted'),
        ccbd_pid=0,
        keeper_pid=None,
    )
    manager = SimpleNamespace(
        mark_unmounted=lambda **kwargs: lease,
        load_state=lambda: lease,
    )
    inspection = SimpleNamespace(
        socket_connectable=False,
        pid_alive=False,
        lease=lease,
    )
    terminated: list[int] = []

    monkeypatch.setattr(daemon_service, 'inspect_daemon', lambda context: (manager, None, inspection))
    monkeypatch.setattr(daemon_service, '_wait_for_keeper_exit', lambda context, timeout_s: False)
    monkeypatch.setattr('cli.services.daemon.is_pid_alive', lambda pid: pid == 654)
    monkeypatch.setattr(
        'cli.services.daemon.terminate_pid_tree',
        lambda pid, timeout_s, is_pid_alive_fn: terminated.append(pid) or True,
    )

    summary = daemon_service.shutdown_daemon(ctx, force=False)
    intent = ShutdownIntentStore(layout).load()
    lifecycle = CcbdLifecycleStore(layout).load()

    assert summary.state == 'unmounted'
    assert terminated == [654]
    assert intent is not None
    assert intent.reason == 'kill'
    assert lifecycle is not None
    assert lifecycle.desired_state == 'stopped'
    assert lifecycle.phase == 'unmounted'

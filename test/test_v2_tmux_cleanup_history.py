from __future__ import annotations

from pathlib import Path

from ccbd.lifecycle_report_store import CcbdShutdownReportStore, CcbdStartupReportStore
from ccbd.models import CcbdShutdownReport, CcbdStartupReport
from ccbd.services.project_namespace_state import ProjectNamespaceEvent, ProjectNamespaceEventStore, ProjectNamespaceState, ProjectNamespaceStateStore
from cli.context import CliContextBuilder
from cli.models import ParsedDoctorCommand
from cli.services.doctor import doctor_summary
from cli.services.daemon_runtime.models import LocalPingSummary
from cli.services.tmux_cleanup_history import TmuxCleanupEvent, TmuxCleanupHistoryStore
from cli.services.tmux_project_cleanup import ProjectTmuxCleanupSummary
from mailbox_kernel import InboundEventRecord, InboundEventStatus, InboundEventStore, InboundEventType, MailboxRecord, MailboxState, MailboxStore
from project.resolver import bootstrap_project
from storage.paths import PathLayout


def test_tmux_cleanup_history_store_loads_latest(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-history'
    project_root.mkdir()
    bootstrap_project(project_root)
    layout = PathLayout(project_root)
    store = TmuxCleanupHistoryStore(layout)

    store.append(
        TmuxCleanupEvent(
            event_kind='start',
            project_id='proj-1',
            occurred_at='2026-03-31T01:00:00Z',
            summaries=(
                ProjectTmuxCleanupSummary(
                    socket_name=None,
                    owned_panes=('%1', '%2'),
                    active_panes=('%1',),
                    orphaned_panes=('%2',),
                    killed_panes=('%2',),
                ),
            ),
        )
    )
    store.append(
        TmuxCleanupEvent(
            event_kind='kill',
            project_id='proj-1',
            occurred_at='2026-03-31T01:10:00Z',
            summaries=(
                ProjectTmuxCleanupSummary(
                    socket_name='sock-a',
                    owned_panes=('%9',),
                    active_panes=(),
                    orphaned_panes=('%9',),
                    killed_panes=('%9',),
                ),
            ),
        )
    )

    latest = store.load_latest()

    assert latest is not None
    assert latest.event_kind == 'kill'
    assert latest.summary_fields()['tmux_cleanup_total_killed'] == 1
    assert latest.summary_fields()['tmux_cleanup_sockets'] == ['sock-a']


def test_doctor_summary_includes_latest_tmux_cleanup_fields(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-doctor-history'
    (project_root / '.ccb').mkdir(parents=True, exist_ok=True)
    (project_root / '.ccb' / 'ccb.config').write_text('demo:codex\n', encoding='utf-8')
    bootstrap_project(project_root)
    context = CliContextBuilder().build(ParsedDoctorCommand(project=None), cwd=project_root, bootstrap_if_missing=False)

    TmuxCleanupHistoryStore(context.paths).append(
        TmuxCleanupEvent(
            event_kind='start',
            project_id=context.project.project_id,
            occurred_at='2026-03-31T01:20:00Z',
            summaries=(
                ProjectTmuxCleanupSummary(
                    socket_name=None,
                    owned_panes=('%1', '%2'),
                    active_panes=('%1',),
                    orphaned_panes=('%2',),
                    killed_panes=('%2',),
                ),
            ),
        )
    )

    payload = doctor_summary(context)

    assert payload['ccbd']['tmux_cleanup_last_kind'] == 'start'
    assert payload['ccbd']['tmux_cleanup_last_at'] == '2026-03-31T01:20:00Z'
    assert payload['ccbd']['tmux_cleanup_total_orphaned'] == 1
    assert payload['ccbd']['tmux_cleanup_total_killed'] == 1


def test_doctor_summary_includes_mailbox_summary_fields_and_tolerates_mailbox_errors(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-doctor-mailbox'
    (project_root / '.ccb').mkdir(parents=True, exist_ok=True)
    (project_root / '.ccb' / 'ccb.config').write_text('demo:codex\n', encoding='utf-8')
    bootstrap_project(project_root)
    context = CliContextBuilder().build(ParsedDoctorCommand(project=None), cwd=project_root, bootstrap_if_missing=False)

    MailboxStore(context.paths).save(
        MailboxRecord(
            mailbox_id='mbx_demo',
            agent_name='demo',
            summary_version=4,
            summary_source='transition-terminal',
            summary_refreshed_at='2026-05-08T00:00:05Z',
            active_inbound_event_id=None,
            queue_depth=1,
            pending_reply_count=1,
            head_inbound_event_id='iev_1',
            head_event_type='task_reply',
            head_status='queued',
            head_message_id='msg_1',
            head_attempt_id='att_1',
            head_payload_ref='reply:rep_1',
            last_inbound_started_at='2026-05-08T00:00:00Z',
            last_inbound_finished_at='2026-05-08T00:00:05Z',
            mailbox_state=MailboxState.BLOCKED,
            lease_version=2,
            updated_at='2026-05-08T00:00:05Z',
        )
    )
    InboundEventStore(context.paths).append(
        InboundEventRecord(
            inbound_event_id='iev_1',
            agent_name='demo',
            event_type=InboundEventType.TASK_REPLY,
            message_id='msg_1',
            attempt_id='att_1',
            payload_ref='reply:rep_1',
            priority=10,
            status=InboundEventStatus.QUEUED,
            created_at='2026-05-08T00:00:00Z',
        )
    )

    payload = doctor_summary(context)

    assert payload['agents'][0]['mailbox_summary_version'] == 4
    assert payload['agents'][0]['mailbox_summary_source'] == 'transition-terminal'
    assert payload['agents'][0]['mailbox_state'] == 'blocked'
    assert payload['agents'][0]['mailbox_head_inbound_event_id'] == 'iev_1'
    assert payload['agents'][0]['mailbox_consistency_status'] == 'ok'
    assert payload['agents'][0]['mailbox_consistency_mismatches'] == ()

    context.paths.agent_mailbox_path('demo').write_text('{broken json}\n', encoding='utf-8')

    payload = doctor_summary(context)

    assert payload['agents'][0]['mailbox_summary_version'] is None
    assert payload['agents'][0]['mailbox_consistency_status'] == 'error'
    assert payload['agents'][0]['mailbox_consistency_mismatches'] == ('summary_unreadable',)
    assert payload['agents'][0]['mailbox_consistency_projected']['head_inbound_event_id'] == 'iev_1'
    assert any(str(error).startswith('mailbox_store:demo:') for error in payload['ccbd']['diagnostic_errors'])


def test_doctor_summary_surfaces_mailbox_summary_mismatch_without_rewriting_summary(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-doctor-mailbox-mismatch'
    (project_root / '.ccb').mkdir(parents=True, exist_ok=True)
    (project_root / '.ccb' / 'ccb.config').write_text('demo:codex\n', encoding='utf-8')
    bootstrap_project(project_root)
    context = CliContextBuilder().build(ParsedDoctorCommand(project=None), cwd=project_root, bootstrap_if_missing=False)

    MailboxStore(context.paths).save(
        MailboxRecord(
            mailbox_id='mbx_demo',
            agent_name='demo',
            summary_version=4,
            summary_source='transition-terminal',
            summary_refreshed_at='2026-05-08T00:00:05Z',
            active_inbound_event_id=None,
            queue_depth=0,
            pending_reply_count=0,
            head_inbound_event_id=None,
            head_event_type=None,
            head_status=None,
            head_message_id=None,
            head_attempt_id=None,
            head_payload_ref=None,
            last_inbound_started_at=None,
            last_inbound_finished_at=None,
            mailbox_state=MailboxState.IDLE,
            lease_version=0,
            updated_at='2026-05-08T00:00:05Z',
        )
    )
    InboundEventStore(context.paths).append(
        InboundEventRecord(
            inbound_event_id='iev_1',
            agent_name='demo',
            event_type=InboundEventType.TASK_REPLY,
            message_id='msg_1',
            attempt_id='att_1',
            payload_ref='reply:rep_1',
            priority=10,
            status=InboundEventStatus.QUEUED,
            created_at='2026-05-08T00:00:00Z',
        )
    )

    payload = doctor_summary(context)

    assert payload['agents'][0]['mailbox_summary_version'] == 4
    assert payload['agents'][0]['mailbox_consistency_status'] == 'mismatch'
    assert payload['agents'][0]['mailbox_consistency_mismatches'] == (
        'mailbox_state',
        'queue_depth',
        'pending_reply_count',
        'head_inbound_event_id',
        'head_event_type',
        'head_status',
        'head_message_id',
        'head_attempt_id',
        'head_payload_ref',
    )
    assert payload['agents'][0]['mailbox_consistency_projected']['mailbox_state'] == 'blocked'
    assert payload['agents'][0]['mailbox_consistency_projected']['head_inbound_event_id'] == 'iev_1'

    persisted = MailboxStore(context.paths).load('demo')
    assert persisted is not None
    assert persisted.summary_version == 4
    assert persisted.queue_depth == 0


def test_doctor_summary_surfaces_missing_mailbox_summary_when_ledger_has_material_state(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-doctor-mailbox-missing'
    (project_root / '.ccb').mkdir(parents=True, exist_ok=True)
    (project_root / '.ccb' / 'ccb.config').write_text('demo:codex\n', encoding='utf-8')
    bootstrap_project(project_root)
    context = CliContextBuilder().build(ParsedDoctorCommand(project=None), cwd=project_root, bootstrap_if_missing=False)

    InboundEventStore(context.paths).append(
        InboundEventRecord(
            inbound_event_id='iev_1',
            agent_name='demo',
            event_type=InboundEventType.TASK_REPLY,
            message_id='msg_1',
            attempt_id='att_1',
            payload_ref='reply:rep_1',
            priority=10,
            status=InboundEventStatus.QUEUED,
            created_at='2026-05-08T00:00:00Z',
        )
    )

    payload = doctor_summary(context)

    assert payload['agents'][0]['mailbox_summary_version'] is None
    assert payload['agents'][0]['mailbox_consistency_status'] == 'mismatch'
    assert payload['agents'][0]['mailbox_consistency_mismatches'] == ('summary_missing',)
    assert payload['agents'][0]['mailbox_consistency_projected']['queue_depth'] == 1
    assert payload['agents'][0]['mailbox_consistency_projected']['head_inbound_event_id'] == 'iev_1'


def test_doctor_summary_includes_installation_and_requirement_fields(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / 'repo-doctor-install'
    (project_root / '.ccb').mkdir(parents=True, exist_ok=True)
    (project_root / '.ccb' / 'ccb.config').write_text('demo:codex\n', encoding='utf-8')
    bootstrap_project(project_root)
    context = CliContextBuilder().build(ParsedDoctorCommand(project=None), cwd=project_root, bootstrap_if_missing=False)

    monkeypatch.setattr(
        'cli.services.doctor.installation_summary',
        lambda: {
            'path': '/tmp/install',
            'version': '5.2.8',
            'commit': 'abc1234',
            'date': '2026-04-09',
            'channel': 'stable',
            'platform': 'linux',
            'arch': 'x86_64',
            'build_time': '2026-04-09T10:11:12Z',
            'installed_at': '2026-04-09T10:15:00Z',
            'source_kind': 'release',
            'install_mode': 'release',
        },
    )
    monkeypatch.setattr(
        'cli.services.doctor.requirements_summary',
        lambda: {
            'python_executable': '/usr/bin/python3',
            'python_version': '3.11.0',
            'tmux_available': True,
            'tmux_path': '/usr/bin/tmux',
            'provider_commands': (
                {
                    'provider': 'codex',
                    'executable': 'codex',
                    'available': True,
                    'path': '/usr/bin/codex',
                },
            ),
        },
    )

    payload = doctor_summary(context)

    assert payload['installation']['install_mode'] == 'release'
    assert payload['installation']['channel'] == 'stable'
    assert payload['requirements']['tmux_available'] is True
    assert payload['requirements']['provider_commands'][0]['provider'] == 'codex'


def test_doctor_summary_falls_back_to_local_ccbd_when_remote_ping_fails(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / 'repo-doctor-remote-fallback'
    (project_root / '.ccb').mkdir(parents=True, exist_ok=True)
    (project_root / '.ccb' / 'ccb.config').write_text('demo:codex\n', encoding='utf-8')
    bootstrap_project(project_root)
    context = CliContextBuilder().build(ParsedDoctorCommand(project=None), cwd=project_root, bootstrap_if_missing=False)

    monkeypatch.setattr(
        'cli.services.doctor.ping_local_state',
        lambda _context: LocalPingSummary(
            project_id=context.project.project_id,
            mount_state='mounted',
            desired_state='running',
            health='healthy',
            generation=4,
            project_anchor_path=str(context.paths.ccb_dir),
            runtime_state_root=str(context.paths.runtime_state_root),
            runtime_root_kind=context.paths.runtime_state_placement.root_kind,
            runtime_relocation_reason=context.paths.runtime_state_placement.relocation_reason,
            runtime_filesystem_hint=context.paths.runtime_state_placement.filesystem_hint,
            runtime_marker_status=context.paths.runtime_marker_status,
            socket_path=str(context.paths.ccbd_socket_path),
            preferred_socket_path=str(context.paths.ccbd_socket_placement.preferred_path),
            effective_socket_path=str(context.paths.ccbd_socket_placement.effective_path),
            socket_root_kind=context.paths.ccbd_socket_placement.root_kind,
            socket_fallback_reason=context.paths.ccbd_socket_placement.fallback_reason,
            socket_filesystem_hint=context.paths.ccbd_socket_placement.filesystem_hint,
            tmux_socket_path=str(context.paths.ccbd_tmux_socket_path),
            tmux_preferred_socket_path=str(context.paths.ccbd_tmux_socket_placement.preferred_path),
            tmux_effective_socket_path=str(context.paths.ccbd_tmux_socket_placement.effective_path),
            tmux_socket_root_kind=context.paths.ccbd_tmux_socket_placement.root_kind,
            tmux_socket_fallback_reason=context.paths.ccbd_tmux_socket_placement.fallback_reason,
            tmux_socket_filesystem_hint=context.paths.ccbd_tmux_socket_placement.filesystem_hint,
            last_heartbeat_at='2026-05-08T00:00:00Z',
            pid_alive=True,
            socket_connectable=True,
            heartbeat_fresh=True,
            takeover_allowed=False,
            reason='healthy',
        ),
    )
    monkeypatch.setattr(
        'cli.services.doctor.CcbdClient',
        lambda socket_path, timeout_s=None: (_ for _ in ()).throw(RuntimeError('boom')),
    )

    payload = doctor_summary(context)

    assert payload['ccbd']['state'] == 'mounted'
    assert payload['ccbd']['last_request_queue_wait_s'] is None
    assert payload['ccbd']['last_submit_duration_s'] is None
    assert payload['ccbd']['last_ping_duration_s'] is None
    assert payload['ccbd']['last_maintenance_duration_s'] is None
    assert payload['ccbd']['pending_maintenance_ticks'] is None
    assert any(str(error).startswith('remote_ccbd_probe:') for error in payload['ccbd']['diagnostic_errors'])


def test_doctor_summary_uses_non_mutating_remote_probe(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / 'repo-doctor-no-restart'
    (project_root / '.ccb').mkdir(parents=True, exist_ok=True)
    (project_root / '.ccb' / 'ccb.config').write_text('demo:codex\n', encoding='utf-8')
    bootstrap_project(project_root)
    context = CliContextBuilder().build(ParsedDoctorCommand(project=None), cwd=project_root, bootstrap_if_missing=False)

    monkeypatch.setattr(
        'cli.services.doctor.ping_local_state',
        lambda _context: LocalPingSummary(
            project_id=context.project.project_id,
            mount_state='mounted',
            desired_state='running',
            health='healthy',
            generation=4,
            project_anchor_path=str(context.paths.ccb_dir),
            runtime_state_root=str(context.paths.runtime_state_root),
            runtime_root_kind=context.paths.runtime_state_placement.root_kind,
            runtime_relocation_reason=context.paths.runtime_state_placement.relocation_reason,
            runtime_filesystem_hint=context.paths.runtime_state_placement.filesystem_hint,
            runtime_marker_status=context.paths.runtime_marker_status,
            socket_path=str(context.paths.ccbd_socket_path),
            preferred_socket_path=str(context.paths.ccbd_socket_placement.preferred_path),
            effective_socket_path=str(context.paths.ccbd_socket_placement.effective_path),
            socket_root_kind=context.paths.ccbd_socket_placement.root_kind,
            socket_fallback_reason=context.paths.ccbd_socket_placement.fallback_reason,
            socket_filesystem_hint=context.paths.ccbd_socket_placement.filesystem_hint,
            tmux_socket_path=str(context.paths.ccbd_tmux_socket_path),
            tmux_preferred_socket_path=str(context.paths.ccbd_tmux_socket_placement.preferred_path),
            tmux_effective_socket_path=str(context.paths.ccbd_tmux_socket_placement.effective_path),
            tmux_socket_root_kind=context.paths.ccbd_tmux_socket_placement.root_kind,
            tmux_socket_fallback_reason=context.paths.ccbd_tmux_socket_placement.fallback_reason,
            tmux_socket_filesystem_hint=context.paths.ccbd_tmux_socket_placement.filesystem_hint,
            last_heartbeat_at='2026-05-08T00:00:00Z',
            pid_alive=True,
            socket_connectable=True,
            heartbeat_fresh=True,
            takeover_allowed=False,
            reason='healthy',
        ),
    )

    seen: list[tuple[object, object]] = []

    class _Client:
        def ping(self, target: str) -> dict:
            assert target == 'ccbd'
            return {'diagnostics': {}}

    def _client(socket_path, timeout_s=None):
        seen.append((socket_path, timeout_s))
        return _Client()

    monkeypatch.setattr('cli.services.doctor.CcbdClient', _client)

    doctor_summary(context)

    assert len(seen) == 1
    assert str(seen[0][0]) == str(context.paths.ccbd_socket_path)
    assert seen[0][1] == 0.5


def test_doctor_summary_skips_remote_probe_when_unmounted(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / 'repo-doctor-unmounted'
    (project_root / '.ccb').mkdir(parents=True, exist_ok=True)
    (project_root / '.ccb' / 'ccb.config').write_text('demo:codex\n', encoding='utf-8')
    bootstrap_project(project_root)
    context = CliContextBuilder().build(ParsedDoctorCommand(project=None), cwd=project_root, bootstrap_if_missing=False)

    monkeypatch.setattr(
        'cli.services.doctor.ping_local_state',
        lambda _context: LocalPingSummary(
            project_id=context.project.project_id,
            mount_state='unmounted',
            desired_state='stopped',
            health='unmounted',
            generation=0,
            project_anchor_path=str(context.paths.ccb_dir),
            runtime_state_root=str(context.paths.runtime_state_root),
            runtime_root_kind=context.paths.runtime_state_placement.root_kind,
            runtime_relocation_reason=context.paths.runtime_state_placement.relocation_reason,
            runtime_filesystem_hint=context.paths.runtime_state_placement.filesystem_hint,
            runtime_marker_status=context.paths.runtime_marker_status,
            socket_path=None,
            preferred_socket_path=str(context.paths.ccbd_socket_placement.preferred_path),
            effective_socket_path=str(context.paths.ccbd_socket_placement.effective_path),
            socket_root_kind=context.paths.ccbd_socket_placement.root_kind,
            socket_fallback_reason=context.paths.ccbd_socket_placement.fallback_reason,
            socket_filesystem_hint=context.paths.ccbd_socket_placement.filesystem_hint,
            tmux_socket_path=str(context.paths.ccbd_tmux_socket_path),
            tmux_preferred_socket_path=str(context.paths.ccbd_tmux_socket_placement.preferred_path),
            tmux_effective_socket_path=str(context.paths.ccbd_tmux_socket_placement.effective_path),
            tmux_socket_root_kind=context.paths.ccbd_tmux_socket_placement.root_kind,
            tmux_socket_fallback_reason=context.paths.ccbd_tmux_socket_placement.fallback_reason,
            tmux_socket_filesystem_hint=context.paths.ccbd_tmux_socket_placement.filesystem_hint,
            last_heartbeat_at=None,
            pid_alive=False,
            socket_connectable=False,
            heartbeat_fresh=False,
            takeover_allowed=True,
            reason='lease_unmounted',
        ),
    )
    monkeypatch.setattr(
        'cli.services.doctor.CcbdClient',
        lambda socket_path, timeout_s=None: (_ for _ in ()).throw(AssertionError('remote probe should not run')),
    )

    payload = doctor_summary(context)

    assert payload['ccbd']['state'] == 'unmounted'


def test_doctor_summary_skips_remote_probe_when_socket_not_connectable(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / 'repo-doctor-socket-unreachable'
    (project_root / '.ccb').mkdir(parents=True, exist_ok=True)
    (project_root / '.ccb' / 'ccb.config').write_text('demo:codex\n', encoding='utf-8')
    bootstrap_project(project_root)
    context = CliContextBuilder().build(ParsedDoctorCommand(project=None), cwd=project_root, bootstrap_if_missing=False)

    monkeypatch.setattr(
        'cli.services.doctor.ping_local_state',
        lambda _context: LocalPingSummary(
            project_id=context.project.project_id,
            mount_state='mounted',
            desired_state='running',
            health='failed',
            generation=1,
            project_anchor_path=str(context.paths.ccb_dir),
            runtime_state_root=str(context.paths.runtime_state_root),
            runtime_root_kind=context.paths.runtime_state_placement.root_kind,
            runtime_relocation_reason=context.paths.runtime_state_placement.relocation_reason,
            runtime_filesystem_hint=context.paths.runtime_state_placement.filesystem_hint,
            runtime_marker_status=context.paths.runtime_marker_status,
            socket_path=str(context.paths.ccbd_socket_path),
            preferred_socket_path=str(context.paths.ccbd_socket_placement.preferred_path),
            effective_socket_path=str(context.paths.ccbd_socket_placement.effective_path),
            socket_root_kind=context.paths.ccbd_socket_placement.root_kind,
            socket_fallback_reason=context.paths.ccbd_socket_placement.fallback_reason,
            socket_filesystem_hint=context.paths.ccbd_socket_placement.filesystem_hint,
            tmux_socket_path=str(context.paths.ccbd_tmux_socket_path),
            tmux_preferred_socket_path=str(context.paths.ccbd_tmux_socket_placement.preferred_path),
            tmux_effective_socket_path=str(context.paths.ccbd_tmux_socket_placement.effective_path),
            tmux_socket_root_kind=context.paths.ccbd_tmux_socket_placement.root_kind,
            tmux_socket_fallback_reason=context.paths.ccbd_tmux_socket_placement.fallback_reason,
            tmux_socket_filesystem_hint=context.paths.ccbd_tmux_socket_placement.filesystem_hint,
            last_heartbeat_at='2026-05-08T00:00:00Z',
            pid_alive=True,
            socket_connectable=False,
            heartbeat_fresh=True,
            takeover_allowed=False,
            reason='socket_unreachable',
        ),
    )
    monkeypatch.setattr(
        'cli.services.doctor.CcbdClient',
        lambda socket_path, timeout_s=None: (_ for _ in ()).throw(AssertionError('remote probe should not run')),
    )

    payload = doctor_summary(context)

    assert payload['ccbd']['state'] == 'mounted'
    assert payload['ccbd']['socket_connectable'] is False
    assert payload['ccbd']['last_request_queue_wait_s'] is None
    assert payload['ccbd']['pending_maintenance_ticks'] is None


def test_doctor_summary_includes_namespace_state_and_latest_event(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-doctor-namespace'
    (project_root / '.ccb').mkdir(parents=True, exist_ok=True)
    (project_root / '.ccb' / 'ccb.config').write_text('demo:codex\n', encoding='utf-8')
    bootstrap_project(project_root)
    context = CliContextBuilder().build(ParsedDoctorCommand(project=None), cwd=project_root, bootstrap_if_missing=False)

    ProjectNamespaceStateStore(context.paths).save(
        ProjectNamespaceState(
            project_id=context.project.project_id,
            namespace_epoch=4,
            tmux_socket_path=str(context.paths.ccbd_tmux_socket_path),
            tmux_session_name=context.paths.ccbd_tmux_session_name,
            layout_version=1,
            ui_attachable=True,
            last_started_at='2026-04-03T00:05:00Z',
            last_destroyed_at=None,
            last_destroy_reason=None,
        )
    )
    ProjectNamespaceEventStore(context.paths).append(
        ProjectNamespaceEvent(
            event_kind='namespace_created',
            project_id=context.project.project_id,
            occurred_at='2026-04-03T00:05:00Z',
            namespace_epoch=4,
            tmux_socket_path=str(context.paths.ccbd_tmux_socket_path),
            tmux_session_name=context.paths.ccbd_tmux_session_name,
            details={'recreated': False},
        )
    )

    payload = doctor_summary(context)

    assert payload['ccbd']['namespace_epoch'] == 4
    assert payload['ccbd']['namespace_tmux_socket_path'] == str(context.paths.ccbd_tmux_socket_path)
    assert payload['ccbd']['namespace_tmux_session_name'] == context.paths.ccbd_tmux_session_name
    assert payload['ccbd']['namespace_last_event_kind'] == 'namespace_created'
    assert payload['ccbd']['namespace_last_event_at'] == '2026-04-03T00:05:00Z'


def test_doctor_summary_includes_startup_and_shutdown_report_fields(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-doctor-reports'
    (project_root / '.ccb').mkdir(parents=True, exist_ok=True)
    (project_root / '.ccb' / 'ccb.config').write_text('demo:codex\n', encoding='utf-8')
    bootstrap_project(project_root)
    context = CliContextBuilder().build(ParsedDoctorCommand(project=None), cwd=project_root, bootstrap_if_missing=False)

    CcbdStartupReportStore(context.paths).save(
        CcbdStartupReport(
            project_id=context.project.project_id,
            generated_at='2026-04-03T00:00:00Z',
            trigger='start_command',
            status='ok',
            requested_agents=('demo',),
            desired_agents=('demo',),
            restore_requested=False,
            auto_permission=False,
            daemon_generation=2,
            daemon_started=True,
            config_signature='sig-1',
            inspection={},
            restore_summary={},
            actions_taken=('launch_runtime:demo',),
            cleanup_summaries=(),
            agent_results=(),
            failure_reason=None,
        )
    )
    CcbdShutdownReportStore(context.paths).save(
        CcbdShutdownReport(
            project_id=context.project.project_id,
            generated_at='2026-04-03T00:10:00Z',
            trigger='kill',
            status='ok',
            forced=False,
            stopped_agents=('demo',),
            daemon_generation=2,
            reason='kill',
            inspection_after={},
            actions_taken=('request_shutdown_intent',),
            cleanup_summaries=(),
            runtime_snapshots=(),
            failure_reason=None,
        )
    )

    payload = doctor_summary(context)

    assert payload['ccbd']['startup_last_trigger'] == 'start_command'
    assert payload['ccbd']['startup_last_status'] == 'ok'
    assert payload['ccbd']['startup_last_daemon_started'] is True
    assert payload['ccbd']['shutdown_last_trigger'] == 'kill'
    assert payload['ccbd']['shutdown_last_status'] == 'ok'
    assert payload['ccbd']['shutdown_last_reason'] == 'kill'


def test_doctor_summary_includes_socket_placement_fields(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / 'repo-doctor-socket-placement'
    (project_root / '.ccb').mkdir(parents=True, exist_ok=True)
    (project_root / '.ccb' / 'ccb.config').write_text('demo:codex\n', encoding='utf-8')
    bootstrap_project(project_root)
    context = CliContextBuilder().build(ParsedDoctorCommand(project=None), cwd=project_root, bootstrap_if_missing=False)

    monkeypatch.setattr(
        'cli.services.doctor.ping_local_state',
        lambda _context: LocalPingSummary(
            project_id=context.project.project_id,
            mount_state='unmounted',
            desired_state='running',
            health='unmounted',
            generation=4,
            project_anchor_path=str(context.paths.ccb_dir),
            runtime_state_root=str(context.paths.runtime_state_root),
            runtime_root_kind=context.paths.runtime_state_placement.root_kind,
            runtime_relocation_reason=context.paths.runtime_state_placement.relocation_reason,
            runtime_filesystem_hint=context.paths.runtime_state_placement.filesystem_hint,
            runtime_marker_status=context.paths.runtime_marker_status,
            socket_path=None,
            preferred_socket_path='/home/demo/.local/state/ccb/projects/proj-1/ccbd/ccbd.sock',
            effective_socket_path='/home/demo/.local/state/ccb/projects/proj-1/ccbd/ccbd.sock',
            socket_root_kind='runtime',
            socket_fallback_reason=None,
            socket_filesystem_hint=None,
            tmux_socket_path='/home/demo/.local/state/ccb/projects/proj-1/ccbd/tmux.sock',
            tmux_preferred_socket_path='/home/demo/.local/state/ccb/projects/proj-1/ccbd/tmux.sock',
            tmux_effective_socket_path='/home/demo/.local/state/ccb/projects/proj-1/ccbd/tmux.sock',
            tmux_socket_root_kind='runtime',
            tmux_socket_fallback_reason=None,
            tmux_socket_filesystem_hint=None,
            last_heartbeat_at=None,
            pid_alive=False,
            socket_connectable=False,
            heartbeat_fresh=False,
            takeover_allowed=True,
            reason='lease_unmounted',
            last_failure_reason='listen_socket_failed',
            shutdown_intent=None,
        ),
    )

    payload = doctor_summary(context)

    assert payload['ccbd']['preferred_socket_path'] == '/home/demo/.local/state/ccb/projects/proj-1/ccbd/ccbd.sock'
    assert payload['ccbd']['effective_socket_path'] == '/home/demo/.local/state/ccb/projects/proj-1/ccbd/ccbd.sock'
    assert payload['ccbd']['preferred_socket_path_bytes'] == len('/home/demo/.local/state/ccb/projects/proj-1/ccbd/ccbd.sock'.encode())
    assert payload['ccbd']['effective_socket_path_bytes'] == len('/home/demo/.local/state/ccb/projects/proj-1/ccbd/ccbd.sock'.encode())
    assert payload['ccbd']['socket_root_kind'] == 'runtime'
    assert payload['ccbd']['socket_fallback_reason'] is None
    assert payload['ccbd']['tmux_effective_socket_path'] == '/home/demo/.local/state/ccb/projects/proj-1/ccbd/tmux.sock'
    assert payload['ccbd']['tmux_preferred_socket_path_bytes'] == len('/home/demo/.local/state/ccb/projects/proj-1/ccbd/tmux.sock'.encode())
    assert payload['ccbd']['tmux_effective_socket_path_bytes'] == len('/home/demo/.local/state/ccb/projects/proj-1/ccbd/tmux.sock'.encode())
    assert payload['ccbd']['tmux_start_server_command'] == 'tmux -f /dev/null -S /home/demo/.local/state/ccb/projects/proj-1/ccbd/tmux.sock start-server'

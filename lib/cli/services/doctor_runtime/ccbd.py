from __future__ import annotations

import os
import shlex

from terminal_runtime.tmux import tmux_base
from .stores import report_summary_fields, safe_report_load


def ccbd_summary(*, local, stores: dict[str, object], errors: list[str], remote: dict | None = None) -> dict:
    return {
        'state': local.mount_state,
        'pid': None,
        'socket_path': local.socket_path,
        'project_anchor_path': local.project_anchor_path,
        'runtime_state_root': local.runtime_state_root,
        'runtime_root_kind': local.runtime_root_kind,
        'runtime_relocation_reason': local.runtime_relocation_reason,
        'runtime_filesystem_hint': local.runtime_filesystem_hint,
        'runtime_marker_status': local.runtime_marker_status,
        'preferred_socket_path': local.preferred_socket_path,
        'effective_socket_path': local.effective_socket_path,
        'preferred_socket_path_bytes': _path_bytes(local.preferred_socket_path),
        'effective_socket_path_bytes': _path_bytes(local.effective_socket_path),
        'socket_root_kind': local.socket_root_kind,
        'socket_fallback_reason': local.socket_fallback_reason,
        'socket_filesystem_hint': local.socket_filesystem_hint,
        'tmux_socket_path': local.tmux_socket_path,
        'tmux_preferred_socket_path': local.tmux_preferred_socket_path,
        'tmux_effective_socket_path': local.tmux_effective_socket_path,
        'tmux_preferred_socket_path_bytes': _path_bytes(local.tmux_preferred_socket_path),
        'tmux_effective_socket_path_bytes': _path_bytes(local.tmux_effective_socket_path),
        'tmux_start_server_command': _tmux_start_server_command(local.tmux_effective_socket_path),
        'tmux_socket_root_kind': local.tmux_socket_root_kind,
        'tmux_socket_fallback_reason': local.tmux_socket_fallback_reason,
        'tmux_socket_filesystem_hint': local.tmux_socket_filesystem_hint,
        'generation': local.generation,
        'health': local.health,
        'last_heartbeat_at': local.last_heartbeat_at,
        'pid_alive': local.pid_alive,
        'socket_connectable': local.socket_connectable,
        'heartbeat_fresh': local.heartbeat_fresh,
        'takeover_allowed': local.takeover_allowed,
        'reason': local.reason,
        'last_request_queue_wait_s': _remote_metric(remote, 'last_request_queue_wait_s'),
        'last_submit_duration_s': _remote_metric(remote, 'last_submit_duration_s'),
        'last_ping_duration_s': _remote_metric(remote, 'last_ping_duration_s'),
        'last_maintenance_duration_s': _remote_metric(remote, 'last_maintenance_duration_s'),
        'pending_maintenance_ticks': _remote_metric(remote, 'pending_maintenance_ticks'),
        'startup_id': local.startup_id,
        'startup_stage': local.startup_stage,
        'last_progress_at': local.last_progress_at,
        'startup_deadline_at': local.startup_deadline_at,
        **stores['execution_state'].summary(),
        **report_summary_fields(safe_report_load(stores['restore_report'].load, errors, label='restore_report')),
        **report_summary_fields(safe_report_load(stores['startup_report'].load, errors, label='startup_report')),
        **report_summary_fields(safe_report_load(stores['shutdown_report'].load, errors, label='shutdown_report')),
        **report_summary_fields(safe_report_load(stores['namespace_state'].load, errors, label='namespace_state')),
        **report_summary_fields(safe_report_load(stores['namespace_event'].load_latest, errors, label='namespace_event')),
        **report_summary_fields(safe_report_load(stores['start_policy'].load, errors, label='start_policy')),
        **report_summary_fields(safe_report_load(stores['tmux_cleanup'].load_latest, errors, label='tmux_cleanup')),
        'diagnostic_errors': errors,
    }


def _path_bytes(path: object) -> int | None:
    text = str(path or '').strip()
    if not text:
        return None
    return len(os.fsencode(text))


def _tmux_start_server_command(socket_path: object) -> str | None:
    text = str(socket_path or '').strip()
    if not text:
        return None
    return shlex.join([*tmux_base(socket_path=text), 'start-server'])


def _remote_metric(remote: dict | None, key: str) -> float | None:
    if not isinstance(remote, dict):
        return None
    diagnostics = remote.get('diagnostics')
    if not isinstance(diagnostics, dict):
        return None
    value = diagnostics.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


__all__ = ['ccbd_summary']

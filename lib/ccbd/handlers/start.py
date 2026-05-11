from __future__ import annotations


def build_start_handler(app):
    def handle(payload: dict) -> dict:
        requested = tuple(
            str(item).strip()
            for item in (payload.get('agent_names') or ())
            if str(item).strip()
        )
        terminal_size = _terminal_size_from_payload(payload)
        with app.start_maintenance_lock:
            summary = app.runtime_supervisor.start(
                agent_names=requested,
                restore=bool(payload.get('restore')),
                auto_permission=bool(payload.get('auto_permission')),
                terminal_size=terminal_size,
            )
            app.persist_start_policy(
                auto_permission=bool(payload.get('auto_permission')),
                source='start_command',
            )
        return summary.to_record()

    return handle


def _terminal_size_from_payload(payload: dict) -> tuple[int, int] | None:
    try:
        width = int(payload.get('terminal_width') or 0)
        height = int(payload.get('terminal_height') or 0)
    except Exception:
        return None
    if width <= 0 or height <= 0:
        return None
    return width, height

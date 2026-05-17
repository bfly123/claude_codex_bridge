from __future__ import annotations


def handle_ask(context, command, out, services) -> int:
    summary = services.submit_ask(context, command)
    services.write_lines(out, services.render_ask(summary))
    return 0


__all__ = ['handle_ask']

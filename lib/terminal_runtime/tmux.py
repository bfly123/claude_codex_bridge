from __future__ import annotations

import os
from pathlib import Path


_DEFAULT_CCB_TMUX_CONFIG = "/dev/null"


def tmux_base(
    socket_name: str | None = None,
    *,
    socket_path: str | None = None,
) -> list[str]:
    cmd = ["tmux", *config_base_args()]
    cmd.extend(socket_base_args(socket_name=socket_name, socket_path=socket_path))
    return cmd


def config_base_args() -> list[str]:
    config_path = str(os.environ.get("CCB_TMUX_CONFIG") or _DEFAULT_CCB_TMUX_CONFIG).strip()
    if not config_path:
        return []
    return ["-f", str(Path(config_path).expanduser())]


def socket_base_args(*, socket_name: str | None, socket_path: str | None) -> list[str]:
    if socket_path:
        return ["-S", str(Path(socket_path).expanduser())]
    if socket_name:
        return ["-L", socket_name]
    return []


def normalize_socket_name(value: str | None) -> str | None:
    text = (value or "").strip()
    if not text:
        return None
    return None if text == "default" else text


def socket_name_from_tmux_env(value: str | None) -> str | None:
    text = (value or "").strip()
    if not text:
        return None
    socket_path = text.split(",", 1)[0].strip()
    if not socket_path:
        return None
    return normalize_socket_name(Path(socket_path).name)


def socket_ref_from_tmux_env(value: str | None) -> str | None:
    text = (value or "").strip()
    if not text:
        return None
    socket_path = text.split(",", 1)[0].strip()
    if not socket_path:
        return None
    if "/" in socket_path or "\\" in socket_path:
        return str(Path(socket_path).expanduser())
    return normalize_socket_name(socket_path)


def looks_like_pane_id(value: str) -> bool:
    return (value or "").strip().startswith("%")


def looks_like_tmux_target(value: str) -> bool:
    v = (value or "").strip()
    if not v:
        return False
    return v.startswith("%") or (":" in v) or ("." in v)


def normalize_split_direction(direction: str) -> tuple[str, str]:
    direction_norm = (direction or "").strip().lower()
    if direction_norm in ("right", "h", "horizontal"):
        return "-h", "right"
    if direction_norm in ("bottom", "v", "vertical"):
        return "-v", "bottom"
    raise ValueError(f"unsupported direction: {direction!r} (use 'right' or 'bottom')")


def pane_id_by_title_marker_output(stdout: str, marker: str) -> str | None:
    marker = normalized_marker(marker)
    if not marker:
        return None
    exact_matches, prefix_matches = collect_pane_title_matches(stdout, marker)
    return select_marker_match(exact_matches, prefix_matches)


def collect_pane_title_matches(stdout: str, marker: str) -> tuple[list[str], list[str]]:
    exact_matches: list[str] = []
    prefix_matches: list[str] = []
    for line in (stdout or "").splitlines():
        parsed = parse_pane_title_line(line)
        if parsed is None:
            continue
        pid, title = parsed
        record_pane_title_match(
            pid=pid,
            title=title,
            marker=marker,
            exact_matches=exact_matches,
            prefix_matches=prefix_matches,
        )
    return exact_matches, prefix_matches


def record_pane_title_match(
    *,
    pid: str,
    title: str,
    marker: str,
    exact_matches: list[str],
    prefix_matches: list[str],
) -> None:
    if title == marker:
        exact_matches.append(pid)
        return
    if title.startswith(marker):
        prefix_matches.append(pid)


def select_marker_match(exact_matches: list[str], prefix_matches: list[str]) -> str | None:
    if len(exact_matches) == 1:
        return exact_matches[0]
    if exact_matches:
        return None
    if len(prefix_matches) == 1:
        return prefix_matches[0]
    return None


def default_detached_session_name(*, cwd: str, pid: int, now_ts: float) -> str:
    return f"ccb-{Path(cwd).name}-{int(now_ts) % 100000}-{pid}"


def normalized_marker(marker: str) -> str:
    return (marker or "").strip()


def parse_pane_title_line(line: str) -> tuple[str, str] | None:
    if not line.strip():
        return None
    pid, title = split_pane_title_line(line)
    pid = pid.strip()
    if not looks_like_pane_id(pid):
        return None
    return pid, (title or "").strip()


def split_pane_title_line(line: str) -> tuple[str, str]:
    if "\t" in line:
        return line.split("\t", 1)
    parts = line.split(" ", 1)
    return parts[0], parts[1] if len(parts) > 1 else ""

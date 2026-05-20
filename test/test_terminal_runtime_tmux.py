from __future__ import annotations

from pathlib import Path

import pytest

from terminal_runtime.tmux import default_detached_session_name
from terminal_runtime.tmux import looks_like_pane_id
from terminal_runtime.tmux import looks_like_tmux_target
from terminal_runtime.tmux import normalize_socket_name
from terminal_runtime.tmux import normalize_split_direction
from terminal_runtime.tmux import pane_id_by_title_marker_output
from terminal_runtime.tmux import socket_name_from_tmux_env
from terminal_runtime.tmux import tmux_base


def test_tmux_base_includes_socket_when_present(monkeypatch) -> None:
    monkeypatch.delenv("CCB_TMUX_CONFIG", raising=False)

    assert tmux_base(None) == ["tmux", "-f", "/dev/null"]
    assert tmux_base("ccb-demo") == ["tmux", "-f", "/dev/null", "-L", "ccb-demo"]
    assert tmux_base("ccb-demo", socket_path="~/.tmux/demo.sock") == [
        "tmux",
        "-f",
        "/dev/null",
        "-S",
        str(Path("~/.tmux/demo.sock").expanduser()),
    ]


def test_tmux_base_allows_managed_config_override(monkeypatch) -> None:
    monkeypatch.setenv("CCB_TMUX_CONFIG", "~/.config/ccb/tmux.conf")

    assert tmux_base("ccb-demo") == [
        "tmux",
        "-f",
        str(Path("~/.config/ccb/tmux.conf").expanduser()),
        "-L",
        "ccb-demo",
    ]


def test_tmux_target_helpers() -> None:
    assert looks_like_pane_id("%1") is True
    assert looks_like_pane_id("sess") is False
    assert looks_like_tmux_target("%1") is True
    assert looks_like_tmux_target("sess:1.0") is True
    assert looks_like_tmux_target("sess") is False


def test_tmux_socket_name_helpers() -> None:
    assert normalize_socket_name(None) is None
    assert normalize_socket_name("") is None
    assert normalize_socket_name("default") is None
    assert normalize_socket_name("ccb") == "ccb"
    assert socket_name_from_tmux_env(None) is None
    assert socket_name_from_tmux_env("") is None
    assert socket_name_from_tmux_env("/tmp/tmux-1000/default,123,0") is None
    assert socket_name_from_tmux_env("/tmp/tmux-1000/ccb,123,0") == "ccb"


def test_normalize_split_direction() -> None:
    assert normalize_split_direction("right") == ("-h", "right")
    assert normalize_split_direction("vertical") == ("-v", "bottom")
    with pytest.raises(ValueError):
        normalize_split_direction("left")


def test_pane_id_by_title_marker_output_parses_list_panes() -> None:
    stdout = "%1\tCCB-a\n%2\tOTHER\n"
    assert pane_id_by_title_marker_output(stdout, "CCB") == "%1"
    assert pane_id_by_title_marker_output(stdout, "missing") is None


def test_pane_id_by_title_marker_output_rejects_ambiguous_prefix_matches() -> None:
    stdout = "%1\tCCB-codex-a1b2c3d4\n%2\tCCB-codex-e5f6g7h8\n"
    assert pane_id_by_title_marker_output(stdout, "CCB-codex") is None


def test_pane_id_by_title_marker_output_prefers_unique_exact_match() -> None:
    stdout = "%1\tCCB-codex\n%2\tCCB-codex-a1b2c3d4\n"
    assert pane_id_by_title_marker_output(stdout, "CCB-codex") == "%1"


def test_default_detached_session_name_is_stable_format() -> None:
    name = default_detached_session_name(cwd="/tmp/demo", pid=123, now_ts=1700000000.0)
    assert name == "ccb-demo-0-123"

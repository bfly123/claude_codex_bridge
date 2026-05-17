from __future__ import annotations

import argparse
from io import StringIO
from pathlib import Path

from cli.entrypoint import run_cli_entrypoint
from cli.router import (
    dispatch_auxiliary_command,
    dispatch_management_command,
    parse_start_args,
)


def test_dispatch_auxiliary_command_routes_droid_only() -> None:
    calls: list[tuple[str, list[str]]] = []

    def droid_handler(argv):
        calls.append(("droid", list(argv)))
        return 11

    assert dispatch_auxiliary_command(
        ["droid", "setup-delegation"],
        droid_handler=droid_handler,
    ) == 11
    assert dispatch_auxiliary_command(
        ["version"],
        droid_handler=droid_handler,
    ) is None
    assert calls == [("droid", ["setup-delegation"])]


def test_dispatch_management_command_parses_and_routes() -> None:
    calls: list[tuple[str, argparse.Namespace]] = []

    def make_handler(name: str):
        def _handler(args: argparse.Namespace) -> int:
            calls.append((name, args))
            return len(calls)
        return _handler

    result = dispatch_management_command(
        ["update", "5.3.0"],
        update_handler=make_handler("update"),
        version_handler=make_handler("version"),
        uninstall_handler=make_handler("uninstall"),
        reinstall_handler=make_handler("reinstall"),
    )

    assert result == 1
    assert len(calls) == 1
    name, args = calls[0]
    assert name == "update"
    assert args.command == "update"
    assert args.target == "5.3.0"


def test_dispatch_management_command_returns_none_for_non_management() -> None:
    def fail(_args: argparse.Namespace) -> int:
        raise AssertionError("handler should not be called")

    assert dispatch_management_command(
        ["codex", "claude"],
        update_handler=fail,
        version_handler=fail,
        uninstall_handler=fail,
        reinstall_handler=fail,
    ) is None


def test_parse_start_args_supports_safe_and_new_context() -> None:
    args = parse_start_args(["-n", "-s"])
    assert args.new_context is True
    assert args.safe is True


def test_run_cli_entrypoint_prints_start_help_without_phase2() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli_entrypoint(
        ["--help"],
        version="5.2.8",
        script_root=Path("/tmp/ccb"),
        cwd=Path("/tmp/project"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert "usage: ccb [-s] [-n]" in stdout.getvalue()
    assert "Primary workflow:" in stdout.getvalue()
    assert "ccb -s" in stdout.getvalue()
    assert "Core commands:" in stdout.getvalue()
    assert "ccb ask <agent> [from <sender>] <message>" in stdout.getvalue()
    assert "ccb doctor" in stdout.getvalue()
    assert "Secondary control-plane status:" in stdout.getvalue()
    assert "Supplementary observer:" in stdout.getvalue()
    assert "ccb pend <agent|job_id> [N]" in stdout.getvalue()
    assert "ccb pend --queue [--detail] <agent|all>" in stdout.getvalue()
    assert "Advanced views:" in stdout.getvalue()
    assert "ccb queue [--detail] <agent|all>" in stdout.getvalue()
    assert "ccb trace <id>" in stdout.getvalue()
    assert "Advanced recovery:" in stdout.getvalue()
    assert "ccb repair <ack|retry|resubmit> ..." in stdout.getvalue()
    assert "ccb watch <agent|job_id>" not in stdout.getvalue()
    assert "ccb inbox [--detail] <agent>" not in stdout.getvalue()
    assert "ccb ps | ccb logs <agent>" not in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_run_cli_entrypoint_prints_kill_help() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli_entrypoint(
        ["kill", "--help"],
        version="5.2.8",
        script_root=Path("/tmp/ccb"),
        cwd=Path("/tmp/project"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert "usage: ccb kill [-f]" in stdout.getvalue()
    assert "Project runtime cleanup:" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_run_cli_entrypoint_prints_start_help_for_start_flags() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli_entrypoint(
        ["-s", "--help"],
        version="5.2.8",
        script_root=Path("/tmp/ccb"),
        cwd=Path("/tmp/project"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert "usage: ccb [-s] [-n]" in stdout.getvalue()
    assert "Primary workflow:" in stdout.getvalue()
    assert "Core commands:" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_run_cli_entrypoint_prints_ping_help() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli_entrypoint(
        ["ping", "--help"],
        version="5.2.8",
        script_root=Path("/tmp/ccb"),
        cwd=Path("/tmp/project"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert "usage: ccb ping <agent|all|ccbd>" in stdout.getvalue()
    assert "Light control-plane status:" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_run_cli_entrypoint_prints_pend_help_as_supplementary_status() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli_entrypoint(
        ["pend", "--help"],
        version="5.2.8",
        script_root=Path("/tmp/ccb"),
        cwd=Path("/tmp/project"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert "usage: ccb pend [--watch|--inbox|--queue] [--detail] <agent|job_id|all> [N]" in stdout.getvalue()
    assert "Weak observer surface:" in stdout.getvalue()
    assert "ccb pend --watch <agent|job_id>" in stdout.getvalue()
    assert "ccb pend --queue <agent|all>" in stdout.getvalue()
    assert "ccb pend --queue --detail <agent>" in stdout.getvalue()
    assert "Use `ccb trace <id>` for lineage when needed." in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_run_cli_entrypoint_prints_watch_help_with_project_prefix() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli_entrypoint(
        ["--project", "/tmp/demo", "watch", "--help"],
        version="5.2.8",
        script_root=Path("/tmp/ccb"),
        cwd=Path("/tmp/project"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert "usage: ccb watch <agent|job_id>" in stdout.getvalue()
    assert "Weak observer compatibility entrypoint:" in stdout.getvalue()
    assert "Prefer `ccb pend --watch <agent|job_id>` as the converged observer entrypoint." in stdout.getvalue()
    assert "Do not treat non-terminal watch output as authoritative completion." in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_run_cli_entrypoint_prints_watch_help_when_help_follows_operand() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli_entrypoint(
        ["watch", "job_123", "--help"],
        version="5.2.8",
        script_root=Path("/tmp/ccb"),
        cwd=Path("/tmp/project"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert "usage: ccb watch <agent|job_id>" in stdout.getvalue()
    assert "Weak observer compatibility entrypoint:" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_run_cli_entrypoint_prints_watch_help_with_plain_help_token() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli_entrypoint(
        ["watch", "help"],
        version="5.2.8",
        script_root=Path("/tmp/ccb"),
        cwd=Path("/tmp/project"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert "usage: ccb watch <agent|job_id>" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_run_cli_entrypoint_prints_ps_help_as_runtime_diagnostics_view() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli_entrypoint(
        ["ps", "--help"],
        version="5.2.8",
        script_root=Path("/tmp/ccb"),
        cwd=Path("/tmp/project"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert "usage: ccb ps" in stdout.getvalue()
    assert "Runtime diagnostics compatibility view:" in stdout.getvalue()
    assert "Prefer `ccb doctor ps` as the converged diagnostics entrypoint." in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_run_cli_entrypoint_prints_ps_help_with_plain_help_token() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli_entrypoint(
        ["ps", "help"],
        version="5.2.8",
        script_root=Path("/tmp/ccb"),
        cwd=Path("/tmp/project"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert "usage: ccb ps" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_run_cli_entrypoint_prints_logs_help_as_runtime_diagnostics_view() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli_entrypoint(
        ["logs", "--help"],
        version="5.2.8",
        script_root=Path("/tmp/ccb"),
        cwd=Path("/tmp/project"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert "usage: ccb logs <agent>" in stdout.getvalue()
    assert "Runtime diagnostics compatibility view:" in stdout.getvalue()
    assert "Prefer `ccb doctor logs <agent>` as the converged diagnostics entrypoint." in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_run_cli_entrypoint_prints_logs_help_with_plain_help_token() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli_entrypoint(
        ["logs", "demo", "help"],
        version="5.2.8",
        script_root=Path("/tmp/ccb"),
        cwd=Path("/tmp/project"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert "usage: ccb logs <agent>" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_run_cli_entrypoint_prints_doctor_help_with_converged_subviews() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli_entrypoint(
        ["doctor", "--help"],
        version="5.2.8",
        script_root=Path("/tmp/ccb"),
        cwd=Path("/tmp/project"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert "usage: ccb doctor [ps|logs <agent>|storage] [--output [PATH]]" in stdout.getvalue()
    assert "ccb doctor ps" in stdout.getvalue()
    assert "ccb doctor logs <agent>" in stdout.getvalue()
    assert "ccb doctor storage" in stdout.getvalue()
    assert "`ccb ps` and `ccb logs <agent>` remain compatibility entrypoints." in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_run_cli_entrypoint_prints_doctor_help_with_plain_help_token() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli_entrypoint(
        ["doctor", "help"],
        version="5.2.8",
        script_root=Path("/tmp/ccb"),
        cwd=Path("/tmp/project"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert "usage: ccb doctor [ps|logs <agent>|storage] [--output [PATH]]" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_run_cli_entrypoint_prints_doctor_storage_subview_help() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli_entrypoint(
        ["doctor", "storage", "--help"],
        version="5.2.8",
        script_root=Path("/tmp/ccb"),
        cwd=Path("/tmp/project"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert "usage: ccb doctor storage [--json]" in stdout.getvalue()
    assert "ccb doctor storage --json" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_run_cli_entrypoint_prints_cleanup_help() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli_entrypoint(
        ["cleanup", "--help"],
        version="5.2.8",
        script_root=Path("/tmp/ccb"),
        cwd=Path("/tmp/project"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert "usage: ccb cleanup" in stdout.getvalue()
    assert "Use `ccb doctor storage` before cleanup" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_run_cli_entrypoint_prints_doctor_ps_subview_help() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli_entrypoint(
        ["doctor", "ps", "--help"],
        version="5.2.8",
        script_root=Path("/tmp/ccb"),
        cwd=Path("/tmp/project"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert "usage: ccb doctor ps" in stdout.getvalue()
    assert "Runtime diagnostics subview:" in stdout.getvalue()
    assert "`ccb ps` remains a compatibility alias." in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_run_cli_entrypoint_prints_doctor_ps_subview_help_with_plain_help_token() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli_entrypoint(
        ["doctor", "ps", "help"],
        version="5.2.8",
        script_root=Path("/tmp/ccb"),
        cwd=Path("/tmp/project"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert "usage: ccb doctor ps" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_run_cli_entrypoint_prints_doctor_runtime_alias_help_with_plain_help_token() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli_entrypoint(
        ["doctor", "--runtime", "help"],
        version="5.2.8",
        script_root=Path("/tmp/ccb"),
        cwd=Path("/tmp/project"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert "usage: ccb doctor ps" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_run_cli_entrypoint_prints_doctor_logs_subview_help() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli_entrypoint(
        ["doctor", "logs", "--help"],
        version="5.2.8",
        script_root=Path("/tmp/ccb"),
        cwd=Path("/tmp/project"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert "usage: ccb doctor logs <agent>" in stdout.getvalue()
    assert "Runtime log diagnostics subview:" in stdout.getvalue()
    assert "`ccb logs <agent>` remains a compatibility alias." in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_run_cli_entrypoint_prints_doctor_logs_subview_help_with_plain_help_token() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli_entrypoint(
        ["doctor", "logs", "help"],
        version="5.2.8",
        script_root=Path("/tmp/ccb"),
        cwd=Path("/tmp/project"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert "usage: ccb doctor logs <agent>" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_run_cli_entrypoint_prints_doctor_logs_alias_help_with_plain_help_token() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli_entrypoint(
        ["doctor", "--logs", "demo", "help"],
        version="5.2.8",
        script_root=Path("/tmp/ccb"),
        cwd=Path("/tmp/project"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert "usage: ccb doctor logs <agent>" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_run_cli_entrypoint_prints_doctor_logs_subview_help_when_help_follows_agent() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli_entrypoint(
        ["doctor", "logs", "demo", "--help"],
        version="5.2.8",
        script_root=Path("/tmp/ccb"),
        cwd=Path("/tmp/project"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert "usage: ccb doctor logs <agent>" in stdout.getvalue()
    assert "Runtime log diagnostics subview:" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_run_cli_entrypoint_prints_queue_help_as_advanced_view() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli_entrypoint(
        ["queue", "--help"],
        version="5.2.8",
        script_root=Path("/tmp/ccb"),
        cwd=Path("/tmp/project"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert "usage: ccb queue [--detail] <agent_name|all>" in stdout.getvalue()
    assert "Advanced backlog view:" in stdout.getvalue()
    assert "`ccb pend --queue [--detail] <agent|all>` remains the equivalent weak-observer form." in stdout.getvalue()
    assert "ccb queue --detail <agent_name>" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_run_cli_entrypoint_prints_queue_help_with_plain_help_token() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli_entrypoint(
        ["queue", "help"],
        version="5.2.8",
        script_root=Path("/tmp/ccb"),
        cwd=Path("/tmp/project"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert "usage: ccb queue [--detail] <agent_name|all>" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_run_cli_entrypoint_prints_pend_help_with_converged_observer_modes() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli_entrypoint(
        ["pend", "--help"],
        version="5.2.8",
        script_root=Path("/tmp/ccb"),
        cwd=Path("/tmp/project"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert "usage: ccb pend [--watch|--inbox|--queue] [--detail] <agent|job_id|all> [N]" in stdout.getvalue()
    assert "ccb pend --watch <agent|job_id>" in stdout.getvalue()
    assert "ccb pend --inbox --detail <agent>" in stdout.getvalue()
    assert "ccb pend --queue --detail <agent>" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_run_cli_entrypoint_prints_trace_help_as_advanced_view() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli_entrypoint(
        ["trace", "--help"],
        version="5.2.8",
        script_root=Path("/tmp/ccb"),
        cwd=Path("/tmp/project"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert "usage: ccb trace <submission_id|message_id|attempt_id|reply_id|job_id>" in stdout.getvalue()
    assert "Advanced lineage view:" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_run_cli_entrypoint_prints_cancel_help_as_job_control_view() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli_entrypoint(
        ["cancel", "--help"],
        version="5.2.8",
        script_root=Path("/tmp/ccb"),
        cwd=Path("/tmp/project"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert "usage: ccb cancel <job_id>" in stdout.getvalue()
    assert "Job control view:" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_run_cli_entrypoint_prints_inbox_help_as_supplementary_status() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli_entrypoint(
        ["inbox", "--help"],
        version="5.2.8",
        script_root=Path("/tmp/ccb"),
        cwd=Path("/tmp/project"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert "usage: ccb inbox [--detail] <agent_name>" in stdout.getvalue()
    assert "Weak observer compatibility entrypoint:" in stdout.getvalue()
    assert "Prefer `ccb pend --inbox [--detail] <agent>` as the converged observer entrypoint." in stdout.getvalue()
    assert "ccb inbox --detail <agent_name>" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_run_cli_entrypoint_prints_inbox_help_with_plain_help_token() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli_entrypoint(
        ["inbox", "help"],
        version="5.2.8",
        script_root=Path("/tmp/ccb"),
        cwd=Path("/tmp/project"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert "usage: ccb inbox [--detail] <agent_name>" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_run_cli_entrypoint_prints_ack_help_as_advanced_recovery() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli_entrypoint(
        ["ack", "--help"],
        version="5.2.8",
        script_root=Path("/tmp/ccb"),
        cwd=Path("/tmp/project"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert "usage: ccb ack <agent_name> [inbound_event_id]" in stdout.getvalue()
    assert "Advanced recovery compatibility entrypoint:" in stdout.getvalue()
    assert "Prefer `ccb repair ack <agent_name> [inbound_event_id]` as the converged recovery entrypoint." in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_run_cli_entrypoint_prints_ack_help_with_plain_help_token() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli_entrypoint(
        ["ack", "demo", "help"],
        version="5.2.8",
        script_root=Path("/tmp/ccb"),
        cwd=Path("/tmp/project"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert "usage: ccb ack <agent_name> [inbound_event_id]" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_run_cli_entrypoint_prints_retry_help_as_advanced_recovery() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli_entrypoint(
        ["retry", "--help"],
        version="5.2.8",
        script_root=Path("/tmp/ccb"),
        cwd=Path("/tmp/project"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert "usage: ccb retry <job_id|attempt_id>" in stdout.getvalue()
    assert "Advanced recovery compatibility entrypoint:" in stdout.getvalue()
    assert "Prefer `ccb repair retry <job_id|attempt_id>` as the converged recovery entrypoint." in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_run_cli_entrypoint_prints_retry_help_with_plain_help_token() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli_entrypoint(
        ["retry", "job_1", "help"],
        version="5.2.8",
        script_root=Path("/tmp/ccb"),
        cwd=Path("/tmp/project"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert "usage: ccb retry <job_id|attempt_id>" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_run_cli_entrypoint_prints_resubmit_help_as_advanced_recovery() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli_entrypoint(
        ["resubmit", "--help"],
        version="5.2.8",
        script_root=Path("/tmp/ccb"),
        cwd=Path("/tmp/project"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert "usage: ccb resubmit <message_id>" in stdout.getvalue()
    assert "Advanced recovery compatibility entrypoint:" in stdout.getvalue()
    assert "Prefer `ccb repair resubmit <message_id>` as the converged recovery entrypoint." in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_run_cli_entrypoint_prints_resubmit_help_with_plain_help_token() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli_entrypoint(
        ["resubmit", "msg_1", "help"],
        version="5.2.8",
        script_root=Path("/tmp/ccb"),
        cwd=Path("/tmp/project"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert "usage: ccb resubmit <message_id>" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_run_cli_entrypoint_prints_repair_help_as_primary_advanced_recovery() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli_entrypoint(
        ["repair", "--help"],
        version="5.2.8",
        script_root=Path("/tmp/ccb"),
        cwd=Path("/tmp/project"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert "usage: ccb repair <ack|retry|resubmit> ..." in stdout.getvalue()
    assert "Advanced recovery:" in stdout.getvalue()
    assert "ccb repair ack <agent_name> [inbound_event_id]" in stdout.getvalue()
    assert "ccb repair retry <job_id|attempt_id>" in stdout.getvalue()
    assert "ccb repair resubmit <message_id>" in stdout.getvalue()
    assert "Legacy `ack` / `retry` / `resubmit` commands remain compatibility entrypoints." in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_run_cli_entrypoint_prints_repair_help_with_plain_help_token() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli_entrypoint(
        ["repair", "help"],
        version="5.2.8",
        script_root=Path("/tmp/ccb"),
        cwd=Path("/tmp/project"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert "usage: ccb repair <ack|retry|resubmit> ..." in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_run_cli_entrypoint_prints_repair_ack_subcommand_help() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli_entrypoint(
        ["repair", "ack", "--help"],
        version="5.2.8",
        script_root=Path("/tmp/ccb"),
        cwd=Path("/tmp/project"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert "usage: ccb repair ack <agent_name> [inbound_event_id]" in stdout.getvalue()
    assert "Advanced recovery subcommand:" in stdout.getvalue()
    assert "`ccb ack <agent_name> [inbound_event_id]` remains a compatibility alias." in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_run_cli_entrypoint_prints_repair_ack_subcommand_help_with_plain_help_token() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli_entrypoint(
        ["repair", "ack", "help"],
        version="5.2.8",
        script_root=Path("/tmp/ccb"),
        cwd=Path("/tmp/project"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert "usage: ccb repair ack <agent_name> [inbound_event_id]" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_run_cli_entrypoint_prints_repair_ack_subcommand_help_when_help_follows_operand() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli_entrypoint(
        ["repair", "ack", "demo", "--help"],
        version="5.2.8",
        script_root=Path("/tmp/ccb"),
        cwd=Path("/tmp/project"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert "usage: ccb repair ack <agent_name> [inbound_event_id]" in stdout.getvalue()
    assert "Advanced recovery subcommand:" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_run_cli_entrypoint_prints_repair_retry_subcommand_help() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli_entrypoint(
        ["repair", "retry", "--help"],
        version="5.2.8",
        script_root=Path("/tmp/ccb"),
        cwd=Path("/tmp/project"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert "usage: ccb repair retry <job_id|attempt_id>" in stdout.getvalue()
    assert "Advanced recovery subcommand:" in stdout.getvalue()
    assert "`ccb retry <job_id|attempt_id>` remains a compatibility alias." in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_run_cli_entrypoint_prints_repair_resubmit_subcommand_help() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli_entrypoint(
        ["repair", "resubmit", "--help"],
        version="5.2.8",
        script_root=Path("/tmp/ccb"),
        cwd=Path("/tmp/project"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert "usage: ccb repair resubmit <message_id>" in stdout.getvalue()
    assert "Advanced recovery subcommand:" in stdout.getvalue()
    assert "`ccb resubmit <message_id>` remains a compatibility alias." in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_run_cli_entrypoint_prints_ask_help() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli_entrypoint(
        ["ask", "--help"],
        version="5.2.8",
        script_root=Path("/tmp/ccb"),
        cwd=Path("/tmp/project"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert "Usage:" in stdout.getvalue()
    assert "ccb ask [--compact] [--silence] [--callback] <target> [--] <message...>" in stdout.getvalue()
    assert "--compact request a distilled reply that preserves key information" in stdout.getvalue()
    assert "--silence request silent-on-success delivery; failures/blockers still surface" in stdout.getvalue()
    assert "--callback route the result back as a new task to the current agent" in stdout.getvalue()
    assert "ccb ask --compact agent1 review latest diff" in stdout.getvalue()
    assert "ccb ask --silence agent1 run smoke check" in stdout.getvalue()
    assert "ccb ask --callback agent2 collect evidence for this task" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_run_cli_entrypoint_rejects_removed_provider_command() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli_entrypoint(
        ["provider", "ping", "--help"],
        version="5.2.8",
        script_root=Path("/tmp/ccb"),
        cwd=Path("/tmp/project"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 2
    assert stdout.getvalue() == ""
    assert "`ccb provider` has been removed" in stderr.getvalue()
    assert "Use `ccb ask` for task submission/results, `ccb doctor` for diagnostics, and `ccb trace` for lineage details." in stderr.getvalue()


def test_run_cli_entrypoint_rejects_removed_mail_command() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli_entrypoint(
        ["mail", "status"],
        version="5.2.8",
        script_root=Path("/tmp/ccb"),
        cwd=Path("/tmp/project"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 2
    assert stdout.getvalue() == ""
    assert "`ccb mail` has been removed" in stderr.getvalue()
    assert "Use `ccb ask` for task submission/results, `ccb doctor` for diagnostics, and `ccb trace` for lineage details." in stderr.getvalue()

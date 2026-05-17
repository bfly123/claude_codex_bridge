from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_PATH = REPO_ROOT / "mcp" / "ccb-delegation" / "server_runtime_tools.py"
SCRIPT_DIR = TOOLS_PATH.parent
LIB_DIR = REPO_ROOT / "lib"


def _load_module():
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    if str(LIB_DIR) not in sys.path:
        sys.path.insert(0, str(LIB_DIR))
    spec = importlib.util.spec_from_file_location("ccb_delegation_server_runtime_tools", TOOLS_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_submit_task_returns_async_status(monkeypatch) -> None:
    module = _load_module()
    monkeypatch.setattr(module, "build_context_for", lambda work_dir: object())
    monkeypatch.setattr(
        module,
        "submit_ask",
        lambda context, command: SimpleNamespace(
            project_id="proj-1",
            submission_id="sub-1",
            jobs=[{"job_id": "job-1", "agent_name": "agent2", "target_kind": "agent", "target_name": "agent2", "status": "accepted"}],
        ),
    )

    payload = module.submit_task({"agent_name": "agent2", "message": "hello"}, caller="agent1")
    data = json.loads(payload["content"][0]["text"])

    assert data["job_id"] == "job-1"
    assert data["terminal"] is False
    assert data["reply_mode"] == "async"
    assert not any(str(key).endswith("_hint") for key in data)


def test_submit_task_returns_terminal_reply_when_requested(monkeypatch) -> None:
    module = _load_module()
    monkeypatch.setattr(module, "build_context_for", lambda work_dir: object())
    monkeypatch.setattr(
        module,
        "submit_ask",
        lambda context, command: SimpleNamespace(
            project_id="proj-1",
            submission_id="sub-1",
            jobs=[{"job_id": "job-2", "agent_name": "agent3", "target_kind": "agent", "target_name": "agent3", "status": "accepted"}],
        ),
    )
    monkeypatch.setattr(
        module,
        "watch_ask_job",
        lambda context, job_id, out, timeout, emit_output: SimpleNamespace(status="completed", reply="done"),
    )

    payload = module.submit_task({"agent_name": "agent3", "message": "hello", "wait": True}, caller="agent1")
    data = json.loads(payload["content"][0]["text"])

    assert data["terminal"] is True
    assert data["status"] == "completed"
    assert data["reply"] == "done"


def test_handle_tool_call_routes_known_handlers(monkeypatch) -> None:
    module = _load_module()
    monkeypatch.setattr(module, "submit_task", lambda args, caller: {"route": "ask", "caller": caller})
    monkeypatch.setattr(module, "pend_task", lambda args: {"route": "pend"})
    monkeypatch.setattr(module, "ping_agent", lambda args: {"route": "ping"})
    monkeypatch.setitem(module._TOOL_HANDLERS, "ccb_ask_agent", lambda args, caller: module.submit_task(args, caller=caller))
    monkeypatch.setitem(module._TOOL_HANDLERS, "ccb_pend_agent", lambda args, caller: module.pend_task(args))
    monkeypatch.setitem(module._TOOL_HANDLERS, "ccb_ping_agent", lambda args, caller: module.ping_agent(args))

    assert module.handle_tool_call("ccb_ask_agent", {}, caller="agent1")["route"] == "ask"
    assert module.handle_tool_call("ccb_pend_agent", {}, caller="agent1")["route"] == "pend"
    assert module.handle_tool_call("ccb_ping_agent", {}, caller="agent1")["route"] == "ping"
    assert module.handle_tool_call("unknown", {}, caller="agent1")["isError"] is True

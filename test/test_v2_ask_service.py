from __future__ import annotations

from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest

from ccbd.api_models import DeliveryScope
from ccbd.socket_client import CcbdClientError
from cli.context import CliContextBuilder
from cli.models import ParsedAskCommand
from cli.services import ask as ask_service
from cli.services.ask_runtime.submission import message_with_reply_guidance
from cli.services.daemon import CcbdServiceError
from project.ids import compute_project_id


def _build_context(project_root: Path) -> object:
    (project_root / '.ccb').mkdir(parents=True, exist_ok=True)
    (project_root / '.ccb' / 'ccb.config').write_text('cmd; agent1:codex, agent2:claude\n', encoding='utf-8')
    command = ParsedAskCommand(project=None, target='agent1', sender=None, message='hello')
    return CliContextBuilder().build(command, cwd=project_root, bootstrap_if_missing=False)


def test_submit_ask_rejects_unknown_target(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-ask-unknown-target'
    project_root.mkdir()
    context = _build_context(project_root)

    with pytest.raises(ValueError) as exc_info:
        ask_service.submit_ask(
            context,
            ParsedAskCommand(project=None, target='agent9', sender=None, message='hello'),
        )

    assert str(exc_info.value) == 'unknown agent: agent9'


def test_submit_ask_maps_broadcast_payload_and_submission(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-ask-broadcast'
    project_root.mkdir()
    context = _build_context(project_root)
    captured: dict[str, object] = {}

    class _FakeClient:
        def submit(self, envelope) -> dict:
            captured['project_id'] = envelope.project_id
            captured['to_agent'] = envelope.to_agent
            captured['from_actor'] = envelope.from_actor
            captured['body'] = envelope.body
            captured['reply_to'] = envelope.reply_to
            captured['message_type'] = envelope.message_type
            captured['delivery_scope'] = envelope.delivery_scope
            captured['silence_on_success'] = envelope.silence_on_success
            captured['route_options'] = envelope.route_options
            return {
                'submission_id': 'sub_1',
                'jobs': [
                    {'job_id': 'job_1', 'agent_name': 'agent1', 'target_name': 'agent1', 'status': 'accepted'},
                    {'job_id': 'job_2', 'agent_name': 'agent2', 'target_name': 'agent2', 'status': 'accepted'},
                ],
            }

    monkeypatch.setattr(
        ask_service,
        'load_project_config',
        lambda project_root: SimpleNamespace(config=SimpleNamespace(agents={'agent1': {}, 'agent2': {}})),
    )
    monkeypatch.setattr(ask_service, 'resolve_ask_sender', lambda context, sender: 'agent1')
    monkeypatch.setattr(
        ask_service,
        'invoke_mounted_daemon',
        lambda context, allow_restart_stale, request_fn: request_fn(_FakeClient()),
    )

    summary = ask_service.submit_ask(
        context,
        ParsedAskCommand(
            project=None,
            target='all',
            sender=None,
            message='ship it',
            reply_to='msg_1',
            mode='notify',
            silence=True,
        ),
    )

    assert summary.project_id == context.project.project_id
    assert summary.submission_id == 'sub_1'
    assert [job['job_id'] for job in summary.jobs] == ['job_1', 'job_2']
    assert captured == {
        'project_id': context.project.project_id,
        'to_agent': 'all',
        'from_actor': 'agent1',
        'body': 'ship it',
        'reply_to': 'msg_1',
        'message_type': 'notify',
        'delivery_scope': DeliveryScope.BROADCAST,
        'silence_on_success': True,
        'route_options': {},
    }


def test_submit_ask_maps_callback_route_options(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-ask-callback'
    project_root.mkdir()
    context = _build_context(project_root)
    captured: dict[str, object] = {}

    class _FakeClient:
        def submit(self, envelope) -> dict:
            captured['route_options'] = envelope.route_options
            return {
                'job_id': 'job_1',
                'agent_name': 'agent2',
                'target_name': 'agent2',
                'status': 'accepted',
            }

    monkeypatch.setattr(
        ask_service,
        'load_project_config',
        lambda project_root: SimpleNamespace(config=SimpleNamespace(agents={'agent1': {}, 'agent2': {}})),
    )
    monkeypatch.setattr(ask_service, 'resolve_ask_sender', lambda context, sender: 'agent1')
    monkeypatch.setattr(
        ask_service,
        'invoke_mounted_daemon',
        lambda context, allow_restart_stale, request_fn: request_fn(_FakeClient()),
    )

    summary = ask_service.submit_ask(
        context,
        ParsedAskCommand(project=None, target='agent2', sender=None, message='collect evidence', callback=True),
    )

    assert summary.jobs[0]['job_id'] == 'job_1'
    assert captured['route_options'] == {'mode': 'callback'}


def test_message_with_reply_guidance_appends_compact_default() -> None:
    body = message_with_reply_guidance('review the diff', message_type='ask')

    assert body.startswith('review the diff\n\nCCB reply guidance:')
    assert 'shortest reply that still preserves the key information' in body
    assert 'CCB nested ask routing:' in body
    assert 'ask --callback' in body
    assert 'no more than' not in body


def test_message_with_reply_guidance_appends_explicit_compact_guidance() -> None:
    body = message_with_reply_guidance('review the diff', message_type='ask', compact=True)

    assert body.startswith('review the diff\n\nCCB reply guidance:')
    assert 'Actively distill the reply' in body
    assert 'do not use a fixed length target' in body
    assert 'Lead with the answer' in body


def test_message_with_reply_guidance_respects_explicit_output_requirements() -> None:
    body = message_with_reply_guidance(
        'review the diff\n\nOutput requirements:\n- Write a full report.',
        message_type='ask',
    )

    assert body == 'review the diff\n\nOutput requirements:\n- Write a full report.'


def test_message_with_reply_guidance_respects_chinese_explicit_output_requirements() -> None:
    body = message_with_reply_guidance(
        '请完整输出测试日志，不要总结。',
        message_type='ask',
        compact=True,
    )

    assert body == '请完整输出测试日志，不要总结。'


def test_message_with_reply_guidance_uses_silent_hint_for_silenced_asks() -> None:
    body = message_with_reply_guidance('run smoke test', message_type='ask', silence_on_success=True)

    assert 'silent-on-success delivery' in body
    assert 'shortest useful success/failure status' in body
    assert 'CCB nested ask routing:' in body


def test_message_with_reply_guidance_skips_non_ask_modes() -> None:
    assert message_with_reply_guidance('ship it', message_type='notify') == 'ship it'


def test_submit_ask_rejects_explicit_cmd_sender(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-ask-explicit-cmd'
    project_root.mkdir()
    context = _build_context(project_root)

    monkeypatch.setattr(
        ask_service,
        'load_project_config',
        lambda project_root: SimpleNamespace(config=SimpleNamespace(agents={'agent1': {}, 'agent2': {}})),
    )

    with pytest.raises(ValueError, match='unknown sender agent: cmd'):
        ask_service.submit_ask(
            context,
            ParsedAskCommand(project=None, target='agent1', sender='cmd', message='hello'),
        )


def test_submit_ask_translates_client_reset_during_shutdown(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-ask-stopping'
    project_root.mkdir()
    context = _build_context(project_root)

    class _FlakyClient:
        def submit(self, envelope) -> dict:
            del envelope
            raise CcbdClientError('socket closed')

    monkeypatch.setattr(
        ask_service,
        'load_project_config',
        lambda project_root: SimpleNamespace(config=SimpleNamespace(agents={'agent1': {}, 'agent2': {}})),
    )
    monkeypatch.setattr(ask_service, 'resolve_ask_sender', lambda context, sender: 'agent1')
    monkeypatch.setattr(
        'cli.services.daemon.connect_mounted_daemon',
        lambda context, allow_restart_stale: SimpleNamespace(client=_FlakyClient()),
    )
    monkeypatch.setattr(
        'cli.services.daemon.inspect_daemon',
        lambda context: (
            None,
            None,
            SimpleNamespace(phase='stopping', desired_state='stopped'),
        ),
    )

    with pytest.raises(CcbdServiceError, match='project ccbd is stopping; wait for shutdown to finish'):
        ask_service.submit_ask(
            context,
            ParsedAskCommand(project=None, target='agent1', sender=None, message='hello'),
        )


def test_resolve_ask_sender_defaults_to_user_for_project_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-ask-default-cmd'
    project_root.mkdir()
    context = _build_context(project_root)

    for env_name in ('CCB_CALLER_ACTOR', 'CCB_CALLER_RUNTIME_DIR', 'CODEX_RUNTIME_DIR', 'CCB_SESSION_ID'):
        monkeypatch.delenv(env_name, raising=False)

    assert ask_service.resolve_ask_sender(context, None) == 'user'


def test_resolve_ask_sender_prefers_runtime_dir_actor(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-ask-runtime-actor'
    project_root.mkdir()
    context = _build_context(project_root)
    runtime_dir = project_root / '.ccb' / 'agents' / 'agent1' / 'provider-runtime' / 'codex'
    runtime_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.delenv('CCB_CALLER_ACTOR', raising=False)
    monkeypatch.delenv('CCB_CALLER_RUNTIME_DIR', raising=False)
    monkeypatch.setenv('CODEX_RUNTIME_DIR', str(runtime_dir))
    monkeypatch.setenv('CCB_SESSION_ID', 'legacy-session-without-actor')

    assert ask_service.resolve_ask_sender(context, None) == 'agent1'


def test_resolve_ask_sender_prefers_relocated_runtime_dir_actor(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-ask-relocated-runtime-actor'
    (project_root / '.ccb').mkdir(parents=True, exist_ok=True)
    (project_root / '.ccb' / 'ccb.config').write_text('agent1:codex\n', encoding='utf-8')
    relocated_root = tmp_path / 'state-root'
    project_id = compute_project_id(project_root)
    (project_root / '.ccb' / 'runtime-root-ref.json').write_text(
        f'{{"schema_version":1,"record_type":"ccb_runtime_root_ref","project_id":"{project_id}","runtime_state_root":"{relocated_root}","created_at":"2026-05-07T00:00:00Z"}}',
        encoding='utf-8',
    )
    context = CliContextBuilder().build(
        ParsedAskCommand(project=None, target='agent1', sender=None, message='hello'),
        cwd=project_root,
        bootstrap_if_missing=False,
    )
    runtime_dir = context.paths.agents_dir / 'agent1' / 'provider-runtime' / 'codex'
    runtime_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.delenv('CCB_CALLER_ACTOR', raising=False)
    monkeypatch.delenv('CCB_CALLER_RUNTIME_DIR', raising=False)
    monkeypatch.setenv('CODEX_RUNTIME_DIR', str(runtime_dir))
    monkeypatch.setenv('CCB_SESSION_ID', 'legacy-session-without-actor')

    assert context.paths.runtime_state_root == relocated_root
    assert ask_service.resolve_ask_sender(context, None) == 'agent1'


def test_watch_ask_job_reconnects_and_preserves_cursor(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-ask-watch'
    project_root.mkdir()
    context = _build_context(project_root)
    rendered: list[tuple[str, ...]] = []

    class _FlakyClient:
        def __init__(self) -> None:
            self.calls: list[int] = []

        def watch(self, job_id: str, *, cursor: int = 0) -> dict:
            assert job_id == 'job_1'
            self.calls.append(cursor)
            if cursor == 0:
                return {
                    'job_id': 'job_1',
                    'agent_name': 'agent1',
                    'target_name': 'agent1',
                    'cursor': 2,
                    'generation': 1,
                    'terminal': False,
                    'status': 'running',
                    'reply': 'partial',
                    'events': [
                        {'event_id': 'evt_1', 'job_id': 'job_1', 'agent_name': 'agent1', 'type': 'job_started', 'timestamp': '2026-04-06T00:00:01Z'},
                    ],
                }
            raise CcbdClientError('socket closed')

    class _StableClient:
        def __init__(self) -> None:
            self.calls: list[int] = []

        def watch(self, job_id: str, *, cursor: int = 0) -> dict:
            assert job_id == 'job_1'
            self.calls.append(cursor)
            return {
                'job_id': 'job_1',
                'agent_name': 'agent1',
                'target_name': 'agent1',
                'cursor': 4,
                'generation': 2,
                'terminal': True,
                'status': 'completed',
                'reply': 'done',
                'events': [],
            }

    flaky = _FlakyClient()
    stable = _StableClient()
    handles = iter([SimpleNamespace(client=flaky), SimpleNamespace(client=stable)])
    seen: list[bool] = []

    def _connect(context, allow_restart_stale):
        seen.append(allow_restart_stale)
        return next(handles)

    monkeypatch.setattr(ask_service, 'connect_mounted_daemon', _connect)
    monkeypatch.setattr(ask_service, 'watch_timeout_seconds', lambda: 1.0)
    monkeypatch.setattr(ask_service, 'watch_poll_interval_seconds', lambda: 0.0)
    monkeypatch.setattr(ask_service, 'render_watch_batch', lambda batch: (f'{batch.job_id}:{batch.cursor}:{batch.terminal}',))
    monkeypatch.setattr(ask_service, 'write_lines', lambda out, lines: rendered.append(lines))
    monkeypatch.setattr(ask_service.time, 'sleep', lambda seconds: None)

    batch = ask_service.watch_ask_job(context, 'job_1', StringIO(), timeout=None, emit_output=True)

    assert batch.cursor == 4
    assert batch.generation == 2
    assert batch.reply == 'done'
    assert flaky.calls == [0, 2]
    assert stable.calls == [2]
    assert rendered == [('job_1:2:False',), ('job_1:4:True',)]
    assert seen == [False, False]


def test_watch_ask_job_times_out_after_reconnect_failures(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-ask-timeout'
    project_root.mkdir()
    context = _build_context(project_root)
    clock = iter([0.0, 0.5, 1.5])

    class _FlakyClient:
        def watch(self, job_id: str, *, cursor: int = 0) -> dict:
            del job_id, cursor
            raise CcbdClientError('socket closed')

    seen: list[bool] = []

    def _connect(context, allow_restart_stale):
        seen.append(allow_restart_stale)
        return SimpleNamespace(client=_FlakyClient())

    monkeypatch.setattr(
        ask_service,
        'connect_mounted_daemon',
        _connect,
    )
    monkeypatch.setattr(ask_service, 'watch_timeout_seconds', lambda: 1.0)
    monkeypatch.setattr(ask_service, 'watch_poll_interval_seconds', lambda: 0.0)
    monkeypatch.setattr(ask_service.time, 'monotonic', lambda: next(clock))
    monkeypatch.setattr(ask_service.time, 'sleep', lambda seconds: None)

    with pytest.raises(RuntimeError) as exc_info:
        ask_service.watch_ask_job(context, 'job_1', StringIO(), timeout=None, emit_output=False)

    assert str(exc_info.value) == 'watch timed out for job_1'
    assert seen == [False, False]


def test_watch_ask_job_retries_when_reconnect_attempt_temporarily_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    project_root = tmp_path / 'repo-ask-reconnect-step-fail'
    project_root.mkdir()
    context = _build_context(project_root)
    clock = iter([0.0, 0.1, 0.2, 0.3, 0.4, 0.5])

    class _FlakyClient:
        def __init__(self) -> None:
            self.calls: list[int] = []

        def watch(self, job_id: str, *, cursor: int = 0) -> dict:
            assert job_id == 'job_1'
            self.calls.append(cursor)
            raise CcbdClientError('socket closed')

    class _StableClient:
        def __init__(self) -> None:
            self.calls: list[int] = []

        def watch(self, job_id: str, *, cursor: int = 0) -> dict:
            assert job_id == 'job_1'
            self.calls.append(cursor)
            return {
                'job_id': 'job_1',
                'agent_name': 'agent1',
                'target_name': 'agent1',
                'cursor': 1,
                'generation': 2,
                'terminal': True,
                'status': 'completed',
                'reply': 'done',
                'events': [],
            }

    flaky = _FlakyClient()
    stable = _StableClient()
    connects = {'count': 0}
    seen: list[bool] = []

    def _connect(context, allow_restart_stale):
        del context
        seen.append(allow_restart_stale)
        connects['count'] += 1
        if connects['count'] == 1:
            return SimpleNamespace(client=flaky)
        if connects['count'] == 2:
            raise CcbdServiceError('daemon restarting')
        return SimpleNamespace(client=stable)

    monkeypatch.setattr(ask_service, 'connect_mounted_daemon', _connect)
    monkeypatch.setattr(ask_service, 'watch_timeout_seconds', lambda: 1.0)
    monkeypatch.setattr(ask_service, 'watch_poll_interval_seconds', lambda: 0.0)
    monkeypatch.setattr(ask_service.time, 'monotonic', lambda: next(clock))
    monkeypatch.setattr(ask_service.time, 'sleep', lambda seconds: None)

    batch = ask_service.watch_ask_job(context, 'job_1', StringIO(), timeout=None, emit_output=False)

    assert batch.terminal is True
    assert batch.reply == 'done'
    assert flaky.calls == [0]
    assert stable.calls == [0]
    assert seen == [False, False, False]


def test_write_ask_output_appends_newline(tmp_path: Path) -> None:
    path = tmp_path / 'reply.txt'

    ask_service.write_ask_output(path, 'done')

    assert path.read_text(encoding='utf-8') == 'done\n'


def test_exit_code_for_ask_status_prefers_no_reply_exit_for_incomplete_with_reply() -> None:
    assert ask_service.exit_code_for_ask_status('incomplete', reply='partial') == 2
    assert ask_service.exit_code_for_ask_status('completed', reply='done') == 0
    assert ask_service.exit_code_for_ask_status('failed', reply='') == 1

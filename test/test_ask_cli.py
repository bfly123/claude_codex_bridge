from __future__ import annotations

import importlib
import io
from pathlib import Path


def test_ask_alias_forwards_to_phase2(monkeypatch, tmp_path: Path) -> None:
    ask_main_module = importlib.import_module('ask_cli.main')
    captured: dict[str, object] = {}

    def fake_phase2(argv, *, cwd, stdout, stderr):
        captured['argv'] = list(argv)
        captured['cwd'] = cwd
        captured['stdout'] = stdout
        captured['stderr'] = stderr
        return 17

    monkeypatch.setattr(ask_main_module, 'maybe_handle_phase2', fake_phase2)

    stdout = io.StringIO()
    stderr = io.StringIO()
    code = ask_main_module.main(
        ['--project', '/tmp/demo', '--compact', 'agent1', 'from', 'agent2', '--', 'hello'],
        stdout=stdout,
        stderr=stderr,
    )

    assert code == 17
    assert captured['argv'] == ['--project', '/tmp/demo', 'ask', '--compact', 'agent1', 'from', 'agent2', '--', 'hello']
    assert captured['cwd'] == Path.cwd()
    assert captured['stdout'] is stdout
    assert captured['stderr'] is stderr


def test_ask_alias_forwards_wait_subcommand(monkeypatch) -> None:
    ask_main_module = importlib.import_module('ask_cli.main')
    captured: dict[str, object] = {}

    def fake_phase2(argv, *, cwd, stdout, stderr):
        captured['argv'] = list(argv)
        return 0

    monkeypatch.setattr(ask_main_module, 'maybe_handle_phase2', fake_phase2)

    code = ask_main_module.main(['wait', 'job_123'], stdout=io.StringIO(), stderr=io.StringIO())

    assert code == 0
    assert captured['argv'] == ['ask', 'wait', 'job_123']


def test_ask_alias_help_uses_canonical_usage(monkeypatch) -> None:
    ask_main_module = importlib.import_module('ask_cli.main')

    def fail(*args, **kwargs):
        raise AssertionError('phase2 should not be called for ask --help')

    monkeypatch.setattr(ask_main_module, 'maybe_handle_phase2', fail)

    stdout = io.StringIO()
    code = ask_main_module.main(['--help'], stdout=stdout, stderr=io.StringIO())

    assert code == 0
    text = stdout.getvalue()
    assert 'ask [--compact] [--silence] [--callback] <target> [--] <message...>' in text
    assert '--compact request a distilled reply that preserves key information' in text
    assert '--silence request silent-on-success delivery; failures/blockers still surface' in text
    assert '--callback route the result back as a new task to the current agent' in text
    assert 'nested asks from active tasks must use --callback or --silence' in text
    assert 'ask --compact agent1 review latest diff' in text
    assert 'ask --silence agent1 run smoke check' in text
    assert 'ask --callback agent2 collect evidence for this task' in text
    assert '--task-id' not in text
    assert '[from <sender>]' not in text
    assert '`ask` is a compatibility alias for `ccb ask`.' in text

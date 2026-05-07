from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from cli.services.daemon_runtime import keeper as keeper_runtime
from storage.paths import PathLayout


def test_spawn_keeper_process_uses_lib_root_keeper_main(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / 'repo'
    paths = PathLayout(project_root)
    context = SimpleNamespace(
        project=SimpleNamespace(project_root=project_root),
        paths=paths,
    )
    popen_calls: list[dict[str, object]] = []

    class _FakePopen:
        def __init__(self, cmd, **kwargs) -> None:
            popen_calls.append({'cmd': cmd, **kwargs})

    monkeypatch.setattr(keeper_runtime.subprocess, 'Popen', _FakePopen)

    keeper_runtime.spawn_keeper_process(context)

    assert len(popen_calls) == 1
    call = popen_calls[0]
    expected_script = Path(keeper_runtime.__file__).resolve().parents[3] / 'ccbd' / 'keeper_main.py'
    assert call['cmd'][1] == str(expected_script)
    assert str(expected_script.parent.parent) in str(call['env']['PYTHONPATH'])

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import textwrap
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_SH = REPO_ROOT / "install.sh"


def _python310_executable() -> str:
    for candidate in (
        sys.executable,
        "python3.14",
        "python3.13",
        "python3.12",
        "python3.11",
        "python3.10",
        "python3",
        "python",
    ):
        try:
            output = subprocess.check_output(
                [
                    candidate,
                    "-c",
                    "import sys\nif sys.version_info < (3, 10): raise SystemExit(1)\nprint(sys.executable)",
                ],
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
        except (OSError, subprocess.CalledProcessError):
            continue
        if output:
            return output
    raise AssertionError("Python 3.10+ is required to test Droid delegation install")


def _run_install_snippet(
    tmp_path: Path,
    body: str,
    *,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    home_dir = tmp_path / "home"
    home_dir.mkdir(exist_ok=True)
    python310 = _python310_executable()
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(home_dir),
            "CODEX_INSTALL_PREFIX": str(tmp_path / "install"),
            "CODEX_BIN_DIR": str(tmp_path / "bin"),
            "CCB_LANG": "en",
            "CCB_SOURCE_KIND": "source",
            "CCB_SOURCE_ROOT": str(REPO_ROOT),
            "CCB_PYTHON_BIN": python310,
        }
    )
    if extra_env:
        env.update(extra_env)
    command = textwrap.dedent(
        f"""
        set -euo pipefail
        source {shlex.quote(str(INSTALL_SH))}
        {body}
        """
    )
    return subprocess.run(
        ["bash", "-lc", command],
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO_ROOT,
    )


def _write_fake_droid(bin_dir: Path, script: str) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    droid = bin_dir / "droid"
    droid.write_text(script, encoding="utf-8")
    droid.chmod(0o755)
    return droid


def test_install_droid_delegation_registers_with_selected_python(tmp_path: Path) -> None:
    fake_bin = tmp_path / "fake-bin"
    args_marker = tmp_path / "droid-args.txt"
    _write_fake_droid(
        fake_bin,
        (
            "#!/usr/bin/env bash\n"
            "printf '%s\\n' \"$@\" > \"$DROID_ARGS_MARKER\"\n"
        ),
    )

    completed = _run_install_snippet(
        tmp_path,
        """
        export PATH="$FAKE_DROID_BIN:$PATH"
        install_droid_delegation
        """,
        extra_env={
            "FAKE_DROID_BIN": str(fake_bin),
            "DROID_ARGS_MARKER": str(args_marker),
        },
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert "OK: Droid MCP delegation registered" in completed.stdout
    args = args_marker.read_text(encoding="utf-8").splitlines()
    assert args == [
        "mcp",
        "add",
        "ccb-delegation",
        "--type",
        "stdio",
        _python310_executable(),
        str(REPO_ROOT / "mcp" / "ccb-delegation" / "server.py"),
    ]


def test_install_droid_delegation_timeout_warns_without_failing_install(tmp_path: Path) -> None:
    fake_bin = tmp_path / "fake-bin"
    _write_fake_droid(
        fake_bin,
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            sleep 5
            """
        ),
    )

    completed = _run_install_snippet(
        tmp_path,
        """
        export PATH="$FAKE_DROID_BIN:$PATH"
        CCB_DROID_AUTOINSTALL_TIMEOUT_S=0.2
        install_droid_delegation
        echo install-continued
        """,
        extra_env={"FAKE_DROID_BIN": str(fake_bin)},
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert "WARN: Failed to register Droid MCP delegation within 0.2s" in completed.stdout
    assert "install-continued" in completed.stdout

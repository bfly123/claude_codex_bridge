from __future__ import annotations

from pathlib import Path
try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    import tomli as tomllib

import pytest

import agents.config_loader_runtime.io_runtime.documents as config_documents
from agents.config_loader import (
    ConfigValidationError,
    build_default_project_config,
    ensure_bootstrap_project_config,
    ensure_default_project_config,
    load_project_config,
    render_project_config_text,
)
from agents.models import AgentApiSpec, PermissionMode, QueuePolicy, RestoreMode, RuntimeMode, WorkspaceMode


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def test_load_valid_project_config(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo'
    config_path = project_root / '.ccb' / 'ccb.config'
    _write(config_path, 'cmd; agent1:codex\n')

    result = load_project_config(project_root)
    spec = result.config.agents['agent1']
    assert result.source_path == config_path
    assert spec.workspace_mode is WorkspaceMode.INPLACE
    assert spec.runtime_mode is RuntimeMode.PANE_BACKED
    assert spec.restore_default is RestoreMode.AUTO
    assert spec.permission_default is PermissionMode.MANUAL
    assert spec.queue_policy is QueuePolicy.SERIAL_PER_AGENT
    assert result.config.layout_spec == 'cmd; agent1:codex'


def test_load_project_config_rejects_provider_only_list(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo'
    config_path = project_root / '.ccb' / 'ccb.config'
    _write(config_path, 'codex,claude,cmd\n')

    with pytest.raises(ConfigValidationError, match='expected'):
        load_project_config(project_root)


def test_load_project_config_supports_named_simple_agent_map(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo'
    config_path = project_root / '.ccb' / 'ccb.config'
    _write(config_path, 'cmd, agent1:codex; agent2:codex, agent3:claude\n')

    result = load_project_config(project_root)

    assert result.source_path == config_path
    assert result.config.default_agents == ('agent1', 'agent2', 'agent3')
    assert set(result.config.agents) == {'agent1', 'agent2', 'agent3'}
    assert result.config.agents['agent1'].provider == 'codex'
    assert result.config.agents['agent2'].provider == 'codex'
    assert result.config.agents['agent3'].provider == 'claude'
    assert result.config.cmd_enabled is True
    assert result.config.layout_spec == 'cmd, agent1:codex; agent2:codex, agent3:claude'


def test_load_project_config_normalizes_mixed_case_compact_agent_names(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-mixed-case'
    config_path = project_root / '.ccb' / 'ccb.config'
    _write(
        config_path,
        'cmd, Alice:codex; Tomy:codex, Hanmeimei:claude; Lilei:gemini, Harry:gemini\n',
    )

    result = load_project_config(project_root)

    assert result.config.default_agents == ('alice', 'tomy', 'hanmeimei', 'lilei', 'harry')
    assert set(result.config.agents) == {'alice', 'tomy', 'hanmeimei', 'lilei', 'harry'}
    assert result.config.layout_spec == (
        'cmd, alice:codex; tomy:codex, hanmeimei:claude; lilei:gemini, harry:gemini'
    )


def test_load_project_config_rejects_case_insensitive_duplicates(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo'
    config_path = project_root / '.ccb' / 'ccb.config'
    _write(config_path, 'Agent1:codex,agent1:claude\n')
    with pytest.raises(ConfigValidationError):
        load_project_config(project_root)


def test_load_project_config_uses_builtin_default_when_project_config_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / 'repo'
    monkeypatch.setenv('HOME', str(tmp_path / 'empty-home'))
    config = build_default_project_config()
    assert config.default_agents == ('agent1', 'agent2', 'agent3')
    assert config.cmd_enabled is True
    loaded = load_project_config(project_root)
    assert loaded.source_path is None
    assert loaded.used_default is True
    assert loaded.config.default_agents == ('agent1', 'agent2', 'agent3')
    assert loaded.config.cmd_enabled is True
    assert set(loaded.config.agents) == {'agent1', 'agent2', 'agent3'}
    assert loaded.config.agents['agent1'].provider == 'codex'
    assert loaded.config.agents['agent2'].provider == 'codex'
    assert loaded.config.agents['agent3'].provider == 'claude'
    assert loaded.config.agents['agent1'].workspace_mode is WorkspaceMode.INPLACE
    assert loaded.config.agents['agent1'].runtime_mode is RuntimeMode.PANE_BACKED


def test_ensure_default_project_config_creates_anchor_without_writing_config(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo'

    config_path = ensure_default_project_config(project_root)

    assert config_path == project_root.resolve() / '.ccb' / 'ccb.config'
    assert config_path.parent.is_dir()
    assert config_path.exists() is False


def test_ensure_bootstrap_project_config_allows_empty_anchor(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-empty-anchor'
    (project_root / '.ccb').mkdir(parents=True, exist_ok=True)

    config_path = ensure_bootstrap_project_config(project_root)

    assert config_path == project_root.resolve() / '.ccb' / 'ccb.config'
    assert config_path.exists() is False


def test_ensure_bootstrap_project_config_allows_persisted_state_without_writing_config(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-missing-config-with-state'
    runtime_path = project_root / '.ccb' / 'agents' / 'demo' / 'runtime.json'
    _write(runtime_path, '{"agent_name":"demo"}\n')

    config_path = ensure_bootstrap_project_config(project_root)

    assert config_path.exists() is False


def test_load_project_config_supports_explicit_worktree_suffix_in_compact_config(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-worktree-compact'
    config_path = project_root / '.ccb' / 'ccb.config'
    _write(config_path, 'cmd; agent1:codex(worktree), agent2:claude\n')

    result = load_project_config(project_root)

    assert result.config.agents['agent1'].workspace_mode is WorkspaceMode.GIT_WORKTREE
    assert result.config.agents['agent2'].workspace_mode is WorkspaceMode.INPLACE
    assert result.config.layout_spec == 'cmd; agent1:codex(worktree), agent2:claude'


def test_ensure_bootstrap_project_config_ignores_session_residue_without_writing_config(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-session-residue'
    _write(project_root / '.ccb' / '.codex-agent1-session', '{}\n')
    _write(project_root / '.ccb' / '.claude-agent3-session', '{}\n')

    config_path = ensure_bootstrap_project_config(project_root)

    assert config_path.exists() is False


def test_load_project_config_rejects_invalid_token(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo'
    config_path = project_root / '.ccb' / 'ccb.config'
    _write(config_path, 'demo\n')

    with pytest.raises(ConfigValidationError, match='expected'):
        load_project_config(project_root)


def test_reserved_agent_name_is_rejected(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo'
    config_path = project_root / '.ccb' / 'ccb.config'
    _write(config_path, 'kill:codex\n')
    with pytest.raises(ConfigValidationError):
        load_project_config(project_root)


def test_cmd_only_config_is_rejected(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo'
    config_path = project_root / '.ccb' / 'ccb.config'
    _write(config_path, 'cmd\n')
    with pytest.raises(ConfigValidationError, match='at least one agent'):
        load_project_config(project_root)


def test_cmd_cannot_be_used_as_agent_name(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo'
    config_path = project_root / '.ccb' / 'ccb.config'
    _write(config_path, 'cmd:codex\n')
    with pytest.raises(ConfigValidationError, match='reserved token'):
        load_project_config(project_root)


def test_load_project_config_uses_user_default_when_project_config_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / 'home'
    user_default_config = home / '.ccb' / 'ccb.config'
    project_root = tmp_path / 'repo'
    project_root.mkdir()
    monkeypatch.setenv('HOME', str(home))
    _write(user_default_config, 'cmd; builder:codex, reviewer:claude; qa:gemini\n')

    result = load_project_config(project_root)

    assert result.source_path == user_default_config
    assert result.used_default is True
    assert result.config.default_agents == ('builder', 'reviewer', 'qa')
    assert result.config.agents['builder'].provider == 'codex'
    assert result.config.agents['reviewer'].provider == 'claude'
    assert result.config.agents['qa'].provider == 'gemini'
    assert result.config.cmd_enabled is True



def test_load_project_config_supports_toml_provider_profile(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo'
    config_path = project_root / '.ccb' / 'ccb.config'
    _write(
        config_path,
        """version = 2
default_agents = ["agent1"]
layout = "cmd; agent1"
cmd_enabled = true

[agents.agent1]
provider = "codex"
target = "."
workspace_mode = "git-worktree"
restore = "auto"
permission = "manual"

[agents.agent1.provider_profile]
mode = "isolated"
home = ".ccb/provider-profiles/agent1/codex"
inherit_api = false
inherit_auth = true
inherit_config = true
inherit_skills = false
inherit_commands = false
inherit_memory = false

[agents.agent1.provider_profile.env]
OPENAI_API_KEY = "sk-test"
""",
    )

    result = load_project_config(project_root)
    spec = result.config.agents['agent1']

    assert spec.provider_profile.mode == 'isolated'
    assert spec.provider_profile.home == '.ccb/provider-profiles/agent1/codex'
    assert spec.provider_profile.inherit_api is False
    assert spec.provider_profile.inherit_auth is True
    assert spec.provider_profile.inherit_skills is False
    assert spec.provider_profile.inherit_commands is False
    assert spec.provider_profile.inherit_memory is False
    assert spec.provider_profile.env == {'OPENAI_API_KEY': 'sk-test'}


@pytest.mark.parametrize('provider', ['claude', 'gemini'])
def test_load_project_config_rejects_non_codex_provider_profile_home(tmp_path: Path, provider: str) -> None:
    project_root = tmp_path / 'repo'
    config_path = project_root / '.ccb' / 'ccb.config'
    _write(
        config_path,
        f"""version = 2
default_agents = ["agent1"]

[agents.agent1]
provider = "{provider}"
target = "."
workspace_mode = "inplace"
restore = "auto"
permission = "manual"

[agents.agent1.provider_profile]
mode = "isolated"
home = ".ccb/provider-profiles/agent1/{provider}"
""",
    )

    with pytest.raises(ConfigValidationError, match='provider_profile\\.home is supported only for codex'):
        load_project_config(project_root)


@pytest.mark.parametrize(
    ('provider', 'api_block', 'expected_key', 'expected_url', 'expected_env', 'expected_inherit_config'),
    [
        (
            'codex',
            'key = "sk-test"\nurl = "https://openai.example.test/v1"\n',
            'sk-test',
            'https://openai.example.test/v1',
            {
                'OPENAI_API_KEY': 'sk-test',
                'OPENAI_BASE_URL': 'https://openai.example.test/v1',
            },
            False,
        ),
        (
            'claude',
            'key = "claude-key"\nurl = "https://claude.example.test"\n',
            'claude-key',
            'https://claude.example.test',
            {
                'ANTHROPIC_API_KEY': 'claude-key',
                'ANTHROPIC_BASE_URL': 'https://claude.example.test',
            },
            True,
        ),
        (
            'gemini',
            'key = "gemini-key"\nurl = "https://gemini.example.test"\n',
            'gemini-key',
            'https://gemini.example.test',
            {
                'GEMINI_API_KEY': 'gemini-key',
                'GOOGLE_GEMINI_BASE_URL': 'https://gemini.example.test',
            },
            True,
        ),
    ],
)
def test_load_project_config_supports_toml_agent_api_shortcut(
    tmp_path: Path,
    provider: str,
    api_block: str,
    expected_key: str,
    expected_url: str,
    expected_env: dict[str, str],
    expected_inherit_config: bool,
) -> None:
    project_root = tmp_path / f'repo-{provider}-api'
    config_path = project_root / '.ccb' / 'ccb.config'
    _write(
        config_path,
        f"""version = 2
default_agents = ["agent1"]
layout = "cmd; agent1"
cmd_enabled = true

[agents.agent1]
provider = "{provider}"
target = "."
workspace_mode = "git-worktree"
restore = "auto"
permission = "manual"

{api_block}""",
    )

    result = load_project_config(project_root)
    spec = result.config.agents['agent1']

    assert spec.api.key == expected_key
    assert spec.api.url == expected_url
    assert spec.provider_profile.inherit_api is False
    assert spec.provider_profile.inherit_auth is False
    assert spec.provider_profile.inherit_config is expected_inherit_config
    assert spec.provider_profile.env == expected_env


def test_load_project_config_supports_legacy_nested_agent_api_shortcut(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-legacy-nested-api'
    config_path = project_root / '.ccb' / 'ccb.config'
    _write(
        config_path,
        """version = 2
default_agents = ["agent1"]
layout = "cmd; agent1"
cmd_enabled = true

[agents.agent1]
provider = "codex"
target = "."
workspace_mode = "git-worktree"
restore = "auto"
permission = "manual"

[agents.agent1.api]
key = "sk-legacy"
url = "https://legacy.example.test/v1"
""",
    )

    result = load_project_config(project_root)
    spec = result.config.agents['agent1']

    assert spec.api.key == 'sk-legacy'
    assert spec.api.url == 'https://legacy.example.test/v1'
    assert spec.provider_profile.inherit_api is False
    assert spec.provider_profile.env == {
        'OPENAI_API_KEY': 'sk-legacy',
        'OPENAI_BASE_URL': 'https://legacy.example.test/v1',
    }
    assert spec.provider_profile.inherit_config is False
    assert spec.provider_profile.inherit_auth is False


def test_load_project_config_codex_api_shortcut_disables_conflicting_global_projection(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-codex-shortcut-flags'
    config_path = project_root / '.ccb' / 'ccb.config'
    _write(
        config_path,
        """version = 2
default_agents = ["agent1"]
layout = "cmd; agent1"
cmd_enabled = true

[agents.agent1]
provider = "codex"
target = "."
workspace_mode = "git-worktree"
restore = "auto"
permission = "manual"
key = "sk-shortcut"
url = "https://api.example.test/v1"
""",
    )

    result = load_project_config(project_root)
    spec = result.config.agents['agent1']

    assert spec.provider_profile.inherit_api is False
    assert spec.provider_profile.inherit_config is False
    assert spec.provider_profile.inherit_auth is False


def test_load_project_config_supports_uppercase_agent_api_keys(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-uppercase-api'
    config_path = project_root / '.ccb' / 'ccb.config'
    _write(
        config_path,
        """version = 2
default_agents = ["agent1"]
layout = "cmd; agent1"
cmd_enabled = true

[agents.agent1]
provider = "codex"
target = "."
workspace_mode = "git-worktree"
restore = "auto"
permission = "manual"

[agents.agent1.api]
KEY = "sk-upper"
URL = "https://upper.example.test/v1"
""",
    )

    result = load_project_config(project_root)
    spec = result.config.agents['agent1']

    assert spec.api.key == 'sk-upper'
    assert spec.api.url == 'https://upper.example.test/v1'
    assert spec.provider_profile.env == {
        'OPENAI_API_KEY': 'sk-upper',
        'OPENAI_BASE_URL': 'https://upper.example.test/v1',
    }


def test_load_project_config_normalizes_bare_codex_api_origin_to_v1_env(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-codex-origin-api'
    config_path = project_root / '.ccb' / 'ccb.config'
    _write(
        config_path,
        """version = 2
default_agents = ["agent1"]
layout = "cmd; agent1"
cmd_enabled = true

[agents.agent1]
provider = "codex"
target = "."
workspace_mode = "git-worktree"
restore = "auto"
permission = "manual"
key = "sk-origin"
url = "https://api.example.test"
""",
    )

    result = load_project_config(project_root)
    spec = result.config.agents['agent1']

    assert spec.api.key == 'sk-origin'
    assert spec.api.url == 'https://api.example.test'
    assert spec.provider_profile.env == {
        'OPENAI_API_KEY': 'sk-origin',
        'OPENAI_BASE_URL': 'https://api.example.test/v1',
    }


def test_load_project_config_supports_compact_header_with_agent_api_overlay(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-hybrid-api'
    config_path = project_root / '.ccb' / 'ccb.config'
    _write(
        config_path,
        """cmd, agent1:codex; agent2:claude

[agents.agent1]
key = "sk-hybrid"
url = "https://api.example.test/v1"
""",
    )

    result = load_project_config(project_root)

    assert result.config.layout_spec == 'cmd, agent1:codex; agent2:claude'
    assert result.config.default_agents == ('agent1', 'agent2')
    assert result.config.agents['agent1'].api == AgentApiSpec(
        key='sk-hybrid',
        url='https://api.example.test/v1',
    )
    assert result.config.agents['agent2'].provider == 'claude'


def test_load_project_config_rejects_mixed_flat_and_nested_agent_api_shortcuts(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-mixed-api-shortcuts'
    config_path = project_root / '.ccb' / 'ccb.config'
    _write(
        config_path,
        """cmd; agent1:codex

[agents.agent1]
key = "sk-flat"

[agents.agent1.api]
url = "https://api.example.test/v1"
""",
    )

    with pytest.raises(ConfigValidationError, match='key/url cannot be combined with agents\\.agent1\\.api'):
        load_project_config(project_root)


@pytest.mark.parametrize(
    ('provider', 'model_name', 'expected_startup_args'),
    [
        ('codex', 'gpt-5', ('-m', 'gpt-5')),
        ('claude', 'opus', ('--model', 'opus')),
        ('gemini', 'gemini-2.5-pro', ('-m', 'gemini-2.5-pro')),
        ('opencode', 'openai/gpt-5', ('-m', 'openai/gpt-5')),
    ],
)
def test_load_project_config_supports_agent_model_shortcut(
    tmp_path: Path,
    provider: str,
    model_name: str,
    expected_startup_args: tuple[str, ...],
) -> None:
    project_root = tmp_path / f'repo-{provider}-model'
    config_path = project_root / '.ccb' / 'ccb.config'
    _write(
        config_path,
        f"""cmd; agent1:{provider}

[agents.agent1]
model = "{model_name}"
""",
    )

    result = load_project_config(project_root)
    spec = result.config.agents['agent1']

    assert spec.model == model_name
    assert spec.startup_args == expected_startup_args


def test_load_project_config_supports_agent_model_shortcut_with_extra_startup_args(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-model-extra-startup-args'
    config_path = project_root / '.ccb' / 'ccb.config'
    _write(
        config_path,
        """cmd; agent1:codex

[agents.agent1]
model = "gpt-5"
startup_args = ["--search"]
""",
    )

    result = load_project_config(project_root)
    spec = result.config.agents['agent1']

    assert spec.model == 'gpt-5'
    assert spec.startup_args == ('-m', 'gpt-5', '--search')


def test_load_project_config_rejects_agent_model_shortcut_for_unsupported_provider(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-model-unsupported-provider'
    config_path = project_root / '.ccb' / 'ccb.config'
    _write(
        config_path,
        """cmd; agent1:droid

[agents.agent1]
model = "droid-pro"
""",
    )

    with pytest.raises(ConfigValidationError, match='model shortcut is supported only for providers'):
        load_project_config(project_root)


def test_load_project_config_rejects_agent_model_shortcut_mixed_with_startup_arg_model_flag(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-model-startup-conflict'
    config_path = project_root / '.ccb' / 'ccb.config'
    _write(
        config_path,
        """cmd; agent1:codex

[agents.agent1]
model = "gpt-5"
startup_args = ["--model", "gpt-4.1"]
""",
    )

    with pytest.raises(ConfigValidationError, match='model cannot be combined with startup_args model flags'):
        load_project_config(project_root)


def test_load_project_config_rejects_hybrid_overlay_redefining_compact_provider(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-hybrid-provider-conflict'
    config_path = project_root / '.ccb' / 'ccb.config'
    _write(
        config_path,
        """cmd; agent1:codex

[agents.agent1]
provider = "claude"
""",
    )

    with pytest.raises(ConfigValidationError, match='cannot redefine compact-header fields'):
        load_project_config(project_root)


def test_load_project_config_rejects_hybrid_overlay_for_unknown_agent(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-hybrid-unknown-agent'
    config_path = project_root / '.ccb' / 'ccb.config'
    _write(
        config_path,
        """cmd; agent1:codex

[agents.agent2]
key = "sk-extra"
""",
    )

    with pytest.raises(ConfigValidationError, match="cannot define agent 'agent2' outside the compact layout"):
        load_project_config(project_root)


def test_load_project_config_rejects_hybrid_overlay_top_level_fields(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-hybrid-top-level'
    config_path = project_root / '.ccb' / 'ccb.config'
    _write(
        config_path,
        """cmd; agent1:codex

version = 2
""",
    )

    with pytest.raises(ConfigValidationError, match='hybrid overlay contains unsupported top-level fields: version'):
        load_project_config(project_root)


def test_load_project_config_rejects_agent_api_shortcut_mixed_with_agent_env(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-agent-api-env-conflict'
    config_path = project_root / '.ccb' / 'ccb.config'
    _write(
        config_path,
        """version = 2
default_agents = ["agent1"]
layout = "cmd; agent1"
cmd_enabled = true

[agents.agent1]
provider = "codex"
target = "."
workspace_mode = "git-worktree"
restore = "auto"
permission = "manual"
key = "sk-shortcut"

[agents.agent1.env]
OPENAI_API_KEY = "sk-conflict"
""",
    )

    with pytest.raises(ConfigValidationError, match='key/url cannot be mixed with provider API env in agents\\.agent1\\.env'):
        load_project_config(project_root)


def test_load_project_config_rejects_agent_api_shortcut_mixed_with_provider_profile_env(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-provider-api-env-conflict'
    config_path = project_root / '.ccb' / 'ccb.config'
    _write(
        config_path,
        """version = 2
default_agents = ["agent1"]
layout = "cmd; agent1"
cmd_enabled = true

[agents.agent1]
provider = "codex"
target = "."
workspace_mode = "git-worktree"
restore = "auto"
permission = "manual"
key = "sk-shortcut"

[agents.agent1.provider_profile.env]
OPENAI_API_KEY = "sk-conflict"
""",
    )

    with pytest.raises(
        ConfigValidationError,
        match='key/url cannot be mixed with provider API env in agents\\.agent1\\.provider_profile\\.env',
    ):
        load_project_config(project_root)


def test_load_project_config_rejects_agent_api_shortcut_with_explicit_inherit_api_true(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-provider-inherit-api-conflict'
    config_path = project_root / '.ccb' / 'ccb.config'
    _write(
        config_path,
        """version = 2
default_agents = ["agent1"]
layout = "cmd; agent1"
cmd_enabled = true

[agents.agent1]
provider = "codex"
target = "."
workspace_mode = "git-worktree"
restore = "auto"
permission = "manual"
key = "sk-shortcut"

[agents.agent1.provider_profile]
inherit_api = true
""",
    )

    with pytest.raises(
        ConfigValidationError,
        match='key/url cannot be combined with agents\\.agent1\\.provider_profile\\.inherit_api = true',
    ):
        load_project_config(project_root)


def test_load_project_config_rejects_codex_api_shortcut_with_explicit_inherit_config_true(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-provider-inherit-config-conflict'
    config_path = project_root / '.ccb' / 'ccb.config'
    _write(
        config_path,
        """version = 2
default_agents = ["agent1"]
layout = "cmd; agent1"
cmd_enabled = true

[agents.agent1]
provider = "codex"
target = "."
workspace_mode = "git-worktree"
restore = "auto"
permission = "manual"
url = "https://api.example.test/v1"

[agents.agent1.provider_profile]
inherit_config = true
""",
    )

    with pytest.raises(
        ConfigValidationError,
        match='key/url cannot be combined with agents\\.agent1\\.provider_profile\\.inherit_config = true for codex',
    ):
        load_project_config(project_root)


@pytest.mark.parametrize('provider,key_field', [('codex', 'sk-shortcut'), ('claude', 'claude-key'), ('gemini', 'gemini-key')])
def test_load_project_config_rejects_agent_api_shortcut_with_explicit_inherit_auth_true(
    tmp_path: Path,
    provider: str,
    key_field: str,
) -> None:
    project_root = tmp_path / f'repo-provider-inherit-auth-conflict-{provider}'
    config_path = project_root / '.ccb' / 'ccb.config'
    _write(
        config_path,
        f"""version = 2
default_agents = ["agent1"]
layout = "cmd; agent1"
cmd_enabled = true

[agents.agent1]
provider = "{provider}"
target = "."
workspace_mode = "git-worktree"
restore = "auto"
permission = "manual"
key = "{key_field}"

[agents.agent1.provider_profile]
inherit_auth = true
""",
    )

    with pytest.raises(
        ConfigValidationError,
        match='key/url cannot be combined with agents\\.agent1\\.provider_profile\\.inherit_auth = true',
    ):
        load_project_config(project_root)


def test_render_project_config_text_round_trips_agent_api_shortcut(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-render-api'
    config_path = project_root / '.ccb' / 'ccb.config'
    _write(
        config_path,
        """version = 2
default_agents = ["agent1"]
layout = "cmd; agent1"
cmd_enabled = true

[agents.agent1]
provider = "codex"
target = "."
workspace_mode = "git-worktree"
restore = "auto"
permission = "manual"
key = "sk-test"
url = "https://api.example.test/v1"

[agents.agent1.provider_profile]
mode = "isolated"
inherit_skills = false
""",
    )

    loaded = load_project_config(project_root)
    rendered = render_project_config_text(loaded.config)

    assert rendered.startswith('cmd; agent1:codex(worktree)\n')
    assert '[agents.agent1]' in rendered
    assert 'key = "sk-test"' in rendered
    assert 'url = "https://api.example.test/v1"' in rendered
    assert '[agents.agent1.api]' not in rendered
    assert 'OPENAI_API_KEY' not in rendered
    assert 'inherit_api = false' not in rendered

    rewritten_path = tmp_path / 'repo-render-api-roundtrip' / '.ccb' / 'ccb.config'
    _write(rewritten_path, rendered)

    round_tripped = load_project_config(rewritten_path.parents[1])
    spec = round_tripped.config.agents['agent1']

    assert spec.api == AgentApiSpec(key='sk-test', url='https://api.example.test/v1')
    assert spec.provider_profile.mode == 'isolated'
    assert spec.provider_profile.inherit_api is False
    assert spec.provider_profile.inherit_skills is False
    assert spec.provider_profile.env == {
        'OPENAI_API_KEY': 'sk-test',
        'OPENAI_BASE_URL': 'https://api.example.test/v1',
    }


def test_render_project_config_text_migrates_legacy_nested_agent_api_shortcut_to_flat_fields(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-render-legacy-api'
    config_path = project_root / '.ccb' / 'ccb.config'
    _write(
        config_path,
        """version = 2
default_agents = ["agent1"]
layout = "cmd; agent1"
cmd_enabled = true

[agents.agent1]
provider = "codex"
target = "."
workspace_mode = "git-worktree"
restore = "auto"
permission = "manual"

[agents.agent1.api]
key = "sk-legacy"
url = "https://legacy.example.test/v1"
""",
    )

    loaded = load_project_config(project_root)
    rendered = render_project_config_text(loaded.config)

    assert '[agents.agent1.api]' not in rendered
    assert '[agents.agent1]' in rendered
    assert 'key = "sk-legacy"' in rendered
    assert 'url = "https://legacy.example.test/v1"' in rendered


def test_render_project_config_text_round_trips_agent_model_shortcut(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-render-model'
    config_path = project_root / '.ccb' / 'ccb.config'
    _write(
        config_path,
        """version = 2
default_agents = ["agent1"]
layout = "cmd; agent1"
cmd_enabled = true

[agents.agent1]
provider = "codex"
target = "."
workspace_mode = "git-worktree"
restore = "auto"
permission = "manual"
model = "gpt-5"
startup_args = ["--search"]
key = "sk-test"
url = "https://api.example.test/v1"
""",
    )

    loaded = load_project_config(project_root)
    rendered = render_project_config_text(loaded.config)

    assert rendered.startswith('cmd; agent1:codex(worktree)\n')
    assert '[agents.agent1]' in rendered
    assert 'model = "gpt-5"' in rendered
    assert 'startup_args = ["--search"]' in rendered
    assert 'startup_args = ["-m", "gpt-5", "--search"]' not in rendered

    rewritten_path = tmp_path / 'repo-render-model-roundtrip' / '.ccb' / 'ccb.config'
    _write(rewritten_path, rendered)

    round_tripped = load_project_config(rewritten_path.parents[1])
    spec = round_tripped.config.agents['agent1']

    assert spec.model == 'gpt-5'
    assert spec.startup_args == ('-m', 'gpt-5', '--search')
    assert spec.api == AgentApiSpec(key='sk-test', url='https://api.example.test/v1')


def test_render_project_config_text_round_trips_noncompact_provider_profile(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-render-provider-profile'
    config_path = project_root / '.ccb' / 'ccb.config'
    _write(
        config_path,
        """version = 2
default_agents = ["agent1"]
layout = "cmd; agent1"
cmd_enabled = true

[agents.agent1]
provider = "claude"
target = "."
workspace_mode = "git-worktree"
restore = "auto"
permission = "manual"

[agents.agent1.provider_profile]
mode = "isolated"
inherit_api = false
inherit_auth = false

[agents.agent1.provider_profile.env]
ANTHROPIC_API_KEY = "claude-key"
ANTHROPIC_BASE_URL = "https://claude.example.test"
""",
    )

    loaded = load_project_config(project_root)
    rendered = render_project_config_text(loaded.config)

    assert rendered.startswith('cmd; agent1:claude(worktree)\n')
    assert '[agents.agent1.provider_profile]' in rendered
    assert '[agents.agent1.provider_profile.env]' in rendered
    assert 'ANTHROPIC_API_KEY = "claude-key"' in rendered

    rewritten_path = tmp_path / 'repo-render-provider-profile-roundtrip' / '.ccb' / 'ccb.config'
    _write(rewritten_path, rendered)

    round_tripped = load_project_config(rewritten_path.parents[1])
    spec = round_tripped.config.agents['agent1']

    assert spec.provider_profile.mode == 'isolated'
    assert spec.provider_profile.inherit_api is False
    assert spec.provider_profile.inherit_auth is False
    assert spec.provider_profile.env == {
        'ANTHROPIC_API_KEY': 'claude-key',
        'ANTHROPIC_BASE_URL': 'https://claude.example.test',
    }


def test_load_project_config_reads_project_ccb_config_path(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-layout-path'
    config_path = project_root / '.ccb' / 'ccb.config'
    _write(config_path, 'cmd; agent1:codex\n')

    result = load_project_config(project_root)

    assert result.source_path == config_path
    assert result.config.layout_spec == 'cmd; agent1:codex'


def test_load_project_config_compact_format_does_not_require_toml_reader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / 'repo-compact-no-toml'
    config_path = project_root / '.ccb' / 'ccb.config'
    _write(config_path, 'cmd; agent1:codex\n')

    def _unexpected_reader(path: Path):
        raise AssertionError(f'compact config unexpectedly requested TOML reader for {path}')

    monkeypatch.setattr(config_documents, '_load_toml_reader', _unexpected_reader)

    result = load_project_config(project_root)

    assert result.config.layout_spec == 'cmd; agent1:codex'


def test_load_project_config_reports_actionable_error_when_rich_toml_parser_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / 'repo-rich-no-toml'
    config_path = project_root / '.ccb' / 'ccb.config'
    _write(
        config_path,
        'version = 2\n'
        'default_agents = ["agent1"]\n'
        'layout = "agent1"\n'
        '\n'
        '[agents.agent1]\n'
        'provider = "codex"\n'
        'target = "."\n',
    )

    monkeypatch.setattr(config_documents, '_import_optional_toml_reader', lambda: None)

    with pytest.raises(ConfigValidationError, match='rich TOML config requires Python 3.11\\+'):
        load_project_config(project_root)


def test_load_project_config_reports_actionable_error_when_hybrid_overlay_parser_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / 'repo-hybrid-no-toml'
    config_path = project_root / '.ccb' / 'ccb.config'
    _write(
        config_path,
        'cmd; agent1:codex\n'
        '\n'
        '[agents.agent1]\n'
        'key = "sk-test"\n',
    )

    monkeypatch.setattr(config_documents, '_import_optional_toml_reader', lambda: None)

    with pytest.raises(ConfigValidationError, match='rich TOML config requires Python 3.11\\+'):
        load_project_config(project_root)


def test_render_toml_value_service_handles_dict_inline_table() -> None:
    from agents.config_loader_runtime.defaults_runtime.rendering_runtime.service import _render_toml_value
    result = _render_toml_value({'key': 'val', 'count': 3})
    assert result == '{ key = "val", count = 3 }'


def test_render_toml_value_service_handles_empty_dict() -> None:
    from agents.config_loader_runtime.defaults_runtime.rendering_runtime.service import _render_toml_value
    result = _render_toml_value({})
    assert result == '{}'


def test_render_toml_value_service_handles_dict_in_mixed_list() -> None:
    from agents.config_loader_runtime.defaults_runtime.rendering_runtime.service import _render_toml_value
    result = _render_toml_value(['literal', {'key': 'val'}])
    assert result == '["literal", { key = "val" }]'


def test_render_toml_mapping_handles_array_of_tables() -> None:
    from agents.config_loader_runtime.defaults_runtime.rendering_runtime.service import _render_toml_document
    payload = {
        'items': [
            {'name': 'first', 'value': 1},
            {'name': 'second', 'value': 2},
        ]
    }
    rendered = _render_toml_document(payload)
    assert '[[items]]' in rendered
    assert 'name = "first"' in rendered
    assert 'value = 1' in rendered
    assert 'name = "second"' in rendered
    assert 'value = 2' in rendered


def test_render_toml_mapping_handles_array_of_tables_with_only_child_tables() -> None:
    from agents.config_loader_runtime.defaults_runtime.rendering_runtime.service import _render_toml_document
    payload = {
        'items': [
            {'child': {'x': 1}},
            {'child': {'x': 2}},
        ]
    }
    rendered = _render_toml_document(payload)
    assert tomllib.loads(rendered) == {
        'items': [
            {'child': {'x': 1}},
            {'child': {'x': 2}},
        ]
    }

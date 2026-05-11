from __future__ import annotations

import json
import os
from pathlib import Path
import shutil

import pytest

from agents.models import AgentSpec, PermissionMode, ProviderProfileSpec, QueuePolicy, RestoreMode, RuntimeMode, WorkspaceMode
import provider_backends.claude.launcher_runtime.home as claude_home_runtime
from provider_backends.claude.launcher_runtime.home import materialize_claude_home_config
from provider_backends.gemini.launcher_runtime.home import materialize_gemini_home_config
import provider_profiles.codex_home_config as codex_home_config
from provider_profiles.codex_home_config import codex_provider_authority_fingerprint
from provider_profiles import materialize_provider_profile, validate_provider_runtime_home_uniqueness
from provider_core.pathing import session_filename_for_agent
from storage.paths import PathLayout


def _spec(name: str, provider: str = "codex", *, provider_profile: ProviderProfileSpec | None = None) -> AgentSpec:
    return AgentSpec(
        name=name,
        provider=provider,
        target='.',
        workspace_mode=WorkspaceMode.GIT_WORKTREE,
        workspace_root=None,
        runtime_mode=RuntimeMode.PANE_BACKED,
        restore_default=RestoreMode.AUTO,
        permission_default=PermissionMode.MANUAL,
        queue_policy=QueuePolicy.SERIAL_PER_AGENT,
        provider_profile=provider_profile or ProviderProfileSpec(),
    )


def _write_project_memory(project_root: Path, text: str) -> None:
    path = project_root / '.ccb' / 'ccb_memory.md'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def _write_codex_plugin_source(
    home: Path,
    *,
    plugin_name: str = 'demo-plugin',
    sha: str | None = 'plugins-sha-v1',
    marketplace_name: str = 'openai-curated',
    skill_body: str = 'plugin skill v1\n',
) -> None:
    plugin_root = home / '.tmp' / 'plugins'
    (plugin_root / '.agents' / 'plugins').mkdir(parents=True, exist_ok=True)
    (plugin_root / '.agents' / 'skills' / 'plugin-creator').mkdir(parents=True, exist_ok=True)
    (plugin_root / 'plugins' / plugin_name / '.codex-plugin').mkdir(parents=True, exist_ok=True)
    (plugin_root / 'plugins' / plugin_name / 'skills' / plugin_name).mkdir(parents=True, exist_ok=True)
    (home / '.tmp').mkdir(parents=True, exist_ok=True)
    if sha is None:
        (home / '.tmp' / 'plugins.sha').unlink(missing_ok=True)
    else:
        (home / '.tmp' / 'plugins.sha').write_text(f'{sha}\n', encoding='utf-8')
    (plugin_root / '.agents' / 'plugins' / 'marketplace.json').write_text(
        json.dumps(
            {
                'name': marketplace_name,
                'plugins': [
                    {
                        'name': plugin_name,
                        'source': {'source': 'local', 'path': f'./plugins/{plugin_name}'},
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )
    (plugin_root / 'plugins' / plugin_name / '.codex-plugin' / 'plugin.json').write_text(
        json.dumps({'name': plugin_name}, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    (plugin_root / 'plugins' / plugin_name / 'skills' / plugin_name / 'SKILL.md').write_text(
        skill_body,
        encoding='utf-8',
    )


def test_materialize_codex_profile_copies_inherited_assets(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / 'repo'
    source_home = tmp_path / 'system-codex-home'
    (source_home / 'skills').mkdir(parents=True, exist_ok=True)
    (source_home / 'commands').mkdir(parents=True, exist_ok=True)
    (source_home / 'config.toml').write_text('model = "gpt-5"\n', encoding='utf-8')
    (source_home / 'auth.json').write_text('{"OPENAI_API_KEY":"system-key"}', encoding='utf-8')
    (source_home / 'skills' / 'demo.md').write_text('demo skill\n', encoding='utf-8')
    (source_home / 'commands' / 'demo.md').write_text('demo command\n', encoding='utf-8')
    _write_codex_plugin_source(source_home)
    monkeypatch.setenv('CODEX_HOME', str(source_home))
    layout = PathLayout(project_root)

    profile = materialize_provider_profile(
        layout=layout,
        spec=_spec(
            'agent1',
            provider_profile=ProviderProfileSpec(
                mode='isolated',
                inherit_api=False,
                inherit_auth=True,
                inherit_config=True,
                inherit_skills=True,
                inherit_commands=True,
            ),
        ),
        workspace_path=project_root,
    )

    runtime_home = Path(profile.runtime_home or '')
    assert runtime_home == layout.agent_provider_state_dir('agent1', 'codex') / 'home'
    assert profile.profile_root is None
    assert not (layout.provider_profiles_dir / 'agent1' / 'codex').exists()
    assert runtime_home.is_dir()
    assert (runtime_home / 'config.toml').is_file()
    assert (runtime_home / 'auth.json').is_file()
    assert (runtime_home / 'skills' / 'demo.md').is_file()
    assert (runtime_home / 'commands' / 'demo.md').is_file()
    assert (runtime_home / '.tmp' / 'plugins.sha').read_text(encoding='utf-8') == 'plugins-sha-v1\n'
    assert (runtime_home / '.tmp' / 'plugins' / '.agents' / 'plugins' / 'marketplace.json').is_file()
    assert (runtime_home / '.tmp' / 'plugins' / 'plugins' / 'demo-plugin' / '.codex-plugin' / 'plugin.json').is_file()
    assert (runtime_home / 'sessions').is_dir()


def test_materialize_codex_profile_preserves_explicit_runtime_home(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / 'repo'
    explicit_home = tmp_path / 'explicit-codex-home'
    source_home = tmp_path / 'system-codex-home'
    source_home.mkdir(parents=True, exist_ok=True)
    (source_home / 'config.toml').write_text('model = "gpt-5"\n', encoding='utf-8')
    monkeypatch.setenv('CODEX_HOME', str(source_home))

    profile = materialize_provider_profile(
        layout=PathLayout(project_root),
        spec=_spec(
            'agent1',
            provider_profile=ProviderProfileSpec(
                mode='isolated',
                home=str(explicit_home),
            ),
        ),
        workspace_path=project_root,
    )

    assert Path(profile.runtime_home or '') == explicit_home.resolve()
    assert Path(profile.profile_root or '') == explicit_home.resolve()
    assert (explicit_home / 'config.toml').is_file()
    assert (explicit_home / 'sessions').is_dir()


def test_materialize_codex_profile_migrates_legacy_profile_runtime_home(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / 'repo'
    layout = PathLayout(project_root)
    source_home = tmp_path / 'system-codex-home'
    source_home.mkdir(parents=True, exist_ok=True)
    (source_home / 'auth.json').write_text('{"OPENAI_API_KEY":"source-key"}\n', encoding='utf-8')
    _write_codex_plugin_source(source_home, plugin_name='source-plugin', sha='source-sha', skill_body='source skill\n')
    monkeypatch.setenv('CODEX_HOME', str(source_home))
    legacy_home = layout.provider_profiles_dir / 'agent1' / 'codex'
    legacy_session = legacy_home / 'sessions' / '2026' / '05' / '10' / 'legacy.jsonl'
    legacy_session.parent.mkdir(parents=True, exist_ok=True)
    legacy_session.write_text('{"type":"session"}\n', encoding='utf-8')
    (legacy_home / 'auth.json').write_text('{"OPENAI_API_KEY":"legacy-key"}\n', encoding='utf-8')
    _write_codex_plugin_source(legacy_home, plugin_name='legacy-plugin', sha='source-sha')
    session_file = layout.ccb_dir / session_filename_for_agent('codex', 'agent1')
    session_file.parent.mkdir(parents=True, exist_ok=True)
    session_file.write_text(
        json.dumps(
            {
                'codex_home': str(legacy_home),
                'codex_session_root': str(legacy_home / 'sessions'),
                'codex_session_path': str(legacy_session),
                'start_cmd': (
                    f'CODEX_HOME={legacy_home} '
                    f'CODEX_SESSION_ROOT={legacy_home / "sessions"} '
                    f'UNCHANGED={legacy_home}-suffix '
                    f'codex resume old'
                ),
                'codex_start_cmd': f'CODEX_HOME={legacy_home} CODEX_SESSION_ROOT={legacy_home / "sessions"} codex resume old',
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )

    profile = materialize_provider_profile(
        layout=layout,
        spec=_spec('agent1', provider_profile=ProviderProfileSpec(mode='isolated')),
        workspace_path=project_root,
    )

    runtime_home = Path(profile.runtime_home or '')
    migrated_session = runtime_home / 'sessions' / '2026' / '05' / '10' / 'legacy.jsonl'
    assert runtime_home == layout.agent_provider_state_dir('agent1', 'codex') / 'home'
    assert profile.profile_root is None
    assert migrated_session.read_text(encoding='utf-8') == '{"type":"session"}\n'
    assert (runtime_home / 'auth.json').read_text(encoding='utf-8') == '{"OPENAI_API_KEY":"source-key"}\n'
    assert (runtime_home / '.tmp' / 'plugins.sha').read_text(encoding='utf-8') == 'source-sha\n'
    assert (runtime_home / '.tmp' / 'plugins' / 'plugins' / 'source-plugin' / 'skills' / 'source-plugin' / 'SKILL.md').read_text(encoding='utf-8') == 'source skill\n'
    assert not (runtime_home / '.tmp' / 'plugins' / 'plugins' / 'legacy-plugin').exists()
    assert not (legacy_home / 'sessions').exists()
    payload = json.loads(session_file.read_text(encoding='utf-8'))
    assert payload['codex_home'] == str(runtime_home)
    assert payload['codex_session_root'] == str(runtime_home / 'sessions')
    assert payload['codex_session_path'] == str(migrated_session)
    assert f'CODEX_HOME={runtime_home}' in payload['start_cmd']
    assert f'CODEX_SESSION_ROOT={runtime_home / "sessions"}' in payload['start_cmd']
    assert str(legacy_home) not in payload['codex_start_cmd']
    assert f'UNCHANGED={legacy_home}-suffix' in payload['start_cmd']
    events = [
        json.loads(line)
        for line in layout.agent_events_path('agent1').read_text(encoding='utf-8').splitlines()
        if line.strip()
    ]
    assert events[-1]['event_type'] == 'codex_profile_migration'
    assert events[-1]['status'] == 'migrated'
    assert events[-1]['reason'] == 'legacy_profile_runtime_home_migrated'


def test_materialize_codex_profile_migration_respects_inherit_auth_false(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / 'repo'
    layout = PathLayout(project_root)
    source_home = tmp_path / 'system-codex-home'
    source_home.mkdir(parents=True, exist_ok=True)
    (source_home / 'auth.json').write_text('{"OPENAI_API_KEY":"source-key"}\n', encoding='utf-8')
    monkeypatch.setenv('CODEX_HOME', str(source_home))
    legacy_home = layout.provider_profiles_dir / 'agent1' / 'codex'
    legacy_session = legacy_home / 'sessions' / '2026' / '05' / '10' / 'legacy.jsonl'
    legacy_session.parent.mkdir(parents=True, exist_ok=True)
    legacy_session.write_text('{"type":"session"}\n', encoding='utf-8')
    (legacy_home / 'auth.json').write_text('{"OPENAI_API_KEY":"legacy-key"}\n', encoding='utf-8')
    session_file = layout.ccb_dir / session_filename_for_agent('codex', 'agent1')
    session_file.parent.mkdir(parents=True, exist_ok=True)
    session_file.write_text(
        json.dumps(
            {
                'codex_home': str(legacy_home),
                'codex_session_root': str(legacy_home / 'sessions'),
                'codex_session_path': str(legacy_session),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )

    profile = materialize_provider_profile(
        layout=layout,
        spec=_spec(
            'agent1',
            provider_profile=ProviderProfileSpec(mode='isolated', inherit_auth=False),
        ),
        workspace_path=project_root,
    )

    runtime_home = Path(profile.runtime_home or '')
    assert (runtime_home / 'sessions' / '2026' / '05' / '10' / 'legacy.jsonl').is_file()
    assert not (runtime_home / 'auth.json').exists()
    assert not (legacy_home / 'sessions').exists()


def test_materialize_codex_profile_does_not_migrate_when_session_authority_is_malformed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root = tmp_path / 'repo'
    layout = PathLayout(project_root)
    source_home = tmp_path / 'system-codex-home'
    source_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv('CODEX_HOME', str(source_home))
    legacy_home = layout.provider_profiles_dir / 'agent1' / 'codex'
    legacy_session = legacy_home / 'sessions' / '2026' / '05' / '10' / 'legacy.jsonl'
    legacy_session.parent.mkdir(parents=True, exist_ok=True)
    legacy_session.write_text('{"type":"session"}\n', encoding='utf-8')
    session_file = layout.ccb_dir / session_filename_for_agent('codex', 'agent1')
    session_file.parent.mkdir(parents=True, exist_ok=True)
    session_file.write_text('{not json}\n', encoding='utf-8')

    profile = materialize_provider_profile(
        layout=layout,
        spec=_spec('agent1', provider_profile=ProviderProfileSpec(mode='isolated')),
        workspace_path=project_root,
    )

    runtime_home = Path(profile.runtime_home or '')
    assert legacy_session.is_file()
    assert not (runtime_home / 'sessions' / '2026' / '05' / '10' / 'legacy.jsonl').exists()
    events = [
        json.loads(line)
        for line in layout.agent_events_path('agent1').read_text(encoding='utf-8').splitlines()
        if line.strip()
    ]
    assert events[-1]['event_type'] == 'codex_profile_migration'
    assert events[-1]['status'] == 'skipped'
    assert events[-1]['reason'] == 'session_authority_preflight_failed'
    assert session_file.read_text(encoding='utf-8') == '{not json}\n'


def test_materialize_codex_profile_migrates_legacy_sessions_with_unrelated_tmp_symlink(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root = tmp_path / 'repo'
    layout = PathLayout(project_root)
    source_home = tmp_path / 'system-codex-home'
    source_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv('CODEX_HOME', str(source_home))
    legacy_home = layout.provider_profiles_dir / 'agent1' / 'codex'
    legacy_session = legacy_home / 'sessions' / '2026' / '05' / '10' / 'legacy.jsonl'
    legacy_session.parent.mkdir(parents=True, exist_ok=True)
    legacy_session.write_text('{"type":"session"}\n', encoding='utf-8')
    outside = tmp_path / 'outside'
    outside.mkdir(parents=True, exist_ok=True)
    tmp_dir = legacy_home / 'tmp' / 'arg0'
    tmp_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(outside, tmp_dir / 'linked-outside')
    except OSError:
        pytest.skip('symlink creation is not available in this test environment')
    session_file = layout.ccb_dir / session_filename_for_agent('codex', 'agent1')
    session_file.parent.mkdir(parents=True, exist_ok=True)
    session_file.write_text(
        json.dumps(
            {
                'codex_home': str(legacy_home),
                'codex_session_root': str(legacy_home / 'sessions'),
                'codex_session_path': str(legacy_session),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )

    profile = materialize_provider_profile(
        layout=layout,
        spec=_spec('agent1', provider_profile=ProviderProfileSpec(mode='isolated')),
        workspace_path=project_root,
    )

    runtime_home = Path(profile.runtime_home or '')
    assert not legacy_session.exists()
    assert (runtime_home / 'sessions' / '2026' / '05' / '10' / 'legacy.jsonl').is_file()
    assert (tmp_dir / 'linked-outside').is_symlink()
    events = [
        json.loads(line)
        for line in layout.agent_events_path('agent1').read_text(encoding='utf-8').splitlines()
        if line.strip()
    ]
    assert events[-1]['event_type'] == 'codex_profile_migration'
    assert events[-1]['status'] == 'migrated'
    assert events[-1]['reason'] == 'legacy_profile_runtime_home_migrated'


def test_materialize_codex_profile_does_not_migrate_session_material_with_symlink(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root = tmp_path / 'repo'
    layout = PathLayout(project_root)
    source_home = tmp_path / 'system-codex-home'
    source_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv('CODEX_HOME', str(source_home))
    legacy_home = layout.provider_profiles_dir / 'agent1' / 'codex'
    legacy_session_root = legacy_home / 'sessions'
    legacy_session = legacy_session_root / '2026' / '05' / '10' / 'legacy.jsonl'
    legacy_session.parent.mkdir(parents=True, exist_ok=True)
    legacy_session.write_text('{"type":"session"}\n', encoding='utf-8')
    outside = tmp_path / 'outside'
    outside.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(outside, legacy_session_root / 'linked-outside')
    except OSError:
        pytest.skip('symlink creation is not available in this test environment')
    session_file = layout.ccb_dir / session_filename_for_agent('codex', 'agent1')
    session_file.parent.mkdir(parents=True, exist_ok=True)
    session_file.write_text(
        json.dumps(
            {
                'codex_home': str(legacy_home),
                'codex_session_root': str(legacy_session_root),
                'codex_session_path': str(legacy_session),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )

    profile = materialize_provider_profile(
        layout=layout,
        spec=_spec('agent1', provider_profile=ProviderProfileSpec(mode='isolated')),
        workspace_path=project_root,
    )

    runtime_home = Path(profile.runtime_home or '')
    assert legacy_session.is_file()
    assert not (runtime_home / 'sessions' / '2026' / '05' / '10' / 'legacy.jsonl').exists()
    events = [
        json.loads(line)
        for line in layout.agent_events_path('agent1').read_text(encoding='utf-8').splitlines()
        if line.strip()
    ]
    assert events[-1]['event_type'] == 'codex_profile_migration'
    assert events[-1]['status'] == 'skipped'
    assert events[-1]['reason'] == 'legacy_home_contains_symlink'


def test_materialize_codex_profile_does_not_migrate_when_agent_runtime_is_active(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root = tmp_path / 'repo'
    layout = PathLayout(project_root)
    source_home = tmp_path / 'system-codex-home'
    source_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv('CODEX_HOME', str(source_home))
    legacy_home = layout.provider_profiles_dir / 'agent1' / 'codex'
    legacy_session = legacy_home / 'sessions' / '2026' / '05' / '10' / 'legacy.jsonl'
    legacy_session.parent.mkdir(parents=True, exist_ok=True)
    legacy_session.write_text('{"type":"session"}\n', encoding='utf-8')
    runtime_path = layout.agent_runtime_path('agent1')
    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_path.write_text(
        json.dumps({'state': 'idle', 'pid': os.getpid()}, ensure_ascii=False) + '\n',
        encoding='utf-8',
    )
    session_file = layout.ccb_dir / session_filename_for_agent('codex', 'agent1')
    session_file.parent.mkdir(parents=True, exist_ok=True)
    session_file.write_text(
        json.dumps(
            {
                'codex_home': str(legacy_home),
                'codex_session_root': str(legacy_home / 'sessions'),
                'codex_session_path': str(legacy_session),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )

    profile = materialize_provider_profile(
        layout=layout,
        spec=_spec('agent1', provider_profile=ProviderProfileSpec(mode='isolated')),
        workspace_path=project_root,
    )

    runtime_home = Path(profile.runtime_home or '')
    assert legacy_session.is_file()
    assert not (runtime_home / 'sessions' / '2026' / '05' / '10' / 'legacy.jsonl').exists()
    events = [
        json.loads(line)
        for line in layout.agent_events_path('agent1').read_text(encoding='utf-8').splitlines()
        if line.strip()
    ]
    assert events[-1]['event_type'] == 'codex_profile_migration'
    assert events[-1]['status'] == 'skipped'
    assert events[-1]['reason'] == 'agent_runtime_active'


def test_materialize_codex_profile_migrates_with_stale_idle_runtime_record(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root = tmp_path / 'repo'
    layout = PathLayout(project_root)
    source_home = tmp_path / 'system-codex-home'
    source_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv('CODEX_HOME', str(source_home))
    legacy_home = layout.provider_profiles_dir / 'agent1' / 'codex'
    legacy_session = legacy_home / 'sessions' / '2026' / '05' / '10' / 'legacy.jsonl'
    legacy_session.parent.mkdir(parents=True, exist_ok=True)
    legacy_session.write_text('{"type":"session"}\n', encoding='utf-8')
    runtime_path = layout.agent_runtime_path('agent1')
    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_path.write_text('{"state":"idle","pid":0}\n', encoding='utf-8')
    session_file = layout.ccb_dir / session_filename_for_agent('codex', 'agent1')
    session_file.parent.mkdir(parents=True, exist_ok=True)
    session_file.write_text(
        json.dumps(
            {
                'codex_home': str(legacy_home),
                'codex_session_root': str(legacy_home / 'sessions'),
                'codex_session_path': str(legacy_session),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )

    profile = materialize_provider_profile(
        layout=layout,
        spec=_spec('agent1', provider_profile=ProviderProfileSpec(mode='isolated')),
        workspace_path=project_root,
    )

    runtime_home = Path(profile.runtime_home or '')
    assert (runtime_home / 'sessions' / '2026' / '05' / '10' / 'legacy.jsonl').is_file()
    assert not legacy_session.exists()


def test_materialize_codex_profile_writes_agent_local_provider_config_for_explicit_api(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root = tmp_path / 'repo'
    source_home = tmp_path / 'system-codex-home'
    source_home.mkdir(parents=True, exist_ok=True)
    (source_home / 'config.toml').write_text(
        '\n'.join(
            [
                'model_provider = "stale"',
                'model = "gpt-5.4-openai-compact"',
                'model_reasoning_effort = "xhigh"',
                'disable_response_storage = true',
                '',
                '[projects."/tmp/demo-project"]',
                'trust_level = "trusted"',
                '',
                '[model_providers.stale]',
                'name = "stale"',
                'base_url = "https://stale.example.test/v1"',
                'wire_api = "responses"',
                'requires_openai_auth = true',
                '',
            ]
        ),
        encoding='utf-8',
    )
    monkeypatch.setenv('CODEX_HOME', str(source_home))
    _write_codex_plugin_source(
        source_home,
        plugin_name='weatherpromise',
        marketplace_name='codex-official',
        skill_body='plugin skill explicit\n',
    )

    profile = materialize_provider_profile(
        layout=PathLayout(project_root),
        spec=_spec(
            'agent2',
            provider_profile=ProviderProfileSpec(
                mode='isolated',
                env={
                    'OPENAI_API_KEY': 'profile-key',
                    'OPENAI_BASE_URL': 'https://api.rootflowai.com',
                },
                inherit_api=False,
                inherit_auth=False,
                inherit_config=False,
            ),
        ),
        workspace_path=project_root,
    )

    runtime_home = Path(profile.runtime_home or '')
    config_text = (runtime_home / 'config.toml').read_text(encoding='utf-8')
    assert 'model_provider = "custom"' in config_text
    assert 'model = "gpt-5.4-openai-compact"' in config_text
    assert 'model_reasoning_effort = "xhigh"' in config_text
    assert 'disable_response_storage = true' in config_text
    assert '[projects."/tmp/demo-project"]' in config_text
    assert '[model_providers.custom]' in config_text
    assert 'base_url = "https://api.rootflowai.com"' in config_text
    assert 'wire_api = "responses"' in config_text
    assert 'requires_openai_auth = false' in config_text
    assert 'https://stale.example.test/v1' not in config_text
    assert 'env_key' not in config_text
    assert codex_provider_authority_fingerprint(profile)
    auth_payload = json.loads((runtime_home / 'auth.json').read_text(encoding='utf-8'))
    assert auth_payload == {'OPENAI_API_KEY': 'profile-key'}
    assert (runtime_home / '.tmp' / 'plugins.sha').read_text(encoding='utf-8') == 'plugins-sha-v1\n'
    assert (runtime_home / '.tmp' / 'plugins' / '.agents' / 'plugins' / 'marketplace.json').is_file()
    assert (runtime_home / '.tmp' / 'plugins' / 'plugins' / 'weatherpromise' / 'skills' / 'weatherpromise' / 'SKILL.md').read_text(encoding='utf-8') == 'plugin skill explicit\n'


def test_materialize_codex_profile_refreshes_plugin_projection_when_source_changes(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / 'repo'
    source_home = tmp_path / 'system-codex-home'
    source_home.mkdir(parents=True, exist_ok=True)
    (source_home / 'config.toml').write_text('model = "gpt-5"\n', encoding='utf-8')
    monkeypatch.setenv('CODEX_HOME', str(source_home))
    _write_codex_plugin_source(
        source_home,
        plugin_name='weatherpromise',
        sha='plugins-sha-v1',
        marketplace_name='market-v1',
        skill_body='plugin skill v1\n',
    )

    profile = materialize_provider_profile(
        layout=PathLayout(project_root),
        spec=_spec('agent1', provider_profile=ProviderProfileSpec(mode='isolated')),
        workspace_path=project_root,
    )

    runtime_home = Path(profile.runtime_home or '')
    marketplace_path = runtime_home / '.tmp' / 'plugins' / '.agents' / 'plugins' / 'marketplace.json'
    skill_path = runtime_home / '.tmp' / 'plugins' / 'plugins' / 'weatherpromise' / 'skills' / 'weatherpromise' / 'SKILL.md'
    assert skill_path.read_text(encoding='utf-8') == 'plugin skill v1\n'

    _write_codex_plugin_source(
        source_home,
        plugin_name='weatherpromise',
        sha='plugins-sha-v2',
        marketplace_name='market-v2',
        skill_body='plugin skill v2\n',
    )

    materialize_provider_profile(
        layout=PathLayout(project_root),
        spec=_spec('agent1', provider_profile=ProviderProfileSpec(mode='isolated')),
        workspace_path=project_root,
    )

    marketplace_payload = json.loads(marketplace_path.read_text(encoding='utf-8'))
    assert marketplace_payload['name'] == 'market-v2'
    assert skill_path.read_text(encoding='utf-8') == 'plugin skill v2\n'
    assert (runtime_home / '.tmp' / 'plugins.sha').read_text(encoding='utf-8') == 'plugins-sha-v2\n'

    plugin_source_root = source_home / '.tmp' / 'plugins'
    plugin_sha_path = source_home / '.tmp' / 'plugins.sha'
    shutil.rmtree(plugin_source_root)
    plugin_sha_path.unlink(missing_ok=True)

    materialize_provider_profile(
        layout=PathLayout(project_root),
        spec=_spec('agent1', provider_profile=ProviderProfileSpec(mode='isolated')),
        workspace_path=project_root,
    )

    assert not (runtime_home / '.tmp' / 'plugins').exists()
    assert not (runtime_home / '.tmp' / 'plugins.sha').exists()


def test_materialize_codex_profile_refreshes_plugin_projection_without_sha_marker(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / 'repo'
    source_home = tmp_path / 'system-codex-home'
    source_home.mkdir(parents=True, exist_ok=True)
    (source_home / 'config.toml').write_text('model = "gpt-5"\n', encoding='utf-8')
    monkeypatch.setenv('CODEX_HOME', str(source_home))
    _write_codex_plugin_source(
        source_home,
        plugin_name='weatherpromise',
        sha=None,
        marketplace_name='market-no-sha-v1',
        skill_body='plugin skill no sha v1\n',
    )

    profile = materialize_provider_profile(
        layout=PathLayout(project_root),
        spec=_spec('agent1', provider_profile=ProviderProfileSpec(mode='isolated')),
        workspace_path=project_root,
    )

    runtime_home = Path(profile.runtime_home or '')
    marketplace_path = runtime_home / '.tmp' / 'plugins' / '.agents' / 'plugins' / 'marketplace.json'
    skill_path = runtime_home / '.tmp' / 'plugins' / 'plugins' / 'weatherpromise' / 'skills' / 'weatherpromise' / 'SKILL.md'
    assert not (runtime_home / '.tmp' / 'plugins.sha').exists()
    assert skill_path.read_text(encoding='utf-8') == 'plugin skill no sha v1\n'

    _write_codex_plugin_source(
        source_home,
        plugin_name='weatherpromise',
        sha=None,
        marketplace_name='market-no-sha-v2',
        skill_body='plugin skill no sha v2 updated\n',
    )

    materialize_provider_profile(
        layout=PathLayout(project_root),
        spec=_spec('agent1', provider_profile=ProviderProfileSpec(mode='isolated')),
        workspace_path=project_root,
    )

    marketplace_payload = json.loads(marketplace_path.read_text(encoding='utf-8'))
    assert marketplace_payload['name'] == 'market-no-sha-v2'
    assert skill_path.read_text(encoding='utf-8') == 'plugin skill no sha v2 updated\n'
    assert not (runtime_home / '.tmp' / 'plugins.sha').exists()


def test_materialize_codex_profile_skips_plugin_recopy_when_sha_is_unchanged(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / 'repo'
    source_home = tmp_path / 'system-codex-home'
    source_home.mkdir(parents=True, exist_ok=True)
    (source_home / 'config.toml').write_text('model = "gpt-5"\n', encoding='utf-8')
    monkeypatch.setenv('CODEX_HOME', str(source_home))
    _write_codex_plugin_source(
        source_home,
        plugin_name='weatherpromise',
        sha='stable-plugin-sha',
        marketplace_name='market-stable',
        skill_body='plugin skill stable\n',
    )

    copied_sources: list[Path] = []
    real_copytree = codex_home_config.shutil.copytree

    def tracking_copytree(src, dst, *args, **kwargs):
        src_path = Path(src)
        if src_path == source_home / '.tmp' / 'plugins':
            copied_sources.append(src_path)
        return real_copytree(src, dst, *args, **kwargs)

    monkeypatch.setattr(codex_home_config.shutil, 'copytree', tracking_copytree)

    materialize_provider_profile(
        layout=PathLayout(project_root),
        spec=_spec('agent1', provider_profile=ProviderProfileSpec(mode='isolated')),
        workspace_path=project_root,
    )
    materialize_provider_profile(
        layout=PathLayout(project_root),
        spec=_spec('agent1', provider_profile=ProviderProfileSpec(mode='isolated')),
        workspace_path=project_root,
    )

    assert copied_sources == [source_home / '.tmp' / 'plugins']


def test_materialize_codex_profile_repairs_incomplete_plugin_projection_even_when_sha_matches(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root = tmp_path / 'repo'
    source_home = tmp_path / 'system-codex-home'
    source_home.mkdir(parents=True, exist_ok=True)
    (source_home / 'config.toml').write_text('model = "gpt-5"\n', encoding='utf-8')
    monkeypatch.setenv('CODEX_HOME', str(source_home))
    _write_codex_plugin_source(
        source_home,
        plugin_name='weatherpromise',
        sha='repairable-plugin-sha',
        marketplace_name='market-repair',
        skill_body='plugin skill repair\n',
    )

    profile = materialize_provider_profile(
        layout=PathLayout(project_root),
        spec=_spec('agent1', provider_profile=ProviderProfileSpec(mode='isolated')),
        workspace_path=project_root,
    )

    runtime_home = Path(profile.runtime_home or '')
    marketplace_path = runtime_home / '.tmp' / 'plugins' / '.agents' / 'plugins' / 'marketplace.json'
    marketplace_path.unlink()
    assert not marketplace_path.exists()

    materialize_provider_profile(
        layout=PathLayout(project_root),
        spec=_spec('agent1', provider_profile=ProviderProfileSpec(mode='isolated')),
        workspace_path=project_root,
    )

    marketplace_payload = json.loads(marketplace_path.read_text(encoding='utf-8'))
    assert marketplace_payload['name'] == 'market-repair'


def test_materialize_claude_profile_keeps_runtime_home_managed_by_agent_state(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo'

    profile = materialize_provider_profile(
        layout=PathLayout(project_root),
        spec=_spec(
            'agent1',
            provider='claude',
            provider_profile=ProviderProfileSpec(
                mode='isolated',
                inherit_api=False,
            ),
        ),
        workspace_path=project_root,
    )

    assert profile.runtime_home is None


def test_materialize_claude_home_config_projects_system_settings_into_managed_home(tmp_path: Path) -> None:
    source_home = tmp_path / 'system-home'
    target_home = tmp_path / 'managed-home'
    source_settings = source_home / '.claude' / 'settings.json'
    source_settings.parent.mkdir(parents=True, exist_ok=True)
    source_settings.write_text(
        json.dumps(
            {
                'env': {
                    'ANTHROPIC_AUTH_TOKEN': 'system-token',
                    'ANTHROPIC_BASE_URL': 'https://claude.example.test',
                },
                'theme': 'light',
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )

    layout = materialize_claude_home_config(target_home, source_home=source_home)

    payload = json.loads(layout.settings_path.read_text(encoding='utf-8'))
    assert payload['env']['ANTHROPIC_AUTH_TOKEN'] == 'system-token'
    assert payload['env']['ANTHROPIC_BASE_URL'] == 'https://claude.example.test'
    assert payload['theme'] == 'light'


def test_materialize_claude_home_config_projects_official_login_auth_into_managed_home(tmp_path: Path) -> None:
    source_home = tmp_path / 'system-home'
    target_home = tmp_path / 'managed-home'
    source_credentials = source_home / '.claude' / '.credentials.json'
    source_legacy_auth = source_home / '.config' / 'claude-code' / 'auth.json'
    source_credentials.parent.mkdir(parents=True, exist_ok=True)
    source_legacy_auth.parent.mkdir(parents=True, exist_ok=True)
    source_credentials.write_text(
        json.dumps({'claudeAiOauth': {'refreshToken': 'system-refresh-token'}}, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    source_legacy_auth.write_text(
        json.dumps({'refresh_token': 'legacy-system-refresh-token'}, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )

    layout = materialize_claude_home_config(target_home, source_home=source_home)

    assert json.loads(layout.credentials_path.read_text(encoding='utf-8'))['claudeAiOauth']['refreshToken'] == 'system-refresh-token'
    assert json.loads(layout.auth_path.read_text(encoding='utf-8'))['refresh_token'] == 'legacy-system-refresh-token'


def test_materialize_claude_home_config_refreshes_login_metadata_without_replacing_trust(
    tmp_path: Path,
) -> None:
    source_home = tmp_path / 'system-home'
    target_home = tmp_path / 'managed-home'
    source_trust = source_home / '.claude.json'
    target_trust = target_home / '.claude.json'
    source_trust.parent.mkdir(parents=True, exist_ok=True)
    target_trust.parent.mkdir(parents=True, exist_ok=True)
    source_trust.write_text(
        json.dumps(
            {
                'oauthAccount': {
                    'emailAddress': 'user@example.test',
                    'organizationUuid': 'org-source',
                },
                'hasCompletedOnboarding': True,
                'lastOnboardingVersion': '2.1.97',
                '/source/workspace': {'hasTrustDialogAccepted': True},
                'primaryApiKey': 'must-not-project',
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )
    target_trust.write_text(
        json.dumps(
            {
                'oauthAccount': {'emailAddress': 'stale@example.test'},
                'primaryApiKey': 'stale-key',
                '/managed/workspace': {'hasTrustDialogAccepted': True},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )

    layout = materialize_claude_home_config(target_home, source_home=source_home)

    payload = json.loads(layout.trust_path.read_text(encoding='utf-8'))
    assert payload['oauthAccount']['emailAddress'] == 'user@example.test'
    assert payload['oauthAccount']['organizationUuid'] == 'org-source'
    assert payload['hasCompletedOnboarding'] is True
    assert payload['lastOnboardingVersion'] == '2.1.97'
    assert payload['/managed/workspace']['hasTrustDialogAccepted'] is True
    assert '/source/workspace' not in payload
    assert 'primaryApiKey' not in payload


def test_materialize_claude_home_config_strips_login_metadata_when_auth_not_inherited(
    tmp_path: Path,
) -> None:
    source_home = tmp_path / 'system-home'
    target_home = tmp_path / 'managed-home'
    target_trust = target_home / '.claude.json'
    target_trust.parent.mkdir(parents=True, exist_ok=True)
    target_trust.write_text(
        json.dumps(
            {
                'oauthAccount': {'emailAddress': 'stale@example.test'},
                'primaryApiKey': 'stale-key',
                '/managed/workspace': {'hasTrustDialogAccepted': True},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )
    (source_home / '.claude.json').parent.mkdir(parents=True, exist_ok=True)
    (source_home / '.claude.json').write_text('{"oauthAccount":{"emailAddress":"source@example.test"}}\n', encoding='utf-8')

    layout = materialize_claude_home_config(
        target_home,
        profile=ProviderProfileSpec(inherit_auth=False, inherit_api=False),
        source_home=source_home,
    )

    payload = json.loads(layout.trust_path.read_text(encoding='utf-8'))
    assert 'oauthAccount' not in payload
    assert 'primaryApiKey' not in payload
    assert payload['/managed/workspace']['hasTrustDialogAccepted'] is True


def test_materialize_claude_home_config_projects_macos_keychain_login_auth(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source_home = tmp_path / 'system-home'
    target_home = tmp_path / 'managed-home'
    source_home.mkdir(parents=True, exist_ok=True)
    calls: list[list[str]] = []

    class Result:
        returncode = 0
        stdout = json.dumps({'claudeAiOauth': {'refreshToken': 'keychain-refresh-token'}})

    def fake_run(argv, **kwargs):
        calls.append([str(part) for part in argv])
        assert kwargs['capture_output'] is True
        assert kwargs['text'] is True
        return Result()

    monkeypatch.setattr(claude_home_runtime.platform, 'system', lambda: 'Darwin')
    monkeypatch.setattr(claude_home_runtime.shutil, 'which', lambda name: '/usr/bin/security')
    monkeypatch.setattr(claude_home_runtime.subprocess, 'run', fake_run)
    monkeypatch.setenv('USER', 'mac-user')

    layout = materialize_claude_home_config(target_home, source_home=source_home)

    payload = json.loads(layout.credentials_path.read_text(encoding='utf-8'))
    assert payload['claudeAiOauth']['refreshToken'] == 'keychain-refresh-token'
    assert calls[0] == [
        '/usr/bin/security',
        'find-generic-password',
        '-a',
        'mac-user',
        '-s',
        'Claude Code-credentials',
        '-w',
    ]


def test_materialize_claude_home_config_falls_back_to_legacy_macos_keychain_service(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source_home = tmp_path / 'system-home'
    target_home = tmp_path / 'managed-home'
    source_home.mkdir(parents=True, exist_ok=True)
    calls: list[list[str]] = []

    class Result:
        def __init__(self, returncode: int, stdout: str = '') -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = ''

    def fake_run(argv, **kwargs):
        calls.append([str(part) for part in argv])
        service = calls[-1][calls[-1].index('-s') + 1]
        if service == 'Claude Code':
            return Result(0, json.dumps({'claudeAiOauth': {'refreshToken': 'legacy-refresh-token'}}))
        return Result(44)

    monkeypatch.setattr(claude_home_runtime.platform, 'system', lambda: 'Darwin')
    monkeypatch.setattr(claude_home_runtime.shutil, 'which', lambda name: '/usr/bin/security')
    monkeypatch.setattr(claude_home_runtime.subprocess, 'run', fake_run)
    monkeypatch.setenv('USER', 'mac-user')

    layout = materialize_claude_home_config(target_home, source_home=source_home)

    payload = json.loads(layout.credentials_path.read_text(encoding='utf-8'))
    assert payload['claudeAiOauth']['refreshToken'] == 'legacy-refresh-token'
    queried_services = [call[call.index('-s') + 1] for call in calls]
    assert queried_services == ['Claude Code-credentials', 'Claude Code-custom-oauth', 'Claude Code']
    assert all('-a' in call for call in calls)


def test_macos_keychain_services_keep_current_credentials_first_when_custom_oauth_enabled(monkeypatch) -> None:
    monkeypatch.setenv('CLAUDE_CODE_CUSTOM_OAUTH_URL', 'https://oauth.example.test')

    assert claude_home_runtime._macos_keychain_services() == (
        'Claude Code-credentials',
        'Claude Code-custom-oauth',
        'Claude Code',
    )


def test_materialize_claude_home_config_preserves_runtime_hooks_and_permissions(tmp_path: Path) -> None:
    source_home = tmp_path / 'system-home'
    target_home = tmp_path / 'managed-home'
    source_settings = source_home / '.claude' / 'settings.json'
    source_settings.parent.mkdir(parents=True, exist_ok=True)
    source_settings.write_text(
        json.dumps(
            {
                'env': {'ANTHROPIC_AUTH_TOKEN': 'system-token'},
                'theme': 'dark',
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )
    target_settings = target_home / '.claude' / 'settings.json'
    target_settings.parent.mkdir(parents=True, exist_ok=True)
    target_settings.write_text(
        json.dumps(
            {
                'hooks': {'Stop': [{'hooks': [{'type': 'command', 'command': 'echo hook'}]}]},
                'permissions': {'allow': ['Bash(ls)']},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )

    layout = materialize_claude_home_config(target_home, source_home=source_home)

    payload = json.loads(layout.settings_path.read_text(encoding='utf-8'))
    assert payload['env']['ANTHROPIC_AUTH_TOKEN'] == 'system-token'
    assert payload['theme'] == 'dark'
    assert payload['hooks']['Stop'][0]['hooks'][0]['command'] == 'echo hook'
    assert payload['permissions']['allow'] == ['Bash(ls)']


def test_materialize_claude_home_config_refreshes_inherited_skill_assets(tmp_path: Path) -> None:
    source_home = tmp_path / 'system-home'
    target_home = tmp_path / 'managed-home'
    source_claude_dir = source_home / '.claude'
    (source_claude_dir / 'skills' / 'review').mkdir(parents=True, exist_ok=True)
    (source_claude_dir / 'commands').mkdir(parents=True, exist_ok=True)
    (source_claude_dir / 'skills' / 'review' / 'SKILL.md').write_text('skill-v1\n', encoding='utf-8')
    (source_claude_dir / 'commands' / 'check.md').write_text('command-v1\n', encoding='utf-8')
    (source_claude_dir / 'CLAUDE.md').write_text('claude-md-v1\n', encoding='utf-8')

    layout = materialize_claude_home_config(target_home, source_home=source_home)

    assert (layout.claude_dir / 'skills' / 'review' / 'SKILL.md').read_text(encoding='utf-8') == 'skill-v1\n'
    assert (layout.claude_dir / 'commands' / 'check.md').read_text(encoding='utf-8') == 'command-v1\n'
    assert not (layout.claude_dir / 'CLAUDE.md').exists()

    (source_claude_dir / 'skills' / 'review' / 'SKILL.md').write_text('skill-v2\n', encoding='utf-8')
    (source_claude_dir / 'commands' / 'check.md').write_text('command-v2\n', encoding='utf-8')
    (source_claude_dir / 'CLAUDE.md').write_text('claude-md-v2\n', encoding='utf-8')

    materialize_claude_home_config(target_home, source_home=source_home)

    assert (layout.claude_dir / 'skills' / 'review' / 'SKILL.md').read_text(encoding='utf-8') == 'skill-v2\n'
    assert (layout.claude_dir / 'commands' / 'check.md').read_text(encoding='utf-8') == 'command-v2\n'
    assert not (layout.claude_dir / 'CLAUDE.md').exists()


def test_materialize_claude_home_config_writes_project_memory_bundle(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo'
    source_home = tmp_path / 'system-home'
    target_home = project_root / '.ccb' / 'agents' / 'reviewer' / 'provider-state' / 'claude' / 'home'
    source_claude_dir = source_home / '.claude'
    source_claude_dir.mkdir(parents=True, exist_ok=True)
    (source_claude_dir / 'CLAUDE.md').write_text('user claude memory\n', encoding='utf-8')
    project_root.mkdir(parents=True, exist_ok=True)
    _write_project_memory(project_root, 'shared ask memory\n')
    (project_root / 'CLAUDE.md').write_text('project claude memory\n', encoding='utf-8')
    private_memory = project_root / '.ccb' / 'agents' / 'reviewer' / 'memory.md'
    private_memory.parent.mkdir(parents=True, exist_ok=True)
    private_memory.write_text('reviewer private memory\n', encoding='utf-8')

    layout = materialize_claude_home_config(
        target_home,
        source_home=source_home,
        project_root=project_root,
        agent_name='reviewer',
        workspace_path=tmp_path / 'worktree',
    )

    text = (layout.claude_dir / 'CLAUDE.md').read_text(encoding='utf-8')
    assert '# CCB Managed Agent Memory' in text
    assert '## Provider User Memory' in text
    assert 'user claude memory' in text
    assert '## CCB Shared Project Memory' in text
    assert 'shared ask memory' in text
    assert '## Provider-Native Project Memory' in text
    assert 'project claude memory' in text
    assert '## Agent Private Memory' in text
    assert 'reviewer private memory' in text


def test_materialize_claude_home_config_respects_inherit_memory_flag(tmp_path: Path) -> None:
    source_home = tmp_path / 'system-home'
    target_home = tmp_path / 'managed-home'
    source_claude_dir = source_home / '.claude'
    source_claude_dir.mkdir(parents=True, exist_ok=True)
    (source_claude_dir / 'skills' / 'review').mkdir(parents=True, exist_ok=True)
    (source_claude_dir / 'skills' / 'review' / 'SKILL.md').write_text('skill\n', encoding='utf-8')
    (source_claude_dir / 'CLAUDE.md').write_text('claude-md\n', encoding='utf-8')

    layout = materialize_claude_home_config(
        target_home,
        profile=ProviderProfileSpec(inherit_skills=True, inherit_memory=False),
        source_home=source_home,
    )

    assert (layout.claude_dir / 'skills' / 'review' / 'SKILL.md').read_text(encoding='utf-8') == 'skill\n'
    assert not (layout.claude_dir / 'CLAUDE.md').exists()


def test_materialize_claude_home_config_skips_memory_without_project_context(tmp_path: Path) -> None:
    source_home = tmp_path / 'system-home'
    target_home = tmp_path / 'managed-home'
    source_claude_dir = source_home / '.claude'
    source_claude_dir.mkdir(parents=True, exist_ok=True)
    (source_claude_dir / 'CLAUDE.md').write_text('source-only memory\n', encoding='utf-8')

    layout = materialize_claude_home_config(target_home, source_home=source_home)

    assert not (layout.claude_dir / 'CLAUDE.md').exists()


def test_materialize_codex_home_config_writes_project_memory_bundle(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo'
    source_home = tmp_path / 'system-codex-home'
    target_home = project_root / '.ccb' / 'agents' / 'agent1' / 'provider-state' / 'codex' / 'home'
    source_home.mkdir(parents=True, exist_ok=True)
    (source_home / 'AGENTS.md').write_text('user codex memory\n', encoding='utf-8')
    project_root.mkdir(parents=True, exist_ok=True)
    _write_project_memory(project_root, 'shared ask memory\n')
    (project_root / 'AGENTS.md').write_text('project codex memory\n', encoding='utf-8')
    private_memory = project_root / '.ccb' / 'agents' / 'agent1' / 'memory.md'
    private_memory.parent.mkdir(parents=True, exist_ok=True)
    private_memory.write_text('agent1 private memory\n', encoding='utf-8')

    codex_home_config.materialize_codex_home_config(
        target_home,
        source_home=source_home,
        project_root=project_root,
        agent_name='agent1',
        workspace_path=tmp_path / 'worktree',
    )

    text = (target_home / 'AGENTS.md').read_text(encoding='utf-8')
    assert '# CCB Managed Agent Memory' in text
    assert 'provider: codex' in text
    assert '## Provider User Memory' in text
    assert 'user codex memory' in text
    assert '## CCB Shared Project Memory' in text
    assert 'shared ask memory' in text
    assert '## Provider-Native Project Memory' in text
    assert 'project codex memory' in text
    assert '## Agent Private Memory' in text
    assert 'agent1 private memory' in text


def test_materialize_codex_home_config_respects_inherit_memory_flag(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo'
    source_home = tmp_path / 'system-codex-home'
    target_home = tmp_path / 'managed-codex-home'
    target_home.mkdir(parents=True, exist_ok=True)
    (target_home / 'AGENTS.md').write_text('stale managed memory\n', encoding='utf-8')

    codex_home_config.materialize_codex_home_config(
        target_home,
        profile=ProviderProfileSpec(inherit_memory=False),
        source_home=source_home,
        project_root=project_root,
        agent_name='agent1',
    )

    assert not (target_home / 'AGENTS.md').exists()


def test_materialize_codex_home_config_skips_memory_without_project_context(tmp_path: Path) -> None:
    source_home = tmp_path / 'system-codex-home'
    target_home = tmp_path / 'managed-codex-home'
    source_home.mkdir(parents=True, exist_ok=True)
    target_home.mkdir(parents=True, exist_ok=True)
    (source_home / 'AGENTS.md').write_text('source-only memory\n', encoding='utf-8')
    (target_home / 'AGENTS.md').write_text('existing managed memory\n', encoding='utf-8')

    codex_home_config.materialize_codex_home_config(target_home, source_home=source_home)

    assert (target_home / 'AGENTS.md').read_text(encoding='utf-8') == 'existing managed memory\n'


def test_materialize_claude_home_config_projects_referenced_home_hook_assets(tmp_path: Path) -> None:
    source_home = tmp_path / 'system-home'
    target_home = tmp_path / 'managed-home'
    source_settings = source_home / '.claude' / 'settings.json'
    source_hook = source_home / '.codeisland' / 'codeisland-hook.sh'
    source_settings.parent.mkdir(parents=True, exist_ok=True)
    source_hook.parent.mkdir(parents=True, exist_ok=True)
    source_settings.write_text(
        json.dumps(
            {
                'hooks': {
                    'Stop': [
                        {
                            'hooks': [
                                {
                                    'type': 'command',
                                    'command': '$HOME/.codeisland/codeisland-hook.sh',
                                }
                            ]
                        }
                    ]
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )
    source_hook.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')

    layout = materialize_claude_home_config(target_home, source_home=source_home)

    assert (layout.home_root / '.codeisland' / 'codeisland-hook.sh').read_text(encoding='utf-8') == '#!/bin/sh\nexit 0\n'


def test_materialize_claude_home_config_does_not_project_home_hook_assets_without_config_inheritance(
    tmp_path: Path,
) -> None:
    source_home = tmp_path / 'system-home'
    target_home = tmp_path / 'managed-home'
    source_settings = source_home / '.claude' / 'settings.json'
    source_hook = source_home / '.codeisland' / 'codeisland-hook.sh'
    source_settings.parent.mkdir(parents=True, exist_ok=True)
    source_hook.parent.mkdir(parents=True, exist_ok=True)
    source_settings.write_text(
        json.dumps(
            {'hooks': {'Stop': [{'hooks': [{'type': 'command', 'command': '${HOME}/.codeisland/codeisland-hook.sh'}]}]}},
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )
    source_hook.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')

    layout = materialize_claude_home_config(
        target_home,
        source_home=source_home,
        profile=ProviderProfileSpec(inherit_config=False),
    )

    assert not (layout.home_root / '.codeisland').exists()


def test_materialize_claude_home_config_respects_inherit_skills_without_disabling_memory(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo'
    source_home = tmp_path / 'system-home'
    target_home = project_root / '.ccb' / 'agents' / 'reviewer' / 'provider-state' / 'claude' / 'home'
    source_claude_dir = source_home / '.claude'
    (source_claude_dir / 'skills' / 'review').mkdir(parents=True, exist_ok=True)
    (source_claude_dir / 'commands').mkdir(parents=True, exist_ok=True)
    (source_claude_dir / 'skills' / 'review' / 'SKILL.md').write_text('skill\n', encoding='utf-8')
    (source_claude_dir / 'commands' / 'check.md').write_text('command\n', encoding='utf-8')
    (source_claude_dir / 'CLAUDE.md').write_text('claude-md\n', encoding='utf-8')
    project_root.mkdir(parents=True, exist_ok=True)
    _write_project_memory(project_root, 'shared memory\n')

    layout = materialize_claude_home_config(
        target_home,
        profile=ProviderProfileSpec(inherit_skills=False, inherit_commands=True),
        source_home=source_home,
        project_root=project_root,
        agent_name='reviewer',
    )

    assert not (layout.claude_dir / 'skills').exists()
    memory_text = (layout.claude_dir / 'CLAUDE.md').read_text(encoding='utf-8')
    assert '# CCB Managed Agent Memory' in memory_text
    assert 'claude-md' in memory_text
    assert 'shared memory' in memory_text
    assert (layout.claude_dir / 'commands' / 'check.md').read_text(encoding='utf-8') == 'command\n'


def test_materialize_claude_home_config_preserves_managed_auth_when_source_is_logged_out(tmp_path: Path) -> None:
    source_home = tmp_path / 'system-home'
    target_home = tmp_path / 'managed-home'
    source_settings = source_home / '.claude' / 'settings.json'
    source_settings.parent.mkdir(parents=True, exist_ok=True)
    source_settings.write_text(
        json.dumps(
            {
                'env': {
                    'ANTHROPIC_BASE_URL': 'https://claude.example.test',
                },
                'theme': 'light',
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )
    target_settings = target_home / '.claude' / 'settings.json'
    target_settings.parent.mkdir(parents=True, exist_ok=True)
    target_settings.write_text(
        json.dumps(
            {
                'env': {
                    'ANTHROPIC_AUTH_TOKEN': 'managed-token',
                    'ANTHROPIC_BASE_URL': 'https://managed.example.test',
                },
                'theme': 'stale-theme',
                'hooks': {'Stop': [{'hooks': [{'type': 'command', 'command': 'echo hook'}]}]},
                'permissions': {'allow': ['Bash(ls)']},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )

    layout = materialize_claude_home_config(target_home, source_home=source_home)

    payload = json.loads(layout.settings_path.read_text(encoding='utf-8'))
    assert payload['env']['ANTHROPIC_AUTH_TOKEN'] == 'managed-token'
    assert payload['env']['ANTHROPIC_BASE_URL'] == 'https://claude.example.test'
    assert payload['theme'] == 'light'
    assert payload['hooks']['Stop'][0]['hooks'][0]['command'] == 'echo hook'
    assert payload['permissions']['allow'] == ['Bash(ls)']


def test_materialize_claude_home_config_refreshes_source_auth_over_managed_auth(tmp_path: Path) -> None:
    source_home = tmp_path / 'system-home'
    target_home = tmp_path / 'managed-home'
    source_settings = source_home / '.claude' / 'settings.json'
    source_settings.parent.mkdir(parents=True, exist_ok=True)
    source_settings.write_text(
        json.dumps(
            {
                'env': {
                    'ANTHROPIC_AUTH_TOKEN': 'system-token',
                    'ANTHROPIC_BASE_URL': 'https://claude.example.test',
                },
                'theme': 'light',
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )
    target_settings = target_home / '.claude' / 'settings.json'
    target_settings.parent.mkdir(parents=True, exist_ok=True)
    target_settings.write_text(
        json.dumps(
            {
                'env': {
                    'ANTHROPIC_AUTH_TOKEN': 'managed-token',
                    'ANTHROPIC_BASE_URL': 'https://managed.example.test',
                },
                'hooks': {'Stop': [{'hooks': [{'type': 'command', 'command': 'echo hook'}]}]},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )

    layout = materialize_claude_home_config(target_home, source_home=source_home)

    payload = json.loads(layout.settings_path.read_text(encoding='utf-8'))
    assert payload['env']['ANTHROPIC_AUTH_TOKEN'] == 'system-token'
    assert payload['env']['ANTHROPIC_BASE_URL'] == 'https://claude.example.test'
    assert payload['theme'] == 'light'
    assert payload['hooks']['Stop'][0]['hooks'][0]['command'] == 'echo hook'


def test_materialize_claude_home_config_clears_stale_managed_auth_when_auth_is_not_inherited(tmp_path: Path) -> None:
    source_home = tmp_path / 'system-home'
    target_home = tmp_path / 'managed-home'
    target_settings = target_home / '.claude' / 'settings.json'
    target_auth = target_home / '.config' / 'claude-code' / 'auth.json'
    target_credentials = target_home / '.claude' / '.credentials.json'
    target_settings.parent.mkdir(parents=True, exist_ok=True)
    target_settings.write_text(
        json.dumps(
            {
                'env': {'ANTHROPIC_AUTH_TOKEN': 'managed-token'},
                'theme': 'stale-theme',
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )
    target_auth.parent.mkdir(parents=True, exist_ok=True)
    target_auth.write_text('{"refresh_token":"stale-token"}\n', encoding='utf-8')
    target_credentials.write_text('{"claudeAiOauth":{"refreshToken":"stale-token"}}\n', encoding='utf-8')

    layout = materialize_claude_home_config(
        target_home,
        profile=ProviderProfileSpec(inherit_auth=False, inherit_api=False, inherit_config=True),
        source_home=source_home,
    )

    payload = json.loads(layout.settings_path.read_text(encoding='utf-8'))
    assert payload == {}
    assert not layout.auth_path.exists()
    assert not layout.credentials_path.exists()


def test_materialize_claude_home_config_preserves_managed_official_login_when_source_is_logged_out(tmp_path: Path) -> None:
    source_home = tmp_path / 'system-home'
    target_home = tmp_path / 'managed-home'
    source_settings = source_home / '.claude' / 'settings.json'
    source_settings.parent.mkdir(parents=True, exist_ok=True)
    source_settings.write_text(
        json.dumps(
            {
                'theme': 'light',
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )
    target_credentials = target_home / '.claude' / '.credentials.json'
    target_credentials.parent.mkdir(parents=True, exist_ok=True)
    target_credentials.write_text('{"claudeAiOauth":{"refreshToken":"managed-refresh-token"}}\n', encoding='utf-8')

    layout = materialize_claude_home_config(target_home, source_home=source_home)

    assert json.loads(layout.credentials_path.read_text(encoding='utf-8'))['claudeAiOauth']['refreshToken'] == 'managed-refresh-token'


def test_materialize_gemini_profile_keeps_runtime_home_unset_without_explicit_override(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo'

    profile = materialize_provider_profile(
        layout=PathLayout(project_root),
        spec=_spec(
            'agent1',
            provider='gemini',
            provider_profile=ProviderProfileSpec(
                mode='isolated',
                inherit_api=False,
            ),
        ),
        workspace_path=project_root,
    )

    assert profile.runtime_home is None


def test_materialize_gemini_profile_rejects_explicit_home_override(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo'
    explicit_home = tmp_path / 'gemini-home'

    with pytest.raises(ValueError, match='provider_profile.home is supported only for codex'):
        materialize_provider_profile(
            layout=PathLayout(project_root),
            spec=_spec(
                'agent1',
                provider='gemini',
                provider_profile=ProviderProfileSpec(
                    mode='isolated',
                    home=str(explicit_home),
                    inherit_api=False,
                ),
            ),
            workspace_path=project_root,
        )


def test_validate_provider_runtime_home_uniqueness_rejects_duplicate_codex_home(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo'
    shared_home = tmp_path / 'shared-codex-home'

    with pytest.raises(ValueError, match='duplicate effective codex_home'):
        validate_provider_runtime_home_uniqueness(
            layout=PathLayout(project_root),
            specs=(
                _spec(
                    'agent1',
                    provider='codex',
                    provider_profile=ProviderProfileSpec(mode='isolated', home=str(shared_home)),
                ),
                _spec(
                    'agent2',
                    provider='codex',
                    provider_profile=ProviderProfileSpec(mode='isolated', home=str(shared_home)),
                ),
            ),
        )


def test_materialize_gemini_home_config_projects_system_settings_into_managed_home(tmp_path: Path) -> None:
    source_home = tmp_path / 'system-home'
    target_home = tmp_path / 'managed-home'
    source_settings = source_home / '.gemini' / 'settings.json'
    source_settings.parent.mkdir(parents=True, exist_ok=True)
    source_settings.write_text(
        json.dumps(
            {
                'env': {
                    'GEMINI_API_KEY': 'system-gemini-key',
                    'GEMINI_MODEL': 'gemini-3.1-pro-preview',
                    'GOOGLE_API_KEY': 'system-google-key',
                    'GOOGLE_GEMINI_BASE_URL': 'https://chatapi.onechats.ai',
                },
                'theme': 'Default',
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )

    layout = materialize_gemini_home_config(target_home, source_home=source_home)

    payload = json.loads(layout.settings_path.read_text(encoding='utf-8'))
    assert payload['env']['GEMINI_API_KEY'] == 'system-gemini-key'
    assert payload['env']['GEMINI_MODEL'] == 'gemini-3.1-pro-preview'
    assert payload['env']['GOOGLE_API_KEY'] == 'system-google-key'
    assert payload['env']['GOOGLE_GEMINI_BASE_URL'] == 'https://chatapi.onechats.ai'
    assert payload['theme'] == 'Default'


def test_materialize_gemini_home_config_projects_dotenv_api_auth_into_managed_home(tmp_path: Path) -> None:
    source_home = tmp_path / 'system-home'
    target_home = tmp_path / 'managed-home'
    source_gemini = source_home / '.gemini'
    source_gemini.mkdir(parents=True, exist_ok=True)
    (source_gemini / 'settings.json').write_text(
        json.dumps(
            {
                'security': {
                    'auth': {
                        'selectedType': 'gemini-api-key',
                    }
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )
    (source_gemini / '.env').write_text(
        '\n'.join(
            [
                'GEMINI_API_KEY=system-gemini-key',
                'GOOGLE_GEMINI_BASE_URL=https://gemini.example.test',
                'GOOGLE_GENAI_USE_GCA=true',
                'GOOGLE_CLOUD_PROJECT=demo-project',
                'OTHER_SECRET=must-not-copy',
            ]
        )
        + '\n',
        encoding='utf-8',
    )

    layout = materialize_gemini_home_config(target_home, source_home=source_home)

    payload = json.loads(layout.settings_path.read_text(encoding='utf-8'))
    dotenv = (layout.gemini_dir / '.env').read_text(encoding='utf-8')
    assert payload['security']['auth']['selectedType'] == 'gemini-api-key'
    assert 'GEMINI_API_KEY="system-gemini-key"' in dotenv
    assert 'GOOGLE_GEMINI_BASE_URL="https://gemini.example.test"' in dotenv
    assert 'GOOGLE_GENAI_USE_GCA="true"' in dotenv
    assert 'GOOGLE_CLOUD_PROJECT="demo-project"' in dotenv
    assert 'OTHER_SECRET' not in dotenv


def test_materialize_gemini_home_config_projects_oauth_credentials_for_login_auth(tmp_path: Path) -> None:
    source_home = tmp_path / 'system-home'
    target_home = tmp_path / 'managed-home'
    source_settings = source_home / '.gemini' / 'settings.json'
    source_oauth = source_home / '.gemini' / 'oauth_creds.json'
    source_accounts = source_home / '.gemini' / 'google_accounts.json'
    source_settings.parent.mkdir(parents=True, exist_ok=True)
    source_settings.write_text(
        json.dumps(
            {
                'security': {
                    'auth': {
                        'selectedType': 'oauth-personal',
                    }
                },
                'theme': 'Default',
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )
    source_oauth.write_text(
        json.dumps({'refresh_token': 'system-refresh-token'}, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    source_accounts.write_text(
        json.dumps({'active': 'user@example.test'}, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )

    layout = materialize_gemini_home_config(target_home, source_home=source_home)

    payload = json.loads(layout.settings_path.read_text(encoding='utf-8'))
    assert payload['security']['auth']['selectedType'] == 'oauth-personal'
    assert json.loads((layout.gemini_dir / 'oauth_creds.json').read_text(encoding='utf-8'))['refresh_token'] == 'system-refresh-token'
    assert json.loads((layout.gemini_dir / 'google_accounts.json').read_text(encoding='utf-8'))['active'] == 'user@example.test'


def test_materialize_gemini_home_config_strips_oauth_selection_and_credentials_when_auth_not_inherited(tmp_path: Path) -> None:
    source_home = tmp_path / 'system-home'
    target_home = tmp_path / 'managed-home'
    source_settings = source_home / '.gemini' / 'settings.json'
    source_oauth = source_home / '.gemini' / 'oauth_creds.json'
    source_settings.parent.mkdir(parents=True, exist_ok=True)
    source_settings.write_text(
        json.dumps(
            {
                'security': {
                    'auth': {
                        'selectedType': 'oauth-personal',
                    }
                },
                'theme': 'Default',
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )
    source_oauth.write_text(
        json.dumps({'refresh_token': 'system-refresh-token'}, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    target_oauth = target_home / '.gemini' / 'oauth_creds.json'
    target_oauth.parent.mkdir(parents=True, exist_ok=True)
    target_oauth.write_text('{"refresh_token":"stale-token"}\n', encoding='utf-8')
    target_accounts = target_home / '.gemini' / 'google_accounts.json'
    target_accounts.write_text('{"active":"stale@example.test"}\n', encoding='utf-8')

    layout = materialize_gemini_home_config(
        target_home,
        profile=ProviderProfileSpec(inherit_auth=False, inherit_config=True),
        source_home=source_home,
    )

    payload = json.loads(layout.settings_path.read_text(encoding='utf-8'))
    assert payload['theme'] == 'Default'
    assert payload.get('security', {}).get('auth', {}).get('selectedType') is None
    assert not (layout.gemini_dir / 'oauth_creds.json').exists()
    assert not (layout.gemini_dir / 'google_accounts.json').exists()


def test_materialize_gemini_home_config_strips_api_auth_selection_when_api_not_inherited(tmp_path: Path) -> None:
    source_home = tmp_path / 'system-home'
    target_home = tmp_path / 'managed-home'
    source_settings = source_home / '.gemini' / 'settings.json'
    source_settings.parent.mkdir(parents=True, exist_ok=True)
    (source_home / '.gemini' / '.env').write_text('GEMINI_API_KEY=system-gemini-key\n', encoding='utf-8')
    source_settings.write_text(
        json.dumps(
            {
                'env': {'GEMINI_API_KEY': 'system-gemini-key'},
                'security': {
                    'auth': {
                        'selectedType': 'gemini-api-key',
                    }
                },
                'theme': 'Default',
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )

    layout = materialize_gemini_home_config(
        target_home,
        profile=ProviderProfileSpec(inherit_api=False, inherit_config=True),
        source_home=source_home,
    )

    payload = json.loads(layout.settings_path.read_text(encoding='utf-8'))
    assert payload['theme'] == 'Default'
    assert payload.get('env') is None
    assert payload.get('security', {}).get('auth', {}).get('selectedType') is None
    assert not (layout.gemini_dir / '.env').exists()


def test_materialize_gemini_home_config_preserves_runtime_hooks(tmp_path: Path) -> None:
    source_home = tmp_path / 'system-home'
    target_home = tmp_path / 'managed-home'
    source_settings = source_home / '.gemini' / 'settings.json'
    source_settings.parent.mkdir(parents=True, exist_ok=True)
    source_settings.write_text(
        json.dumps(
            {
                'env': {'GEMINI_API_KEY': 'system-gemini-key'},
                'theme': 'Atom One',
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )
    target_settings = target_home / '.gemini' / 'settings.json'
    target_settings.parent.mkdir(parents=True, exist_ok=True)
    target_settings.write_text(
        json.dumps(
            {
                'hooks': {
                    'AfterAgent': [
                        {'matcher': '*', 'hooks': [{'type': 'command', 'command': 'echo hook'}]},
                    ]
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )

    layout = materialize_gemini_home_config(target_home, source_home=source_home)

    payload = json.loads(layout.settings_path.read_text(encoding='utf-8'))
    assert payload['env']['GEMINI_API_KEY'] == 'system-gemini-key'
    assert payload['theme'] == 'Atom One'
    assert payload['hooks']['AfterAgent'][0]['hooks'][0]['command'] == 'echo hook'


def test_materialize_gemini_home_config_merges_trusted_folders(tmp_path: Path) -> None:
    source_home = tmp_path / 'system-home'
    target_home = tmp_path / 'managed-home'
    source_trust = source_home / '.gemini' / 'trustedFolders.json'
    source_trust.parent.mkdir(parents=True, exist_ok=True)
    source_trust.write_text(
        json.dumps({'/system/project': 'TRUST_FOLDER'}, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    target_trust = target_home / '.gemini' / 'trustedFolders.json'
    target_trust.parent.mkdir(parents=True, exist_ok=True)
    target_trust.write_text(
        json.dumps({'/managed/project': 'TRUST_FOLDER'}, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )

    layout = materialize_gemini_home_config(target_home, source_home=source_home)

    payload = json.loads(layout.trusted_folders_path.read_text(encoding='utf-8'))
    assert payload['/system/project'] == 'TRUST_FOLDER'
    assert payload['/managed/project'] == 'TRUST_FOLDER'


def test_materialize_gemini_home_config_writes_project_memory_bundle(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo'
    source_home = tmp_path / 'system-home'
    target_home = tmp_path / 'managed-home'
    source_gemini = source_home / '.gemini'
    source_gemini.mkdir(parents=True, exist_ok=True)
    (source_gemini / 'GEMINI.md').write_text('user gemini memory\n', encoding='utf-8')
    project_root.mkdir(parents=True, exist_ok=True)
    _write_project_memory(project_root, 'shared ask memory\n')
    (project_root / 'GEMINI.md').write_text('project gemini memory\n', encoding='utf-8')
    private_memory = project_root / '.ccb' / 'agents' / 'reviewer' / 'memory.md'
    private_memory.parent.mkdir(parents=True, exist_ok=True)
    private_memory.write_text('reviewer private memory\n', encoding='utf-8')

    layout = materialize_gemini_home_config(
        target_home,
        source_home=source_home,
        project_root=project_root,
        agent_name='reviewer',
        workspace_path=tmp_path / 'worktree',
    )

    text = (layout.gemini_dir / 'GEMINI.md').read_text(encoding='utf-8')
    settings = json.loads(layout.settings_path.read_text(encoding='utf-8'))
    assert '# CCB Managed Agent Memory' in text
    assert '## Provider User Memory' in text
    assert 'user gemini memory' in text
    assert '## CCB Shared Project Memory' in text
    assert 'shared ask memory' in text
    assert '## Provider-Native Project Memory' in text
    assert 'project gemini memory' in text
    assert '## Agent Private Memory' in text
    assert 'reviewer private memory' in text
    assert settings['contextFileName'] == 'GEMINI.md'


def test_materialize_gemini_home_config_respects_inherit_memory_flag(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo'
    source_home = tmp_path / 'system-home'
    target_home = tmp_path / 'managed-home'
    target_gemini = target_home / '.gemini'
    target_gemini.mkdir(parents=True, exist_ok=True)
    (target_gemini / 'GEMINI.md').write_text('stale managed memory\n', encoding='utf-8')
    (target_gemini / 'settings.json').write_text('{"contextFileName":"GEMINI.md"}\n', encoding='utf-8')

    layout = materialize_gemini_home_config(
        target_home,
        profile=ProviderProfileSpec(inherit_memory=False),
        source_home=source_home,
        project_root=project_root,
        agent_name='reviewer',
    )

    settings = json.loads(layout.settings_path.read_text(encoding='utf-8'))
    assert not (layout.gemini_dir / 'GEMINI.md').exists()
    assert 'contextFileName' not in settings


def test_materialize_gemini_home_config_skips_memory_without_project_context(tmp_path: Path) -> None:
    source_home = tmp_path / 'system-home'
    target_home = tmp_path / 'managed-home'
    source_gemini = source_home / '.gemini'
    target_gemini = target_home / '.gemini'
    source_gemini.mkdir(parents=True, exist_ok=True)
    target_gemini.mkdir(parents=True, exist_ok=True)
    (source_gemini / 'GEMINI.md').write_text('source-only memory\n', encoding='utf-8')

    layout = materialize_gemini_home_config(target_home, source_home=source_home)

    assert not (layout.gemini_dir / 'GEMINI.md').exists()

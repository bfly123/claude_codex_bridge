from __future__ import annotations

from pathlib import Path

from provider_backends.claude.home_layout import ClaudeHomeLayout, claude_layout_for_home

from .common import load_json, save_json, workspace_key


def install_claude_hooks(*, home_root: Path, command: str) -> Path:
    settings_path = claude_layout_for_home(Path(home_root).expanduser()).settings_path
    data = _load_settings(settings_path)
    hooks = _hooks_payload(data)
    groups = _event_groups(hooks, event_name='Stop')
    if not claude_event_has_command(groups, command):
        groups.append(_command_hook_group(command))
    hooks['Stop'] = groups
    return save_json(settings_path, data)


def trust_claude_workspace(*, home_root: Path, workspace_path: Path) -> Path:
    layout = claude_layout_for_home(Path(home_root).expanduser())
    data = _load_settings(layout.trust_path)
    key = workspace_key(workspace_path)
    record = data.get(key)
    if not isinstance(record, dict):
        record = {}
    record['hasTrustDialogAccepted'] = True
    data[key] = record
    projects = data.get('projects')
    if not isinstance(projects, dict):
        projects = {}
    project_record = projects.get(key)
    if not isinstance(project_record, dict):
        project_record = {}
    project_record['hasTrustDialogAccepted'] = True
    projects[key] = project_record
    data['projects'] = projects
    save_json(layout.trust_path, data)
    return layout.trust_path


def claude_hook_home_layout(home_root: Path) -> ClaudeHomeLayout:
    return claude_layout_for_home(Path(home_root).expanduser())


def claude_event_has_command(groups: list[object], command: str) -> bool:
    for group in groups:
        if not isinstance(group, dict):
            continue
        hooks = group.get('hooks')
        if not isinstance(hooks, list):
            continue
        for hook in hooks:
            if not isinstance(hook, dict):
                continue
            if str(hook.get('type') or '').strip().lower() != 'command':
                continue
            if str(hook.get('command') or '').strip() == command:
                return True
    return False


def _load_settings(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return load_json(path)


def _hooks_payload(data: dict[str, object]) -> dict[str, object]:
    hooks = data.get('hooks')
    if not isinstance(hooks, dict):
        hooks = {}
    data['hooks'] = hooks
    return hooks


def _event_groups(hooks: dict[str, object], *, event_name: str) -> list[object]:
    groups = hooks.get(event_name)
    if not isinstance(groups, list):
        return []
    return groups


def _command_hook_group(command: str) -> dict[str, list[dict[str, str]]]:
    return {
        'hooks': [
            {
                'type': 'command',
                'command': command,
            }
        ]
    }


__all__ = [
    'claude_event_has_command',
    'claude_hook_home_layout',
    'install_claude_hooks',
    'trust_claude_workspace',
]

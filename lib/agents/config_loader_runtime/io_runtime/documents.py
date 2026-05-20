from __future__ import annotations

import importlib
from pathlib import Path

from agents.models import normalize_agent_name, parse_layout_spec

from ..common import ConfigLoadResult, ConfigValidationError
from ..defaults import build_default_project_config
from ..parsing import validate_project_config
from ..paths import project_config_path, user_default_config_path

_ALLOWED_HYBRID_TOP_LEVEL_KEYS = {'agents'}
_HYBRID_HEADER_OWNED_AGENT_KEYS = {'provider', 'workspace_mode'}


def _build_compact_agent_record(provider: str, *, workspace_mode: str) -> dict[str, str]:
    return {
        'provider': provider,
        'target': '.',
        'workspace_mode': workspace_mode,
        'restore': 'auto',
        'permission': 'manual',
    }


def _strip_layout_comments(line: str) -> str:
    return line.split('#', 1)[0].split('//', 1)[0].strip()


def _normalize_compact_layout_text(text: str) -> str:
    return '\n'.join(
        cleaned
        for cleaned in (_strip_layout_comments(line) for line in text.splitlines())
        if cleaned
    ).strip()


def _raise_invalid_compact_token(path: Path, token: str) -> None:
    raise ConfigValidationError(
        f"{path}: invalid token {token!r}; expected 'agent_name:provider' or 'cmd'"
    )


def _consume_compact_leaf(
    leaf,
    *,
    path: Path,
    default_agents: list[str],
    agents: dict[str, dict[str, str]],
    cmd_enabled: bool,
) -> bool:
    token = leaf.name.strip()
    normalized_name = token.lower()
    if normalized_name == 'cmd':
        if leaf.provider is not None:
            raise ConfigValidationError(f"{path}: reserved token 'cmd' cannot declare a provider")
        if cmd_enabled:
            raise ConfigValidationError(f'{path}: compact config cannot define cmd more than once')
        return True
    if leaf.provider is None:
        _raise_invalid_compact_token(path, token)
    if normalized_name in agents:
        raise ConfigValidationError(f'{path}: duplicate agent name in compact config: {token}')
    default_agents.append(token)
    agents[normalized_name] = _build_compact_agent_record(
        leaf.provider,
        workspace_mode='git-worktree' if str(leaf.workspace_mode or '').strip() == 'worktree' else 'inplace',
    )
    return cmd_enabled


def _parse_compact_config_document(text: str, *, path: Path) -> dict[str, object]:
    layout_text = _normalize_compact_layout_text(text)
    if not layout_text:
        raise ConfigValidationError(f'{path}: config is empty')
    try:
        layout = parse_layout_spec(layout_text)
    except Exception as exc:
        raise ConfigValidationError(f'{path}: invalid compact layout: {exc}') from exc

    default_agents: list[str] = []
    agents: dict[str, dict[str, str]] = {}
    cmd_enabled = False
    for leaf in layout.iter_leaves():
        cmd_enabled = _consume_compact_leaf(
            leaf,
            path=path,
            default_agents=default_agents,
            agents=agents,
            cmd_enabled=cmd_enabled,
        )
    if not default_agents:
        raise ConfigValidationError(f'{path}: compact config must define at least one agent')

    return {
        'version': 2,
        'default_agents': default_agents,
        'agents': agents,
        'cmd_enabled': cmd_enabled,
        'layout': layout.render(),
    }


def _classify_config_document(text: str) -> tuple[str, str, str | None]:
    lines = text.splitlines()
    first_meaningful_kind: str | None = None
    first_rich_index: int | None = None
    for index, line in enumerate(lines):
        body = line.split('#', 1)[0].strip()
        if not body:
            continue
        kind = 'rich' if body.startswith('[') or '=' in body else 'compact'
        if first_meaningful_kind is None:
            first_meaningful_kind = kind
        if kind == 'rich':
            first_rich_index = index
            break

    if first_meaningful_kind == 'rich':
        return 'rich', text, None
    if first_meaningful_kind == 'compact' and first_rich_index is None:
        return 'compact', text, None
    if first_meaningful_kind == 'compact' and first_rich_index is not None:
        compact_text = '\n'.join(lines[:first_rich_index])
        overlay_text = '\n'.join(lines[first_rich_index:])
        return 'hybrid', compact_text, overlay_text
    return 'compact', text, None


def _import_optional_toml_reader():
    for module_name in ('tomllib', 'tomli', 'toml'):
        try:
            return importlib.import_module(module_name)
        except ModuleNotFoundError:
            continue
    return None


def _load_toml_reader(path: Path):
    reader = _import_optional_toml_reader()
    if reader is None:
        raise ConfigValidationError(
            f'{path}: rich TOML config requires Python 3.11+ or an installed tomli/toml parser'
        )
    loads = getattr(reader, 'loads', None)
    if not callable(loads):  # pragma: no cover - defensive guard for unexpected parser shims
        raise ConfigValidationError(f'{path}: TOML parser does not expose a supported loads() entrypoint')
    return loads


def _parse_toml_config_document(text: str, *, path: Path) -> dict[str, object]:
    try:
        document = _load_toml_reader(path)(text)
    except Exception as exc:
        if isinstance(exc, ConfigValidationError):
            raise
        raise ConfigValidationError(f'{path}: invalid TOML config: {exc}') from exc
    if not isinstance(document, dict):
        raise ConfigValidationError(f'{path}: TOML config must decode to a table/object')
    return dict(document)


def _parse_hybrid_config_document(text: str, overlay_text: str, *, path: Path) -> dict[str, object]:
    base_document = _parse_compact_config_document(text, path=path)
    overlay_document = _parse_toml_config_document(overlay_text, path=path)
    return _merge_hybrid_overlay(base_document, overlay_document, path=path)


def _merge_hybrid_overlay(
    base_document: dict[str, object],
    overlay_document: dict[str, object],
    *,
    path: Path,
) -> dict[str, object]:
    unknown_top = sorted(set(overlay_document) - _ALLOWED_HYBRID_TOP_LEVEL_KEYS)
    if unknown_top:
        raise ConfigValidationError(
            f'{path}: hybrid overlay contains unsupported top-level fields: {", ".join(unknown_top)}'
        )

    merged_agents = {
        str(name): dict(spec)
        for name, spec in dict(base_document.get('agents') or {}).items()
    }
    raw_overlay_agents = overlay_document.get('agents') or {}
    if not isinstance(raw_overlay_agents, dict):
        raise ConfigValidationError(f'{path}: hybrid overlay agents must be a table/object')

    for raw_name, raw_spec in raw_overlay_agents.items():
        if not isinstance(raw_name, str):
            raise ConfigValidationError(f'{path}: hybrid overlay agent names must be strings')
        normalized_name = normalize_agent_name(raw_name)
        if normalized_name not in merged_agents:
            raise ConfigValidationError(
                f'{path}: hybrid overlay cannot define agent {normalized_name!r} outside the compact layout'
            )
        if not isinstance(raw_spec, dict):
            raise ConfigValidationError(f'{path}: agents.{raw_name} must be a table/object')
        forbidden = sorted(set(raw_spec) & _HYBRID_HEADER_OWNED_AGENT_KEYS)
        if forbidden:
            raise ConfigValidationError(
                f'{path}: hybrid overlay cannot redefine compact-header fields for agents.{normalized_name}: '
                + ', '.join(forbidden)
            )
        merged_agents[normalized_name] = _deep_merge_dicts(merged_agents[normalized_name], dict(raw_spec))

    return {
        **dict(base_document),
        'agents': merged_agents,
    }


def _deep_merge_dicts(base: dict[str, object], overlay: dict[str, object]) -> dict[str, object]:
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dicts(dict(merged[key]), dict(value))
        else:
            merged[key] = value
    return merged


def _load_config_document(path: Path) -> dict[str, object]:
    text = path.read_text(encoding='utf-8')
    kind, primary_text, overlay_text = _classify_config_document(text)
    if kind == 'rich':
        return _parse_toml_config_document(primary_text, path=path)
    if kind == 'hybrid':
        assert overlay_text is not None
        return _parse_hybrid_config_document(primary_text, overlay_text, path=path)
    return _parse_compact_config_document(primary_text, path=path)


def load_project_config(project_root: Path) -> ConfigLoadResult:
    project_path = project_config_path(project_root)
    if project_path.exists():
        return ConfigLoadResult(
            config=validate_project_config(_load_config_document(project_path), source_path=project_path),
            source_path=project_path,
            used_default=False,
        )
    user_default_path = user_default_config_path()
    if user_default_path.exists():
        return ConfigLoadResult(
            config=validate_project_config(_load_config_document(user_default_path), source_path=user_default_path),
            source_path=user_default_path,
            used_default=True,
        )
    return ConfigLoadResult(
        config=build_default_project_config(),
        source_path=None,
        used_default=True,
    )


__all__ = ['load_project_config']

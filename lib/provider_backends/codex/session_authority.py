from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from provider_profiles.codex_home_config import codex_provider_authority_fingerprint

from .start_cmd import extract_resume_session_id

_MEMORY_PROJECTION_MARKER = 'codex-memory-projection.json'


def current_provider_authority_fingerprint(profile) -> str:
    return _normalized_fingerprint(codex_provider_authority_fingerprint(profile))


def current_memory_projection_fingerprint(runtime_dir: Path | None) -> str:
    if runtime_dir is None:
        return ''
    marker_path = Path(runtime_dir) / _MEMORY_PROJECTION_MARKER
    try:
        data = json.loads(marker_path.read_text(encoding='utf-8'))
    except Exception:
        return ''
    if not isinstance(data, dict):
        return ''
    return _normalized_fingerprint(data.get('sha256'))


def stored_provider_authority_fingerprint(data: Mapping[str, object]) -> str:
    return _normalized_fingerprint(data.get('codex_provider_authority_fingerprint'))


def stored_session_authority_fingerprint(data: Mapping[str, object]) -> str:
    return _normalized_fingerprint(data.get('codex_session_authority_fingerprint'))


def stored_memory_projection_fingerprint(data: Mapping[str, object]) -> str:
    return _normalized_fingerprint(data.get('codex_memory_projection_sha256'))


def resume_authority_matches(
    data: Mapping[str, object],
    *,
    profile=None,
    current_fingerprint: str | None = None,
    current_memory_fingerprint: str | None = None,
) -> bool:
    del current_memory_fingerprint
    current = (
        _normalized_fingerprint(current_fingerprint)
        if current_fingerprint is not None
        else current_provider_authority_fingerprint(profile)
    )
    if stored_provider_authority_fingerprint(data) != current:
        return False
    if not has_resume_candidate(data):
        return True
    stored_binding = stored_session_authority_fingerprint(data)
    if stored_binding:
        return stored_binding == current
    return not current


def remember_bound_session_authority(data: dict[str, object]) -> None:
    current = stored_provider_authority_fingerprint(data)
    if current:
        data['codex_session_authority_fingerprint'] = current
    else:
        data.pop('codex_session_authority_fingerprint', None)


def has_resume_candidate(data: Mapping[str, object]) -> bool:
    if str(data.get('codex_session_id') or '').strip():
        return True
    for key in ('codex_start_cmd', 'start_cmd'):
        if extract_resume_session_id(data.get(key)):
            return True
    return False


def _normalized_fingerprint(value: object) -> str:
    return str(value or '').strip()


__all__ = [
    'current_memory_projection_fingerprint',
    'current_provider_authority_fingerprint',
    'has_resume_candidate',
    'remember_bound_session_authority',
    'resume_authority_matches',
    'stored_memory_projection_fingerprint',
    'stored_provider_authority_fingerprint',
    'stored_session_authority_fingerprint',
]

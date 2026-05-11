from __future__ import annotations

from datetime import datetime, timezone
import errno
import json
import os
from pathlib import Path

from storage.atomic import atomic_write_json
from storage.paths import PathLayout

from .hashing import sha256_text
from .template import DEFAULT_PROJECT_MEMORY, TEMPLATE_VERSION
from .types import ProjectMemoryEnsureResult

_SEED_SCHEMA_VERSION = 1
_SEED_RECORD_TYPE = 'ccb_project_memory_seed'


def project_memory_path(project_root_or_layout) -> Path:
    layout = _layout(project_root_or_layout)
    return layout.project_memory_path


def seed_metadata_path(project_root_or_layout) -> Path:
    layout = _layout(project_root_or_layout)
    return layout.memory_seed_path


def ensure_project_memory(project_root_or_layout, *, now: str | None = None) -> ProjectMemoryEnsureResult:
    layout = _layout(project_root_or_layout)
    path = layout.project_memory_path
    seed_path = layout.memory_seed_path
    template = DEFAULT_PROJECT_MEMORY
    template_hash = sha256_text(template)
    created = False
    warning = ''

    try:
        created = _atomic_create_text(path, template)
    except OSError as exc:
        if exc.errno == errno.EEXIST:
            created = False
        else:
            return ProjectMemoryEnsureResult(
                path=path,
                seed_path=seed_path,
                created=False,
                seed_written=False,
                sha256='',
                warning=f'failed_to_create_project_memory: {exc}',
            )

    seed_written = False
    if created:
        seed_written, seed_warning = _write_seed_metadata(
            seed_path,
            memory_path=path,
            memory_hash=template_hash,
            now=now,
        )
        warning = seed_warning
        return ProjectMemoryEnsureResult(
            path=path,
            seed_path=seed_path,
            created=True,
            seed_written=seed_written,
            sha256=template_hash,
            warning=warning,
        )

    current_hash = _file_sha256(path)
    seed_written = False
    if current_hash == template_hash and not seed_path.is_file():
        seed_written, seed_warning = _write_seed_metadata(
            seed_path,
            memory_path=path,
            memory_hash=template_hash,
            now=now,
        )
        warning = seed_warning
    return ProjectMemoryEnsureResult(
        path=path,
        seed_path=seed_path,
        created=False,
        seed_written=seed_written,
        sha256=current_hash,
        warning=warning,
    )


def _atomic_create_text(path: Path, text: str) -> bool:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(str(target), flags, 0o644)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write(text)
    except Exception:
        try:
            os.unlink(target)
        except OSError:
            pass
        raise
    return True


def _write_seed_metadata(seed_path: Path, *, memory_path: Path, memory_hash: str, now: str | None) -> tuple[bool, str]:
    timestamp = now or datetime.now(timezone.utc).isoformat()
    payload = {
        'schema_version': _SEED_SCHEMA_VERSION,
        'record_type': _SEED_RECORD_TYPE,
        'template_version': TEMPLATE_VERSION,
        'memory_path': str(memory_path),
        'sha256': memory_hash,
        'created_at': timestamp,
    }
    try:
        atomic_write_json(seed_path, payload)
    except OSError as exc:
        return False, f'failed_to_write_project_memory_seed: {exc}'
    return True, ''


def _file_sha256(path: Path) -> str:
    try:
        return sha256_text(Path(path).read_text(encoding='utf-8'))
    except Exception:
        return ''


def read_seed_metadata(project_root_or_layout) -> dict[str, object]:
    path = seed_metadata_path(project_root_or_layout)
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _layout(project_root_or_layout) -> PathLayout:
    if isinstance(project_root_or_layout, PathLayout):
        return project_root_or_layout
    return PathLayout(Path(project_root_or_layout))


__all__ = [
    'ensure_project_memory',
    'project_memory_path',
    'read_seed_metadata',
    'seed_metadata_path',
]

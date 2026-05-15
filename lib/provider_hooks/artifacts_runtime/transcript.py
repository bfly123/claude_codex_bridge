from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from provider_core.protocol import ANY_REQ_ID_PATTERN, REQ_ID_BOUNDARY_PATTERN

REQ_ID_RE = re.compile(rf'CCB_REQ_ID:\s*({ANY_REQ_ID_PATTERN}){REQ_ID_BOUNDARY_PATTERN}', re.IGNORECASE)
OUTER_REQ_ID_RE = re.compile(rf'^\s*CCB_REQ_ID:\s*({ANY_REQ_ID_PATTERN}){REQ_ID_BOUNDARY_PATTERN}', re.IGNORECASE)


def extract_req_id(text: str) -> str | None:
    match = REQ_ID_RE.search(str(text or ''))
    if not match:
        return None
    return str(match.group(1) or '').strip() or None


def extract_outer_req_id(text: str) -> str | None:
    match = OUTER_REQ_ID_RE.search(str(text or ''))
    if not match:
        return None
    return str(match.group(1) or '').strip() or None


def latest_req_id_from_transcript(transcript_path: str | Path | None) -> str | None:
    raw = str(transcript_path or '').strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    if not path.exists():
        return None
    try:
        content = path.read_text(encoding='utf-8', errors='replace')
    except Exception:
        return None
    user_req_id = latest_user_req_id_from_transcript_text(content)
    if user_req_id:
        return user_req_id
    prompt_req_id = latest_last_prompt_req_id_from_transcript_text(content)
    if prompt_req_id:
        return prompt_req_id
    return extract_outer_req_id(content)


def latest_user_req_id_from_transcript_text(content: str) -> str | None:
    latest: str | None = None
    for line in str(content or '').splitlines():
        try:
            record = json.loads(line)
        except Exception:
            continue
        text = _user_message_text(record)
        if text is None:
            continue
        req_id = extract_outer_req_id(text)
        if req_id:
            latest = req_id
    return latest


def latest_last_prompt_req_id_from_transcript_text(content: str) -> str | None:
    latest: str | None = None
    for line in str(content or '').splitlines():
        try:
            record = json.loads(line)
        except Exception:
            continue
        if not isinstance(record, dict):
            continue
        if str(record.get('type') or '').strip().lower() != 'last-prompt':
            continue
        req_id = extract_outer_req_id(str(record.get('lastPrompt') or ''))
        if req_id:
            latest = req_id
    return latest


def _user_message_text(record: Any) -> str | None:
    if not isinstance(record, dict):
        return None
    message = record.get('message')
    if not isinstance(message, dict):
        return None
    if str(record.get('type') or '').strip().lower() != 'user':
        return None
    role = str(message.get('role') or '').strip().lower()
    if role and role != 'user':
        return None
    return _content_text(message.get('content'))


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content or '')
    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict):
            text = item.get('text')
            if text is not None:
                parts.append(str(text))
    return '\n'.join(parts)


__all__ = [
    'extract_outer_req_id',
    'extract_req_id',
    'latest_last_prompt_req_id_from_transcript_text',
    'latest_req_id_from_transcript',
    'latest_user_req_id_from_transcript_text',
]

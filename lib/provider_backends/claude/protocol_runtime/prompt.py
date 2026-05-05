from __future__ import annotations

import os

from provider_core.protocol import BEGIN_PREFIX, DONE_PREFIX, REQ_ID_PREFIX


def wrap_claude_prompt(message: str, req_id: str) -> str:
    body = _build_prompt_body(message)
    return (
        f'{REQ_ID_PREFIX} {req_id}\n\n'
        f'{body}'
        'Reply using exactly this format:\n'
        f'{BEGIN_PREFIX} {req_id}\n'
        '<reply>\n'
        f'{DONE_PREFIX} {req_id}\n'
    )


def wrap_claude_turn_prompt(message: str, req_id: str) -> str:
    body = _build_prompt_body(message)
    return f'{REQ_ID_PREFIX} {req_id}\n\n{body}'


def _build_prompt_body(message: str) -> str:
    rendered = (message or '').rstrip()
    extras = _prompt_extras(rendered)
    if extras:
        return f'{rendered}\n\n{extras}\n\n'
    return f'{rendered}\n\n'


def _prompt_extras(message: str) -> str:
    extra_lines: list[str] = []
    if _wants_markdown_table(message):
        extra_lines.append(
            'If asked for a Markdown table, output only pipe-and-dash Markdown table syntax (no box-drawing characters).'
        )
    lang_hint = _language_hint()
    if lang_hint:
        extra_lines.append(lang_hint)
    return '\n'.join(extra_lines).strip()


def _wants_markdown_table(message: str) -> bool:
    msg = (message or '').lower()
    if 'markdown' not in msg:
        return False
    return ('table' in msg) or ('表格' in message)


def _language_hint() -> str:
    lang = (os.environ.get('CCB_REPLY_LANG') or os.environ.get('CCB_LANG') or '').strip().lower()
    if lang in {'zh', 'cn', 'chinese'}:
        return 'Reply in Chinese.'
    if lang in {'en', 'english'}:
        return 'Reply in English.'
    return ''


__all__ = ['wrap_claude_prompt', 'wrap_claude_turn_prompt']

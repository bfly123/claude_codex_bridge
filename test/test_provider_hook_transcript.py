from __future__ import annotations

import json
from pathlib import Path

from provider_hooks.artifacts_runtime.transcript import (
    latest_last_prompt_req_id_from_transcript_text,
    latest_req_id_from_transcript,
    latest_user_req_id_from_transcript_text,
)


def _jsonl(*records: dict) -> str:
    return "\n".join(json.dumps(record) for record in records) + "\n"


def test_latest_user_req_id_uses_outer_marker_when_body_contains_req_ids() -> None:
    content = _jsonl(
        {
            "type": "user",
            "message": {
                "role": "user",
                "content": (
                    "CCB_REQ_ID: job_current123\n\n"
                    "Review this transcript:\n"
                    "CCB_REQ_ID: job_old456\n\n"
                    "```text\n"
                    "CCB_REQ_ID: job_code789\n"
                    "```\n"
                ),
            },
        }
    )

    assert latest_user_req_id_from_transcript_text(content) == "job_current123"


def test_latest_user_req_id_ignores_body_only_req_id_mentions() -> None:
    content = _jsonl(
        {
            "type": "user",
            "message": {
                "role": "user",
                "content": "Please inspect why CCB_REQ_ID: job_old456 did not return.",
            },
        }
    )

    assert latest_user_req_id_from_transcript_text(content) is None


def test_latest_user_req_id_ignores_tool_result_req_id_after_outer_marker() -> None:
    content = _jsonl(
        {
            "type": "user",
            "message": {
                "role": "user",
                "content": "CCB_REQ_ID: job_current123\n\nRun the check.",
            },
        },
        {
            "type": "user",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "content": "Command output mentioned CCB_REQ_ID: job_tool999",
                    }
                ],
            },
        },
    )

    assert latest_user_req_id_from_transcript_text(content) == "job_current123"


def test_latest_req_id_prefers_latest_outer_user_marker(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        _jsonl(
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": "CCB_REQ_ID: job_first111\n\nInitial request.",
                },
            },
            {
                "type": "assistant",
                "message": {"role": "assistant", "content": "Working."},
            },
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": (
                        "CCB_REQ_ID: job_second222\n\n"
                        "Forwarded text contains CCB_REQ_ID: job_old333."
                    ),
                },
            },
        ),
        encoding="utf-8",
    )

    assert latest_req_id_from_transcript(transcript) == "job_second222"


def test_last_prompt_req_id_uses_outer_marker_not_body_marker() -> None:
    content = _jsonl(
        {
            "type": "last-prompt",
            "lastPrompt": (
                "CCB_REQ_ID: job_prompt123\n\n"
                "The request body includes CCB_REQ_ID: job_body456."
            ),
        }
    )

    assert latest_last_prompt_req_id_from_transcript_text(content) == "job_prompt123"

from __future__ import annotations

from ccbd.api_models import DeliveryScope, JobEvent, JobRecord, JobStatus, MessageEnvelope, SubmissionRecord, TargetKind
from storage.jsonl_store import JsonlStore
from storage.paths import PathLayout

SCHEMA_VERSION = 2


class JobStore:
    def __init__(self, layout: PathLayout, store: JsonlStore | None = None) -> None:
        self._layout = layout
        self._store = store or JsonlStore()

    def append(self, record: JobRecord) -> None:
        self._store.append(
            self._layout.target_jobs_path(record.target_kind, record.target_name),
            record,
            serializer=lambda value: value.to_record(),
        )

    def list_agent(self, agent_name: str) -> list[JobRecord]:
        return self.list_target(TargetKind.AGENT, agent_name)

    def list_target(self, target_kind: TargetKind | str, target_name: str) -> list[JobRecord]:
        return self._store.read_all(
            self._layout.target_jobs_path(target_kind, target_name),
            loader=_job_record_from_record,
        )

    def get_latest(self, agent_name: str, job_id: str) -> JobRecord | None:
        return self.get_latest_target(TargetKind.AGENT, agent_name, job_id)

    def get_latest_target(self, target_kind: TargetKind | str, target_name: str, job_id: str) -> JobRecord | None:
        return self._store.find_last(
            self._layout.target_jobs_path(target_kind, target_name),
            predicate=lambda payload: str(payload.get('job_id') or '') == job_id,
            loader=_job_record_from_record,
        )


class JobEventStore:
    def __init__(self, layout: PathLayout, store: JsonlStore | None = None) -> None:
        self._layout = layout
        self._store = store or JsonlStore()

    def append(self, event: JobEvent) -> None:
        self._store.append(
            self._layout.target_events_path(event.target_kind, event.target_name),
            event,
            serializer=lambda value: value.to_record(),
        )

    def read_since(self, agent_name: str, start_line: int = 0) -> tuple[int, list[JobEvent]]:
        return self.read_since_target(TargetKind.AGENT, agent_name, start_line)

    def read_since_target(
        self,
        target_kind: TargetKind | str,
        target_name: str,
        start_line: int = 0,
    ) -> tuple[int, list[JobEvent]]:
        line_no, rows = self._store.read_since(
            self._layout.target_events_path(target_kind, target_name),
            start_line,
        )
        events: list[JobEvent] = []
        for row in rows:
            if row.get('record_type') != 'job_event':
                continue
            events.append(_job_event_from_record(row))
        return line_no, events


class SubmissionStore:
    def __init__(self, layout: PathLayout, store: JsonlStore | None = None) -> None:
        self._layout = layout
        self._store = store or JsonlStore()

    def append(self, record: SubmissionRecord) -> None:
        self._store.append(self._layout.ccbd_submissions_path, record, serializer=lambda value: value.to_record())

    def list_all(self) -> list[SubmissionRecord]:
        return self._store.read_all(self._layout.ccbd_submissions_path, loader=_submission_record_from_record)

    def get_latest(self, submission_id: str) -> SubmissionRecord | None:
        return self._store.find_last(
            self._layout.ccbd_submissions_path,
            predicate=lambda payload: str(payload.get('submission_id') or '') == submission_id,
            loader=_submission_record_from_record,
        )


def _validate_record(record: dict, expected_type: str) -> None:
    if record.get('schema_version') != SCHEMA_VERSION:
        raise ValueError(f'schema_version must be {SCHEMA_VERSION}')
    if record.get('record_type') != expected_type:
        raise ValueError(f'record_type must be {expected_type!r}')


def _message_envelope_from_record(record: dict) -> MessageEnvelope:
    return MessageEnvelope(
        project_id=record['project_id'],
        to_agent=record['to_agent'],
        from_actor=record['from_actor'],
        body=record['body'],
        task_id=record.get('task_id'),
        reply_to=record.get('reply_to'),
        message_type=record['message_type'],
        delivery_scope=DeliveryScope(record['delivery_scope']),
        silence_on_success=bool(record.get('silence_on_success', False)),
        route_options=dict(record.get('route_options') or {}),
    )


def _job_record_from_record(record: dict) -> JobRecord:
    _validate_record(record, 'job_record')
    return JobRecord(
        job_id=record['job_id'],
        submission_id=record.get('submission_id'),
        agent_name=record.get('agent_name', ''),
        provider=record['provider'],
        request=_message_envelope_from_record(record['request']),
        status=JobStatus(record['status']),
        terminal_decision=record.get('terminal_decision'),
        cancel_requested_at=record.get('cancel_requested_at'),
        created_at=record['created_at'],
        updated_at=record['updated_at'],
        workspace_path=record.get('workspace_path'),
        target_kind=record.get('target_kind', TargetKind.AGENT.value),
        target_name=record.get('target_name', record.get('agent_name', '')),
        provider_instance=record.get('provider_instance'),
        provider_options=dict(record.get('provider_options') or {}),
    )


def _submission_record_from_record(record: dict) -> SubmissionRecord:
    _validate_record(record, 'submission_record')
    return SubmissionRecord(
        submission_id=record['submission_id'],
        project_id=record['project_id'],
        from_actor=record['from_actor'],
        target_scope=record['target_scope'],
        task_id=record.get('task_id'),
        job_ids=list(record.get('job_ids', [])),
        created_at=record.get('created_at', ''),
        updated_at=record.get('updated_at', ''),
    )


def _job_event_from_record(record: dict) -> JobEvent:
    _validate_record(record, 'job_event')
    return JobEvent(
        event_id=record['event_id'],
        job_id=record['job_id'],
        agent_name=record.get('agent_name', ''),
        target_kind=record.get('target_kind', TargetKind.AGENT.value),
        target_name=record.get('target_name', record.get('agent_name', '')),
        type=record['type'],
        payload=dict(record.get('payload', {})),
        timestamp=record['timestamp'],
    )

from __future__ import annotations

import json
from pathlib import Path

from ccbd.api_models import DeliveryScope, JobEvent, JobRecord, JobStatus, MessageEnvelope, SubmissionRecord, TargetKind
from jobs.store import JobEventStore, JobStore, SubmissionStore
from storage.paths import PathLayout


def _envelope() -> MessageEnvelope:
    return MessageEnvelope(
        project_id='proj-1',
        to_agent='agent1',
        from_actor='user',
        body='hello',
        task_id='task-1',
        reply_to=None,
        message_type='ask',
        delivery_scope=DeliveryScope.SINGLE,
    )


def test_job_store_tracks_latest_job_record(tmp_path: Path) -> None:
    layout = PathLayout(tmp_path / 'repo')
    store = JobStore(layout)
    store.append(
        JobRecord(
            job_id='job-1',
            submission_id=None,
            agent_name='agent1',
            provider='codex',
            request=_envelope(),
            status=JobStatus.QUEUED,
            terminal_decision=None,
            cancel_requested_at=None,
            created_at='2026-03-18T00:00:00Z',
            updated_at='2026-03-18T00:00:00Z',
        )
    )
    store.append(
        JobRecord(
            job_id='job-1',
            submission_id=None,
            agent_name='agent1',
            provider='codex',
            request=_envelope(),
            status=JobStatus.RUNNING,
            terminal_decision=None,
            cancel_requested_at=None,
            created_at='2026-03-18T00:00:00Z',
            updated_at='2026-03-18T00:00:01Z',
        )
    )

    latest = store.get_latest('agent1', 'job-1')
    assert latest is not None
    assert latest.status is JobStatus.RUNNING


def test_event_and_submission_stores_roundtrip(tmp_path: Path) -> None:
    layout = PathLayout(tmp_path / 'repo')
    event_store = JobEventStore(layout)
    submission_store = SubmissionStore(layout)

    event_store.append(
        JobEvent(
            event_id='evt-1',
            job_id='job-1',
            agent_name='agent1',
            type='job_started',
            payload={'status': 'running'},
            timestamp='2026-03-18T00:00:00Z',
        )
    )
    line_no, events = event_store.read_since('agent1', 0)
    assert line_no == 1
    assert events[0].type == 'job_started'

    submission_store.append(
        SubmissionRecord(
            submission_id='sub-1',
            project_id='proj-1',
            from_actor='system',
            target_scope='all',
            task_id='task-1',
            job_ids=['job-1', 'job-2'],
            created_at='2026-03-18T00:00:00Z',
            updated_at='2026-03-18T00:00:01Z',
        )
    )
    latest = submission_store.get_latest('sub-1')
    assert latest is not None
    assert latest.job_ids == ['job-1', 'job-2']


def test_event_store_skips_provider_diagnostics_in_event_log(tmp_path: Path) -> None:
    layout = PathLayout(tmp_path / 'repo')
    event_store = JobEventStore(layout)
    event_store.append(
        JobEvent(
            event_id='evt-1',
            job_id='job-1',
            agent_name='agent1',
            type='job_started',
            payload={'status': 'running'},
            timestamp='2026-03-18T00:00:00Z',
        )
    )
    events_path = layout.agent_events_path('agent1')
    with events_path.open('a', encoding='utf-8') as handle:
        handle.write(
            json.dumps(
                {
                    'record_type': 'agent_event',
                    'event_type': 'codex_memory_projection_ok',
                    'provider': 'codex',
                    'agent_name': 'agent1',
                },
                ensure_ascii=False,
            )
            + '\n'
        )
    event_store.append(
        JobEvent(
            event_id='evt-2',
            job_id='job-1',
            agent_name='agent1',
            type='job_completed',
            payload={'status': 'completed'},
            timestamp='2026-03-18T00:00:01Z',
        )
    )

    line_no, events = event_store.read_since('agent1', 0)
    assert line_no == 3
    assert [event.event_id for event in events] == ['evt-1', 'evt-2']


def test_submission_store_preserves_user_sender(tmp_path: Path) -> None:
    layout = PathLayout(tmp_path / 'repo')
    submission_store = SubmissionStore(layout)

    submission_store.append(
        SubmissionRecord(
            submission_id='sub-user',
            project_id='proj-1',
            from_actor='USER',
            target_scope='single',
            task_id='task-user',
            job_ids=['job-9'],
            created_at='2026-03-18T00:00:00Z',
            updated_at='2026-03-18T00:00:01Z',
        )
    )

    latest = submission_store.get_latest('sub-user')
    assert latest is not None
    assert latest.from_actor == 'user'


def test_job_store_supports_explicit_target_lookup(tmp_path: Path) -> None:
    layout = PathLayout(tmp_path / 'repo')
    store = JobStore(layout)
    store.append(
        JobRecord(
            job_id='job-agent-1',
            submission_id=None,
            agent_name='agent1',
            provider='codex',
            provider_options={'no_wrap': True},
            target_kind=TargetKind.AGENT,
            target_name='agent1',
            request=_envelope(),
            status=JobStatus.ACCEPTED,
            terminal_decision=None,
            cancel_requested_at=None,
            created_at='2026-03-18T00:00:00Z',
            updated_at='2026-03-18T00:00:00Z',
        )
    )

    latest = store.get_latest_target(TargetKind.AGENT, 'agent1', 'job-agent-1')
    assert latest is not None
    assert latest.target_kind is TargetKind.AGENT
    assert latest.target_name == 'agent1'
    assert latest.provider_options == {'no_wrap': True}


def test_job_store_roundtrips_silence_on_success_request_flag(tmp_path: Path) -> None:
    layout = PathLayout(tmp_path / 'repo')
    store = JobStore(layout)
    envelope = MessageEnvelope(
        project_id='proj-1',
        to_agent='agent1',
        from_actor='user',
        body='hello',
        task_id='task-1',
        reply_to=None,
        message_type='ask',
        delivery_scope=DeliveryScope.SINGLE,
        silence_on_success=True,
    )
    store.append(
        JobRecord(
            job_id='job-silent-1',
            submission_id=None,
            agent_name='agent1',
            provider='codex',
            request=envelope,
            status=JobStatus.ACCEPTED,
            terminal_decision=None,
            cancel_requested_at=None,
            created_at='2026-03-18T00:00:00Z',
            updated_at='2026-03-18T00:00:00Z',
        )
    )

    latest = store.get_latest('agent1', 'job-silent-1')
    assert latest is not None
    assert latest.request.silence_on_success is True


def test_job_store_roundtrips_request_route_options(tmp_path: Path) -> None:
    layout = PathLayout(tmp_path / 'repo-job-store-route-options')
    store = JobStore(layout)
    envelope = MessageEnvelope(
        project_id='project-1',
        to_agent='agent1',
        from_actor='agent2',
        body='hello',
        task_id=None,
        reply_to=None,
        message_type='ask',
        delivery_scope=DeliveryScope.SINGLE,
        route_options={'mode': 'callback', 'callback_edge_id': 'cb_1'},
    )
    record = JobRecord(
        job_id='job_route_options',
        submission_id=None,
        agent_name='agent1',
        provider='codex',
        request=envelope,
        status=JobStatus.ACCEPTED,
        terminal_decision=None,
        cancel_requested_at=None,
        created_at='2026-03-30T00:00:00Z',
        updated_at='2026-03-30T00:00:00Z',
    )

    store.append(record)

    latest = store.get_latest('agent1', 'job_route_options')
    assert latest is not None
    assert latest.request.route_options == {'mode': 'callback', 'callback_edge_id': 'cb_1'}


def test_event_store_supports_explicit_target_lookup(tmp_path: Path) -> None:
    layout = PathLayout(tmp_path / 'repo')
    event_store = JobEventStore(layout)
    event_store.append(
        JobEvent(
            event_id='evt-agent-1',
            job_id='job-agent-1',
            agent_name='agent1',
            target_kind=TargetKind.AGENT,
            target_name='agent1',
            type='job_started',
            payload={'status': 'running'},
            timestamp='2026-03-18T00:00:00Z',
        )
    )

    line_no, events = event_store.read_since_target(TargetKind.AGENT, 'agent1', 0)
    assert line_no == 1
    assert events[0].target_kind is TargetKind.AGENT
    assert events[0].target_name == 'agent1'

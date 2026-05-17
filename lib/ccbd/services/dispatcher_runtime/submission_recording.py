from __future__ import annotations

from ccbd.api_models import AcceptedJobReceipt, JobRecord, JobStatus, SubmissionRecord, SubmitReceipt, TargetKind

from .callbacks import register_callback_edge
from .records import append_event, append_job
from .runtime_state import sync_runtime
from .submission_models import _JobDraft, _SubmissionPlan


def _pending_status(dispatcher, *, target_kind: TargetKind, target_name: str) -> JobStatus:
    if dispatcher._state.has_outstanding_for(target_kind, target_name):
        return JobStatus.QUEUED
    return JobStatus.ACCEPTED


def _receipt_for_job(job: JobRecord, *, status: JobStatus, accepted_at: str) -> AcceptedJobReceipt:
    return AcceptedJobReceipt(
        job_id=job.job_id,
        agent_name=job.agent_name,
        target_kind=job.target_kind,
        target_name=job.target_name,
        provider_instance=job.provider_instance,
        status=status,
        accepted_at=accepted_at,
    )


def _enqueue_submitted_job(
    dispatcher,
    job: JobRecord,
    *,
    status: JobStatus,
    accepted_at: str,
) -> AcceptedJobReceipt:
    append_job(dispatcher, job)
    append_event(
        dispatcher,
        job,
        'job_accepted' if status is JobStatus.ACCEPTED else 'job_queued',
        {'status': status.value},
        timestamp=accepted_at,
    )
    dispatcher._state.enqueue_for(job.target_kind, job.target_name, job.job_id)
    if job.target_kind is TargetKind.AGENT:
        sync_runtime(dispatcher, job.agent_name)
    return _receipt_for_job(job, status=status, accepted_at=accepted_at)


def _build_job_record(
    dispatcher,
    draft: _JobDraft,
    *,
    job_id: str,
    submission_id: str | None,
    accepted_at: str,
) -> tuple[JobRecord, JobStatus]:
    status = _pending_status(
        dispatcher,
        target_kind=draft.target_kind,
        target_name=draft.target_name,
    )
    return (
        JobRecord(
            job_id=job_id,
            submission_id=submission_id,
            agent_name=draft.agent_name,
            provider=draft.provider,
            provider_instance=draft.provider_instance,
            provider_options=draft.provider_options,
            workspace_path=draft.workspace_path,
            target_kind=draft.target_kind,
            target_name=draft.target_name,
            request=draft.request,
            status=status,
            terminal_decision=None,
            cancel_requested_at=None,
            created_at=accepted_at,
            updated_at=accepted_at,
        ),
        status,
    )


def _submit_plan(dispatcher, plan: _SubmissionPlan, *, accepted_at: str) -> tuple[SubmitReceipt, str | None]:
    receipts: list[AcceptedJobReceipt] = []
    job_ids: list[str] = []
    jobs: list[JobRecord] = []
    for draft in plan.drafts:
        job_id = dispatcher._new_id('job')
        job, status = _build_job_record(
            dispatcher,
            draft,
            job_id=job_id,
            submission_id=plan.submission_id,
            accepted_at=accepted_at,
        )
        receipts.append(_enqueue_submitted_job(dispatcher, job, status=status, accepted_at=accepted_at))
        job_ids.append(job_id)
        jobs.append(job)

    if plan.submission_id is not None:
        dispatcher._submission_store.append(
            SubmissionRecord(
                submission_id=plan.submission_id,
                project_id=plan.project_id,
                from_actor=plan.from_actor,
                target_scope=plan.target_scope or 'all',
                task_id=plan.task_id,
                job_ids=job_ids,
                created_at=accepted_at,
                updated_at=accepted_at,
            )
        )
    message_id: str | None = None
    if dispatcher._message_bureau is not None:
        message_id = dispatcher._message_bureau.record_submission(
            plan.request,
            tuple(jobs),
            submission_id=plan.submission_id,
            accepted_at=accepted_at,
            origin_message_id=plan.origin_message_id,
        )
        if message_id is not None:
            register_callback_edge(
                dispatcher,
                request=plan.request,
                jobs=tuple(jobs),
                message_id=message_id,
                accepted_at=accepted_at,
            )

    return (
        SubmitReceipt(
            accepted_at=accepted_at,
            jobs=tuple(receipts),
            submission_id=plan.submission_id,
        ),
        message_id,
    )


def _append_submission_job(dispatcher, submission_id: str | None, *, job_id: str, updated_at: str) -> None:
    if not submission_id:
        return
    current = dispatcher._submission_store.get_latest(submission_id)
    if current is None:
        return
    job_ids = list(current.job_ids)
    if job_id not in job_ids:
        job_ids.append(job_id)
    dispatcher._submission_store.append(
        SubmissionRecord(
            submission_id=current.submission_id,
            project_id=current.project_id,
            from_actor=current.from_actor,
            target_scope=current.target_scope,
            task_id=current.task_id,
            job_ids=job_ids,
            created_at=current.created_at,
            updated_at=updated_at,
        )
    )


__all__ = [
    '_append_submission_job',
    '_build_job_record',
    '_enqueue_submitted_job',
    '_submit_plan',
]

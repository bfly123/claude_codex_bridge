from __future__ import annotations

from collections.abc import Callable
from typing import TextIO

from cli.services.watch import WatchEventBatch
from cli.services.watch_fallback import load_persisted_terminal_watch_payload


def watch_ask_job(
    context,
    job_id: str,
    out: TextIO,
    *,
    timeout: float | None,
    emit_output: bool,
    connect_mounted_daemon_fn: Callable,
    reconnect_error_classes: tuple[type[BaseException], ...],
    monotonic_fn: Callable[[], float],
    sleep_fn: Callable[[float], None],
    poll_interval_seconds_fn: Callable[[], float],
    timeout_seconds_fn: Callable[[], float],
    render_watch_batch_fn: Callable[[WatchEventBatch], tuple[str, ...]],
    write_lines_fn: Callable[[TextIO, tuple[str, ...]], None],
) -> WatchEventBatch:
    cursor = 0
    deadline = _watch_deadline(timeout, timeout_seconds_fn=timeout_seconds_fn, monotonic_fn=monotonic_fn)
    poll_interval = poll_interval_seconds_fn()
    try:
        handle = connect_mounted_daemon_fn(context, allow_restart_stale=False)
    except reconnect_error_classes:
        fallback = _persisted_terminal_batch(context, job_id, cursor=cursor)
        if fallback is not None:
            if emit_output:
                write_lines_fn(out, render_watch_batch_fn(fallback))
            return fallback
        raise
    assert handle.client is not None
    client = handle.client

    while True:
        try:
            payload = client.watch(job_id, cursor=cursor)
        except reconnect_error_classes:
            fallback = _persisted_terminal_batch(context, job_id, cursor=cursor)
            if fallback is not None:
                if emit_output:
                    write_lines_fn(out, render_watch_batch_fn(fallback))
                return fallback
            client = _connect_client(
                context,
                job_id=job_id,
                cursor=cursor,
                connect_mounted_daemon_fn=connect_mounted_daemon_fn,
                reconnect_error_classes=reconnect_error_classes,
                monotonic_fn=monotonic_fn,
                sleep_fn=sleep_fn,
                deadline=deadline,
                poll_interval=poll_interval,
            )
            if client is None:
                fallback = _persisted_terminal_batch(context, job_id, cursor=cursor)
                if fallback is not None:
                    if emit_output:
                        write_lines_fn(out, render_watch_batch_fn(fallback))
                    return fallback
                raise RuntimeError(f'watch timed out for {job_id}')
            sleep_fn(poll_interval)
            continue

        batch = _watch_batch_from_payload(job_id, payload)
        if emit_output and batch.events:
            write_lines_fn(out, render_watch_batch_fn(batch))
        cursor = batch.cursor
        if batch.terminal:
            if emit_output and not batch.events:
                write_lines_fn(out, render_watch_batch_fn(batch))
            return batch
        if _deadline_exceeded(deadline, monotonic_fn=monotonic_fn):
            fallback = _persisted_terminal_batch(context, job_id, cursor=cursor)
            if fallback is not None:
                if emit_output:
                    write_lines_fn(out, render_watch_batch_fn(fallback))
                return fallback
            raise RuntimeError(f'watch timed out for {job_id}')
        sleep_fn(poll_interval)


def _watch_deadline(
    timeout: float | None,
    *,
    timeout_seconds_fn: Callable[[], float],
    monotonic_fn: Callable[[], float],
) -> float | None:
    timeout_s = timeout_seconds_fn() if timeout is None else float(timeout)
    if timeout_s <= 0:
        return None
    return monotonic_fn() + timeout_s


def _deadline_exceeded(deadline: float | None, *, monotonic_fn: Callable[[], float]) -> bool:
    return deadline is not None and monotonic_fn() > deadline


def _watch_batch_from_payload(job_id: str, payload: dict) -> WatchEventBatch:
    return WatchEventBatch(
        target=job_id,
        job_id=payload['job_id'],
        agent_name=payload.get('agent_name') or '',
        target_kind=payload.get('target_kind'),
        target_name=payload.get('target_name') or payload.get('agent_name') or '',
        provider=payload.get('provider'),
        provider_instance=payload.get('provider_instance'),
        cursor=int(payload['cursor']),
        generation=int(payload['generation']) if payload.get('generation') is not None else None,
        terminal=bool(payload['terminal']),
        status=payload.get('status'),
        reply=payload.get('reply') or '',
        events=tuple(payload.get('events', ())),
    )


def _connect_client(
    context,
    *,
    job_id: str,
    cursor: int,
    connect_mounted_daemon_fn: Callable,
    reconnect_error_classes: tuple[type[BaseException], ...],
    monotonic_fn: Callable[[], float],
    sleep_fn: Callable[[float], None],
    deadline: float | None,
    poll_interval: float,
):
    while True:
        if _deadline_exceeded(deadline, monotonic_fn=monotonic_fn):
            return None
        try:
            handle = connect_mounted_daemon_fn(context, allow_restart_stale=False)
        except reconnect_error_classes:
            fallback = _persisted_terminal_batch(context, job_id, cursor=cursor)
            if fallback is not None:
                return None
            sleep_fn(poll_interval)
            continue
        assert handle.client is not None
        return handle.client


def _persisted_terminal_batch(context, job_id: str, *, cursor: int) -> WatchEventBatch | None:
    payload = load_persisted_terminal_watch_payload(context, job_id, cursor=cursor)
    if payload is None:
        return None
    return _watch_batch_from_payload(job_id, payload)


__all__ = ['watch_ask_job']

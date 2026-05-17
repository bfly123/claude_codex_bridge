from __future__ import annotations

from time import monotonic

from ccbd.api_models import DeliveryScope, MessageEnvelope


def build_submit_handler(dispatcher):
    def handle(payload: dict) -> dict:
        started = monotonic()
        envelope = MessageEnvelope(
            project_id=payload['project_id'],
            to_agent=payload['to_agent'],
            from_actor=payload['from_actor'],
            body=payload['body'],
            task_id=payload.get('task_id'),
            reply_to=payload.get('reply_to'),
            message_type=payload.get('message_type', 'ask'),
            delivery_scope=DeliveryScope(payload.get('delivery_scope', DeliveryScope.SINGLE.value)),
            silence_on_success=bool(payload.get('silence_on_success', False)),
            route_options=dict(payload.get('route_options') or {}),
        )
        try:
            return dispatcher.submit(envelope).to_record()
        finally:
            duration = max(0.0, monotonic() - started)
            if dispatcher._timing_sink is not None:
                dispatcher._timing_sink.last_submit_duration_s = duration

    return handle

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agents.models import normalize_agent_name
from mailbox_runtime.targets import normalize_actor_name

from .common import DeliveryScope


@dataclass(frozen=True)
class MessageEnvelope:
    project_id: str
    to_agent: str
    from_actor: str
    body: str
    task_id: str | None
    reply_to: str | None
    message_type: str
    delivery_scope: DeliveryScope
    silence_on_success: bool = False
    route_options: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.project_id:
            raise ValueError("project_id cannot be empty")
        if not self.to_agent:
            raise ValueError("to_agent cannot be empty")
        if not self.from_actor:
            raise ValueError("from_actor cannot be empty")
        if not self.body.strip():
            raise ValueError("body cannot be empty")
        if str(self.to_agent).strip().lower() == "all":
            object.__setattr__(self, "to_agent", "all")
        else:
            object.__setattr__(self, "to_agent", normalize_agent_name(self.to_agent))
        object.__setattr__(self, "from_actor", normalize_actor_name(self.from_actor))
        object.__setattr__(self, "route_options", dict(self.route_options or {}))
        if self.to_agent == "all" and self.delivery_scope is not DeliveryScope.BROADCAST:
            raise ValueError("to_agent=all requires delivery_scope=broadcast")
        if self.to_agent != "all" and self.delivery_scope is not DeliveryScope.SINGLE:
            raise ValueError("single target requires delivery_scope=single")

    def to_record(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "to_agent": self.to_agent,
            "from_actor": self.from_actor,
            "body": self.body,
            "task_id": self.task_id,
            "reply_to": self.reply_to,
            "message_type": self.message_type,
            "delivery_scope": self.delivery_scope.value,
            "silence_on_success": bool(self.silence_on_success),
            "route_options": dict(self.route_options),
        }

__all__ = ["MessageEnvelope"]

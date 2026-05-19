from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from agents.models import AgentSpec, PermissionMode, RestoreMode


class EffectiveRestoreMode(str, Enum):
    ATTACH = 'attach'
    PROVIDER = 'provider'
    MEMORY = 'memory'
    FRESH = 'fresh'
    AUTO = 'auto'


@dataclass(frozen=True)
class AgentLaunchPolicy:
    agent_name: str
    restore_mode: EffectiveRestoreMode
    permission_mode: PermissionMode
    queue_policy: str


def resolve_effective_restore_mode(default_mode: RestoreMode, *, cli_restore: bool) -> EffectiveRestoreMode:
    if not cli_restore:
        return EffectiveRestoreMode.FRESH
    mapping = {
        RestoreMode.FRESH: EffectiveRestoreMode.FRESH,
        RestoreMode.PROVIDER: EffectiveRestoreMode.PROVIDER,
        RestoreMode.AUTO: EffectiveRestoreMode.AUTO,
    }
    return mapping[default_mode]


def should_restore_provider_history(default_mode: RestoreMode, *, cli_restore: bool) -> bool:
    return resolve_effective_restore_mode(default_mode, cli_restore=cli_restore) is not EffectiveRestoreMode.FRESH


def resolve_effective_permission_mode(
    default_mode: PermissionMode,
    *,
    cli_auto_permission: bool,
) -> PermissionMode:
    if cli_auto_permission:
        return PermissionMode.AUTO
    return default_mode


def resolve_agent_launch_policy(
    spec: AgentSpec,
    *,
    cli_restore: bool,
    cli_auto_permission: bool,
) -> AgentLaunchPolicy:
    return AgentLaunchPolicy(
        agent_name=spec.name,
        restore_mode=resolve_effective_restore_mode(spec.restore_default, cli_restore=cli_restore),
        permission_mode=resolve_effective_permission_mode(
            spec.permission_default,
            cli_auto_permission=cli_auto_permission,
        ),
        queue_policy=spec.queue_policy.value,
    )

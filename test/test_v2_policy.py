from __future__ import annotations

import pytest

from agents.models import (
    AgentSpec,
    PermissionMode,
    QueuePolicy,
    RestoreMode,
    RuntimeMode,
    WorkspaceMode,
)
from agents.policy import EffectiveRestoreMode, resolve_agent_launch_policy


@pytest.mark.parametrize(
    ('permission_default', 'restore_default', 'expected_permission', 'expected_restore'),
    [
        (PermissionMode.MANUAL, RestoreMode.FRESH, PermissionMode.MANUAL, EffectiveRestoreMode.FRESH),
        (PermissionMode.MANUAL, RestoreMode.PROVIDER, PermissionMode.MANUAL, EffectiveRestoreMode.PROVIDER),
        (PermissionMode.MANUAL, RestoreMode.AUTO, PermissionMode.MANUAL, EffectiveRestoreMode.AUTO),
        (PermissionMode.AUTO, RestoreMode.FRESH, PermissionMode.AUTO, EffectiveRestoreMode.FRESH),
        (PermissionMode.AUTO, RestoreMode.PROVIDER, PermissionMode.AUTO, EffectiveRestoreMode.PROVIDER),
        (PermissionMode.AUTO, RestoreMode.AUTO, PermissionMode.AUTO, EffectiveRestoreMode.AUTO),
    ],
)
def test_launch_policy_matrix(
    permission_default: PermissionMode,
    restore_default: RestoreMode,
    expected_permission: PermissionMode,
    expected_restore: EffectiveRestoreMode,
) -> None:
    spec = AgentSpec(
        name='agent1',
        provider='codex',
        target='.',
        workspace_mode=WorkspaceMode.GIT_WORKTREE,
        workspace_root=None,
        runtime_mode=RuntimeMode.PANE_BACKED,
        restore_default=restore_default,
        permission_default=permission_default,
        queue_policy=QueuePolicy.SERIAL_PER_AGENT,
    )

    policy = resolve_agent_launch_policy(spec, cli_restore=True, cli_auto_permission=False)
    assert policy.permission_mode is expected_permission
    assert policy.restore_mode is expected_restore


def test_cli_new_context_forces_fresh_restore_policy() -> None:
    spec = AgentSpec(
        name='agent1',
        provider='claude',
        target='.',
        workspace_mode=WorkspaceMode.GIT_WORKTREE,
        workspace_root=None,
        runtime_mode='pane',
        restore_default=RestoreMode.PROVIDER,
        permission_default=PermissionMode.MANUAL,
        queue_policy=QueuePolicy.REJECT_WHEN_BUSY,
    )

    policy = resolve_agent_launch_policy(spec, cli_restore=False, cli_auto_permission=True)
    assert policy.agent_name == 'agent1'
    assert policy.restore_mode is EffectiveRestoreMode.FRESH
    assert policy.permission_mode is PermissionMode.AUTO
    assert policy.queue_policy == 'reject-when-busy'

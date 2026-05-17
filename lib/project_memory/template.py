from __future__ import annotations

TEMPLATE_VERSION = 3

DEFAULT_PROJECT_MEMORY = """# CCB Project Memory

This project is managed by CCB as a visible multi-agent workspace.

## Agent Awareness

- You are one agent in a CCB-managed project team.
- Other configured agents may be available in the same project.
- When work should be handled, reviewed, or cross-checked by another visible project agent, use CCB `ask`.
- Prefer CCB `ask` over provider-native hidden subagents for project-level collaboration.
- When delegating, include the goal, relevant files, current assumptions, and expected output.
- When replying to another agent, be concrete: include findings, changed files, blockers, and verification results.

## Ask Communication

Use CCB `ask` as an asynchronous handoff channel.

Preferred provider form, when slash commands are available:

```text
/ask <agent> <message>
```

Shell fallback:

```bash
command ask "$TARGET" <<'EOF'
$MESSAGE
EOF
```

After submitting, stop. Do not wait for the reply, poll status, or run observer
commands such as `pend`, `watch`, or `ping` unless the user explicitly asks for
diagnostics.

When this agent is already handling an active CCB ask task and delegates work
needed to finish that same task, use `ask --callback` so the child result returns
as a continuation task. Use `ask --silence` only for independent work whose result
is not needed by the active task. Plain nested `ask` from an active task is
rejected by CCB.
"""

__all__ = ['DEFAULT_PROJECT_MEMORY', 'TEMPLATE_VERSION']

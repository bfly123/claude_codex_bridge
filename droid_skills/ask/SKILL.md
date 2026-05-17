---
name: ask
description: Send a request to a CCB agent with `ask`.
metadata:
  short-description: Ask agent
---

Use this only for `/ask <target> <message...>`.

- `TARGET` = first token; `MESSAGE` = raw remainder, forwarded verbatim.
- `TARGET=all` broadcasts.
- Plain `ask` injects concise-reply guidance while still delivering the full reply body.
- Use `--compact` when the caller wants an actively distilled answer, such as review findings, status, risks, blockers, or next actions.
- Use `--silence` when success does not need a body; failures, blockers, or required next actions should still surface.
- Use `--callback` only from inside an active CCB task when this agent needs the target's result before finishing the original task. The current turn must end after submit; CCB will route the target result back as a new continuation task.
- Plain nested `ask` from an active CCB task is rejected; choose `--callback` for needed results or `--silence` for independent no-result-needed work.
- Do not manually append output-policy text; `ask` injects reply guidance.

Always send `MESSAGE` through the `<<'EOF' ... EOF` heredoc below. No other form is allowed.

```bash
command ask "$TARGET" <<'EOF'
$MESSAGE
EOF
```

```bash
command ask --compact "$TARGET" <<'EOF'
$MESSAGE
EOF
```

```bash
command ask --silence "$TARGET" <<'EOF'
$MESSAGE
EOF
```

```bash
command ask --callback "$TARGET" <<'EOF'
$MESSAGE
EOF
```

After the command returns, immediately end the turn. Do not wait for a reply, do not run `pend` / `ping` / `watch`, do not poll, do not add commentary. For `--callback`, report only that delegation was submitted; the final result belongs in the later continuation task.

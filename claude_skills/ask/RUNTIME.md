# Async Ask

Use this only for `/ask`.

Always send `MESSAGE` through the `<<'EOF' ... EOF` heredoc below. No other form is allowed.

```bash
command ask "$TARGET" <<'EOF'
$MESSAGE
EOF
```

- Sender is inferred from the current CCB workspace.
- `TARGET=all` broadcasts.
- Use `--compact` for actively distilled replies.
- Use `--silence` for silent-on-success delivery.
- Use `--callback` from inside an active task when the target result should return as a continuation task.
- Plain nested `ask` from an active CCB task is rejected; choose `--callback` for needed results or `--silence` for independent no-result-needed work.
- After the command returns, immediately end the turn. Do not wait for a reply, do not run `pend` / `ping` / `watch`, do not poll.
- For `--callback`, report only that delegation was submitted; the final result belongs in the later continuation task.

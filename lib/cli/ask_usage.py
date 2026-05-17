from __future__ import annotations

from typing import TextIO


def write_ask_usage(
    out: TextIO,
    *,
    command_name: str,
    error: str | None = None,
    alias_note: str | None = None,
) -> None:
    if error:
        print(f"error: {error}", file=out)
        print("", file=out)
    print("Usage:", file=out)
    print(
        f"  {command_name} [--compact] [--silence] [--callback] <target> [--] <message...>",
        file=out,
    )
    print("      --compact request a distilled reply that preserves key information", file=out)
    print("      --silence request silent-on-success delivery; failures/blockers still surface", file=out)
    print("      --callback route the result back as a new task to the current agent", file=out)
    print("      nested asks from active tasks must use --callback or --silence", file=out)
    print("      sender is inferred from the current workspace agent and falls back to user", file=out)
    print("      message text may be supplied on stdin", file=out)
    print("      examples:", file=out)
    print(f"        {command_name} --compact agent1 review latest diff", file=out)
    print(f"        {command_name} --silence agent1 run smoke check", file=out)
    print(f"        {command_name} --callback agent2 collect evidence for this task", file=out)
    print(f"  {command_name} get <job_id>", file=out)
    print(f"  {command_name} cancel <job_id>", file=out)
    if alias_note:
        print("", file=out)
        print(alias_note, file=out)


__all__ = [
    "write_ask_usage",
]

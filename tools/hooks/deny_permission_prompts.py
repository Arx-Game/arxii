"""PermissionRequest hook: answer a permission prompt with "deny" so no agent waits on a person.

Claude Code still prompts in bypass mode when a Bash command builds its own
arguments while running (an array filled by awk, a `$(...)` substitution, a loop
over files): it cannot rule out `rm`, so it asks. Overnight, an unanswered prompt
stalls the run for hours. This hook answers it with "deny" and a message telling
the agent how to rewrite the command, so the agent retries instead of waiting.

It denies when either is true:
  - the session runs inside the devcontainer (`/.dockerenv` exists), or
  - the session's permission mode means nobody is meant to answer prompts
    (`bypassPermissions`, `auto` or `dontAsk`).
Otherwise (an interactive session on the host) it prints nothing and the prompt
appears as usual. Registered by `tools/hooks/install.py`.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

UNATTENDED_MODES = frozenset({"bypassPermissions", "auto", "dontAsk"})
CONTAINER_MARKER = Path("/.dockerenv")

DENY_MESSAGE = """\
This command needed a person's approval, and nobody is watching this session, so the \
request was denied automatically. Rewrite it so it needs no approval, then retry:
- Type every path out literally. Do not build a file list with arrays, $(...), \
backticks, loops, awk or xargs.
- Commit named files with plain commands: `git add -- a.py b.py`, then \
`git commit -m "message" -- a.py b.py`.
- Split a compound command into separate Bash calls, one command each.
- Put anything that genuinely needs scripting in a file under your scratchpad and run it \
with `bash <file>`.
Do not retry the same command unchanged."""


def should_deny(payload: dict, *, in_container: bool) -> bool:
    if in_container:
        return True
    return payload.get("permission_mode") in UNATTENDED_MODES


def decision_output() -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PermissionRequest",
            "decision": {"behavior": "deny", "message": DENY_MESSAGE},
        }
    }


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    if should_deny(payload, in_container=CONTAINER_MARKER.exists()):
        json.dump(decision_output(), sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())

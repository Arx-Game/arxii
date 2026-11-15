"""PermissionRequest hook: deny a Bash permission prompt in a session nobody is watching.

Claude Code still prompts in bypass mode when a Bash command builds its own
arguments while running (an array filled by awk, a `$(...)` substitution, a loop
over files): it cannot rule out `rm`, so it asks. Overnight, an unanswered prompt
stalls the run for hours. This hook answers it with "deny" and a message telling
the agent how to rewrite the command, so the agent retries instead of waiting.

It denies only when all of these are true:
  - the tool is Bash (AskUserQuestion, ExitPlanMode, Edit, Write and MCP prompts
    are never touched);
  - the session runs in bypassPermissions or dontAsk mode, where nobody is meant
    to answer prompts;
  - ARXII_ALLOW_PROMPTS is not set to 1 (an escape hatch for a watched session).
In every other case it prints nothing and the prompt appears as usual. Any bad
payload also prints nothing. A PermissionRequest hook that fails, for any reason,
leaves the prompt unchanged, so this hook can never block a call by crashing.

`tools/hooks/install.py` copies this file into the Claude config directory and
registers the copy.
"""

from __future__ import annotations

import json
import os
import sys

UNATTENDED_MODES = frozenset({"bypassPermissions", "dontAsk"})
OPT_OUT_ENV = "ARXII_ALLOW_PROMPTS"

DENY_MESSAGE = """\
This Bash command needed a person's approval, and this session runs unattended, so \
the request was denied automatically. Rewrite it so it needs no approval, then retry:
- Type every path out literally. Do not build a file list with arrays, $(...), \
backticks, loops, awk or xargs.
- Commit named files with plain commands: `git add -- a.py b.py`, then \
`git commit -m "message" -- a.py b.py`.
- Split a compound command into separate Bash calls, one command each.
- Put anything that genuinely needs scripting in a file under your scratchpad and run it \
with `bash <file>`.
Do not retry the same command unchanged."""


def should_deny(payload: object, *, environ: dict[str, str]) -> bool:
    if not isinstance(payload, dict):
        return False
    if environ.get(OPT_OUT_ENV) == "1":
        return False
    return payload.get("tool_name") == "Bash" and payload.get("permission_mode") in (
        UNATTENDED_MODES
    )


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
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 0
    if should_deny(payload, environ=dict(os.environ)):
        json.dump(decision_output(), sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())

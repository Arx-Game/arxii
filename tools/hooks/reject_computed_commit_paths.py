"""PreToolUse hook: reject a `git add` or `git commit` that works out its file list while running.

Sonnet subagents follow the pathspec-commit rule (`git commit -m <msg> -- <files>`)
by computing the file list: `FILES=($(git diff --name-only | awk ...))`, a `for`
loop, `xargs`. Claude Code cannot tell which programs such a command runs, cannot
rule out `rm`, and stops for a person's approval even in bypass mode. This hook
rejects the command before it gets that far and shows the typed-out form, so the
agent gets it right on the next try.

`$(cat <<'EOF' ... EOF)` stays allowed: it is the usual way to pass a multi-line
commit message, and it builds no paths. Registered by `tools/hooks/install.py`.
"""

from __future__ import annotations

import json
import re
import sys

# `git` must start a command (line start, after ; & | or an open paren, or after
# do/then/else/xargs), so a PR body or message that mentions `git add` in prose
# does not match.
GIT_ADD_OR_COMMIT = re.compile(
    r"(?:^\s*|[;&|(]\s*|\b(?:do|then|else|xargs)\s+)"
    r"git(?:\s+-C\s+\S+)?(?:\s+-\S+)*\s+(?:add|commit)\b",
    re.MULTILINE,
)
# A heredoc body is text, not shell: drop it before matching anything.
HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1.*?^\s*\2\s*$", re.DOTALL | re.MULTILINE)

COMPUTED_PATH_PATTERNS = (
    re.compile(r"(?:^|[\s;&|(])[A-Za-z_]\w*=\("),  # array assignment: FILES=(...)
    re.compile(r"\$\{[^}]*\[[@*]\]\}"),  # array expansion: "${FILES[@]}"
    re.compile(r"(?:^|[;&|(]\s*|\n\s*)(?:for|while|until)\s"),  # shell loop
    re.compile(r"\bxargs\b"),
    re.compile(r"\$\((?!\s*cat\b)"),  # command substitution, except $(cat <<EOF)
)

REJECTION_REASON = """\
Blocked: this git add/commit works out its file list while running (an array, a loop, \
xargs or $(...)). Claude Code cannot check such a command in advance and would stop for \
a person's approval, which stalls an unattended run for hours.
Type the paths out instead, as separate Bash calls:
  git add -- path/one.py path/two.py
  git commit -m "message" -- path/one.py path/two.py
To see which files you changed, run `git status --short` first and copy the paths."""


def is_computed_commit(command: str) -> bool:
    command = HEREDOC.sub("", command)
    if not GIT_ADD_OR_COMMIT.search(command):
        return False
    return any(pattern.search(command) for pattern in COMPUTED_PATH_PATTERNS)


def rejection_output() -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": REJECTION_REASON,
        }
    }


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    if payload.get("tool_name") != "Bash":
        return 0
    command = payload.get("tool_input", {}).get("command", "")
    if is_computed_commit(command):
        json.dump(rejection_output(), sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())

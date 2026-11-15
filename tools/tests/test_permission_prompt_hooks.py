"""The hooks that keep unattended agents from waiting on a permission prompt.

Each test runs the hook script the way Claude Code does: a JSON payload on stdin,
the decision read back from stdout.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from hooks.deny_permission_prompts import should_deny
from hooks.install import install
import pytest

HOOKS_DIR = Path(__file__).resolve().parent.parent / "hooks"


def run_hook(script: str, payload: dict) -> dict | None:
    result = subprocess.run(
        [sys.executable, str(HOOKS_DIR / script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout) if result.stdout.strip() else None


def bash(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


@pytest.mark.parametrize(
    ("mode", "in_container", "expected"),
    [
        ("default", True, True),
        ("default", False, False),
        ("acceptEdits", False, False),
        ("bypassPermissions", False, True),
        ("auto", False, True),
        ("dontAsk", False, True),
    ],
)
def test_prompt_is_denied_in_the_container_or_an_unattended_mode(mode, in_container, expected):
    assert should_deny({"permission_mode": mode}, in_container=in_container) is expected


def test_denied_prompt_tells_the_agent_how_to_rewrite_the_command():
    output = run_hook(
        "deny_permission_prompts.py",
        {**bash("FILES=($(git diff --name-only)); rm x"), "permission_mode": "bypassPermissions"},
    )
    decision = output["hookSpecificOutput"]["decision"]
    assert output["hookSpecificOutput"]["hookEventName"] == "PermissionRequest"
    assert decision["behavior"] == "deny"
    assert "git commit -m" in decision["message"]


@pytest.mark.parametrize(
    "command",
    [
        "FILES=($(git diff --name-only | awk '{print $1}')); git add -- \"${FILES[@]}\"",
        'git commit -m "msg" -- $(git diff --name-only --cached)',
        "for f in $(git status --short | awk '{print $2}'); do git add -- \"$f\"; done",
        "git diff --name-only | xargs git add --",
        'git -C /workspaces/arxii commit -m "x" -- "${FILES[@]}"',
    ],
)
def test_commit_with_a_computed_file_list_is_rejected(command):
    output = run_hook("reject_computed_commit_paths.py", bash(command))
    assert output["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "git add -- path/one.py" in output["hookSpecificOutput"]["permissionDecisionReason"]


@pytest.mark.parametrize(
    "command",
    [
        "git add -- src/a.py src/b.py",
        'git commit -m "Fix the `foo` call" -- src/a.py',
        "git commit -m \"$(cat <<'EOF'\nTitle\n\nBody for the commit\nEOF\n)\" -- src/a.py",
        "git -C /workspaces/arxii commit -m msg -- tools/x.py",
        "FILES=($(ls)); echo ${FILES[@]}",
    ],
)
def test_plain_commit_and_non_git_scripting_pass(command):
    assert run_hook("reject_computed_commit_paths.py", bash(command)) is None


def test_install_replaces_its_own_entries_and_keeps_other_settings():
    settings = {
        "theme": "dark",
        "hooks": {
            "PreToolUse": [
                {"matcher": "Edit", "hooks": [{"type": "command", "command": "other-hook"}]},
                {
                    "matcher": "Bash",
                    "hooks": [{"type": "command", "command": "python3 /old/tools/hooks/x.py"}],
                },
            ]
        },
    }
    result = install(install(settings, HOOKS_DIR), HOOKS_DIR)
    assert result["theme"] == "dark"
    pre_tool = result["hooks"]["PreToolUse"]
    assert [group["matcher"] for group in pre_tool] == ["Edit", "Bash"]
    assert pre_tool[1]["hooks"][0]["command"].endswith("reject_computed_commit_paths.py")
    assert len(result["hooks"]["PermissionRequest"]) == 1

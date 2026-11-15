"""The hook that keeps an unattended agent from waiting on a Bash permission prompt.

Hook tests pipe a JSON payload into the script the way Claude Code does and read
the decision back from stdout. Installer tests run against a real config
directory under pytest's tmp_path, never the user's own settings.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from hooks.deny_permission_prompts import should_deny
from hooks.install import INSTALLED_NAME, LEGACY_COMMANDS, hook_command, install, run
import pytest

HOOK = Path(__file__).resolve().parent.parent / "hooks" / "deny_permission_prompts.py"


def payload(tool: str = "Bash", mode: str = "bypassPermissions") -> dict:
    return {
        "tool_name": tool,
        "permission_mode": mode,
        "tool_input": {"command": "FILES=($(git diff --name-only)); git add -- ${FILES[@]}"},
    }


def run_shell(command: str, stdin: dict) -> subprocess.CompletedProcess:
    """Run a registered hook command through sh, as Claude Code does."""
    return subprocess.run(
        ["sh", "-c", command], input=json.dumps(stdin), capture_output=True, text=True, check=False
    )


@pytest.mark.parametrize(
    ("tool", "mode", "expected"),
    [
        ("Bash", "bypassPermissions", True),
        ("Bash", "dontAsk", True),
        ("Bash", "default", False),
        ("Bash", "acceptEdits", False),
        ("Bash", "auto", False),
        ("Bash", "plan", False),
        ("AskUserQuestion", "bypassPermissions", False),
        ("ExitPlanMode", "bypassPermissions", False),
        ("Edit", "bypassPermissions", False),
        ("mcp__claude_ai_Claude_Docs__batch", "dontAsk", False),
    ],
)
def test_only_bash_prompts_in_unattended_modes_are_denied(tool, mode, expected):
    assert should_deny(payload(tool, mode), environ={}) is expected


def test_opt_out_variable_lets_the_prompt_through():
    assert should_deny(payload(), environ={"ARXII_ALLOW_PROMPTS": "1"}) is False


@pytest.mark.parametrize("bad", [None, [], "Bash", 3])
def test_a_payload_that_is_not_an_object_is_left_alone(bad):
    assert should_deny(bad, environ={}) is False


def test_denied_prompt_tells_the_agent_how_to_rewrite_the_command():
    result = run_shell(f"{sys.executable} {HOOK}", payload())
    decision = json.loads(result.stdout)["hookSpecificOutput"]
    assert result.returncode == 0
    assert decision["hookEventName"] == "PermissionRequest"
    assert decision["decision"]["behavior"] == "deny"
    assert "git commit -m" in decision["decision"]["message"]


def test_hook_prints_nothing_for_unreadable_input():
    result = subprocess.run(
        [sys.executable, str(HOOK)], input="not json", capture_output=True, text=True, check=False
    )
    assert (result.returncode, result.stdout) == (0, "")


def test_registered_command_exits_quietly_when_its_script_is_missing(tmp_path):
    result = run_shell(hook_command(tmp_path / "gone.py"), payload())
    assert (result.returncode, result.stdout) == (0, "")


def test_installed_copy_runs_from_the_config_dir_and_denies(tmp_path):
    run(tmp_path)
    settings = json.loads((tmp_path / "settings.json").read_text())
    [group] = settings["hooks"]["PermissionRequest"]
    assert group["matcher"] == "Bash"
    command = group["hooks"][0]["command"]
    assert str(tmp_path / "hooks" / INSTALLED_NAME) in command
    assert "/workspaces/arxii/tools/hooks" not in command
    result = run_shell(command, payload())
    assert json.loads(result.stdout)["hookSpecificOutput"]["decision"]["behavior"] == "deny"


def test_install_keeps_every_other_setting_and_hook(tmp_path):
    other_handler = {"type": "command", "command": "python3 /home/u/mytools/hooks/mine.py"}
    original = {
        "model": "opus",
        "enabledPlugins": {"superpowers@claude-plugins-official": True},
        "hooks": {
            "PermissionRequest": [
                {"matcher": "*", "hooks": [other_handler, {"command": "keepme"}]}
            ],
            "PreToolUse": [{"matcher": "Edit", "hooks": [{"command": "other-hook"}]}],
        },
    }
    (tmp_path / "settings.json").write_text(json.dumps(original))
    run(tmp_path)
    run(tmp_path)
    settings = json.loads((tmp_path / "settings.json").read_text())
    assert settings["model"] == "opus"
    assert settings["enabledPlugins"] == original["enabledPlugins"]
    assert settings["hooks"]["PreToolUse"] == original["hooks"]["PreToolUse"]
    groups = settings["hooks"]["PermissionRequest"]
    assert groups[0] == original["hooks"]["PermissionRequest"][0]
    assert len(groups) == 2


def test_install_writes_through_a_symlinked_settings_file(tmp_path):
    target = tmp_path / "dotfiles" / "settings.json"
    target.parent.mkdir()
    target.write_text('{"theme": "dark"}')
    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    (config_dir / "settings.json").symlink_to(target)
    assert run(config_dir) is True
    assert (config_dir / "settings.json").is_symlink()
    assert json.loads(target.read_text())["hooks"]["PermissionRequest"][0]["matcher"] == "Bash"


def test_a_handler_with_an_odd_command_is_kept():
    odd = {"matcher": "Bash", "hooks": [{"command": ["python3", "x.py"]}]}
    result = install({"hooks": {"PreToolUse": [odd]}}, "new-command")
    assert result["hooks"]["PreToolUse"] == [odd]


def test_install_removes_the_first_drafts_registrations():
    legacy = sorted(LEGACY_COMMANDS)
    settings = {
        "hooks": {
            "PermissionRequest": [{"matcher": "*", "hooks": [{"command": legacy[0]}]}],
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [{"command": legacy[1]}, {"command": "mine"}]}
            ],
        }
    }
    result = install(settings, "new-command")
    assert result["hooks"]["PreToolUse"] == [{"matcher": "Bash", "hooks": [{"command": "mine"}]}]
    assert result["hooks"]["PermissionRequest"] == [
        {"matcher": "Bash", "hooks": [{"type": "command", "command": "new-command"}]}
    ]


@pytest.mark.parametrize(
    "contents",
    [
        "{not json",
        "",
        "null",
        "[]",
        '{"hooks": null}',
        '{"hooks": {"PermissionRequest": null}}',
        '{"hooks": {"PermissionRequest": {"matcher": "Bash"}}}',
    ],
)
def test_install_leaves_an_unreadable_settings_file_untouched(tmp_path, contents):
    path = tmp_path / "settings.json"
    path.write_text(contents)
    assert run(tmp_path) is False
    assert path.read_text() == contents
    assert not (tmp_path / "hooks").exists()

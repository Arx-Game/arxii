"""Install the hook in `tools/hooks/` into the user's Claude Code settings.

The hook script is copied into `$CLAUDE_CONFIG_DIR/hooks/` (in the devcontainer,
`/home/vscode/.claude`, a named volume the host never reads), and the copy is
registered in `$CLAUDE_CONFIG_DIR/settings.json`. Registering the copy, not the
checkout's file, means the hook keeps working whatever branch the main checkout
or any worktree has checked out. The registered command also exits quietly if the
copy or python3 is ever missing.

This script is careful with `settings.json`:
  - if the file cannot be read or is not a settings object, it warns and changes
    nothing;
  - it adds or replaces only its own handler, and never removes anything else;
  - it writes a temporary file next to `settings.json` and renames it into place,
    so a crash mid-write cannot leave the file empty.
It always exits 0, so a failed install never fails container setup. Run by
`.devcontainer/post-create.sh`; safe to re-run.

Usage: python3 tools/hooks/install.py [--config-dir PATH]
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import sys
import tempfile

SOURCE = Path(__file__).resolve().parent / "deny_permission_prompts.py"
INSTALLED_NAME = "arxii_deny_permission_prompts.py"
EVENT = "PermissionRequest"
MATCHER = "Bash"

# Registrations written by the first version of this installer (PR #5132, before
# review). They pointed at the main checkout and must be cleaned up on upgrade.
LEGACY_COMMANDS = frozenset(
    {
        "python3 /workspaces/arxii/tools/hooks/deny_permission_prompts.py",
        "python3 /workspaces/arxii/tools/hooks/reject_computed_commit_paths.py",
    }
)


def default_config_dir() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


def hook_command(script: Path) -> str:
    """A command that runs the hook, or exits 0 if the script or python3 is missing."""
    body = 'f="$1"; [ -f "$f" ] && command -v python3 >/dev/null 2>&1 || exit 0; exec python3 "$f"'
    return f"sh -c {shlex.quote(body)} arxii-hook {shlex.quote(str(script))}"


def is_ours(handler: object, command: str) -> bool:
    if not isinstance(handler, dict):
        return False
    return handler.get("command") in LEGACY_COMMANDS | {command}


def install(settings: dict, command: str) -> dict:
    """Return settings with exactly one handler of ours, under PermissionRequest/Bash."""
    hooks = settings.setdefault("hooks", {})
    for event, groups in list(hooks.items()):
        if not isinstance(groups, list):
            continue
        kept_groups = []
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                kept_groups.append(group)
                continue
            handlers = [handler for handler in group["hooks"] if not is_ours(handler, command)]
            if handlers or len(handlers) == len(group["hooks"]):
                kept_groups.append({**group, "hooks": handlers})
        hooks[event] = kept_groups
    hooks.setdefault(EVENT, []).append(
        {"matcher": MATCHER, "hooks": [{"type": "command", "command": command}]}
    )
    return settings


def read_settings(path: Path) -> dict | None:
    if not path.exists():
        return {}
    try:
        settings = json.loads(path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        print(f"[hooks] {path} could not be read ({error}); left unchanged.", file=sys.stderr)
        return None
    if not isinstance(settings, dict) or not isinstance(settings.get("hooks", {}), dict):
        print(f"[hooks] {path} is not a settings object; left unchanged.", file=sys.stderr)
        return None
    return settings


def write_atomically(path: Path, text: str) -> None:
    handle, temp_name = tempfile.mkstemp(dir=path.parent, prefix=".settings.", suffix=".tmp")
    try:
        with os.fdopen(handle, "w") as temp_file:
            temp_file.write(text)
        if path.exists():
            shutil.copymode(path, temp_name)
        Path(temp_name).replace(path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


def run(config_dir: Path) -> bool:
    settings_path = config_dir / "settings.json"
    settings = read_settings(settings_path)
    if settings is None:
        return False
    installed = config_dir / "hooks" / INSTALLED_NAME
    installed.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SOURCE, installed)
    updated = install(settings, hook_command(installed))
    write_atomically(settings_path, json.dumps(updated, indent=2) + "\n")
    print(f"[hooks] Installed {installed} and registered it in {settings_path}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-dir", type=Path, default=default_config_dir())
    args = parser.parse_args()
    try:
        run(args.config_dir)
    except OSError as error:
        print(f"[hooks] install failed ({error}); settings left as they were.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

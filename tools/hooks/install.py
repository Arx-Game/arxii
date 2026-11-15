"""Register the hooks in `tools/hooks/` in the user's Claude Code settings.

`.claude/` is gitignored, and the project's `.claude/settings.json` sits on the
bind mount the host shares, so the registration goes in the user-level settings
file instead: `$CLAUDE_CONFIG_DIR/settings.json` (in the devcontainer that is
`/home/vscode/.claude`, a named volume the host never reads). Run by
`.devcontainer/post-create.sh`; safe to re-run, since it replaces its own entries
and leaves every other setting alone.

Usage: python3 tools/hooks/install.py [--settings PATH]
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

HOOKS_DIR = Path(__file__).resolve().parent
MARKER = "tools/hooks/"

REGISTRATIONS = (
    ("PermissionRequest", "deny_permission_prompts.py"),
    ("PreToolUse", "reject_computed_commit_paths.py"),
)


def default_settings_path() -> Path:
    config_dir = os.environ.get("CLAUDE_CONFIG_DIR") or str(Path.home() / ".claude")
    return Path(config_dir) / "settings.json"


def install(settings: dict, hooks_dir: Path) -> dict:
    hooks = settings.setdefault("hooks", {})
    for event, script in REGISTRATIONS:
        groups = [
            group
            for group in hooks.get(event, [])
            if not any(MARKER in handler.get("command", "") for handler in group.get("hooks", []))
        ]
        groups.append(
            {
                "matcher": "Bash" if event == "PreToolUse" else "*",
                "hooks": [{"type": "command", "command": f"python3 {hooks_dir / script}"}],
            }
        )
        hooks[event] = groups
    return settings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--settings", type=Path, default=default_settings_path())
    args = parser.parse_args()
    path: Path = args.settings
    settings = json.loads(path.read_text()) if path.exists() else {}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(install(settings, HOOKS_DIR), indent=2) + "\n")
    print(f"Registered tools/hooks/ in {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

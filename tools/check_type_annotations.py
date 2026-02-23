"""Pre-commit hook: enforce type annotations in ty-checked apps.

Runs ruff ANN rules only on *staged* files within the apps listed in
[tool.ty.src].include, excluding tests, migrations, admin, serializers,
and factories (matching ty's excludes).

Because existing code has unannotated functions, running against every file
would block all commits.  By accepting filenames from pre-commit
(pass_filenames: true) we only enforce the rule on files being committed,
incentivising gradual annotation as code is touched.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

# Must match [tool.ty.src].include in pyproject.toml
TYPED_DIRS = [
    "src/flows",
    "src/world/traits",
    "src/commands",
    "src/behaviors",
    "src/world/roster",
    "src/world/scenes",
    "src/world/stories",
    "src/world/character_sheets",
    "src/world/progression",
    "src/world/character_creation",
]

# File/directory names to skip (matches ty's exclude patterns).
# Use simple names — ruff's --exclude on Windows doesn't reliably match
# double-star glob patterns.
EXCLUDE_NAMES = {
    "tests",
    "test_",
    "tests.py",
    "migrations",
    "admin.py",
    "admin",
    "serializers",
    "serializers.py",
    "factories.py",
}

# ANN401 (Any) is too strict for Django code with dynamic attributes.
IGNORED_RULES = ["ANN401"]


def _is_in_typed_dir(filepath: str) -> bool:
    """Return True if *filepath* falls under one of the TYPED_DIRS."""
    normalized = pathlib.PurePosixPath(pathlib.Path(filepath).as_posix())
    return any(str(normalized).startswith(d + "/") or str(normalized) == d for d in TYPED_DIRS)


def _is_excluded(filepath: str) -> bool:
    """Return True if any path component matches an exclude pattern."""
    parts = pathlib.Path(filepath).parts
    for part in parts:
        if part in EXCLUDE_NAMES:
            return True
        if part.startswith("test_") and part.endswith(".py"):
            return True
    return False


def main() -> int:
    # pre-commit passes staged filenames as positional args
    candidates = sys.argv[1:]
    if not candidates:
        return 0

    targets = [
        f for f in candidates if f.endswith(".py") and _is_in_typed_dir(f) and not _is_excluded(f)
    ]
    if not targets:
        return 0

    cmd = [
        "ruff",
        "check",
        "--select",
        "ANN",
        "--ignore",
        ",".join(IGNORED_RULES),
        *targets,
    ]
    result = subprocess.run(cmd, capture_output=False, check=False)  # noqa: S603
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())

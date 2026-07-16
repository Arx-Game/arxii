"""Ratchet on grandfathered ``# noqa`` suppressions — the count may only go down.

The custom linters (e.g. ``lint_getattr_literal.py``) block new violations, but a
``# noqa: <TOKEN>`` is self-service: an agent that hits the linter can silence it
instead of building the missing scaffolding, and nothing notices (it happened
repeatedly through 2026-06/07 — see #2386). This check makes that visible: the
committed baseline in ``tools/noqa_ratchet_baseline.txt`` is the maximum allowed
count per token, so any new suppression fails CI until a human deliberately bumps
the baseline (which a reviewer sees as a diff line).

When a cleanup tranche lowers the real count, the check also fails until the
baseline is lowered to match — progress gets locked in, not silently eroded.
"""

from __future__ import annotations

from pathlib import Path
import re
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
BASELINE_FILE = REPO_ROOT / "tools" / "noqa_ratchet_baseline.txt"

# Non-noqa ratcheted patterns: baseline tokens prefixed "pattern:" count regex
# matches across src/**/*.py instead of noqa suppressions. Same rule: the
# count may only go down.
PATTERNS: dict[str, str] = {
    # Bare ObjectDB rows lack the ObjectParent mixin (no trigger_handler /
    # character_sheet / positions_cached) and cannot exist in production —
    # tests must use evennia_extensions.factories.ObjectDBFactory (which goes
    # through create_object). The grandfathered remainder is the handful of
    # deliberate production services that build rooms/exits as bare rows.
    "BARE_OBJECTDB_CREATE": r"ObjectDB\.objects\.create\(",
}


def count_token(token: str) -> int:
    """Count occurrences of ``# noqa: <token>`` under src/ (comments only)."""
    pattern = re.compile(rf"#\s*noqa:.*\b{re.escape(token)}\b")
    total = 0
    for path in SRC.rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        total += sum(1 for line in text.splitlines() if pattern.search(line))
    return total


def count_pattern(regex: str) -> int:
    """Count regex matches across src/**/*.py."""
    pattern = re.compile(regex)
    total = 0
    for path in SRC.rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        total += len(pattern.findall(text))
    return total


def main() -> int:
    failures: list[str] = []
    for raw in BASELINE_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        token, _, allowed_str = line.partition(" ")
        allowed = int(allowed_str)
        if token.startswith("pattern:"):
            name = token.removeprefix("pattern:")
            actual = count_pattern(PATTERNS[name])
        else:
            actual = count_token(token)
        if actual > allowed:
            failures.append(
                f"{token}: {actual} suppressions in src/ exceeds the baseline of {allowed}.\n"
                f"  A new '# noqa: {token}' was added. Do NOT silence the linter — add the\n"
                f"  missing scaffolding (property/helper/column) the linter is pointing at.\n"
                f"  If suppression is genuinely correct, bump the baseline in\n"
                f"  {BASELINE_FILE.relative_to(REPO_ROOT)} in the same commit and justify it\n"
                f"  in the commit message so a reviewer sees the exception."
            )
        elif actual < allowed:
            failures.append(
                f"{token}: {actual} suppressions in src/ is below the baseline of {allowed}.\n"
                f"  Nice — a cleanup landed. Lock it in: lower the {token} line in\n"
                f"  {BASELINE_FILE.relative_to(REPO_ROOT)} to {actual}."
            )
    if failures:
        print("noqa ratchet failed:\n\n" + "\n\n".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

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
    # Broad exception handlers in production code (tranche 4, #1164): every
    # grandfathered site is a classified boundary (per-item isolation, cron
    # tick, CLI/request boundary) that logs with exc_info. New ones need the
    # same classification — or a narrower catch.
    "BROAD_EXCEPT": r"except Exception\b",
}

# Pattern tokens whose count should skip test files (tests legitimately use
# broad catches and bare fixtures the production rule forbids... except where
# another token explicitly covers tests, like BARE_OBJECTDB_CREATE).
PATTERNS_EXCLUDE_TESTS = {"BROAD_EXCEPT"}

_TEST_PATH_RE = re.compile(r"(^|/)tests?(/|\.py$)|(^|/)test_[^/]*\.py$")


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


def count_pattern(regex: str, *, exclude_tests: bool = False) -> int:
    """Count regex matches across src/**/*.py (optionally skipping test files)."""
    pattern = re.compile(regex)
    total = 0
    for path in SRC.rglob("*.py"):
        rel = path.relative_to(SRC).as_posix()
        if exclude_tests and _TEST_PATH_RE.search(rel):
            continue
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
            actual = count_pattern(PATTERNS[name], exclude_tests=name in PATTERNS_EXCLUDE_TESTS)
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

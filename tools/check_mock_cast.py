"""Reject `Record<string, any>` mock casts in TanStack Query hook test files.

The codebase convention for typing mocked hook returns is::

    } as unknown as ReturnType<typeof useFooHook>;

Diverging to ``const mockX: Record<string, any> = { ... }`` (or ``as Record<string, any>``)
abandons all type checking on the mock object and silences
``@typescript-eslint/no-explicit-any`` in a way that hides drift between the mock and the
real hook return shape. Established pattern visible in 26+ files including
``frontend/src/narrative/__tests__/MuteSettingsPage.test.tsx``.

This linter fires only on test files that actually call ``vi.mock`` (so production code
and non-mock-using tests are unaffected). To suppress an intentional case, add a comment
``// noqa: MOCK_CAST`` on the offending line or the line above.
"""

from __future__ import annotations

from pathlib import Path
import re
import sys

SUPPRESSION_TOKEN = "noqa: MOCK_CAST"  # noqa: S105

# Matches typed declarations like `const mockMutation: Record<string, any> = {`
# or `let mockHook: Record<string, any>;`. Variable name must start with `mock`
# to scope to mock-style declarations, not unrelated `Record<string, any>` uses
# (which are rare but legitimate).
DECLARATION_PATTERN = re.compile(
    r"\b(const|let|var)\s+mock\w*\s*:\s*Record<\s*string\s*,\s*any\s*>"
)

# Matches inline casts like `const x = {...} as Record<string, any>` or
# `} as Record<string, any>;`.
CAST_PATTERN = re.compile(r"\bas\s+Record<\s*string\s*,\s*any\s*>")

# Only check files that actually use vi.mock — otherwise the cast is unrelated
# to hook mocking and the convention doesn't apply.
VI_MOCK_PATTERN = re.compile(r"\bvi\.mock\s*\(")


def file_uses_vi_mock(text: str) -> bool:
    return bool(VI_MOCK_PATTERN.search(text))


def is_suppressed(line: str, prev_line: str) -> bool:
    return SUPPRESSION_TOKEN in line or SUPPRESSION_TOKEN in prev_line


def check_file(path: Path) -> list[tuple[int, str]]:
    """Return list of (line_number, offending_text) for violations in path."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    if not file_uses_vi_mock(text):
        return []

    violations: list[tuple[int, str]] = []
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        prev = lines[idx - 1] if idx > 0 else ""
        if is_suppressed(line, prev):
            continue
        if DECLARATION_PATTERN.search(line) or CAST_PATTERN.search(line):
            violations.append((idx + 1, line.rstrip()))
    return violations


def main(argv: list[str]) -> int:
    paths = [Path(p) for p in argv[1:]]
    if not paths:
        return 0

    failed = False
    for path in paths:
        # Only check test files. Pre-commit's `types`/`files` filter narrows
        # to TS, but the linter receives all matching files; gate to tests here.
        name = path.name
        if not name.endswith((".test.tsx", ".test.ts")):
            continue
        violations = check_file(path)
        if not violations:
            continue
        failed = True
        for line_no, text in violations:
            print(
                f"{path}:{line_no}: MOCK_CAST: avoid `Record<string, any>` for hook mocks; "
                f"use `as unknown as ReturnType<typeof <hook>>`",
                file=sys.stderr,
            )
            print(f"  {text}", file=sys.stderr)

    if failed:
        print(
            "\nThe codebase convention for hook mocks is:\n"
            "  } as unknown as ReturnType<typeof useFooHook>;\n"
            "See frontend/src/narrative/__tests__/MuteSettingsPage.test.tsx for a reference.\n"
            "Suppress with `// noqa: MOCK_CAST` if intentionally needed.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

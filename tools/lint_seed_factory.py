"""Reject test factories called from production code (#4378).

A FactoryBoy factory invents values: ``CheckOutcomeFactory`` gives a new row a random
``success_level`` and Faker text. Called from seed code it creates the row nobody
authored whenever the row is missing, and every later ``get_or_create`` then leaves it
alone. Production's Failure, Partial Success and Success outcomes were made that way
(Success read -4, Failure read 3), so rolls were read backwards.

Two rules, over non-test code:

1. ``CheckOutcomeFactory(...)`` without an explicit ``success_level=`` is rejected
   everywhere, factory modules included. Seed code asks for an outcome tier through
   ``world.traits.services.ensure_check_outcome`` / ``ensure_canonical_check_outcome``.
2. Outside ``factories*.py`` modules, no call to any ``...Factory(...)``. Seeds write
   their rows with ``get_or_create`` on the natural key and explicit values. The modules
   in ``GRANDFATHERED`` predate the rule; the list is closed (a new offender is fixed,
   not listed), and each entry is a cleanup owed.

``# noqa: SEED_FACTORY`` on the call's line suppresses, and must say why.
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys

SUPPRESSION_TOKEN = "noqa: seed_factory"  # noqa: S105

# Closed list (#4378): modules that called factories before this rule existed.
GRANDFATHERED: frozenset[str] = frozenset(
    {
        "src/world/combat/consider.py",
        "src/world/combat/simulation.py",
        "src/world/narrative/ambient_triggers.py",
        "src/world/seeds/underworld.py",
        "src/world/seeds/game_content/battles.py",
        "src/world/seeds/game_content/challenges.py",
        "src/world/seeds/game_content/characters.py",
        "src/world/seeds/game_content/clash.py",
        "src/world/seeds/game_content/conditions.py",
        "src/world/seeds/game_content/magic.py",
        "src/world/seeds/game_content/missions.py",
        "src/world/seeds/game_content/social.py",
        "src/world/seeds/game_content/tutorial.py",
    }
)

OUTCOME_FACTORY = "CheckOutcomeFactory"


def is_test_path(path: str) -> bool:
    """Return whether ``path`` is test code, which may use factories freely."""
    parts = path.split("/")
    name = parts[-1]
    return (
        "tests" in parts
        or "integration_tests" in parts
        or "tools" in parts
        or name.startswith("test_")
        or name in {"tests.py", "conftest.py"}
    )


def is_factory_module(path: str) -> bool:
    """Return whether ``path`` is a ``factories*.py`` module."""
    return Path(path).name.startswith("factories")


def _called_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def find_violations(path: str, source: str) -> list[tuple[int, str]]:
    """Return ``(line, message)`` for every factory call the rules reject in ``path``."""
    if is_test_path(path):
        return []
    lines = source.splitlines()
    found: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        name = _called_name(node)
        if not name.endswith("Factory"):
            continue
        line = lines[node.lineno - 1] if node.lineno <= len(lines) else ""
        if SUPPRESSION_TOKEN in line.lower():
            continue
        if name == OUTCOME_FACTORY and not any(k.arg == "success_level" for k in node.keywords):
            found.append(
                (
                    node.lineno,
                    "CheckOutcomeFactory() without success_level= gives a random level; "
                    "use world.traits.services.ensure_canonical_check_outcome (#4378)",
                )
            )
        elif not is_factory_module(path) and path not in GRANDFATHERED:
            found.append(
                (
                    node.lineno,
                    f"{name}() is a test factory called from production code; "
                    "write the row with get_or_create and explicit values (#4378)",
                )
            )
    return found


def main(argv: list[str]) -> int:
    """Check each file named in ``argv``; return 1 when any violation is found."""
    failed = False
    for arg in argv:
        path = Path(arg).as_posix()
        if not path.endswith(".py"):
            continue
        for lineno, message in find_violations(path, Path(arg).read_text(encoding="utf-8")):
            print(f"{path}:{lineno}: {message}")
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

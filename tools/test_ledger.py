"""The test ledger (#3657): a mechanical first pass over an app's test modules.

Run via: uv run python tools/test_ledger.py world.conditions [--csv <path>]

Reads every test module under the app's ``tests/`` package with ``ast`` and
counts the signals that say which layer a module belongs to, then proposes a
layer and a reason. The proposal is the start of a conversation, never a
verdict: a person confirms each ``R`` row and names the ``J`` or ``X`` test
that still asserts the behaviour before anything is removed. "Nothing calls
it" never appears in the reason column; "journey N asserts this" does.

Layers (the rubric ruled on the issue):

- ``J`` journey: drives the real seam (``JourneyCase``, ``execute_cmd``,
  ``dispatch_player_action``) and asserts what the player saw.
- ``F`` fuzz: Hypothesis at a seam.
- ``X`` cross-system: reaches into two or more other ``world.*`` packages'
  services, and no per-app suite can see the break.
- ``U-keep``: a unit the journey cannot reach (a parser with branches, an
  error-path mapping, a pure function's edge). The default when the
  signals do not say otherwise: a person decides.
- ``R`` removal candidate, with one reason: ``builtin`` (Django or DRF
  behaviour), ``shape`` (dict, queryset or instance shape), ``dup`` (a named
  journey already asserts the outcome; only a person can assign this),
  ``mock-pinned`` (the assertion is that a mock was called), ``smoke``
  (factory builds, ``__str__``, ``Meta``).
"""

from __future__ import annotations

import argparse
import ast
from collections.abc import Iterable
import csv
from dataclasses import asdict, dataclass
from pathlib import Path
import re
import sys

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC_ROOT = _REPO_ROOT / "src"

_JOURNEY_SEAMS = ("JourneyCase", "execute_cmd", "dispatch_player_action", "cmdhandler")
_BY_HAND_SEAMS = (".func()",)
_API_SEAMS = ("APIClient", "self.client.", "APITestCase", "APIRequestFactory")
_MOCK_CALLS = ("patch(", "patch.object(", "Mock(", "MagicMock(", "patch.dict(")
_MOCK_ASSERTS = ("assert_called", "assert_not_called", "assert_awaited", "call_count", "call_args")
_SHAPE_ASSERTS = ("assertIsInstance", "assertDictEqual", "assertListEqual", "assertSetEqual")
_SMOKE_NAMES = re.compile(
    r"^test_(str|repr|meta|factory|factories|ordering|default|defaults|verbose_name|help_text|"
    r"unicode|can_create|creation|create_instance|model_fields|field_)"
)
_BUILTIN_NAMES = re.compile(
    r"^test_.*(unique_constraint|null|blank|max_length|choices_are|is_registered|admin_registered|"
    r"serializer_fields|read_only_fields|pagination|filterset|filter_backends|permission_classes)"
)
_OUTCOME_ASSERTS = ("assertIn(", "assertEqual(", "assertTrue(", "assertFalse(", "assertRaises")


@dataclass(frozen=True)
class ModuleLedger:
    """What the first pass says about one test module."""

    module: str
    tests: int
    classes: int
    postgres_tagged: bool
    journey_seams: int
    by_hand_cmd: int
    api_seams: int
    hypothesis: bool
    mock_calls: int
    mock_asserts: int
    shape_asserts: int
    outcome_asserts: int
    smoke_named: int
    builtin_named: int
    world_packages_imported: int
    layer: str
    reason: str


def _count(text: str, needles: Iterable[str]) -> int:
    return sum(text.count(needle) for needle in needles)


_REACHING_MODULES = ("services", "service_functions", "flows", "views", "handlers", "actions")


def _world_packages(tree: ast.Module, own_app: str) -> set[str]:
    """Other ``world.<name>`` packages whose behaviour a module reaches.

    Only an import of a service-like module counts (``services``, ``flows``,
    ``views``, ``handlers``, ``actions``): a factory, model or constant from
    another package is setup, not a seam between systems.
    """
    found: set[str] = set()
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
        elif isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        for name in names:
            parts = name.split(".")
            if len(parts) < 3 or parts[0] != "world" or f"world.{parts[1]}" == own_app:
                continue
            if any(part.startswith(_REACHING_MODULES) for part in parts[2:]):
                found.add(f"world.{parts[1]}")
    return found


def _test_functions(tree: ast.Module) -> tuple[list[str], int]:
    """Names of every ``test_*`` function or method, and the class count."""
    names: list[str] = []
    classes = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            classes += 1
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
            "test"
        ):
            names.append(node.name)
    return names, classes


_BEFORE_HARNESS = (
    "a journey written before the harness: builds the Cmd and calls .func(); move onto JourneyCase"
)
_BUILTIN = "builtin: every test checks Django or DRF behaviour (fields, constraints, registration)"
_REAL_SEAM = "drives the real seam (handler, dispatch or JourneyCase)"
_SMOKE = "smoke: every test is a __str__/factory/Meta/default check"
_ENDPOINT = "endpoint tests through APIClient; keep until a journey covers the route, then re-grade"


def _rules(signals: dict[str, int | bool]) -> list[tuple[bool, str, str]]:
    """The rubric as an ordered table: the first true predicate wins."""
    tests = int(signals["tests"])
    smoke = int(signals["smoke_named"])
    builtin = int(signals["builtin_named"])
    mock_asserts = int(signals["mock_asserts"])
    outcome = int(signals["outcome_asserts"])
    shape = int(signals["shape_asserts"])
    return [
        (tests == 0, "U-keep", "no tests; a helper module, not a test"),
        (bool(signals["hypothesis"]), "F", "Hypothesis strategies at a seam"),
        (bool(signals["journey_seams"]), "J", _REAL_SEAM),
        (bool(signals["by_hand_cmd"]), "J", _BEFORE_HARNESS),
        (bool(smoke) and smoke >= tests, "R", _SMOKE),
        (bool(builtin) and builtin >= tests, "R", _BUILTIN),
        (
            bool(mock_asserts) and mock_asserts > outcome,
            "R",
            "mock-pinned: more assertions about mocks being called than about outcomes",
        ),
        (
            bool(shape) and shape * 2 > outcome,
            "R",
            "shape: the assertions are mostly about types and container shapes",
        ),
        (
            int(signals["world_packages_imported"]) >= 2 and not signals["api_seams"],
            "X",
            "reaches two or more other world.* packages; a cross-system seam",
        ),
        (bool(signals["api_seams"]), "U-keep", _ENDPOINT),
    ]


def propose(signals: dict[str, int | bool]) -> tuple[str, str]:
    """The layer the signals suggest, and why, in one line each."""
    for holds, layer, reason in _rules(signals):
        if holds:
            return layer, reason
    return "U-keep", "a unit; a person decides whether a journey reaches it"


def grade_module(path: Path, module_name: str, own_app: str) -> ModuleLedger:
    text = path.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(text)
    names, classes = _test_functions(tree)
    signals: dict[str, int | bool] = {
        "tests": len(names),
        "classes": classes,
        "postgres_tagged": 'tag("postgres")' in text or "tag('postgres')" in text,
        "journey_seams": _count(text, _JOURNEY_SEAMS),
        "by_hand_cmd": _count(text, _BY_HAND_SEAMS),
        "api_seams": _count(text, _API_SEAMS),
        "hypothesis": "hypothesis" in text and "@given" in text,
        "mock_calls": _count(text, _MOCK_CALLS),
        "mock_asserts": _count(text, _MOCK_ASSERTS),
        "shape_asserts": _count(text, _SHAPE_ASSERTS),
        "outcome_asserts": _count(text, _OUTCOME_ASSERTS),
        "smoke_named": sum(1 for name in names if _SMOKE_NAMES.match(name)),
        "builtin_named": sum(1 for name in names if _BUILTIN_NAMES.match(name)),
        "world_packages_imported": len(_world_packages(tree, own_app)),
    }
    layer, reason = propose(signals)
    return ModuleLedger(module=module_name, layer=layer, reason=reason, **signals)  # type: ignore[arg-type]


def app_test_modules(app: str, src_root: Path = _SRC_ROOT) -> list[tuple[Path, str]]:
    """``(path, dotted module)`` for every ``test*.py`` under the app's tests package."""
    app_dir = src_root / Path(*app.split("."))
    tests_dir = app_dir / "tests"
    roots = [tests_dir] if tests_dir.is_dir() else [app_dir]
    out: list[tuple[Path, str]] = []
    for root in roots:
        for path in sorted(root.rglob("test*.py")):
            rel = path.relative_to(src_root).with_suffix("").as_posix().replace("/", ".")
            out.append((path, rel))
    return out


def ledger_for(app: str, src_root: Path = _SRC_ROOT) -> list[ModuleLedger]:
    return [grade_module(path, module, app) for path, module in app_test_modules(app, src_root)]


def write_csv(rows: list[ModuleLedger], target) -> None:
    fields = list(ModuleLedger.__dataclass_fields__)
    writer = csv.DictWriter(target, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        writer.writerow(asdict(row))


def summary(rows: list[ModuleLedger]) -> str:
    by_layer: dict[str, int] = {}
    tests_by_layer: dict[str, int] = {}
    for row in rows:
        by_layer[row.layer] = by_layer.get(row.layer, 0) + 1
        tests_by_layer[row.layer] = tests_by_layer.get(row.layer, 0) + row.tests
    lines = [f"{len(rows)} modules, {sum(r.tests for r in rows)} tests"]
    lines += [
        f"  {layer:7} {by_layer[layer]:4} modules {tests_by_layer[layer]:6} tests"
        for layer in sorted(by_layer)
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("app", help="dotted app, e.g. world.conditions or integration_tests")
    parser.add_argument("--csv", type=Path, help="write the ledger here (parents are created)")
    args = parser.parse_args(argv)
    rows = ledger_for(args.app)
    if not rows:
        sys.stderr.write(f"no test modules found for {args.app}\n")
        return 1
    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", newline="", encoding="utf-8") as handle:
            write_csv(rows, handle)
    else:
        write_csv(rows, sys.stdout)
    sys.stderr.write(summary(rows) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

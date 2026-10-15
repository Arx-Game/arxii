"""Generate the journey inventory (#3657): everything a player or staff member
can do, read from the code's own registries, with the tests that mention it.

Run via: uv run python tools/journey_inventory.py > docs/testing/journey-inventory.md

The inventory is the spine of the suite audit. Four registries say what a
user can do: the keyed ``Action`` classes (the seam both web and telnet
converge on), the ``Cmd`` classes in the character and account cmdsets, the
router registrations and ``path()`` views under ``/api/``, and the frontend
routes in ``App.tsx``. For each entry the last column lists the test files
that name it, so a surface with none is a journey nobody has written. The
hand-curated list of journeys that matter lives next door in
``docs/testing/journeys.md``; this file is regenerated, never edited.

The parsers over source text are stdlib and unit-tested in ``tools/tests``;
the two registry readers need Django and run only when the script is run.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
import os
from pathlib import Path
import re
import sys

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC_ROOT = _REPO_ROOT / "src"
_FRONTEND_ROOT = _REPO_ROOT / "frontend"
_APP_TSX = _FRONTEND_ROOT / "src" / "App.tsx"

_ROUTE_RE = re.compile(r'path="(?P<path>[^"]+)"')
_ROUTER_RE = re.compile(
    r'router\.register\(\s*r?"(?P<prefix>[^"]*)"\s*,\s*(?P<view>[A-Za-z_][A-Za-z0-9_]*)'
)
_PATH_RE = re.compile(r'path\(\s*r?"(?P<route>[^"]*)"\s*,\s*(?P<view>[A-Za-z_][A-Za-z0-9_]*)')
_TEST_DIR_MARKERS = ("/tests/", "/integration_tests/")


@dataclass(frozen=True)
class Surface:
    """One thing a user can do, as a registry names it."""

    kind: str  # action | command | api | route
    key: str
    where: str  # class or module that implements it
    detail: str = ""  # category/target for actions, aliases for commands, view for api
    tests: tuple[str, ...] = field(default_factory=tuple)


# --- source-text parsers (no Django) -----------------------------------------


def frontend_routes(app_tsx: str) -> list[str]:
    """Every ``path="..."`` in the router, in file order, deduplicated."""
    seen: list[str] = []
    for match in _ROUTE_RE.finditer(app_tsx):
        route = match["path"]
        if route not in seen:
            seen.append(route)
    return seen


def api_routes(urls_py: str, module: str) -> list[Surface]:
    """Router registrations and ``path()`` views in one ``urls.py``.

    ``include()`` lines are not surfaces (the included module is read on its
    own); a ``path()`` whose view is a plain name or ``X.as_view()`` is.
    """
    out: list[Surface] = [
        Surface("api", match["prefix"] + "/", module, match["view"])
        for match in _ROUTER_RE.finditer(urls_py)
    ]
    for match in _PATH_RE.finditer(urls_py):
        view = match["view"]
        if view == "include":
            continue
        out.append(Surface("api", match["route"], module, view))
    return out


def tests_mentioning(tokens: Iterable[str], corpus: dict[str, str]) -> tuple[str, ...]:
    """The test files whose text holds any of ``tokens`` (exact substrings)."""
    wanted = [token for token in tokens if token]
    return tuple(
        sorted(path for path, text in corpus.items() if any(token in text for token in wanted))
    )


def is_test_file(path: str) -> bool:
    return path.endswith(".py") and any(marker in path for marker in _TEST_DIR_MARKERS)


def load_test_corpus(
    src_root: Path = _SRC_ROOT, frontend_root: Path = _FRONTEND_ROOT
) -> dict[str, str]:
    """Every backend test file under ``src/`` and every Vitest or Playwright
    file under ``frontend/``, keyed by path relative to the repo root."""
    corpus: dict[str, str] = {}
    for path in src_root.rglob("*.py"):
        rel = path.relative_to(src_root).as_posix()
        if is_test_file("/" + rel) and path.name.startswith("test"):
            corpus["src/" + rel] = path.read_text(encoding="utf-8", errors="replace")
    for pattern in ("src/**/*.test.ts", "src/**/*.test.tsx", "e2e/**/*.spec.ts"):
        for path in frontend_root.glob(pattern):
            if "node_modules" in path.parts:
                continue
            rel = path.relative_to(frontend_root).as_posix()
            corpus["frontend/" + rel] = path.read_text(encoding="utf-8", errors="replace")
    return corpus


# --- registry readers (Django) -----------------------------------------------


def _ensure_django_setup() -> None:
    import django  # noqa: PLC0415
    from django.conf import settings  # noqa: PLC0415

    if settings.configured:
        return
    src_dir = str(_SRC_ROOT)
    os.chdir(src_dir)
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "server.conf.settings")
    django.setup()
    # Evennia fills its top-level names (``evennia.Command``) only on its own
    # init; a command module imported before that sees ``Command`` as None.
    import evennia  # noqa: PLC0415

    evennia._init()  # noqa: SLF001


def registry_actions(corpus: dict[str, str]) -> list[Surface]:
    """Every keyed action in ``actions.registry``, with the tests naming its key."""
    from actions.registry import ACTIONS_BY_KEY  # noqa: PLC0415

    out: list[Surface] = []
    for key, action in sorted(ACTIONS_BY_KEY.items()):
        cls = type(action)
        tokens = (f'"{key}"', f"'{key}'", cls.__name__)
        out.append(
            Surface(
                "action",
                key,
                f"{cls.__module__}.{cls.__name__}",
                f"{action.category} / {action.target_type.value}",
                tests_mentioning(tokens, corpus),
            )
        )
    return out


def cmdset_commands(corpus: dict[str, str]) -> list[Surface]:
    """Every command a character or account cmdset carries, with its tests.

    A test names a command by its class (``CmdMarket``) or by typing it
    through the harness (``telnet(..., "market ...")``).
    """
    from commands.default_cmdsets import AccountCmdSet, CharacterCmdSet  # noqa: PLC0415

    out: list[Surface] = []
    seen: set[str] = set()
    for cmdset_cls in (CharacterCmdSet, AccountCmdSet):
        cmdset = cmdset_cls()
        for cmd in sorted(cmdset.commands, key=lambda c: c.key):
            cls = type(cmd)
            ident = f"{cls.__module__}.{cls.__name__}"
            if ident in seen:
                continue
            seen.add(ident)
            aliases = ", ".join(sorted(cmd.aliases)) if cmd.aliases else ""
            tokens = (cls.__name__, f'"{cmd.key} ', f'"{cmd.key}"', f"'{cmd.key} ")
            out.append(
                Surface("command", cmd.key, ident, aliases, tests_mentioning(tokens, corpus))
            )
    return out


def all_api_routes(corpus: dict[str, str]) -> list[Surface]:
    """Every ``urls.py`` under ``src/`` that is not a test, parsed."""
    out: list[Surface] = []
    for path in sorted(_SRC_ROOT.rglob("urls.py")):
        rel = path.relative_to(_SRC_ROOT).as_posix()
        if is_test_file("/" + rel):
            continue
        module = rel[: -len(".py")].replace("/", ".")
        for surface in api_routes(path.read_text(encoding="utf-8"), module):
            tokens = (surface.detail, surface.key.rstrip("/")) if surface.key.strip("/") else ()
            out.append(
                Surface(
                    surface.kind,
                    surface.key,
                    surface.where,
                    surface.detail,
                    tests_mentioning(tokens, corpus) if tokens else (),
                )
            )
    return out


def all_frontend_routes(corpus: dict[str, str]) -> list[Surface]:
    text = _APP_TSX.read_text(encoding="utf-8")
    return [
        Surface(
            "route",
            route,
            "frontend/src/App.tsx",
            "",
            tests_mentioning((f'"{route}"', f"'{route}'"), corpus),
        )
        for route in frontend_routes(text)
    ]


# --- rendering ---------------------------------------------------------------


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def _tests_cell(tests: tuple[str, ...], limit: int = 4) -> str:
    if not tests:
        return "none"
    shown = ", ".join(f"`{t}`" for t in tests[:limit])
    extra = len(tests) - limit
    return shown + (f" (+{extra})" if extra > 0 else "")


def render(
    actions: list[Surface],
    commands: list[Surface],
    api: list[Surface],
    routes: list[Surface],
) -> str:
    def uncovered(rows: list[Surface]) -> int:
        return sum(1 for row in rows if not row.tests)

    lines = [
        "# Journey inventory",
        "",
        "Generated by `tools/journey_inventory.py` from the code's own registries;",
        "regenerate with",
        "`uv run python tools/journey_inventory.py > docs/testing/journey-inventory.md`.",
        "Never edit by hand: the hand-curated journeys live in `journeys.md`.",
        "",
        "The last column of each table is the test files that name the surface. `none`",
        "is a surface no test reaches by name: either a journey nobody has written or a",
        "surface that is dead, and the ledger (`tools/test_ledger.py`) decides which.",
        "",
        "| Registry | Surfaces | Named by no test |",
        "|---|---|---|",
        f"| Actions (`actions.registry`) | {len(actions)} | {uncovered(actions)} |",
        f"| Commands (character + account cmdsets) | {len(commands)} | {uncovered(commands)} |",
        f"| API routes (`urls.py` under `src/`) | {len(api)} | {uncovered(api)} |",
        f"| Frontend routes (`App.tsx`) | {len(routes)} | {uncovered(routes)} |",
        "",
        "## Actions",
        "",
        "| Key | Class | Category / target | Tests naming it |",
        "|---|---|---|---|",
    ]
    lines += [
        f"| `{_cell(a.key)}` | `{_cell(a.where)}` | {_cell(a.detail)} | {_tests_cell(a.tests)} |"
        for a in actions
    ]
    lines += [
        "",
        "## Commands",
        "",
        "| Key | Aliases | Class | Tests naming it |",
        "|---|---|---|---|",
    ]
    lines += [
        f"| `{_cell(c.key)}` | {_cell(c.detail)} | `{_cell(c.where)}` | {_tests_cell(c.tests)} |"
        for c in commands
    ]
    lines += [
        "",
        "## API routes",
        "",
        "| Route | View | Module | Tests naming it |",
        "|---|---|---|---|",
    ]
    lines += [
        f"| `{_cell(r.key)}` | `{_cell(r.detail)}` | `{_cell(r.where)}` | {_tests_cell(r.tests)} |"
        for r in api
    ]
    lines += ["", "## Frontend routes", "", "| Path | Tests naming it |", "|---|---|"]
    lines += [f"| `{_cell(r.key)}` | {_tests_cell(r.tests)} |" for r in routes]
    return "\n".join(lines) + "\n"


def main() -> None:
    corpus = load_test_corpus()
    _ensure_django_setup()
    sys.stdout.write(
        render(
            registry_actions(corpus),
            cmdset_commands(corpus),
            all_api_routes(corpus),
            all_frontend_routes(corpus),
        )
    )


if __name__ == "__main__":
    main()

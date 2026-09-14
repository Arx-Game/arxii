"""Reject a ``to_attr`` prefetch unless it targets a ``PrunedCachedProperty`` (#3816).

``Prefetch(..., to_attr="x")`` writes a plain attribute into the instance
``__dict__``, and Django decides whether to run a prefetch by asking whether the
attribute is already there. For a genuine ``cached_property``-family descriptor
that check is ``"x" in instance.__dict__`` (correct: empty on a fresh instance);
for anything else - a bare attribute, a plain ``@property`` - Django falls back to
``hasattr(instance, "x")``, which a getter that never raises satisfies immediately,
so the batched query never runs at all. Under the identity map (ADR-0008) every
queryset returns the same Python object for a pk for the life of the process, so
once that first (skipped-or-not) prefetch sets ``x``, every later one onto that
instance is a silent no-op: the next request re-serves the first request's rows,
deleted ones included, arriving with a null id (``Collector.delete()`` nulls the
pk on the shared instance it deleted, ADR-0263).

``PrunedCachedProperty`` (``evennia_extensions/cached_property.py``) is the
sanctioned target: it is a genuine data descriptor (so Django's freshness check
is correct) that also re-filters pk-gone-falsey rows out of the cached list on
every read, self-healing against the zombie-row failure mode above. See
ADR-0296 for the fuller rationale. A bare-string ``prefetch_related("x")`` is
never safe regardless of the target - it goes stale the same way through
``instance._prefetched_objects_cache`` - and stays rejected unconditionally by
``lint_prefetch_string.py``.

Precisely resolving which model class a ``to_attr`` string lands on requires
cross-referencing the queryset's model back through the AST, which is not
reliable to do from a single file in the general case (the model may be
imported, subclassed, or the queryset built through a chain of helpers). This
hook uses a narrower, same-file heuristic instead: a ``to_attr`` value passes
only when the file both imports ``PrunedCachedProperty`` from
``evennia_extensions.cached_property`` **and** decorates a property of that
exact name with it, somewhere in the file. That catches the common mistake -
targeting a bare attribute or an ordinary ``@property``/``cached_property`` -
without needing full cross-file type inference; a genuine same-name collision
between two unrelated classes in one file, one of which decorates the wrong one,
is a theoretical gap this hook accepts (narrower than a per-model check, but far
narrower than "any to_attr is fine").

Use ``# noqa: PREFETCH_TO_ATTR`` to suppress a target this heuristic cannot see,
with a reason.

This hook's ``files:`` scope in ``.pre-commit-config.yaml`` currently contains
zero ``to_attr`` call sites at all (only prose mentions), so a clean run there
is not evidence this rewrite works against real code - only that it doesn't
false-positive on those two directories. Widening the scope to the apps #3816
actually converted is blocked on #3835: most of their ``to_attr`` sites split
the ``Prefetch`` call from the ``PrunedCachedProperty`` definition across
files (the dominant, correct layout in this codebase), which this same-file
heuristic cannot see across, so widening naively flags already-correct code
alongside the genuinely unconverted sites. See the hook's config comment for
the counted breakdown.
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys

SUPPRESSION_TOKEN = "noqa: prefetch_to_attr"  # noqa: S105
_PRUNED_CACHED_PROPERTY_MODULE = "evennia_extensions.cached_property"
_PRUNED_CACHED_PROPERTY_NAME = "PrunedCachedProperty"


def has_suppression(line: str) -> bool:
    """Return whether ``line`` carries the suppression token."""
    return SUPPRESSION_TOKEN in line.lower()


def _is_prefetch_call(node: ast.Call) -> bool:
    """Whether ``node`` is a ``Prefetch(...)`` call, however it was imported."""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "Prefetch"
    return isinstance(func, ast.Attribute) and func.attr == "Prefetch"


def _imports_pruned_cached_property(tree: ast.Module) -> bool:
    """Whether ``tree`` imports the genuine ``PrunedCachedProperty`` descriptor.

    A local class or alias of the same name does not count - the heuristic only
    trusts the real descriptor, imported from its own module.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module != _PRUNED_CACHED_PROPERTY_MODULE:
            continue
        if any(alias.name == _PRUNED_CACHED_PROPERTY_NAME for alias in node.names):
            return True
    return False


def _decorator_names(decorators: list[ast.expr]) -> set[str]:
    """Return the bare names a list of decorator expressions resolves to."""
    names: set[str] = set()
    for decorator in decorators:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, ast.Attribute):
            names.add(target.attr)
    return names


def _pruned_cached_property_names(tree: ast.Module) -> set[str]:
    """Return the names of every property in ``tree`` decorated with the real
    ``PrunedCachedProperty`` (only meaningful once the import is confirmed)."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if _PRUNED_CACHED_PROPERTY_NAME in _decorator_names(node.decorator_list):
            names.add(node.name)
    return names


def check_source(source: str) -> list[tuple[int, int]]:
    """Return ``(lineno, col)`` for every unsanctioned ``to_attr`` prefetch.

    A hit is sanctioned - and excluded from the result - only when the target
    name matches a property in this same file that is genuinely decorated with
    ``PrunedCachedProperty``; see the module docstring for the heuristic's
    documented limits.
    """
    tree = ast.parse(source)
    lines = source.splitlines()
    sanctioned_names = (
        _pruned_cached_property_names(tree) if _imports_pruned_cached_property(tree) else set()
    )
    hits: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _is_prefetch_call(node):
            continue
        for keyword in node.keywords:
            if keyword.arg != "to_attr":
                continue
            target = keyword.value
            if (
                isinstance(target, ast.Constant)
                and isinstance(target.value, str)
                and target.value in sanctioned_names
            ):
                continue
            lineno = target.lineno
            # The suppression may sit on the keyword's own line or on the line
            # opening the Prefetch call, which is where a reader looks first.
            span = {lineno, node.lineno}
            if any(has_suppression(lines[n - 1]) for n in span if 0 < n <= len(lines)):
                continue
            hits.append((lineno, target.col_offset))
    return sorted(hits)


def check_file(path: Path) -> list[tuple[int, int]]:
    """Return the unsanctioned ``to_attr`` prefetches in the file at ``path``."""
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    try:
        return check_source(source)
    except SyntaxError:
        return []


def main(argv: list[str]) -> int:
    """Lint the given files; print each violation and return 1 if any were found."""
    failed = False
    for filename in argv:
        for lineno, col in check_file(Path(filename)):
            failed = True
            print(
                f"{filename}:{lineno}:{col + 1}: unsanctioned `to_attr` prefetch onto an "
                "identity-mapped instance. Django skips a prefetch whose `to_attr` is already "
                "set (a plain attribute or `@property` never signals 'unset' correctly, so "
                "the batched query silently never runs), and the identity map then hands the "
                "same instance to the next request, so this serves stale rows - including "
                "deleted ones, which arrive with a null id (ADR-0263, #3816, #3673). Target a "
                "`PrunedCachedProperty` (`evennia_extensions/cached_property.py`) instead - "
                "it is a real data descriptor and self-heals against pk-nulled zombie rows on "
                "every read. `CachedRowsHandler` (`evennia_extensions/handlers.py`) remains "
                "for the narrow case `PrunedCachedProperty` cannot cover: rows parameterized "
                "per-parent that need their own cache key rather than a plain property "
                "(its one surviving consumer is `CompanionOrderHandler`). Suppress with "
                "`# noqa: PREFETCH_TO_ATTR` plus a reason."
            )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

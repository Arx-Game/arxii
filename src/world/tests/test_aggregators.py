"""Completeness guard for the `world` single-app aggregators (#2906).

`world/models.py` and `world/admin.py` exist because Django only autodiscovers
`<app>.models` / `<app>.admin` once per *installed app* — and the 66
`world.*` sub-packages are about to stop being separate installed apps in
favor of one collapsed `world` app. If a sub-package is ever missing from
one of these aggregators, its models silently vanish from the schema (or its
admin registrations silently vanish) with no error anywhere.

This test walks `world`'s sub-packages with `pkgutil`, independently
discovers which ones actually define a `models` module and (separately) an
`admin` module, and asserts every one of them is imported by the matching
aggregator. It is deliberately NOT derived from `world/models.py` /
`world/admin.py` themselves — that would just check the file agrees with
itself.

**Evidence source is the aggregator's own file text, not `sys.modules`.**
While `world.*` are still separately installed apps (true for this whole
task — see world/apps.py's docstring), Django's own app loading imports
every `world.<pkg>.models` / `world.<pkg>.admin` module during ordinary
`django.setup()`, before this test ever runs — so a `sys.modules` scan would
already show every module as "imported" regardless of what `world/models.py`
/ `world/admin.py` actually contain. An empty aggregator file would pass a
`sys.modules`-based check. Parsing the aggregator's own `import` statements
(via `ast`) is the only check whose result depends on the file's contents.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
import importlib.util
from pathlib import Path
import pkgutil
import re

from django.test import SimpleTestCase

import world

# Sanity floors (#2906): a broken discovery filter (e.g. a typo'd suffix, an
# empty world.__path__) must not make these tests pass by finding nothing.
# 63 of 66 world.* sub-packages currently have a models module (all but
# staff_inbox, predicates, tidings); 61 have an admin module (also missing
# missions, npc_services). Floors sit comfortably below both so ordinary
# future additions/removals don't make this test flaky.
MINIMUM_EXPECTED_MODELS_MODULES = 60
MINIMUM_EXPECTED_ADMIN_MODULES = 55
# world/apps.py's ArxiiConfig.ready() currently calls 20 sub-package ready()
# hooks; floor sits comfortably below so ordinary future additions/removals
# don't make this test flaky (see the two floors above for the same reasoning).
MINIMUM_EXPECTED_READY_MODULES = 15

_WORLD_DIR = Path(world.__file__).resolve().parent
MODELS_AGGREGATOR = _WORLD_DIR / "models.py"
ADMIN_AGGREGATOR = _WORLD_DIR / "admin.py"
APPS_AGGREGATOR = _WORLD_DIR / "apps.py"


def _world_subpackages() -> Iterator[str]:
    """Yield the name of every immediate subpackage of ``world``."""
    for _finder, name, is_pkg in pkgutil.iter_modules(world.__path__):
        if is_pkg:
            yield name


def _has_submodule(subpackage_name: str, submodule_name: str) -> bool:
    """True if ``world.<subpackage_name>.<submodule_name>`` exists.

    Uses ``find_spec`` so discovery never imports (and thus never executes)
    the sub-package's ``models``/``admin`` module — only the aggregator
    files themselves should trigger that.
    """
    dotted = f"world.{subpackage_name}.{submodule_name}"
    try:
        spec = importlib.util.find_spec(dotted)
    except ModuleNotFoundError:
        return False
    return spec is not None


def _imported_leaf_packages_from_source(aggregator_path: Path, suffix: str) -> set[str]:
    """Sub-package names the aggregator FILE actually imports, per its own source.

    Parses ``aggregator_path`` with ``ast`` and collects the ``<name>`` from every
    top-level ``import world.<name>.<suffix>`` statement. This reads the file's
    text — not any runtime import state — so it fails when a line is missing,
    regardless of what's already sitting in ``sys.modules`` from Django's normal
    app loading of the still-separately-installed ``world.*`` apps.

    Args:
        aggregator_path: Path to ``world/models.py`` or ``world/admin.py``.
        suffix: ``"models"`` or ``"admin"``.

    Returns:
        The set of sub-package names imported for that suffix.
    """
    tree = ast.parse(aggregator_path.read_text(encoding="utf-8"), filename=str(aggregator_path))
    pattern = re.compile(rf"^world\.([^.]+)\.{re.escape(suffix)}$")
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Import):
            continue
        for alias in node.names:
            match = pattern.match(alias.name)
            if match:
                found.add(match.group(1))
    return found


class ModelsAggregatorCompletenessTests(SimpleTestCase):
    """`world/models.py` must import every sub-package's `models` module."""

    def test_every_models_module_is_imported(self) -> None:
        discovered = {name for name in _world_subpackages() if _has_submodule(name, "models")}
        self.assertGreaterEqual(
            len(discovered),
            MINIMUM_EXPECTED_MODELS_MODULES,
            f"Only found {len(discovered)} world.*.models modules via pkgutil "
            f"discovery (expected >= {MINIMUM_EXPECTED_MODELS_MODULES}). "
            "Discovery is probably broken rather than the codebase having "
            "shrunk this much.",
        )

        # Importing here is a bonus signal (a listed-but-nonexistent module would
        # raise ImportError) but is NOT the evidence for completeness — see
        # `_imported_leaf_packages_from_source`'s docstring for why.
        import world.models  # noqa: F401

        imported = _imported_leaf_packages_from_source(MODELS_AGGREGATOR, "models")
        missing = discovered - imported
        self.assertFalse(
            missing,
            "world/models.py is missing `import world.<pkg>.models` for: "
            f"{sorted(missing)}. Without it, those models silently vanish "
            "from the schema once world.* stop being separate installed apps.",
        )

    def test_no_stale_imports_for_packages_without_models(self) -> None:
        """Every import in world/models.py corresponds to a real models module."""
        discovered = {name for name in _world_subpackages() if _has_submodule(name, "models")}

        imported = _imported_leaf_packages_from_source(MODELS_AGGREGATOR, "models")
        stale = imported - discovered
        self.assertFalse(
            stale,
            f"world/models.py imports a models module that pkgutil discovery "
            f"can't find: {sorted(stale)}. This aggregator should only import "
            "modules that actually exist.",
        )


class AdminAggregatorCompletenessTests(SimpleTestCase):
    """`world/admin.py` must import every sub-package's `admin` module."""

    def test_every_admin_module_is_imported(self) -> None:
        discovered = {name for name in _world_subpackages() if _has_submodule(name, "admin")}
        self.assertGreaterEqual(
            len(discovered),
            MINIMUM_EXPECTED_ADMIN_MODULES,
            f"Only found {len(discovered)} world.*.admin modules via pkgutil "
            f"discovery (expected >= {MINIMUM_EXPECTED_ADMIN_MODULES}). "
            "Discovery is probably broken rather than the codebase having "
            "shrunk this much.",
        )

        # Importing here is a bonus signal (a listed-but-nonexistent module would
        # raise ImportError) but is NOT the evidence for completeness — see
        # `_imported_leaf_packages_from_source`'s docstring for why.
        import world.admin  # noqa: F401

        imported = _imported_leaf_packages_from_source(ADMIN_AGGREGATOR, "admin")
        missing = discovered - imported
        self.assertFalse(
            missing,
            "world/admin.py is missing `import world.<pkg>.admin` for: "
            f"{sorted(missing)}. Without it, those admin registrations "
            "silently vanish once world.* stop being separate installed apps.",
        )

    def test_no_stale_imports_for_packages_without_admin(self) -> None:
        """Every import in world/admin.py corresponds to a real admin module."""
        discovered = {name for name in _world_subpackages() if _has_submodule(name, "admin")}

        imported = _imported_leaf_packages_from_source(ADMIN_AGGREGATOR, "admin")
        stale = imported - discovered
        self.assertFalse(
            stale,
            f"world/admin.py imports an admin module that pkgutil discovery "
            f"can't find: {sorted(stale)}. This aggregator should only import "
            "modules that actually exist.",
        )


def _has_module_level_ready(subpackage_name: str) -> bool:
    """True if ``world.<subpackage_name>.apps`` defines a module-level ``ready()``.

    Parses the module's source with ``ast`` rather than importing it, matching
    ``_has_submodule``'s no-import discovery discipline above -- discovery must
    never execute a sub-package's ``apps`` module, only the aggregator itself
    should trigger that (via Django's normal app loading).
    """
    dotted = f"world.{subpackage_name}.apps"
    try:
        spec = importlib.util.find_spec(dotted)
    except ModuleNotFoundError:
        return False
    if spec is None or spec.origin is None:
        return False
    source_path = Path(spec.origin)
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    return any(isinstance(node, ast.FunctionDef) and node.name == "ready" for node in tree.body)


def _imported_apps_aliases_from_source(aggregator_path: Path) -> dict[str, str]:
    """Return ``{alias: subpackage_name}`` for every ``import world.<name>.apps as <alias>``."""
    tree = ast.parse(aggregator_path.read_text(encoding="utf-8"), filename=str(aggregator_path))
    pattern = re.compile(r"^world\.([^.]+)\.apps$")
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Import):
            continue
        for alias in node.names:
            match = pattern.match(alias.name)
            if match and alias.asname:
                aliases[alias.asname] = match.group(1)
    return aliases


def _called_ready_packages_from_source(aggregator_path: Path) -> set[str]:
    """Sub-package names whose ``<alias>.ready()`` is actually CALLED in the aggregator.

    Unlike ``_imported_leaf_packages_from_source`` (which only checks that
    world/models.py and world/admin.py *import* each sub-package's module --
    the mere existence of the module is what registers models/admin), an
    ``apps.py`` ``ready()`` hook only runs its registration side effects when
    ``<alias>.ready()`` is actually CALLED, so an import with no call would
    silently skip that sub-package's registration handshake with no error
    anywhere. This checks the call, not just the import.
    """
    aliases = _imported_apps_aliases_from_source(aggregator_path)
    tree = ast.parse(aggregator_path.read_text(encoding="utf-8"), filename=str(aggregator_path))
    called: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "ready"
            and isinstance(func.value, ast.Name)
            and func.value.id in aliases
        ):
            called.add(aliases[func.value.id])
    return called


class ReadyAggregatorCompletenessTests(SimpleTestCase):
    """`world/apps.py`'s ``ArxiiConfig.ready()`` must call every sub-package's `ready()` hook.

    Deliberately does NOT assert on call *order* -- world/apps.py's docstring
    records that the order is load-bearing (a cross-app registration handshake)
    and independently verified, but order is not mechanically derivable from
    sub-package discovery the way "does this hook get called at all" is.
    """

    def test_every_ready_hook_is_called(self) -> None:
        discovered = {name for name in _world_subpackages() if _has_module_level_ready(name)}
        self.assertGreaterEqual(
            len(discovered),
            MINIMUM_EXPECTED_READY_MODULES,
            f"Only found {len(discovered)} world.*.apps modules with a module-level "
            f"ready() via source parsing (expected >= {MINIMUM_EXPECTED_READY_MODULES}). "
            "Discovery is probably broken rather than the codebase having "
            "shrunk this much.",
        )

        called = _called_ready_packages_from_source(APPS_AGGREGATOR)
        missing = discovered - called
        self.assertFalse(
            missing,
            "world/apps.py's ArxiiConfig.ready() is missing a call to `<pkg>.ready()` "
            f"for: {sorted(missing)}. Without it, that sub-package's ready() hook "
            "silently never runs once world.* stop being separate installed apps.",
        )

    def test_no_stale_calls_for_packages_without_ready(self) -> None:
        """Every `<alias>.ready()` call in world/apps.py corresponds to a real hook."""
        discovered = {name for name in _world_subpackages() if _has_module_level_ready(name)}

        called = _called_ready_packages_from_source(APPS_AGGREGATOR)
        stale = called - discovered
        self.assertFalse(
            stale,
            f"world/apps.py calls a ready() hook that source parsing can't find: "
            f"{sorted(stale)}. This aggregator should only call hooks that "
            "actually exist.",
        )

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
"""

from __future__ import annotations

from collections.abc import Iterator
import importlib.util
import pkgutil
import sys

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


def _imported_leaf_packages(suffix: str) -> set[str]:
    """Sub-package names with a `world.<name>.<suffix>` entry in sys.modules."""
    found = set()
    prefix = "world."
    for mod_name in sys.modules:
        if not mod_name.startswith(prefix) or not mod_name.endswith(f".{suffix}"):
            continue
        # Exactly "world.<pkg>.<suffix>" — two dots. Excludes deeper
        # submodules like "world.magic.services.techniques" or
        # "world.progression.admin.kudos_admin".
        if mod_name.count(".") != 2:
            continue
        pkg_name = mod_name[len(prefix) : -len(f".{suffix}")]
        found.add(pkg_name)
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

        import world.models  # noqa: F401 — imported for its sys.modules side effect

        imported = _imported_leaf_packages("models")
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

        import world.models  # noqa: F401 — imported for its sys.modules side effect

        imported = _imported_leaf_packages("models")
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

        import world.admin  # noqa: F401 — imported for its sys.modules side effect

        imported = _imported_leaf_packages("admin")
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

        import world.admin  # noqa: F401 — imported for its sys.modules side effect

        imported = _imported_leaf_packages("admin")
        stale = imported - discovered
        self.assertFalse(
            stale,
            f"world/admin.py imports an admin module that pkgutil discovery "
            f"can't find: {sorted(stale)}. This aggregator should only import "
            "modules that actually exist.",
        )

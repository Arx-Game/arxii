"""Service function registry for the flows system."""

from collections.abc import Callable
import importlib

from flows.helpers.hooks import get_package_hooks

SERVICE_MODULES = [
    "flows.service_functions.actions",
    "flows.service_functions.agriculture",
    "flows.service_functions.communication",
    "flows.service_functions.conditions",
    "flows.service_functions.forms",
    "flows.service_functions.inventory",
    "flows.service_functions.movement",
    "flows.service_functions.outfits",
    "flows.service_functions.perception",
    "flows.service_functions.packages",
]

SERVICE_FUNCTIONS: dict[str, Callable] = {}

_loaded = False


def _ensure_loaded() -> None:
    """Populate ``SERVICE_FUNCTIONS`` from ``SERVICE_MODULES`` hooks, once.

    Uses ``setdefault`` (not ``update``) so a ``register_service_function``
    call made before this first runs (e.g. ``world.apps.ready()`` at Django
    startup) is never clobbered by a same-named hook-loaded entry.
    """
    global _loaded  # noqa: PLW0603 — module-level lazy-load flag
    if _loaded:
        return
    for path in SERVICE_MODULES:
        for key, value in get_package_hooks(path).items():
            SERVICE_FUNCTIONS.setdefault(key, value)
    _loaded = True


def register_service_function(name: str, func: Callable) -> None:
    """Register an out-of-app flow verb under a short name (idempotent).

    Safe to call before or after ``_ensure_loaded`` has run: entries
    registered first are preserved (never overwritten by hook loading);
    entries registered after are inserted directly.
    """
    SERVICE_FUNCTIONS[name] = func


def list_service_functions() -> dict[str, Callable]:
    """Enumerable copy of the registry for the authoring catalog."""
    _ensure_loaded()
    return dict(SERVICE_FUNCTIONS)


def _resolve_dotted_path(name: str) -> Callable:
    """Resolve a fully-qualified dotted-path function reference via importlib.

    For example, ``"world.magic.services.soul_tether.soul_tether_redirect_handler"``
    splits into module ``"world.magic.services.soul_tether"`` and function name
    ``"soul_tether_redirect_handler"``.

    Args:
        name: A dotted Python module path ending in a function name.

    Returns:
        The callable at that path.

    Raises:
        ValueError: If the module cannot be imported or the attribute is absent.
    """
    module_path, _, func_name = name.rpartition(".")
    if not module_path:
        msg = f"Cannot resolve dotted path '{name}': no module component."
        raise ValueError(msg)
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        msg = f"Service function module '{module_path}' could not be imported: {exc}"
        raise ValueError(msg) from exc
    func = getattr(module, func_name, None)
    if func is None or not callable(func):
        msg = f"Service function '{func_name}' not found in module '{module_path}'."
        raise ValueError(msg)
    return func


def get_service_function(name: str) -> Callable:
    """Retrieve a service function by name.

    Two resolution strategies:

    1. Short name (no dots): looked up in the ``SERVICE_FUNCTIONS`` registry
       populated from the ``SERVICE_MODULES`` hooks dictionaries.
    2. Fully-qualified dotted path (contains a dot): resolved via ``importlib``
       so that functions outside the standard hooks registry can be registered
       as flow steps without requiring a module-level hooks dict.

    Args:
        name: The function name or fully-qualified dotted path.

    Returns:
        The callable service function.

    Raises:
        ValueError: If no matching service function exists.
    """
    if "." in name:
        return _resolve_dotted_path(name)

    _ensure_loaded()
    try:
        return SERVICE_FUNCTIONS[name]
    except KeyError as exc:
        msg = f"Service function '{name}' not found."
        raise ValueError(msg) from exc

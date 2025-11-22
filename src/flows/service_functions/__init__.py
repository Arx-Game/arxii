"""Service function registry for the flows system."""

from collections.abc import Callable

from flows.helpers.hooks import get_package_hooks

SERVICE_MODULES = [
    "flows.service_functions.communication",
    "flows.service_functions.movement",
    "flows.service_functions.perception",
    "flows.service_functions.packages",
]

SERVICE_FUNCTIONS: dict[str, Callable] = {}


def _ensure_loaded() -> None:
    if SERVICE_FUNCTIONS:
        return
    for path in SERVICE_MODULES:
        SERVICE_FUNCTIONS.update(get_package_hooks(path))


def get_service_function(name: str) -> Callable:
    """Retrieve a service function by name.

    Args:
        name: The function name.

    Returns:
        The callable service function.

    Raises:
        ValueError: If no matching service function exists.
    """
    _ensure_loaded()
    try:
        return SERVICE_FUNCTIONS[name]
    except KeyError as exc:
        msg = f"Service function '{name}' not found."
        raise ValueError(msg) from exc

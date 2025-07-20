"""Service function registry for the flows system."""

from typing import Callable

from flows.service_functions import perception

# Mapping of available service functions.
SERVICE_FUNCTIONS: dict[str, Callable] = {
    "get_formatted_description": perception.get_formatted_description,
}


def get_service_function(name: str) -> Callable:
    """Retrieve a service function by name.

    Args:
        name: The function name.

    Returns:
        The callable service function.

    Raises:
        ValueError: If no matching service function exists.
    """
    try:
        return SERVICE_FUNCTIONS[name]
    except KeyError as exc:
        raise ValueError(f"Service function '{name}' not found.") from exc

"""Service function registry for the flows system."""

from typing import Callable

from flows.service_functions import communication, movement, perception

# Mapping of available service functions.
SERVICE_FUNCTIONS: dict[str, Callable] = {
    "get_formatted_description": perception.get_formatted_description,
    "send_message": communication.send_message,
    "message_location": communication.message_location,
    "object_has_tag": perception.object_has_tag,
    "append_to_attribute": perception.append_to_attribute,
    "show_inventory": perception.show_inventory,
    "move_object": movement.move_object,
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

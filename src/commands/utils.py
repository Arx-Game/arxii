"""Utility helpers for command handling."""

from __future__ import annotations

from typing import Any


def serialize_cmdset(obj: Any) -> list[dict[str, Any]]:
    """Serialize commands in *obj*'s cmdset using Django serializers.

    Args:
        obj: Object providing a cmdset.

    Returns:
        list[dict[str, Any]]: Command payloads from the object's cmdset.
    """
    from flows.service_functions.serializers import CommandSerializer

    try:
        cmdset = obj.cmdset.current
    except AttributeError:
        return []
    if not cmdset:
        return []

    results = []
    for command in cmdset.commands:
        try:
            serializer = CommandSerializer(command)
            results.append(serializer.data)
        except Exception as e:
            # Log the error but continue with other commands
            import logging

            logging.warning(
                f"Failed to serialize command "
                f"{getattr(command, 'key', 'unknown')}: {e}"
            )
            # Fallback to old method if available
            if hasattr(command, "to_payload"):
                try:
                    results.append(command.to_payload())
                except Exception:
                    pass  # Skip commands that can't be serialized

    return results

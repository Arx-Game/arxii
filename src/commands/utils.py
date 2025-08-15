"""Utility helpers for command handling."""

from __future__ import annotations

from typing import Any

from commands.frontend_types import FrontendDescriptor


def serialize_cmdset(obj: Any) -> list[FrontendDescriptor]:
    """Serialize commands in *obj*'s cmdset using Django serializers.

    Args:
        obj: Object providing a cmdset.

    Returns:
        list[FrontendDescriptor]: Command payloads from the object's cmdset.
    """
    from commands.serializers import CommandSerializer

    try:
        cmdset = obj.cmdset.current
    except AttributeError:
        return []
    if not cmdset:
        return []

    results: list[FrontendDescriptor] = []
    for command in cmdset.commands:
        if not hasattr(command, "to_payload"):
            continue
        try:
            serializer = CommandSerializer(command)
            payload = serializer.data
            results.extend(payload["descriptors"])
        except Exception as e:
            # Log the error but continue with other commands
            import logging

            logging.warning(
                "Failed to serialize command %s: %s",
                getattr(command, "key", "unknown"),
                e,
            )
            # Skip commands that can't be serialized
            continue

    return results

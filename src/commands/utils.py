"""Utility helpers for command handling."""

from __future__ import annotations

from typing import Any


def serialize_cmdset(obj: Any) -> list[dict[str, Any]]:
    """Serialize all commands in *obj*'s current cmdset.

    Args:
        obj: Object providing a cmdset.

    Returns:
        list[dict[str, Any]]: Command payloads from the object's cmdset.
    """
    try:
        cmdset = obj.cmdset.current
    except AttributeError:
        return []
    if not cmdset:
        return []
    return [command.to_payload() for command in cmdset.commands]

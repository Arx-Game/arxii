"""Utility helpers for command handling."""

from __future__ import annotations

import logging
from typing import Any

from commands.frontend_types import FrontendDescriptor
from commands.serializers import CommandSerializer


def serialize_cmdset(obj: Any) -> list[FrontendDescriptor]:
    """Serialize commands in *obj*'s cmdset using Django serializers.

    When the object is a Character with an associated Account, this function
    will include both the character's commands and the account's commands,
    mimicking Evennia's command resolution behavior.

    Args:
        obj: Object providing a cmdset.

    Returns:
        list[FrontendDescriptor]: Command payloads from the object's cmdset and
        associated account cmdset (if any).
    """
    results: list[FrontendDescriptor] = []

    def _serialize_cmdset_commands(cmdset_obj: Any, source_name: str) -> None:
        """Helper to serialize commands from a cmdset object."""
        try:
            cmdset = cmdset_obj.cmdset.current
        except AttributeError:
            return

        if not cmdset:
            return

        for command in cmdset.commands:
            if not hasattr(command, "to_payload"):
                continue

            # Check if the cmdset owner has access to this command
            try:
                if not command.access(cmdset_obj, "cmd"):
                    continue  # Skip commands the user doesn't have access to
            except Exception as e:  # noqa: BLE001
                logging.warning(
                    "Failed to check access for %s command %s: %s",
                    source_name,
                    getattr(command, "key", "unknown"),
                    e,
                )
                continue  # Skip on access check failure

            try:
                serializer = CommandSerializer(command)
                payload = serializer.data
                results.extend(payload["descriptors"])
            except Exception as e:  # noqa: BLE001
                logging.warning(
                    "Failed to serialize %s command %s: %s",
                    source_name,
                    getattr(command, "key", "unknown"),
                    e,
                )
                continue

    # Always serialize the object's own commands
    _serialize_cmdset_commands(obj, "object")

    # For Characters with an associated Account, also include account commands
    # This mimics Evennia's command resolution which merges account + character commands
    if hasattr(obj, "account") and obj.account:
        _serialize_cmdset_commands(obj.account, "account")

    return results

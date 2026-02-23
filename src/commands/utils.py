"""Utility helpers for command handling."""

from __future__ import annotations

import logging
from typing import Any

from commands.frontend_types import FrontendDescriptor
from commands.serializers import CommandSerializer


def _get_cmdset(cmdset_obj: Any) -> Any:
    try:
        cmdset = cmdset_obj.cmdset.current
    except AttributeError:
        return None
    return cmdset or None


def _get_command_key(command: Any) -> str:
    try:
        return command.key
    except AttributeError:
        return "unknown"


def _has_payload(command: Any) -> bool:
    try:
        to_payload = command.to_payload
    except AttributeError:
        return False
    return callable(to_payload)


def _has_command_access(command: Any, cmdset_obj: Any, source_name: str) -> bool:
    try:
        return bool(command.access(cmdset_obj, "cmd"))
    except Exception as e:  # noqa: BLE001
        logging.warning(
            "Failed to check access for %s command %s: %s",
            source_name,
            _get_command_key(command),
            e,
        )
        return False


def _serialize_command(
    command: Any,
    source_name: str,
    results: list[FrontendDescriptor],
) -> None:
    try:
        serializer = CommandSerializer(command)
        payload = serializer.data
        results.extend(payload["descriptors"])
    except Exception as e:  # noqa: BLE001
        logging.warning(
            "Failed to serialize %s command %s: %s",
            source_name,
            _get_command_key(command),
            e,
        )


def _serialize_cmdset_commands(
    cmdset_obj: Any,
    source_name: str,
    results: list[FrontendDescriptor],
) -> None:
    cmdset = _get_cmdset(cmdset_obj)
    if not cmdset:
        return

    for command in cmdset.commands:
        if not _has_payload(command):
            continue
        if not _has_command_access(command, cmdset_obj, source_name):
            continue
        _serialize_command(command, source_name, results)


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

    # Always serialize the object's own commands
    _serialize_cmdset_commands(obj, "object", results)

    # For Characters with an associated Account, also include account commands
    # This mimics Evennia's command resolution which merges account + character commands
    try:
        account = obj.account
    except AttributeError:
        account = None
    if account:
        _serialize_cmdset_commands(account, "account", results)

    return results

"""Utility helpers for command handling."""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings

from commands.frontend_types import FrontendDescriptor
from commands.serializers import CommandSerializer

UNKNOWN_COMMAND_KEY = "unknown"
# Evennia's own no-input / no-match / multi-match handlers. Nobody types them.
SYSTEM_COMMAND_PREFIX = "__"


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
        return UNKNOWN_COMMAND_KEY


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
            exc_info=True,
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
            exc_info=True,
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


def _typed_names(command: Any) -> set[str]:
    """The words a typed line can reach *command* by, compared the way Evennia does.

    Evennia's parser also matches a key or alias with its leading
    ``CMD_IGNORE_PREFIXES`` stripped, so ``@desc`` and ``desc`` reach the same
    command and ``+friend`` answers to ``friend``. Lowercased, as Evennia
    lowercases the typed word before matching.
    """
    try:
        raw_names = [command.key, *command.aliases]
    except AttributeError:
        return set()
    names = set()
    for raw_name in raw_names:
        name = str(raw_name).lower().lstrip(settings.CMD_IGNORE_PREFIXES)
        if name and not name.startswith(SYSTEM_COMMAND_PREFIX):
            names.add(name)
    return names


def _collect_command_names(cmdset_obj: Any, source_name: str, names: set[str]) -> None:
    cmdset = _get_cmdset(cmdset_obj)
    if not cmdset:
        return

    for command in cmdset.commands:
        if not _has_command_access(command, cmdset_obj, source_name):
            continue
        names.update(_typed_names(command))


def command_names(obj: Any) -> list[str]:
    """Every name a line typed as *obj* can reach a command by (#4346).

    The web composer reads this list to tell ``@desc`` (a command this
    character can run) from ``@Nyx`` (someone to address) and from a word that
    is neither. Covers every command *obj* and its account can run, not only
    the ones with a web form, which is all ``serialize_cmdset`` sends. The
    session cmdset (Evennia's ``sessions``) is not read.

    Returns:
        list[str]: Sorted, prefix-free, lowercased names.
    """
    names: set[str] = set()
    _collect_command_names(obj, "object", names)
    try:
        account = obj.account
    except AttributeError:
        account = None
    if account:
        _collect_command_names(account, "account", names)
    return sorted(names)


def commands_frame(obj: Any) -> tuple[list[FrontendDescriptor], dict[str, list[str]]]:
    """The ``commands`` frame for *obj*: its web-form descriptors, and every name it can type.

    Send it as ``session.msg(commands=commands_frame(obj))``. The descriptors are
    the frame's args; the names ride its kwargs as ``names``, which the web
    composer reads (#4346).
    """
    return serialize_cmdset(obj), {"names": command_names(obj)}

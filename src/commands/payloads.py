"""Payload builders for interactive command responses."""

from commands.serializers import CommandDescriptorSerializer
from commands.types import CommandDescriptor
from flows.object_states.base_state import BaseState


def _get_object_commands(
    viewer: BaseState, target: BaseState
) -> list[CommandDescriptor]:
    """Return commands available to ``viewer`` for ``target``.

    Currently includes an ``examine`` command for all targets and a ``get`` command
    when ``viewer`` has permission to move the target.
    """

    commands = [
        CommandDescriptor(
            label="Examine",
            action="look",
            params={"target": target.pk},
            icon="search",
        )
    ]
    if target.can_move(actor=viewer):
        commands.append(
            CommandDescriptor(
                label="Get",
                action="get",
                params={"target": target.pk},
                icon="hand",
            )
        )
    return commands


def build_look_payload(viewer: BaseState, target: BaseState) -> dict:
    """Build a payload for a ``look`` action including available commands."""

    description = target.return_appearance(mode="look", looker=viewer)
    commands = CommandDescriptorSerializer(
        _get_object_commands(viewer, target), many=True
    ).data
    return {"description": description, "commands": commands}


def build_examine_payload(viewer: BaseState, target: BaseState) -> dict:
    """Build a payload for an ``examine`` action including available commands."""

    description = target.return_appearance(mode="examine", looker=viewer)
    commands = CommandDescriptorSerializer(
        _get_object_commands(viewer, target), many=True
    ).data
    return {"description": description, "commands": commands}

"""Evennia builder command overrides with frontend metadata."""

from __future__ import annotations

from typing import ClassVar

from evennia.commands.default.building import (
    CmdDig as EvenniaCmdDig,
    CmdLink as EvenniaCmdLink,
    CmdOpen as EvenniaCmdOpen,
    CmdUnLink as EvenniaCmdUnlink,
)

from commands.frontend import FrontendMetadataMixin
from commands.frontend_types import UsageEntry


class CmdDig(FrontendMetadataMixin, EvenniaCmdDig):
    """Create a new room and optional connecting exits."""

    usage: ClassVar[list[UsageEntry]] = [
        {
            "prompt": "@dig room_name=exit_name, back_exit",
            "params_schema": {
                "room_name": {"type": "string"},
                "exit_name": {"type": "string"},
                "back_exit": {"type": "string", "required": False},
            },
        },
    ]


class CmdOpen(FrontendMetadataMixin, EvenniaCmdOpen):
    """Create an exit from the current room."""

    usage: ClassVar[list[UsageEntry]] = [
        {
            "prompt": "@open exit_name=destination",
            "params_schema": {
                "exit_name": {"type": "string"},
                "destination": {"type": "string"},
            },
        },
    ]


class CmdLink(FrontendMetadataMixin, EvenniaCmdLink):
    """Link an existing exit to a destination."""

    usage: ClassVar[list[UsageEntry]] = [
        {
            "prompt": "@link exit_name=destination",
            "params_schema": {
                "exit_name": {"type": "string"},
                "destination": {"type": "string"},
            },
        },
    ]


class CmdUnlink(FrontendMetadataMixin, EvenniaCmdUnlink):
    """Remove the destination from an exit."""

    usage: ClassVar[list[UsageEntry]] = [
        {
            "prompt": "unlink exit_name",
            "params_schema": {"exit_name": {"type": "string"}},
        },
    ]

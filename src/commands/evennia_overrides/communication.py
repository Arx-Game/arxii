"""Evennia command overrides for communication."""

from commands.command import ArxCommand
from commands.dispatchers import TargetTextDispatcher, TextDispatcher
from commands.handlers.base import BaseHandler


class CmdSay(ArxCommand):
    """Speak aloud to the room."""

    key = "say"
    locks = "cmd:all()"
    dispatchers = [TextDispatcher(r"^(?P<text>.+)$", BaseHandler(flow_name="say"))]


class CmdWhisper(ArxCommand):
    """Whisper something to a target."""

    key = "whisper"
    locks = "cmd:all()"
    dispatchers = [
        TargetTextDispatcher(
            r"^(?P<target>[^=]+)=(?P<text>.+)$",
            BaseHandler(flow_name="whisper"),
        )
    ]


class CmdPose(ArxCommand):
    """Emote an action to the room."""

    key = "pose"
    aliases = ["emote"]
    locks = "cmd:all()"
    dispatchers = [TextDispatcher(r"^(?P<text>.+)$", BaseHandler(flow_name="pose"))]

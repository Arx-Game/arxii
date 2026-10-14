"""The option keys and type values a ``text`` frame's kwargs may carry.

Every layer that emits or reads a ``text`` frame shares this vocabulary: the
action and flow layers that tag a compatibility line, the typeclasses that
announce a puppet lifecycle milestone, the session inputfuncs that set a
per-window option, and the web client that decides what to render. It lives in
``core`` because none of it is protocol-specific and ``flows`` sits below
``web``; the websocket frame names themselves stay in
``web.webclient.message_types``.
"""

from enum import Enum


class TextFrameOption(str, Enum):
    """Keys a ``text`` frame's kwargs may carry beyond ``type`` (#3856, #3857, #3933)."""

    CONSOLE = "console"
    INTERACTION_ECHO = "interaction_echo"
    ON_ENTRY = "on_entry"


class TextFrameType(str, Enum):
    """``type`` values a ``text`` frame carries that are not an InteractionMode (#3933)."""

    # A puppet-lifecycle milestone rather than story text (#3933); telnet
    # prints the line and ignores the options.
    LIFECYCLE = "lifecycle"
    ARRIVE = "arrive"
    # A departure. Evennia's own movement broadcast sends its move_type, `move`;
    # the logout line is a departure too and uses the same kind (#4336).
    MOVE = "move"
    # A look result and a refusal (#3856's feed kinds); the arrival look sends
    # them outside a command (#4329), where ArxCommand.send_result is not in reach.
    LOOK = "look"
    ERROR = "error"


class LifecycleEvent(str, Enum):
    """``event`` values on a ``type: "lifecycle"`` text frame (#3933)."""

    BECOME = "become"
    SWITCH = "switch"
    PUPPET = "puppet"

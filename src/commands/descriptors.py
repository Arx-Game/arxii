"""Serializable descriptors for commands and dispatchers."""

from dataclasses import asdict, dataclass

from commands.frontend_types import FrontendDescriptor


@dataclass
class DispatcherDescriptor:
    """Lightweight description of a command dispatcher.

    Attributes:
        syntax: Human readable syntax string for dispatcher.
        context: Context where dispatcher is valid, e.g., ``room`` or ``object``.
    """

    syntax: str
    context: str

    def to_dict(self) -> dict[str, str]:
        """Serialize descriptor into a dictionary."""
        return asdict(self)


@dataclass
class CommandDescriptor:
    """Serializable description of a command.

    Attributes:
        key: Primary command name.
        aliases: Alternate command names.
        dispatchers: Descriptors for the command's dispatchers.
        descriptors: Frontend usage patterns for the command.
    """

    key: str
    aliases: list[str]
    dispatchers: list[DispatcherDescriptor]
    descriptors: list[FrontendDescriptor]

    def to_dict(self) -> dict[str, object]:
        """Serialize descriptor into a dictionary."""
        return {
            "key": self.key,
            "aliases": self.aliases,
            "dispatchers": [disp.to_dict() for disp in self.dispatchers],
            "descriptors": self.descriptors,
        }

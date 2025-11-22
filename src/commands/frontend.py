"""Helpers for exposing command usage to the frontend."""

from typing import ClassVar

from commands.descriptors import CommandDescriptor
from commands.frontend_types import FrontendDescriptor, ParamSchema, UsageEntry


class FrontendMetadataMixin:
    """Serialize Evennia command usage without rewriting it.

    Evennia's default commands don't use Arx's dispatcher system, so they lack
    structured metadata describing how the command should be presented in the
    client. Subclassing this mixin lets legacy commands declare a ``usage`` class
    attribute that lists supported syntax patterns. Each entry contains a
    ``prompt`` string and a ``params_schema`` mapping. The :meth:`to_payload`
    method returns these entries alongside basic command information, allowing
    the frontend to render forms or quick actions for the command without
    converting it into the new dispatcher-based style.
    """

    # Descriptions of usage patterns; override in subclasses.
    key: str
    usage: ClassVar[list[UsageEntry]] = []

    def to_payload(self, context: str | None = None) -> dict:
        """Return serialized metadata for the command.

        Args:
            context: Unused context filter for API compatibility.

        Returns:
            Dict: Serialized command descriptor including usage patterns.
        """
        descriptors: list[FrontendDescriptor] = []
        for entry in self.usage:
            params: dict[str, ParamSchema] = entry.get("params_schema", {})
            descriptors.append(
                FrontendDescriptor(
                    action=self.key,
                    prompt=entry.get("prompt", ""),
                    params_schema=params,
                    icon=entry.get("icon", ""),
                ),
            )
        descriptor = CommandDescriptor(
            key=self.key,
            aliases=sorted(getattr(self, "aliases", [])),
            dispatchers=[],
            descriptors=descriptors,
        )
        return descriptor.to_dict()

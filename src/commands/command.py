"""Commands — thin telnet compatibility layer that delegates to Actions."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from evennia.commands.command import Command

from commands.consts import HelpFileViewMode
from commands.descriptors import CommandDescriptor
from commands.exceptions import CommandError
from commands.frontend_types import FrontendDescriptor
from commands.types import Kwargs

if TYPE_CHECKING:
    from actions.base import Action


class ArxCommand(Command):
    """Base command class for Arx II.

    Commands are a thin telnet compatibility layer. They parse text input
    and delegate to :class:`Action` instances. The web path bypasses
    commands entirely and calls ``action.run()`` directly.

    Subclasses set ``action`` and override ``resolve_action_args()`` to
    translate telnet text into keyword arguments for the action.
    """

    # The action this command delegates to. Set by subclass.
    action: Action | None = None

    # Help text
    title = ""
    description = ""
    base_ascii_template = "{title}\n\n{syntax}\n\n{description}"

    # Values populated by Evennia's cmdhandler
    caller: Any = None
    cmdname: str | None = None
    raw_cmdname: str | None = None
    args: str | None = None
    cmdset: Any = None
    cmdset_providers: Any = None
    session: Any = None
    account: Any = None
    raw_string: str | None = None
    obj: Any | None = None

    def msg(self, *args: object, **kwargs: Kwargs) -> None:
        """Send a message to the caller."""
        self.caller.msg(*args, **kwargs)

    def resolve_action_args(self) -> dict[str, Any]:
        """Parse telnet text into kwargs for ``action.run()``.

        Override in subclasses that need to resolve targets or parse text
        from the command arguments.

        Returns:
            Keyword arguments to pass to the action.

        Raises:
            CommandError: If the input cannot be parsed.
        """
        return {}

    def require_args(self, empty_msg: str) -> str:
        """Return stripped ``self.args``; raise ``CommandError`` if blank."""
        args = (self.args or "").strip()
        if not args:
            raise CommandError(empty_msg)
        return args

    def search_or_raise(
        self,
        name: str,
        *,
        location: object | None = None,
        not_found_msg: str | None = None,
    ) -> Any:
        """Search for ``name`` near the caller; raise ``CommandError`` if not found.

        Args:
            name: The text to search for.
            location: Restrict search to this object's contents
                (default: caller's room).
            not_found_msg: Override the default
                ``"Could not find '<name>'."`` message.
        """
        if location is None:
            target = self.caller.search(name)
        else:
            target = self.caller.search(name, location=location)
        if not target:
            msg = not_found_msg or f"Could not find '{name}'."
            raise CommandError(msg)
        return target

    def parse_two_args(
        self,
        connector: str,
        *,
        empty_msg: str,
        usage_msg: str,
    ) -> tuple[str, str]:
        """Parse ``"a <connector> b"`` from ``self.args``.

        Returns:
            ``(a, b)`` as stripped strings.

        Raises:
            CommandError: If args are blank (with ``empty_msg``) or do not
                match the expected ``a <connector> b`` shape (with
                ``usage_msg``).
        """
        args = self.require_args(empty_msg)
        match = re.match(
            rf"^(.+?)\s+{re.escape(connector)}\s+(.+)$",
            args,
            flags=re.IGNORECASE,
        )
        if not match:
            raise CommandError(usage_msg)
        return match.group(1).strip(), match.group(2).strip()

    def func(self) -> None:
        """Execute the command by delegating to the action.

        Parses arguments via :meth:`resolve_action_args`, calls
        ``action.run()``, and sends results to the caller.
        """
        if self.action is None:
            self.msg("This command is not available.")
            return

        try:
            kwargs = self.resolve_action_args()
            result = self.action.run(actor=self.caller, **kwargs)
            if result.message:
                self.msg(result.message)
        except CommandError as err:
            self.msg(str(err))
            self.msg(
                command_error={
                    "error": str(err),
                    "command": self.raw_string or "",
                },
            )

    def get_help(
        self,
        caller: Any,
        cmdset: Any,
        mode: HelpFileViewMode = HelpFileViewMode.TEXT,
    ) -> str:
        """Return help text for this command."""
        title = self.title or self.key
        description = self.description or (self.__doc__ or "").strip()
        return self.base_ascii_template.format(
            title=title,
            syntax=self.key,
            description=description,
        )

    def to_payload(self, context: str | None = None) -> dict[str, Any]:
        """Serialize command metadata for the frontend.

        Builds a payload from the action's metadata when available.
        """
        aliases = sorted(self.aliases) if self.aliases else []
        descriptors: list[FrontendDescriptor] = []

        if self.action is not None:
            descriptors.append(
                FrontendDescriptor(
                    action=self.action.key,
                    prompt=self.key,
                    params_schema={},
                    icon=self.action.icon,
                ),
            )

        descriptor = CommandDescriptor(
            key=self.key,
            aliases=aliases,
            dispatchers=[],
            descriptors=descriptors,
        )
        return descriptor.to_dict()

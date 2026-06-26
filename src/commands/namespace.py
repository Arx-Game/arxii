"""Shared base for thin ``ArxCommand`` subverb namespaces.

Commands that expose several related actions under one leading keyword
(encounter, story, etc.) use the same routing boilerplate.  This module
keeps that routing in one place so each concrete command only declares its
subverbs and handlers.
"""

from __future__ import annotations

from typing import Any

from commands.command import ArxCommand
from commands.exceptions import CommandError


class ArxNamespaceCommand(ArxCommand):
    """Base for telnet commands that route ``<keyword> <subverb> ...``.

    Subclasses provide ``_USAGE`` (printed when the command is bare or the
    subverb is unknown) and ``_SUBVERB_HANDLERS`` mapping subverb strings to
    handler method names.  Each handler receives the remainder of the command
    line as a single string.  ``CommandError`` raised by a handler is forwarded
    to the caller.
    """

    action = None  # Routed manually by subverb.
    _USAGE: str = ""
    _SUBVERB_HANDLERS: dict[str, str] = {}

    def func(self) -> None:
        """Route the leading subverb to the appropriate handler."""
        raw = (self.args or "").strip()
        if not raw:
            self.msg(self._USAGE)
            return

        parts = raw.split(maxsplit=1)
        subverb = parts[0].lower()
        rest = parts[1].strip() if len(parts) > 1 else ""

        handler_name = self._SUBVERB_HANDLERS.get(subverb)
        if handler_name is None:
            self.msg(self._USAGE)
            return

        try:
            getattr(self, handler_name)(rest)
        except CommandError as err:
            self.msg(str(err))

    def _run_action(self, action_cls: type[Any], **kwargs: Any) -> None:
        """Instantiate *action_cls* and forward the result message."""
        result = action_cls().run(actor=self.caller, **kwargs)
        if result.message:
            self.msg(result.message)

    def _require_arg(self, value: str, usage: str) -> str:
        """Return a stripped token or raise CommandError with *usage*."""
        token = value.strip()
        if not token:
            raise CommandError(usage)
        return token

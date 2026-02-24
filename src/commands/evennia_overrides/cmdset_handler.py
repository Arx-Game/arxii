"""Custom CmdSetHandler that notifies sessions on updates."""

from typing import Any, cast

from evennia.commands.cmdsethandler import CmdSetHandler as EvenniaCmdSetHandler
from twisted.internet import reactor

from commands.utils import serialize_cmdset


class CmdSetHandler(EvenniaCmdSetHandler):
    """CmdSetHandler that sends updates to attached sessions."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._update_handle = None

    def _send_update(self) -> None:
        """Send serialized commands to all sessions."""
        self._update_handle = None
        payload = serialize_cmdset(self.obj)
        for session in self.obj.sessions.all():
            session.msg(commands=(payload, {}))

    def _schedule_update(self) -> None:
        """Debounce cmdset updates to only send once."""
        if self._update_handle is None:
            self._update_handle = cast(Any, reactor).callLater(0, self._send_update)

    def add(self, *args: Any, **kwargs: Any) -> Any:
        """Add a cmdset and schedule a session update."""
        result = super().add(*args, **kwargs)
        self._schedule_update()
        return result

    def remove(self, *args: Any, **kwargs: Any) -> Any:
        """Remove a cmdset and schedule a session update."""
        result = super().remove(*args, **kwargs)
        self._schedule_update()
        return result

    def clear(self) -> Any:
        """Clear cmdsets and schedule a session update."""
        result = super().clear()
        self._schedule_update()
        return result

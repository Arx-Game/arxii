"""Custom CmdSetHandler that notifies sessions on updates."""

from evennia.commands.cmdsethandler import CmdSetHandler as EvenniaCmdSetHandler
from twisted.internet import reactor

from commands.utils import serialize_cmdset


class CmdSetHandler(EvenniaCmdSetHandler):
    """CmdSetHandler that sends updates to attached sessions."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._update_handle = None

    def _send_update(self):
        """Send serialized commands to all sessions."""
        self._update_handle = None
        payload = serialize_cmdset(self.obj)
        for session in self.obj.sessions.all():
            session.msg(commands=(payload, {}))

    def _schedule_update(self):
        """Debounce cmdset updates to only send once."""
        if self._update_handle is None:
            self._update_handle = reactor.callLater(0, self._send_update)  # type: ignore[attr-defined]

    def add(self, *args, **kwargs):
        """Add a cmdset and schedule a session update."""
        result = super().add(*args, **kwargs)
        self._schedule_update()
        return result

    def remove(self, *args, **kwargs):
        """Remove a cmdset and schedule a session update."""
        result = super().remove(*args, **kwargs)
        self._schedule_update()
        return result

    def clear(self):
        """Clear cmdsets and schedule a session update."""
        result = super().clear()
        self._schedule_update()
        return result

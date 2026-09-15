"""
ServerSession

The serversession is the Server-side in-memory representation of a
user connecting to the game.  Evennia manages one Session per
connection to the game. So a user logged into the game with multiple
clients (if Evennia is configured to allow that) will have multiple
sessions tied to one Account object. All communication between Evennia
and the real-world user goes through the Session(s) associated with that user.

It should be noted that modifying the Session object is not usually
necessary except for the most custom and exotic designs - and even
then it might be enough to just add custom session-level commands to
the SessionCmdSet instead.

This module is not normally called. To tell Evennia to use the class
in this module instead of the default one, add the following to your
settings file:

    SERVER_SESSION_CLASS = "server.conf.serversession.ServerSession"

"""

from evennia.server.serversession import ServerSession as BaseServerSession

# The send-command whose options the console tag rides on.
TEXT_KEY = "text"


class ServerSession(BaseServerSession):
    """
    This class represents a player's session and is a template for
    individual protocols to communicate with Evennia.

    Each account gets one or more sessions assigned to them whenever they connect
    to the game server. All communication between game and account goes
    through their session(s).

    Wired by ``settings.SERVER_SESSION_CLASS``. Its one override tags the
    output of a staff console line (#3857): while ``ndb.console_capture`` is
    set (the ``text`` inputfunc sets it for the duration of a ``console=True``
    line), every ``text`` frame leaving this session carries
    ``{"console": True}`` in its options, so the web client can keep it out
    of the player-facing column.
    """

    def data_out(self, **kwargs):
        """Tag a ``text`` frame with the console option while a console line runs."""
        # An unset ndb attribute reads as None, so no getattr default is needed.
        if self.ndb.console_capture and TEXT_KEY in kwargs:
            kwargs[TEXT_KEY] = _tag_console(kwargs[TEXT_KEY])
        super().data_out(**kwargs)


def _tag_console(text: object) -> object:
    """Return ``text`` in the tuple form with ``console`` merged into its options.

    Evennia accepts a bare string or ``(string, {options})``; the session handler
    turns the dict into the frame's kwargs, which is where the client reads it.
    An existing option, such as the ``type`` a command sets (#3856), is kept.
    """
    if isinstance(text, tuple):
        body = text[0] if text else ""
        options = dict(text[1]) if len(text) > 1 and isinstance(text[1], dict) else {}
    else:
        body, options = text, {}
    options["console"] = True
    return (body, options)

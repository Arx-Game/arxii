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

# The send-command whose options carry every per-session text-frame tag.
TEXT_KEY = "text"


class ServerSession(BaseServerSession):
    """
    This class represents a player's session and is a template for
    individual protocols to communicate with Evennia.

    Each account gets one or more sessions assigned to them whenever they connect
    to the game server. All communication between game and account goes
    through their session(s).

    Wired by ``settings.SERVER_SESSION_CLASS``. Its one override merges per-session
    text-frame options: while ``ndb.text_frame_options`` holds a dict, every
    ``text`` frame leaving this session carries those options merged into its own.
    The ``text`` inputfunc sets ``{"console": True}`` for a staff console line
    (#3857); ``Character.at_post_puppet`` sets ``{"on_entry": True}`` around the
    joining session's look (#3933). The frame's own keys win over the session's.
    """

    def data_out(self, **kwargs):
        """Merge the session's text-frame options into a ``text`` frame."""
        # An unset ndb attribute reads as None, so no getattr default is needed.
        options = self.ndb.text_frame_options
        if options and TEXT_KEY in kwargs:
            kwargs[TEXT_KEY] = merge_text_options(kwargs[TEXT_KEY], options)
        super().data_out(**kwargs)


def merge_text_options(text: object, options: dict[str, object]) -> object:
    """Return ``text`` in tuple form with ``options`` merged in; the frame's own keys win.

    Evennia accepts a bare string or ``(string, {options})``; the session handler
    turns the dict into the frame's kwargs, which is where the client reads it.
    """
    if isinstance(text, tuple):
        body = text[0] if text else ""
        existing = dict(text[1]) if len(text) > 1 and isinstance(text[1], dict) else {}
    else:
        body, existing = text, {}
    return (body, {**options, **existing})

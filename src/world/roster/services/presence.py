"""A character's live presence, read from the sessions that puppet it (#4321).

Presence is a server fact. A browser tab knows only about the socket it opened
itself, so a second tab, or a second computer, used to say "Not in the world"
about a character standing in a room. These two functions are what the roster
``mine`` payload and the disconnect endpoint read, and they read Evennia's own
session handler, never a column: a character is in the world while at least one
session puppets it, and nowhere else is that recorded.

Both run inside the Evennia Server process, where the web server lives, so the
``ObjectSessionHandler`` on a character (``character.sessions``) resolves against
the live ``SESSION_HANDLER``. ``world.scenes.presence.who_listing`` reads the same
handler from a view for the Who tab.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

#: The close reason handed to every session a disconnect-everywhere closes. The
#: web client reads it as leaving the world (``SERVER_QUIT_CLOSE_REASONS`` in
#: ``frontend/src/hooks/types.ts``, the set Evennia's ``CmdQuit`` gives), so a
#: tab whose socket is closed this way ends its session and goes to the Hall
#: exactly as a typed ``quit`` does. No new reason, no new frame type.
QUIT_REASON = "quit"


def session_count(character: ObjectDB) -> int:  # noqa: OBJECTDB_PARAM
    """How many sessions puppet ``character`` right now.

    ObjectDB on purpose: the sessions hang off Evennia's object, and the roster
    serializer hands in ``character_sheet.character`` straight from the row.
    """
    return character.sessions.count()


def room_name(character: ObjectDB) -> str | None:  # noqa: OBJECTDB_PARAM
    """The name of the room ``character`` stands in while puppeted, else None.

    ObjectDB on purpose, for the same reason as ``session_count``. An
    unpuppeted character may still hold a location (Evennia leaves it there
    until the next puppet moves it), and that is not presence, so the room is
    reported only while a session puppets the character.
    """
    if not character.sessions.count():
        return None
    location = character.location
    return location.key if location is not None else None


def disconnect_everywhere(character: ObjectDB) -> int:  # noqa: OBJECTDB_PARAM
    """Close every session puppeting ``character`` and return how many closed.

    ObjectDB on purpose, for the same reason as ``session_count``. Each session
    is closed with ``QUIT_REASON``; the last one going is what unpuppets the
    character (Evennia's own rule, the same one a typed ``quit`` relies on), so
    the character leaves the grid rather than standing there unpiloted.
    """
    from evennia import SESSION_HANDLER  # noqa: PLC0415

    sessions = list(character.sessions.all())
    for session in sessions:
        SESSION_HANDLER.disconnect(session, reason=QUIT_REASON)
    return len(sessions)

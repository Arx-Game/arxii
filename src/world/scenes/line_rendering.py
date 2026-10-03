"""The one formatter that puts the actor into a line (#3858, ADR-0299).

A pose or a say is a whole sentence with its actor in it, on the web and on
telnet alike. The recorded ``content`` stays what the player typed; this module
renders the line from it at display time, given the name the viewer should see
and the mode. Both protocols call it, so the sentence shape can never drift
between them.

Two lead-ins (#4128): a whisper typed as an emote (``whisper Nyx=:leans in``)
reads ``Quietly, Tehom leans in``, and anything said or posed at a place reads
``At the long table, ...`` first, so a reader knows where without a label.
"""

from __future__ import annotations

from world.scenes.constants import InteractionMode

_SPEECH_VERBS: dict[str, str] = {
    InteractionMode.SAY: "says",
    InteractionMode.WHISPER: "whispers",
    InteractionMode.MUTTER: "mutters",
    InteractionMode.SHOUT: "shouts",
}

# A pose that opens with one of these glues straight onto the name: ``'s cloak``
# renders ``Apostate's cloak``, ``, tired, sits`` renders ``Apostate, tired, sits``.
_SEMIPOSE_OPENERS = ("'", "’", ",")

# A whisper whose content opens with this is an emote, not speech.
_EMOTE_MARK = ":"
_WHISPER_EMOTE_LEAD_IN = "Quietly, "


def _already_named(name: str, content: str) -> bool:
    """Whether ``content`` already opens with ``name`` as a whole word.

    A pose typed as ``Apostate looks up.`` keeps its author's own placement of
    the name instead of gaining a second one (spec decision 6). A bare name with
    nothing after it, or a longer name sharing the prefix (``Rose`` vs
    ``Rosemary``), does not count.
    """
    if not name or not content.startswith(name):
        return False
    rest = content[len(name) :]
    return bool(rest) and (rest[0].isspace() or rest[0] in _SEMIPOSE_OPENERS)


def _pose_line(name: str, content: str, actor_name: str) -> str:
    """``name content``, with semipose glue; a pose already naming the actor is left alone."""
    if not content or _already_named(actor_name, content):
        return content
    glue = "" if content.startswith(_SEMIPOSE_OPENERS) else " "
    return f"{name}{glue}{content}"


def _at_place(line: str, place_name: str | None) -> str:
    """Open ``line`` with the place it was said at; an empty line stays empty."""
    if not place_name or not line:
        return line
    return f"At {place_name}, {line}"


def render_line(  # noqa: PLR0913 - the channel knobs of one pure formatter; cohesive
    name: str,
    mode: str,
    content: str,
    *,
    language_name: str | None = None,
    place_name: str | None = None,
    actor_name: str | None = None,
) -> str:
    """Render the line a viewer reads for ``content`` said or posed by ``name``.

    ``name`` is whatever the caller's channel resolves for that viewer: the
    persona's name (or its mask, #1109) on the web, ``{caller}`` for
    ``msg_contents``' per-looker names on telnet, the companion's name for a
    companion pose (#3294). ``content`` is the per-viewer content the channel
    already produced, so a comprehension-garbled say (#2993) reads as a garbled
    sentence rather than a bare fragment. ``place_name`` is the place the line
    was said at, when it was said at one (tabletalk). ``actor_name`` is the name
    an already-named pose would open with; it defaults to ``name`` and exists for
    telnet, whose ``name`` is the ``{caller}`` placeholder and so could never match
    the text a player typed (``Bram deals.`` must not read ``Bram Bram deals.``).

    - pose: ``name content`` (semipose glue; an already-named pose is left alone)
    - whisper opening with ``:``: ``Quietly, name content`` (the emote form)
    - say, whisper, mutter, shout: ``name verbs[ in language], "content"``
    - any of those at a place: ``At place, `` before the sentence
    - anything else (emit, action, outcome): ``content`` untouched
    """
    named = actor_name if actor_name is not None else name
    if mode == InteractionMode.WHISPER and content.startswith(_EMOTE_MARK):
        emote = _pose_line(name, content[len(_EMOTE_MARK) :].lstrip(), named)
        return _at_place(_WHISPER_EMOTE_LEAD_IN + emote if emote else "", place_name)
    if mode == InteractionMode.POSE:
        return _at_place(_pose_line(name, content, named), place_name)
    verb = _SPEECH_VERBS.get(mode)
    if verb is None:
        return content
    spoken_in = f" in {language_name}" if language_name else ""
    return _at_place(f'{name} {verb}{spoken_in}, "{content}"', place_name)

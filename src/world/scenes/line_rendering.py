"""The one formatter that puts the actor into a line (#3858, ADR-0299).

A pose or a say is a whole sentence with its actor in it, on the web and on
telnet alike. The recorded ``content`` stays what the player typed; this module
renders the line from it at display time, given the name the viewer should see
and the mode. Both protocols call it, so the sentence shape can never drift
between them.
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


def render_line(
    name: str,
    mode: str,
    content: str,
    *,
    language_name: str | None = None,
) -> str:
    """Render the line a viewer reads for ``content`` said or posed by ``name``.

    ``name`` is whatever the caller's channel resolves for that viewer: the
    persona's name (or its mask, #1109) on the web, ``{caller}`` for
    ``msg_contents``' per-looker names on telnet, the companion's name for a
    companion pose (#3294). ``content`` is the per-viewer content the channel
    already produced, so a comprehension-garbled say (#2993) reads as a garbled
    sentence rather than a bare fragment.

    - pose: ``name content`` (semipose glue; an already-named pose is left alone)
    - say, whisper, mutter, shout: ``name verbs[ in language], "content"``
    - anything else (emit, action, outcome): ``content`` untouched
    """
    if mode == InteractionMode.POSE:
        if not content or _already_named(name, content):
            return content
        glue = "" if content.startswith(_SEMIPOSE_OPENERS) else " "
        return f"{name}{glue}{content}"
    verb = _SPEECH_VERBS.get(mode)
    if verb is None:
        return content
    spoken_in = f" in {language_name}" if language_name else ""
    return f'{name} {verb}{spoken_in}, "{content}"'

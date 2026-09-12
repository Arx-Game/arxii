"""One reachability predicate: can this persona receive content of this shape.

This is decision 3 of the approved #3787 spec: "you can only name or answer
someone in a venue where they are available." It is one rule, stated in two
places - the reply refusal (``world.scenes.thread_services``) and the tagging/
naming refusal (a later task). This module is the shared predicate both read.

``persona_can_receive`` answers a LIVE spatial-presence question - is this
persona standing somewhere this content actually reaches, right now - which is
a different question from ``InteractionQuerySet.visible_to``
(``world/scenes/managers.py``). ``visible_to`` decides whether an ACCOUNT may
read an interaction already in the log (a privacy-tier / pinned-party
question, evaluated against history); it never checks where a character is
standing. The two do share one thing: the same broadcast-vs-directed shape
classification that ``visible_to``'s ``room_heard`` clause uses (place is
None, no explicit receivers, not a whisper). This module mirrors that
classification on purpose so the two rules never quietly diverge, then asks
presence instead of read-access for each shape:

- whisper or an explicit receiver list -> reachable only if the persona is one
  of the receivers (the directed party).
- a ``Place`` -> reachable only if the persona is currently present at that
  Place (and, when the Place-scoped row also names explicit receivers, only if
  the persona is one of them too - a private aside at a table).
- otherwise (room-heard: no place, no receivers, not a whisper) -> reachable
  if the persona's character is physically present in the scene's room.

Do NOT implement audience promotion here or at any caller: a persona who is
unreachable stays unreachable. The spec's decision 2 rejects widening a
private venue's audience to fit; the venue name in ``UnreachableError.venue_hint``
tells the player where to go instead.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from world.scenes.constants import InteractionMode
from world.scenes.place_models import Place, PlacePresence

if TYPE_CHECKING:
    from world.scenes.models import Persona, Scene


def _receiver_ids(receivers: Iterable[Persona] | Iterable[int] | None) -> frozenset[int] | None:
    """Normalize a receivers argument (personas or ids) to a set of persona ids."""
    if receivers is None:
        return None
    ids: set[int] = set()
    for item in receivers:
        ids.add(item if isinstance(item, int) else item.pk)
    return frozenset(ids)


def persona_can_receive(
    persona: Persona,
    *,
    scene: Scene | None,
    place: Place | None,
    receivers: Iterable[Persona] | Iterable[int] | None,
    mode: str,
) -> bool:
    """Return whether ``persona`` can receive content with this audience shape.

    ``scene``/``place``/``receivers``/``mode`` describe the SHAPE of the content
    being named or answered (mirrors ``Interaction``'s own fields), not a
    specific persisted row - callers may check a hypothetical shape before
    anything is written.
    """
    receiver_ids = _receiver_ids(receivers)

    if mode == InteractionMode.WHISPER:
        # A whisper is directed by construction: reachable only for its party.
        return receiver_ids is not None and persona.pk in receiver_ids

    if place is not None:
        present_at_place = PlacePresence.objects.filter(
            place_id=place.pk, persona_id=persona.pk
        ).exists()
        if not present_at_place:
            return False
        # A Place row may ALSO narrow to explicit receivers (a private aside at
        # the table) - being at the place is necessary but not sufficient then.
        return receiver_ids is None or persona.pk in receiver_ids

    if receiver_ids is not None:
        # Directed without a place (e.g. a targeted mutter in the open room).
        return persona.pk in receiver_ids

    # Room-heard: no place, no explicit receivers, not a whisper - broadcast to
    # whoever is physically present in the scene's room right now.
    if scene is None or scene.location is None:
        return False
    return scene.has_character_present({persona.character_sheet_id})


class UnreachableError(Exception):
    """Raised when one or more personas cannot receive content in a given venue.

    ``personas`` are the ones that failed ``persona_can_receive``; ``venue_hint``
    is the player-facing sentence telling them how to reach a venue where they
    can (e.g. leave a Place). Consumed by the tagging/naming refusal; the reply
    refusal keeps its own ``InteractionThreadError`` (a different HTTP contract
    the frontend already matches on, see #3760).
    """

    def __init__(self, personas: list[Persona], venue_hint: str) -> None:
        self.personas = personas
        self.venue_hint = venue_hint
        super().__init__(venue_hint)

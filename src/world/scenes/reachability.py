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
question, evaluated against history, with staff/GM read exceptions for
scene administration); it never checks where a character is standing. The
two do share one thing: the same broadcast-vs-directed shape classification
that ``visible_to``'s ``room_heard`` clause uses (place is None, no explicit
receivers, not a whisper). This module mirrors that classification on
purpose so the two rules never quietly diverge on WHICH shapes count as
broadcast vs. directed, then asks presence instead of read-access for each
shape:

- whisper or an explicit receiver list -> reachable only if the persona is one
  of the receivers (the directed party). Escalating an interaction's
  ``visibility`` (``mark_very_private``) never touches these recorded rows,
  so this branch is visibility-independent - the audience was already this
  narrow.
- a ``Place`` -> reachable only if the persona is currently present at that
  Place (and, when the Place-scoped row also names explicit receivers, only if
  the persona is one of them too - a private aside at a table). Also
  visibility-independent for the same reason: a Place is never ``room_heard``
  in ``visible_to`` either way, so escalating it changes only who may read the
  log afterward, not who was ever the live audience.
- otherwise (room-heard: no place, no receivers, not a whisper) -> reachable
  if ``visibility`` is ``DEFAULT`` AND the persona's character is physically
  present in the room -- the scene's room when a ``Scene`` is attached, or the
  caller-supplied ``location`` when it is not (``Interaction.scene`` is
  nullable; a room-heard pose need not belong to one). Neither available ->
  refuses; there is no room to test presence against. A receiver-less
  broadcast pose can be escalated after the fact (``mark_very_private``) to
  ``VERY_PRIVATE`` or ``PERCEIVED_ONLY`` with no shape change at all (same
  ``place``/``receivers`` fields) - ``visible_to``'s ``room_heard`` clause
  requires ``visibility=DEFAULT`` explicitly, so an escalated row stops being
  broadcast-readable to anyone but its writer's own account. Presence alone
  cannot answer reachability here without checking ``visibility`` too, or it
  would call someone "reachable" for a row that has since gone private.

**Deliberate divergence from ``visible_to`` (decision, not an oversight):**
this predicate does NOT mirror ``visible_to``'s staff/GM read exceptions for
``PERCEIVED_ONLY`` (both remain visible for scene-log administration) or
admit any exception for ``VERY_PRIVATE`` (which ``visible_to`` also refuses
outright, staff included). Reachability answers "can I address this persona
right now" - a narrative-presence question about where a character's body
is - not "may this account read the log row for oversight," which is an
administrative permission unrelated to where anyone is standing. So an
escalated room-heard row (``PERCEIVED_ONLY`` or ``VERY_PRIVATE``, no recorded
receivers) is unreachable to EVERYONE through this predicate, including a
staff account or the scene's GM - there is no persona-level "staff" concept
for this function to special-case, and manufacturing one here would let a GM
who was never actually present get treated as addressable, which is not what
"in a venue where they are available" means.

Do NOT implement audience promotion here or at any caller: a persona who is
unreachable stays unreachable. The spec's decision 2 rejects widening a
private venue's audience to fit; the venue name in ``UnreachableError.venue_hint``
tells the player where to go instead.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from world.scenes.constants import InteractionMode, InteractionVisibility
from world.scenes.place_models import Place, PlacePresence

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.scenes.models import Persona, Scene


def _receiver_ids(receivers: Iterable[Persona] | Iterable[int] | None) -> frozenset[int] | None:
    """Normalize a receivers argument (personas or ids) to a set of persona ids.

    An EMPTY receivers argument normalizes to ``None``, exactly like ``None`` itself:
    both mean "this content names no explicit receivers", which is what the
    directed-vs-broadcast branches below test for. Returning an empty frozenset
    instead made an explicit ``receivers=[]`` refuse EVERYONE, while
    ``create_interaction`` reads the same ``[]`` as falsy and writes no
    ``InteractionReceiver`` rows at all -- two code paths disagreeing about one
    value, with the shape that actually gets persisted being the broadcast one.
    ``visible_to``'s ``room_heard`` clause agrees with the persisted shape too (it
    keys on the absence of receiver rows), so ``None`` is the reading that keeps all
    three in step.
    """
    if receivers is None:
        return None
    ids: set[int] = set()
    for item in receivers:
        ids.add(item if isinstance(item, int) else item.pk)
    return frozenset(ids) if ids else None


# Why both signatures in this module keep an `ObjectDB`-typed `location`
# (CLAUDE.md: "a keeper without a stated reason is indistinguishable from an
# oversight"): an Evennia room genuinely IS an ObjectDB here. `Scene.location`
# is itself an ObjectDB FK, `get_active_scene` takes one, and the callers hand
# this straight through from `character.location`, so narrowing the annotation
# to `RoomProfile` would mean converting at every call site to test presence
# against a `.contents` cache that lives on the ObjectDB anyway. This is the
# "could this be a vase of flowers" question answered NO by the room's own
# nature, not by convenience. `world/scenes/*` is outside the `objectdb-param`
# hook's `files:` scope (`.pre-commit-config.yaml`), so no OBJECTDB_PARAM
# suppression token is needed; the rationale is what CLAUDE.md asks for either
# way, suppression or not. Revisit when
# `Scene.location` is retargeted off ObjectDB, which that config already names
# as the trigger for pulling `scenes/models.py` into scope.
def _room_has_character(location: ObjectDB | None, character_sheet_id: int) -> bool:
    """Return whether ``character_sheet_id`` is physically present at ``location``.

    Mirrors ``Scene.has_character_present`` (``world/scenes/models.py``) for a
    room that has no ``Scene`` wrapper at all -- both read the room's Evennia
    contents cache (no DB hit when the room is already loaded), and both key
    on the ObjectDB pk, which ``CharacterSheet`` shares with its character
    (see CLAUDE.md's "RoomProfile and CharacterSheet share ObjectDB's pk").
    """
    if location is None:
        return False
    present_ids = {ob.pk for ob in location.contents}
    return character_sheet_id in present_ids


# `location: ObjectDB | None` below: see the rationale above `_room_has_character`.
def persona_can_receive(  # noqa: PLR0913 - one arg per Interaction shape field being tested
    persona: Persona,
    *,
    scene: Scene | None,
    place: Place | None,
    receivers: Iterable[Persona] | Iterable[int] | None,
    mode: str,
    visibility: str,
    location: ObjectDB | None = None,
    place_presence_persona_ids: Iterable[int] | None = None,
) -> bool:
    """Return whether ``persona`` can receive content with this audience shape.

    ``scene``/``place``/``receivers``/``mode``/``visibility`` describe the SHAPE
    of the content being named or answered (mirrors ``Interaction``'s own
    fields), not a specific persisted row - callers may check a hypothetical
    shape before anything is written. ``visibility`` only changes the answer
    for the room-heard branch (see the module docstring) - the directed
    branches (whisper, receivers, place) already encode their own audience via
    the recorded rows, which escalating ``visibility`` never rewrites.

    ``location`` is the room this content actually occurs in -- required to
    answer the room-heard branch when there is no ``Scene`` (``Interaction.scene``
    is nullable; "Scenes are optional containers", ``world/scenes/models.py``).
    Without it, a scene-less room-heard shape refuses outright (there is no room
    to test presence against); with it, presence is read straight off the room's
    contents, same as the scene-backed case. Passing ``location`` never widens
    who counts as room-heard on its own -- ``visibility`` still gates it first.

    ``place_presence_persona_ids``, if given, is a prefetched set of persona ids
    present at ``place`` (e.g. ``PlacePresence.objects.filter(place=place,
    persona_id__in=[...]).values_list("persona_id", flat=True)``) -- a caller
    checking several personas against the same place batches one query instead
    of this function issuing its own per call. Omitted, this function queries
    ``PlacePresence`` itself (unchanged single-check behavior).
    """
    receiver_ids = _receiver_ids(receivers)

    if mode == InteractionMode.WHISPER:
        # A whisper is directed by construction: reachable only for its party.
        return receiver_ids is not None and persona.pk in receiver_ids

    if place is not None:
        if place_presence_persona_ids is not None:
            present_at_place = persona.pk in place_presence_persona_ids
        else:
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
    # whoever is physically present in the room right now, but ONLY while
    # visibility is still DEFAULT. `visible_to`'s `room_heard` clause requires
    # `visibility=DEFAULT` explicitly, so a receiver-less broadcast escalated
    # after the fact (`mark_very_private`, PERCEIVED_ONLY or VERY_PRIVATE) stops
    # being broadcast-reachable to anyone - not staff, not the scene's GM,
    # regardless of who is standing in the room. There is no recorded audience
    # to fall back on for an escalated broadcast, so the honest answer is
    # nobody, full stop -- checked BEFORE presence, so an escalated row is
    # refused whether or not a room/scene is even available to test against.
    if visibility != InteractionVisibility.DEFAULT:
        return False
    if scene is not None and scene.location is not None:
        return scene.has_character_present({persona.character_sheet_id})
    # No scene (or a locationless one): fall back to the room the content
    # actually occurred in, if the caller supplied one. Still refuses (rather
    # than guessing) when neither is available.
    return _room_has_character(location, persona.character_sheet_id)


class UnreachableError(Exception):
    """Raised when one or more personas cannot receive content in a given venue.

    ``personas`` are the ones that failed ``persona_can_receive``; ``venue_hint``
    is the player-facing sentence telling them how to reach a venue where they
    can (e.g. leave a Place). Consumed by the tagging/naming refusal (Task 4,
    ``create_interaction``); the reply refusal keeps its own
    ``InteractionThreadError`` (a different HTTP contract the frontend already
    matches on, see #3760).

    ``message``, if given, is the detail shown to the caller (e.g. naming the
    unreachable persona(s)); it defaults to ``venue_hint`` when omitted, which
    keeps the original two-positional-argument shape callers already use.
    ``code`` mirrors ``InteractionThreadError.code`` so a view can build the
    same ``{code, field, detail, hint}`` response shape for both refusals.
    """

    code = "target_unreachable"

    def __init__(
        self,
        personas: list[Persona],
        venue_hint: str,
        *,
        message: str | None = None,
    ) -> None:
        self.personas = personas
        self.venue_hint = venue_hint
        # See InteractionThreadError.detail: the view reads this, never str(exc).
        self.detail = message if message is not None else venue_hint
        super().__init__(self.detail)

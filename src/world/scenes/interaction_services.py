from __future__ import annotations

import contextlib
from dataclasses import dataclass
from datetime import timedelta
import itertools
from typing import TYPE_CHECKING, Any, cast
import uuid

from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, transaction
from django.utils import timezone

from world.scenes.constants import (
    InteractionMode,
    InteractionVisibility,
    PoseKind,
    ScenePrivacyMode,
)
from world.scenes.models import (
    Interaction,
    InteractionTargetPersona,
    Persona,
    PoseSubmission,
    Scene,
)
from world.scenes.place_models import InteractionReceiver, Place, PlacePresence
from world.scenes.reachability import UnreachableError, persona_can_receive
from world.scenes.thread_services import (
    InteractionThreadError,
    ReplyTarget,
    assign_interaction_thread,
    pending_thread_update,
)
from world.scenes.types import InteractionPayload, PersonaPayload, ReplyParentPayload

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from evennia.objects.models import ObjectDB

    from world.companions.models import Companion
    from world.magic.models import FuryTier
    from world.scenes.models import SceneRound
    from world.species.models import Language

DELETION_WINDOW_DAYS = 30
_ephemeral_counter = itertools.count()

# #3787 Task 4 - approved demo copy (Screen 3). Fixed regardless of WHY a target
# is unreachable (place-scoped, receiver-scoped, or whisper): both routes it
# names (address the room, or whisper) are always available to the writer.
_TARGET_UNREACHABLE_HINT = "Address the room to reach them, or send a whisper. Your draft is kept."

# #3787 Task 8 - telnet parity for the web reader's InvolvementFlag ("This happened
# to you"). One phrasing for every row kind that carries target_personas (spec
# decision 8) - see _send_to_objects.
_INVOLVEMENT_MARK_TEXT = "This happened to you."


def _describe_unreachable_targets(personas: list[Persona]) -> str:
    """Player-facing detail naming the unreachable persona(s) (#3787 demo copy).

    Names only personas the caller already resolved via
    ``resolve_characters_by_name(..., character.location)`` -- that function only
    ever returns characters in the writer's own location, so naming them back
    confirms nothing the writer could not already observe (the leak guard).
    """
    names = [p.name for p in personas]
    if len(names) == 1:
        return f"{names[0]} is across the room and will not see table talk."
    joined = ", ".join(names[:-1]) + f" and {names[-1]}"
    return f"{joined} are across the room and will not see table talk."


def get_active_scene(location: ObjectDB | None) -> Scene | None:
    """The location → active-scene resolver, with in-memory caching (#1370).

    The single public entry point for deriving the scene at a room — shared by the say/pose
    recorders and the telnet scene-derivation commands (consent / endorse / react / etc.), so
    they never hand-roll a parallel ``Scene.objects.filter(...)`` query. Caches the result on
    the location object (which persists in memory via SharedMemoryModel's identity map);
    invalidated by ``invalidate_active_scene_cache()`` when a scene starts or ends.
    Excludes battle-backed scenes (``Scene.objects.active_for_room``, #2010 review) — a
    staged Battle's backing Scene must never hijack the room's RP scene resolution.
    """
    if location is None:
        return None
    try:
        cached: Scene | None = location._active_scene_cache  # noqa: SLF001
        return cached
    except AttributeError:
        pass
    scene = Scene.objects.active_for_room(location).first()
    location._active_scene_cache = scene  # noqa: SLF001
    return scene


def invalidate_active_scene_cache(location: ObjectDB) -> None:
    """Clear the cached active scene for a location.

    Call this when a scene starts or ends.
    """
    with contextlib.suppress(AttributeError):
        del location._active_scene_cache  # noqa: SLF001


def broadcast_scene_emit(character: ObjectDB, text: str) -> None:
    """Broadcast ``text`` as a system EMIT to the active scene at ``character``'s location.

    The shared system-announcement seam for character-anchored magic beats (the
    Audere Majora manifestation, the Audere surge line, #3451). No-ops silently
    when: no active scene at the character's location, or the character has no
    primary persona (a plain ObjectDB, or a sheet with no PRIMARY row).

    Queries the scene uncached on purpose: ``get_active_scene``'s per-location
    cache is only invalidated by the scene start/end services, and this seam is
    reached from cast/accept paths where a scene may have opened through other
    routes since the location was last resolved.
    """
    # No None-guard on location: a location-less character can still share a
    # location-less scene (active_for_room(None) matches it) — the pre-#3451
    # inline behavior, load-bearing for factory-built worlds.
    scene = Scene.objects.active_for_room(character.location).first()
    if scene is None:
        return

    try:
        # sheet_data is CharacterSheet's OneToOne reverse accessor.
        persona = character.sheet_data.primary_persona
    except (AttributeError, Persona.DoesNotExist):
        return

    interaction = create_interaction(
        persona=persona,
        content=text,
        mode=InteractionMode.EMIT,
        scene=scene,
    )
    push_interaction(
        interaction,
        receiver_persona_ids=[],
        target_persona_ids=[],
        receiver_characters=[],
    )


def reassign_persona_interactions(
    *,
    source_persona: Persona,
    target_persona: Persona,
) -> int:
    """Reassign all interactions from source_persona to target_persona.

    Both personas must belong to the same CharacterSheet. This is used
    when merging personas (e.g., discovering a temporary disguise is the
    same person as an established identity).

    Returns the number of interactions reassigned.
    """
    if source_persona.character_sheet_id != target_persona.character_sheet_id:
        msg = "Cannot reassign between personas of different characters."
        raise ValueError(msg)

    count = Interaction.objects.filter(
        persona=source_persona,
    ).update(persona=target_persona)

    InteractionTargetPersona.objects.filter(
        persona=source_persona,
    ).update(persona=target_persona)

    InteractionReceiver.objects.filter(
        persona=source_persona,
    ).update(persona=target_persona)

    from world.scenes.models import SceneSummaryRevision  # noqa: PLC0415

    SceneSummaryRevision.objects.filter(
        persona=source_persona,
    ).update(persona=target_persona)

    return count


def write_target_personas(interaction: Interaction, target_personas: Iterable[Persona]) -> None:
    """Bulk-write the ``InteractionTargetPersona`` rows naming who this row was about.

    ADR-0293 decision 3 draws the line this function sits on: a SYSTEM-authored row
    records what happened and is not governed by reachability; a PLAYER-authored row
    addresses someone and is. ``create_interaction``'s own ``target_personas`` kwarg
    is the player-authored side and validates with ``persona_can_receive`` (#3787
    Task 4) before calling this. Every system-authored writer calls this directly and
    deliberately skips that validation:

    - ``create_action_interaction_core`` (this module) and
      ``create_npc_action_interaction`` / ``broadcast_action_outcome``
      (``world.combat.interaction_services``) -- combat's resolved actions.
    - ``create_cast_outcome_pose`` (``world.scenes.cast_services``) -- the Narrator
      OUTCOME pose(s) for a resolved standalone cast.
    - ``narrate_privately`` (this module) -- a Narrator line addressed to one player.
    - the resolved-action-request outcome writers in ``world.scenes.action_services``.

    Their shared justification: the target is already governed by the mechanic's own
    targeting rules (a resolved action's target must already be a live participant, a
    cast's target was validated by ``validate_cast_target``, an action request's target
    was fixed and accepted when the request was created), not by the narrative "is this
    persona standing somewhere this pose actually reaches" question
    ``persona_can_receive`` answers -- which several of them could not satisfy in any
    case, since the Narrator's character is never physically placed and a Battle-backed
    scene has ``location=None`` by construction. "System-authored" is about who composed
    the text, not which persona is credited: several of these credit a player's persona
    for machine-rendered content. Does no reachability check of its own; callers that
    need one run it before calling this.
    """
    InteractionTargetPersona.objects.bulk_create(
        [
            InteractionTargetPersona(
                interaction=interaction,
                timestamp=interaction.timestamp,
                persona=p,
            )
            for p in target_personas
        ]
    )


def create_interaction(  # noqa: PLR0913 - atomic creation requires all interaction fields
    *,
    persona: Persona,
    content: str,
    mode: str,
    scene: Scene | None = None,
    place: Place | None = None,
    receivers: list[Persona] | None = None,
    target_personas: list[Persona] | None = None,
    strain_committed: int = 0,
    fury_committed: FuryTier | None = None,
    pose_kind: str = PoseKind.STANDARD,
    visibility: str = InteractionVisibility.DEFAULT,
    language: Language | None = None,
    attributed_companion: Companion | None = None,
    reply_to: ReplyTarget | None = None,
) -> Interaction:
    """Create an atomic RP interaction with optional receiver and thread records.

    Receiver logic:
    - If receivers are explicitly provided, create InteractionReceiver rows.
    - If place is provided without receivers, auto-populate from PlacePresence.
    - If neither place nor receivers, the interaction is public (no receiver rows).

    Callers must handle ephemeral scenes before calling this function -- ephemeral
    interactions should never be persisted.

    Args:
        persona: The writer's identity (non-nullable).
        content: The actual written text.
        mode: InteractionMode value (pose, emit, say, whisper, etc.).
        scene: Scene container if one was active.
        place: Sub-location where this interaction occurred.
        receivers: Explicit list of personas who should receive this.
        target_personas: Explicit IC targets for the interaction.
        strain_committed: Strain the initiator actually committed for this action.
        fury_committed: Realized FuryTier post-resolution (null = no fury).
        pose_kind: PoseKind classification for POSE interactions.
        visibility: InteractionVisibility tier.
        language: Spoken language, or null for universal/untagged content.
        attributed_companion: Cosmetic pose attribution.
        reply_to: Optional serializer-level target used to select a thread.

    Returns:
        The created Interaction.
    """
    writer_account_id = _get_account_for_persona(persona)
    with transaction.atomic():
        # Pin the writer's account at creation (#1219) — party identity for
        # private-content log visibility, stable across persona hand-offs.
        interaction = Interaction.objects.create(
            persona=persona,
            writer_account_id=writer_account_id,
            content=content,
            mode=mode,
            scene=scene,
            place=place,
            strain_committed=strain_committed,
            fury_committed=fury_committed,
            pose_kind=pose_kind,
            visibility=visibility,
            language=language,
            attributed_companion=attributed_companion,
        )
        # #1826 — posing in a scene is IC action in its area: lie-low breaks.
        _break_lie_low_for_interaction(persona, scene)

        # Determine receiver list.
        effective_receivers = receivers
        if effective_receivers is None and place is not None:
            # Auto-populate from PlacePresence, excluding the writer.
            effective_receivers = list(
                Persona.objects.filter(
                    place_presences__place=place,
                ).exclude(pk=persona.pk)
            )

        if effective_receivers:
            # Pin each receiver's account too (#1219), batched to one query.
            receiver_accounts = accounts_for_personas(effective_receivers)
            InteractionReceiver.objects.bulk_create(
                [
                    InteractionReceiver(
                        interaction=interaction,
                        timestamp=interaction.timestamp,
                        persona=recv_persona,
                        account_id=receiver_accounts.get(recv_persona.pk),
                    )
                    for recv_persona in effective_receivers
                ]
            )

        if target_personas:
            # #3787 Task 4 - the live defect: target_personas appeared nowhere in
            # visible_to, so a Place-scoped pose (which auto-populates receivers
            # from PlacePresence above, making this a DIRECTED row) could name a
            # persona sitting at a different table -- the row was written and
            # never delivered. Validate with the shared `persona_can_receive`
            # predicate (Task 3) before writing anything, for every shape --
            # no shape-based exemption here (fix round 1 finding): the room-heard
            # branch answers correctly on its own now, given the writer's own
            # `location` as a fallback for when there is no `Scene` to anchor it.
            #
            # Batch the Place-presence lookup once for every target instead of
            # letting `persona_can_receive` issue one `PlacePresence` query per
            # call (fix round 1 finding 2, "no queries in loop").
            place_presence_ids = None
            if place is not None:
                place_presence_ids = frozenset(
                    PlacePresence.objects.filter(
                        place_id=place.pk,
                        persona_id__in=[p.pk for p in target_personas],
                    ).values_list("persona_id", flat=True)
                )
            writer_location = persona.character_sheet.character.location
            unreachable = [
                target
                for target in target_personas
                if not persona_can_receive(
                    target,
                    scene=scene,
                    place=place,
                    receivers=effective_receivers,
                    mode=mode,
                    visibility=visibility,
                    location=writer_location,
                    place_presence_persona_ids=place_presence_ids,
                )
            ]
            if unreachable:
                raise UnreachableError(
                    unreachable,
                    _TARGET_UNREACHABLE_HINT,
                    message=_describe_unreachable_targets(unreachable),
                )
            write_target_personas(interaction, target_personas)

        if reply_to is not None:
            assignment = assign_interaction_thread(
                interaction=interaction,
                reply_target=reply_to,
                account_id=writer_account_id,
            )
            interaction.thread_assignment = assignment

    return interaction


def create_action_interaction_core(  # noqa: PLR0913 - one arg per resolved-action field recorded
    *,
    persona: Persona,
    scene: Scene | None,
    summary_label: str,
    strain_committed: int = 0,
    fury_committed: FuryTier | None = None,
    target_personas: list[Persona] | None = None,
) -> Interaction:
    """Create one ACTION-mode Interaction for a resolved action/cast.

    The shared core behind combat's create_action_interaction and the scene
    cast path. Keyed on persona + (nullable) scene.

    ``target_personas`` (#3787 Task 5) records whom this resolved action was
    about -- PC personas only (an NPC opponent has no Persona, so a blow that
    lands on one records no target; that is correct, not a gap). Written via
    ``write_target_personas`` with no reachability check -- see that
    function's docstring for why combat's own targets skip
    ``persona_can_receive``.
    """
    interaction = Interaction.objects.create(
        persona=persona,
        scene=scene,
        content=summary_label,
        mode=InteractionMode.ACTION,
        strain_committed=strain_committed,
        fury_committed=fury_committed,
    )
    if target_personas:
        write_target_personas(interaction, target_personas)
    return interaction


def _target_character_ids(target_persona_ids: list[int] | None) -> frozenset[int]:
    """Resolve targeted persona ids to their character (ObjectDB) ids, once per call.

    ``CharacterSheet`` is a ``primary_key=True`` O2O onto ``ObjectDB`` (see
    ``django_notes.md``), so ``Persona.character_sheet_id`` already IS the
    character's own pk -- no join needed. Returns an empty set (no query) when
    there are no targets, which is the overwhelmingly common broadcast.
    """
    if not target_persona_ids:
        return frozenset()
    return frozenset(
        Persona.objects.filter(pk__in=target_persona_ids).values_list(
            "character_sheet_id", flat=True
        )
    )


def _non_web_sessions(obj: ObjectDB) -> list[Any]:
    """Sessions on ``obj`` that do NOT already receive the structured payload.

    Evennia's webclient protocols stamp ``session.protocol_key`` as
    ``"webclient/websocket"`` or ``"webclient/ajax"`` (see
    ``evennia/server/portal/webclient*.py``); telnet, telnet/ssl and ssh use
    ``"telnet"``/``"telnet/ssl"``/``"ssh"``. This mirrors the existing
    telnet-vs-web discriminator in ``server/conf/inputfuncs.py``'s ``text()``
    (``protocol_key.startswith("telnet")``), inverted and widened to "not
    webclient" so ssh sessions -- which also never receive the ``interaction=``
    outputfunc -- get the mark too.
    """
    return [
        session
        for session in obj.sessions.all()
        if not str(session.protocol_key or "").startswith("webclient")
    ]


def _send_involvement_mark(obj: ObjectDB) -> None:
    """Send the plain-text involvement mark to ``obj``'s non-web sessions only.

    ``obj.msg(text)`` with no ``session=`` is protocol-agnostic -- it would
    reach EVERY session ``obj`` has, web included. The web client already
    renders its own ``InvolvementFlag`` chip off ``target_persona_ids``
    (#3787 Task 7), so sending the plain-text line there too would double the
    signal (Task 8 fix round 2, Finding 1). Scoping to ``session=`` a specific
    list is how Evennia targets delivery (``DefaultObject.msg``); passing an
    EMPTY list here would fall back to "all sessions" (Evennia's own
    ``session or self.sessions.all()`` default), so a webclient-only
    character (no non-web session) gets skipped entirely rather than sent
    with an empty list.
    """
    non_web = _non_web_sessions(obj)
    if non_web:
        obj.msg(_INVOLVEMENT_MARK_TEXT, session=non_web)


def _send_to_objects(
    objects: Iterable[ObjectDB],
    payload: InteractionPayload,
    *,
    render_for: Callable[[ObjectDB], str] | None = None,
) -> None:
    """Send an interaction payload to specific objects via WebSocket.

    When ``render_for`` is given (#2993 per-recipient language comprehension),
    each object gets its own copy of the payload with ``content`` rebuilt via
    ``render_for(obj)``. ``InteractionPayload`` is a TypedDict, so the per-object
    payload is rebuilt via dict-spread rather than ``dataclasses.replace``.

    Telnet involvement mark (#3787 Task 8, spec decisions 7+8): the
    ``interaction=`` kwarg above is a WebSocket-only message type -- a bare
    telnet session never receives it (no ``interaction`` outputfunc is
    registered for that protocol), so it gives telnet no equivalent of the
    web reader's ``InvolvementFlag`` ("This happened to you"). Every recipient
    named in ``payload["target_persona_ids"]`` additionally gets one plain-text
    line, ``_send_involvement_mark``, scoped to their non-web sessions only
    (see that function's docstring -- a webclient session already got the
    structured signal above and must not also get the raw line). This is the
    one shared seam every targeted row already passes through (pose tagging,
    whisper, mutter, and combat's unconcealed action outcome all build their
    payload via ``_build_interaction_payload`` and reach clients only through
    this function or ``_broadcast_to_location``), so one rule here covers
    every row kind with no per-mode copy (decision 8) and no duplicated
    targeting logic in a command class.
    """
    target_character_ids = _target_character_ids(payload.get("target_persona_ids"))
    for obj in objects:
        try:
            obj_payload = payload
            if render_for is not None:
                obj_payload = cast(InteractionPayload, {**payload, "content": render_for(obj)})
            obj.msg(interaction=((), obj_payload))
            if obj.pk in target_character_ids:
                _send_involvement_mark(obj)
        except AttributeError:
            continue


def _broadcast_to_location(
    location: ObjectDB,
    payload: InteractionPayload,
    *,
    render_for: Callable[[ObjectDB], str] | None = None,
) -> None:
    """Send an interaction payload to all objects in a location via WebSocket."""
    _send_to_objects(location.contents, payload, render_for=render_for)


def _build_interaction_payload(  # noqa: PLR0913 - payload needs all interaction fields
    *,
    interaction_id: int,
    persona: Persona,
    content: str,
    mode: str,
    timestamp: str,
    scene_id: int | None,
    thread_id: str | None = None,
    root_thread_id: str | None = None,
    place_id: int | None = None,
    place_name: str | None = None,
    receiver_persona_ids: list[int] | None = None,
    target_persona_ids: list[int] | None = None,
    language_id: int | None = None,
    language_name: str | None = None,
    attributed_companion_id: int | None = None,
    attributed_companion_name: str | None = None,
    reply_to: ReplyParentPayload | None = None,
) -> InteractionPayload:
    """Build a structured interaction payload for WebSocket delivery.

    ``reply_to`` (#3787) mirrors ``InteractionSerializer.get_reply_to``'s REST shape so
    the parent chip appears for every viewer the moment the reply lands, instead of only
    after a refetch. It defaults to ``None`` for every payload built for a row that
    cannot have a parent (combat outcomes, companion emotes, tavern games, GM
    adjudications, ephemeral pushes); ``push_interaction`` is the one builder that
    resolves it. See ``_reply_parent_payload`` for the privacy gate.
    """
    return InteractionPayload(
        id=interaction_id,
        persona=PersonaPayload(
            id=persona.pk,
            name=persona.name,
            thumbnail_url=persona.thumbnail_url or "",
        ),
        content=content,
        mode=mode,
        timestamp=timestamp,
        thread_id=thread_id,
        root_thread_id=root_thread_id,
        scene_id=scene_id,
        place_id=place_id,
        place_name=place_name,
        receiver_persona_ids=receiver_persona_ids or [],
        target_persona_ids=target_persona_ids or [],
        language_id=language_id,
        language_name=language_name,
        attributed_companion_id=attributed_companion_id,
        attributed_companion_name=attributed_companion_name,
        reply_to=reply_to,
    )


def _root_thread_id(interaction: Interaction) -> str | None:
    """The top of the nesting tree this row's exchange belongs to (#3787).

    A row's thread is what it ANSWERS, so answering a reply nests a thread inside
    the one the answered row lives in and a single back-and-forth spans several
    threads. This is the one key every row of that exchange shares, so a reader
    renders the whole of it as one card. Null when the row's own thread IS the
    root, and for a row that answers nothing, mirroring
    ``InteractionSerializer.get_root_thread_id`` so the live push and the refetch
    group a row identically. No extra query: ``_reply_parent_payload`` fetches the
    same thread row on this same push, and a row that answers nothing never
    touches the database here.
    """
    if interaction.thread_id is None:
        return None
    thread = interaction.thread
    if thread is None or thread.root_id is None:
        return None
    return str(thread.root_id)


def _reply_parent_payload(interaction: Interaction) -> ReplyParentPayload | None:
    """The parent chip for a LIVE push, or ``None`` when it cannot be sent safely.

    The REST serializer gates this per viewer, against
    ``Interaction.objects.visible_to(user)`` for the request's own account. A WebSocket
    push has no single viewer -- one payload goes to every object in the room -- and
    re-running that queryset once per recipient account would put a query per player in
    the room on every reply. So this gate is structural and evaluated once per push: the
    parent goes on the wire only when it is ROOM-HEARD IN THIS SAME SCENE (the shared
    ``managers.room_heard_q`` classification, not a second copy of it).

    **What this gate guarantees, stated exactly.** It discloses strictly less than the
    live push it rides on already delivers to that same audience. It does NOT match
    per-recipient REST visibility, and two known cases send a parent ``visible_to``
    would withhold from that recipient:

    1. A room-heard parent in a PRIVATE scene, to a bystander standing in the room who
       is neither a participant, nor its GM, nor a prior writer or receiver in it.
       ``visible_to``'s ``present_scene_ids`` clause (``managers.py``) keys on having
       AUTHORED or RECEIVED something in the scene, not on standing there.
    2. A parent older than ``visible_to``'s 90-day ``time_bound``, which the room-heard
       predicate does not carry.

    Both are accepted rather than fixed. The disclosure is an opaque id and an ISO
    timestamp with no path to content: ``ParentChip`` (``scenes/components/PoseUnit.tsx``)
    renders "a pose not currently loaded" on a lookup miss and never fetches. And both
    recipients are, in the same breath, receiving the REPLY's full text over the same
    ``_broadcast_to_location`` call. So the parent id tells them strictly less than the
    push already has. Do not restate this as "can never over-disclose".

    Every narrower parent -- a whisper, a table-scoped aside, a row escalated to
    PERCEIVED_ONLY or VERY_PRIVATE, or a parent in another scene -- sends ``None``
    rather than guess, and those readers still get the chip from the REST serializer's
    own per-viewer gate on their next fetch.

    **Cost.** One room-heard query per reply push, and none at all for the
    overwhelmingly common row that answers nothing: ``thread_id`` is a plain column
    already on the row, so the ``None`` branch below never touches the database.
    """
    # The parent edge IS the thread (#3787): ``assign_interaction_thread``
    # (``world/scenes/thread_services.py``) is the only writer of ``interaction.thread``
    # and it always points at a thread anchored on the answered row. So a null
    # ``thread_id`` means "answers nothing" without a lookup, and a set one carries the
    # whole chip payload on the thread row itself. Pinned by
    # ``test_a_reply_always_carries_a_thread_id``.
    if interaction.thread_id is None:
        return None
    thread = interaction.thread
    if thread is None or thread.anchor_interaction_id is None:
        return None
    if interaction.scene_id is None:
        return None
    if not (
        Interaction.objects.room_heard()
        .filter(pk=thread.anchor_interaction_id, scene_id=interaction.scene_id)
        .exists()
    ):
        return None
    return ReplyParentPayload(
        id=str(thread.anchor_interaction_id),
        timestamp=thread.anchor_timestamp.isoformat(),
    )


def _language_render_for(
    interaction: Interaction,
    persona: Persona,
) -> Callable[[ObjectDB], str] | None:
    """Per-recipient language-comprehension renderer for the broadcast branch (#2993).

    None when the interaction carries no language or a universal one — the caller
    then skips the per-object payload rebuild and broadcasts identical content,
    exactly as before #2993. The writer and staff always get ground truth; any
    object without a resolvable sheet (no CharacterSheet — e.g. an NPC prop or
    other non-player object) also gets ground truth rather than a garbled read.
    """
    language = interaction.language if interaction.language_id else None
    if language is None or language.is_universal:
        return None

    from world.species.language_constants import fluency_band  # noqa: PLC0415
    from world.species.language_services import fluency_value, render_speech  # noqa: PLC0415

    speaker_sheet = persona.character_sheet
    speaker_band = fluency_band(fluency_value(speaker_sheet, language))
    writer_char = speaker_sheet.character

    def _render_for(obj: ObjectDB) -> str:
        if obj.pk == writer_char.pk:
            return interaction.content
        # obj.account is a plain nullable attribute on every ObjectDB (never
        # raises); obj.sheet_data is the reverse OneToOne from
        # CharacterSheet.character and raises ObjectDoesNotExist — not
        # AttributeError — for a non-player object with no linked sheet
        # (matches the existing sheet_data-access pattern in this file, e.g.
        # personas_for_characters).
        account = obj.account
        if account is not None and account.is_staff:
            return interaction.content
        try:
            sheet = obj.sheet_data
        except ObjectDoesNotExist:
            return interaction.content
        return render_speech(
            interaction.content,
            language=language,
            speaker_band=speaker_band,
            listener_value=fluency_value(sheet, language),
        )

    return _render_for


def push_interaction(
    interaction: Interaction,
    *,
    receiver_persona_ids: list[int] | None = None,
    target_persona_ids: list[int] | None = None,
    receiver_characters: list[ObjectDB] | None = None,
) -> None:
    """Push a persisted interaction payload to connected clients via WebSocket.

    Uses Evennia's msg() which routes through the WebSocket to connected
    web clients. The message type 'interaction' will be handled by a new
    WS_MESSAGE_TYPE on the frontend.

    Whispers are sent only to the writer and receivers. Place-scoped
    interactions are sent to the writer and receivers. All other modes
    broadcast to the entire room.

    When called from record_interaction / record_whisper_interaction, the
    receiver and target IDs are passed directly to avoid re-querying rows
    that were just created. When called standalone (e.g. from tests),
    falls back to querying.
    """
    persona = interaction.persona
    location = persona.character_sheet.character.location
    if location is None:
        return

    # Use passed IDs if available; otherwise fall back to querying.
    if receiver_persona_ids is None or receiver_characters is None:
        receivers = list(
            InteractionReceiver.objects.filter(
                interaction=interaction,
            ).select_related("persona__character_sheet__character")
        )
        r_ids = [r.persona_id for r in receivers]
        r_chars = [r.persona.character_sheet.character for r in receivers]
    else:
        r_ids = receiver_persona_ids
        r_chars = receiver_characters

    if target_persona_ids is None:
        targets = list(
            InteractionTargetPersona.objects.filter(
                interaction=interaction,
            ).select_related("persona")
        )
        t_ids = [t.persona_id for t in targets]
    else:
        t_ids = target_persona_ids

    payload = _build_interaction_payload(
        interaction_id=interaction.pk,
        persona=persona,
        content=interaction.content,
        mode=interaction.mode,
        timestamp=interaction.timestamp.isoformat(),
        thread_id=str(interaction.thread_id) if interaction.thread_id else None,
        root_thread_id=_root_thread_id(interaction),
        scene_id=interaction.scene_id,
        place_id=interaction.place_id,
        place_name=interaction.place.name if interaction.place_id else None,
        receiver_persona_ids=r_ids,
        target_persona_ids=t_ids,
        language_id=interaction.language_id,
        language_name=interaction.language.name if interaction.language_id else None,
        attributed_companion_id=interaction.attributed_companion_id,
        attributed_companion_name=(
            interaction.attributed_companion.name if interaction.attributed_companion_id else None
        ),
        reply_to=_reply_parent_payload(interaction),
    )

    # Any escalated visibility is receiver-scoped, not room-heard. Before #2710 this
    # branch tested only whisper/place, so a VERY_PRIVATE pose would have broadcast to
    # the whole room over the WebSocket — no live caller did that, but the next one
    # would have. Fixed on sight.
    receiver_scoped = (
        interaction.mode == InteractionMode.WHISPER
        or interaction.place_id is not None
        or interaction.visibility != InteractionVisibility.DEFAULT
    )
    if receiver_scoped:
        # Receiver-scoped modes (whisper, place-scoped, escalated visibility) keep
        # full text to their explicit receivers — the speaker chose this audience,
        # so it never gets the language garble (#2993).
        writer_char = persona.character_sheet.character
        _send_to_objects([writer_char, *r_chars], payload)
    else:
        _broadcast_to_location(
            location, payload, render_for=_language_render_for(interaction, persona)
        )


def push_ephemeral_interaction(  # noqa: PLR0913 - ephemeral payload mirrors persisted payload
    *,
    persona: Persona,
    content: str,
    mode: str,
    scene: Scene,
    recipients: list[ObjectDB] | None = None,
    place_id: int | None = None,
    place_name: str | None = None,
    receiver_persona_ids: list[int] | None = None,
    target_persona_ids: list[int] | None = None,
    attributed_companion: Companion | None = None,
) -> None:
    """Push an ephemeral interaction payload — real-time delivery without persistence.

    For ephemeral scenes, the content is never written to the database. This
    function builds and broadcasts a payload directly so players still see
    each other's poses in real-time. The content exists only in transit.

    Uses a negative timestamp-based ID (with monotonic counter) to distinguish
    from persisted interactions on the frontend (no DB primary key exists).

    Args:
        persona: The writer's identity.
        content: The interaction text.
        mode: InteractionMode value.
        scene: The ephemeral scene.
        recipients: If provided, send only to these objects (e.g. whisper).
            Otherwise broadcast to the full room.
        place_id: Optional place ID for place-scoped interactions.
        place_name: Optional place name for display.
        receiver_persona_ids: IDs of receiver personas.
        target_persona_ids: IDs of target personas.
        attributed_companion: Cosmetic pose attribution (#3294) — see ``record_interaction``.
    """
    now = timezone.now()
    counter = next(_ephemeral_counter) % 1000
    ephemeral_id = -(int(now.timestamp() * 1000) * 1000 + counter)

    payload = _build_interaction_payload(
        interaction_id=ephemeral_id,
        persona=persona,
        content=content,
        mode=mode,
        timestamp=now.isoformat(),
        scene_id=scene.pk,
        place_id=place_id,
        place_name=place_name,
        receiver_persona_ids=receiver_persona_ids,
        target_persona_ids=target_persona_ids,
        attributed_companion_id=attributed_companion.pk if attributed_companion else None,
        attributed_companion_name=attributed_companion.name if attributed_companion else None,
    )

    if recipients is not None:
        _send_to_objects(recipients, payload)
    else:
        location = persona.character_sheet.character.location
        if location is None:
            return
        _broadcast_to_location(location, payload)


def _is_receiver_scoped(interaction: Interaction) -> bool:
    """Whether this interaction is limited to its writer and named receivers.

    Whispers, table talk (place-scoped) and receiver-scoped mutters stay between
    writer and receivers even inside a public scene, mirroring the real-time push
    rule so the persisted log never shows more than the room heard. A mutter
    WITHOUT receiver rows is the public fragment (#905) — what the room heard —
    and is not receiver-scoped, so it falls through to scene-level visibility.
    """
    if interaction.mode == InteractionMode.WHISPER or interaction.place_id is not None:
        return True
    return (
        interaction.mode == InteractionMode.MUTTER
        and InteractionReceiver.objects.filter(interaction=interaction).exists()
    )


def _private_scene_admits(scene: Scene, persona: Persona, *, is_writer: bool) -> bool:
    """Whether a private scene's log is open to this persona.

    Participation is Account-based (via ``SceneParticipation``), so a persona
    whose character has no current tenure resolves to no account and is admitted
    only as the writer.
    """
    from world.scenes.models import SceneParticipation  # noqa: PLC0415

    account_id = _get_account_for_persona(persona)
    if account_id is None:
        return is_writer
    is_participant = SceneParticipation.objects.filter(
        scene=scene,
        account_id=account_id,
    ).exists()
    return is_participant or is_writer


def can_view_interaction(
    interaction: Interaction,
    persona: Persona,
    *,
    is_staff: bool = False,
) -> bool:
    """Check if a persona can view an interaction.

    This gate governs an IC ACTION (a scene reaction — "did you actually witness
    this event?"), which is why it exists as a third cascade alongside
    ``InteractionQuerySet.visible_to`` (read-visibility for the scene log) and
    ``CanViewInteraction`` (REST object permission) rather than being redundant
    with either: a reactor whose account can technically read the log is still
    blocked here if their PERSONA never perceived the event (#2710).

    Visibility cascade:
    1. very_private -> writer + InteractionReceiver check (not staff)
    2. perceived_only -> writer + InteractionReceiver check (+ staff) (#2710)
    3. Whisper or place-scoped -> writer + InteractionReceiver check (+ staff),
       regardless of scene privacy — mirrors the real-time push rule so the
       persisted log never shows more than the room heard
    4. Private scene -> all scene participants (Account-based via SceneParticipation)
    5. Public -> everyone
    """
    is_writer = interaction.persona_id == persona.pk
    is_receiver = InteractionReceiver.objects.filter(
        interaction=interaction,
        persona=persona,
    ).exists()
    heard_it = is_receiver or is_writer

    # Very private: only original receivers and writer, never staff
    if interaction.visibility == InteractionVisibility.VERY_PRIVATE:
        return heard_it

    # Staff can see everything except very_private
    if is_staff:
        return True

    # Perceived only (#2710): only the characters who actually perceived the
    # event, plus staff (already returned True above). Unlike VERY_PRIVATE this
    # tier still admits staff — checked here, after the staff early-return.
    if interaction.visibility == InteractionVisibility.PERCEIVED_ONLY:
        return heard_it

    if _is_receiver_scoped(interaction):
        return heard_it

    # Private scene: all scene participants
    scene = interaction.scene
    if scene is not None and scene.privacy_mode == ScenePrivacyMode.PRIVATE:
        return _private_scene_admits(scene, persona, is_writer=is_writer)

    # Public scene, or no scene at all (pose/emit/say/shout/action) = public
    return True


def _get_account_for_persona(persona: Persona) -> int | None:
    """Get the account ID for a persona's character via roster tenure."""
    return _get_account_for_character(persona.character_sheet_id)


def accounts_for_personas(personas: list[Persona]) -> dict[int, int]:
    """Map persona pk -> current account id for a batch of personas, in one query (#1219).

    The batched form of ``_get_account_for_persona`` — used when pinning receiver accounts at
    interaction creation so a place-scoped (whole-room) interaction stays O(1) queries.
    Personas whose character has no current tenure are simply absent from the map. Public
    (#2710) so callers outside this module — e.g. concealing a cast's ACTION interaction in
    ``world.scenes.cast_services`` — can pin receiver accounts without reaching for an
    underscore-prefixed name.
    """
    from world.roster.models import RosterTenure  # noqa: PLC0415

    sheet_ids = {p.character_sheet_id for p in personas}
    sheet_to_account = dict(
        RosterTenure.objects.filter(
            roster_entry__character_sheet_id__in=sheet_ids,
            end_date__isnull=True,
        ).values_list("roster_entry__character_sheet_id", "player_data__account_id")
    )
    return {
        p.pk: sheet_to_account[p.character_sheet_id]
        for p in personas
        if p.character_sheet_id in sheet_to_account
    }


def _get_account_for_character(character_id: int) -> int | None:
    """Get the account ID for a character via roster tenure."""
    from world.roster.models import RosterEntry  # noqa: PLC0415

    try:
        entry = RosterEntry.objects.get(character_sheet_id=character_id)
        tenure = entry.tenures.filter(end_date__isnull=True).first()
        if tenure is None:
            return None
        player_data = tenure.player_data
        return player_data.account_id
    except RosterEntry.DoesNotExist:
        return None


def ensure_scene_participation(scene: Scene, character: ObjectDB) -> None:
    """Add a character's account as a SceneParticipation if not already present.

    Membership only — no covenant side-effects. No-op when the character has no
    account. Caches known participant account IDs on the Scene to avoid a
    get_or_create per call.
    """
    from world.scenes.models import SceneParticipation  # noqa: PLC0415

    account_id = _get_account_for_character(character.pk)
    if account_id is None:
        return

    try:
        known_ids = scene._participant_account_ids  # noqa: SLF001
    except AttributeError:
        known_ids = set(
            SceneParticipation.objects.filter(scene=scene).values_list("account_id", flat=True)
        )
        scene._participant_account_ids = known_ids  # noqa: SLF001

    if account_id in known_ids:
        return

    SceneParticipation.objects.get_or_create(scene=scene, account_id=account_id)
    known_ids.add(account_id)


def _ensure_scene_participation(scene: Scene, character: ObjectDB) -> None:
    """Membership (see ensure_scene_participation) plus covenant engagement.

    Used by the interaction-recording path; combat uses the membership-only
    public function to avoid double-firing scene engagement.
    """
    ensure_scene_participation(scene, character)

    # Auto-engage covenant for the participant (Slice B §4.10). Fires even when
    # the character has no account yet, matching prior behavior.
    sheet = character.character_sheet
    if sheet is not None and scene.location is not None:
        from world.covenants.services import evaluate_scene_engagement  # noqa: PLC0415

        evaluate_scene_engagement(character_sheet=sheet, room=scene.location)


def mark_very_private(
    interaction: Interaction,
    persona: Persona,
) -> None:
    """Mark an interaction as very_private. One-way operation.

    Any receiver or the writer can escalate.

    TODO: Callers should mark whole conversation threads at once, not single
    interactions. A future ``mark_thread_very_private()`` should find all
    interactions in the same thread (same target_persona pairing in both
    directions within a time window) and mark them all. Thread detection
    logic deferred as a UX concern -- the per-interaction primitive is correct.
    """
    is_receiver = InteractionReceiver.objects.filter(
        interaction=interaction,
        persona=persona,
    ).exists()
    is_writer = interaction.persona_id == persona.pk

    if not (is_receiver or is_writer):
        return

    interaction.visibility = InteractionVisibility.VERY_PRIVATE
    interaction.save(update_fields=["visibility"])


def delete_interaction(
    interaction: Interaction,
    persona: Persona,
) -> bool:
    """Hard-delete an interaction if the requester is the writer and within 30 days.

    Returns True if deleted, False if not allowed.
    """
    if interaction.persona_id != persona.pk:
        return False

    age = timezone.now() - interaction.timestamp
    if age > timedelta(days=DELETION_WINDOW_DAYS):
        return False

    interaction.delete()
    return True


def resolve_audience(character: ObjectDB) -> list[Persona]:
    """Get the active personas of all other characters in the room.

    Returns empty list if the character is alone or has no location.
    Characters without a CharacterSheet/primary persona (NPCs) are skipped.
    """
    location = character.location
    if location is None:
        return []

    from world.scenes.constants import PersonaType  # noqa: PLC0415
    from world.scenes.models import Persona  # noqa: PLC0415

    other_pks = [obj.pk for obj in location.contents if obj != character]
    if not other_pks:
        return []

    return list(
        Persona.objects.filter(
            character_sheet__character_id__in=other_pks,
            persona_type=PersonaType.PRIMARY,
        )
    )


def resolve_characters_by_name(names: Iterable[str], location: ObjectDB) -> list[ObjectDB]:
    """Resolve bare character names against a room's contents (case-insensitive exact match).

    Shared target-resolution semantics for directed communication: the telnet/WS
    ``@Name``-prefix parser (``commands.parsing.parse_targets_from_text``) and the
    REST submit-pose ``target_names`` field both resolve through this helper, so a
    directed pose behaves identically regardless of which surface sent it.
    Unresolvable names are silently skipped (not an error).
    """
    targets: list[ObjectDB] = []
    for name in names:
        lower_name = name.lower()
        for obj in location.contents:
            if obj.db_key.lower() == lower_name:
                targets.append(obj)
                break
    return targets


def personas_for_characters(characters: Iterable[ObjectDB]) -> list[Persona] | None:
    """Resolve each character to its primary persona, for communication targeting.

    Shared by the WS/telnet communication actions
    (``actions.definitions.communication._characters_to_active_personas``) and the
    REST submit-pose path, so both derive ``InteractionTargetPersona`` rows the same
    way. Returns ``None`` (not an empty list) when nothing resolves, matching
    ``create_interaction``/``record_interaction``'s "no explicit targets" contract.
    """
    personas: list[Persona] = []
    for character in characters:
        try:
            sheet = character.sheet_data
            primary = sheet.primary_persona
        except (AttributeError, ObjectDoesNotExist):
            continue
        if primary is not None:
            personas.append(primary)
    return personas or None


@dataclass
class IdempotentSubmissionResult:
    """Outcome of an idempotency-checked interaction submission."""

    interaction: Interaction | None
    replayed: bool
    conflict: bool


def _comparison_fields_match(
    stored: Interaction, comparison_fields: dict[str, object | Callable[[Interaction], bool]]
) -> bool:
    """True when every `comparison_fields` entry matches `stored` (#3760 review fix).

    A plain (non-callable) value is compared via `getattr(stored, field) == value` -- the
    original scalar-only behavior, unchanged; `SayAction` still uses this form only (directed-say
    idempotency is out of scope, see #3760). `submit_pose` now also uses the callable form below
    for target identity. A callable value is called with `stored` and its truthy/falsy
    return is the match result directly -- the caller closes over whatever "current" value
    it wants to compare against, since target/place identity isn't always a simple scalar
    attribute (`Interaction.target_personas` is M2M via `InteractionTargetPersona`, so
    `getattr(stored, "target_personas")` returns a manager, not a comparable value):

        comparison_fields={
            "content": text,
            "target": lambda stored: {p.pk for p in stored.target_personas.all()} == {pk},
        }

    Without this, a reused `client_request_id` against the same text but a genuinely
    different target/place was silently misclassified as a replay -- `replayed=True`,
    nothing (re-)delivered to the new intended audience, caller told it succeeded.
    """
    for field, value in comparison_fields.items():
        if callable(value):
            # `ty` can't narrow `object | Callable[[Interaction], bool]` from a bare
            # `callable()` check alone -- the cast asserts the concrete signature the
            # docstring above already documents as the contract.
            matcher = cast("Callable[[Interaction], bool]", value)
            if not matcher(stored):
                return False
        elif getattr(stored, field) != value:
            return False
    return True


def idempotent_record_interaction(
    *,
    persona: Persona,
    client_request_id: uuid.UUID,
    comparison_fields: dict[str, object | Callable[[Interaction], bool]],
    record_fn: Callable[..., Interaction | None] | None = None,
    **record_kwargs: Any,
) -> IdempotentSubmissionResult:
    """Idempotency-checked wrapper around `record_interaction` (#3760).

    Looks up an existing `PoseSubmission` for (persona, client_request_id) first.
    Found + no `Interaction` stored (an ephemeral-scene acceptance - `record_interaction`
    returns `None` there, nothing is ever persisted to compare against): a clean replay,
    never a conflict - there is nothing to recompute either way. Found + `comparison_fields`
    match the stored Interaction (see `_comparison_fields_match`): return that Interaction,
    nothing recomputed (no re-roll, no duplicate row). Found + any field differs: a
    `payload_conflict` (the caller reused a request id for genuinely different content/target/
    place - a client bug, not a legitimate retry). Not found: run the real work via `record_fn`
    (default `record_interaction`) inside a transaction; a concurrent duplicate insert (two
    near-simultaneous retries) raises `IntegrityError`, which is caught by re-reading and
    returning the winner's row rather than erroring - this is what makes the check race-safe.

    **The `PoseSubmission` row is written via `record_fn`'s `on_before_push` hook, not after
    `record_fn` returns (#3783 fix)**: the ledger insert must land BEFORE any real-time push,
    inside the same transaction, so that a genuine race between two retries is decided by
    Postgres's unique-index insert ordering -- the loser's `IntegrityError` fires from inside
    `record_fn`, before it ever reaches its own push call, and unwinds the whole `atomic()`
    block (including the `Interaction` row `record_fn` may have already created). Writing the
    ledger row only after `record_fn` returned (the pre-#3783 shape) let both racing retries
    clear their own push before either's ledger insert could block the other -- the persisted
    row stayed unique (proven by a Postgres-tagged concurrency test), but a visible duplicate
    pose could still reach the room in that narrow window.

    ``record_fn`` (#3760 Task 5) lets a caller substitute a differently-shaped recorder for
    `record_interaction` -- e.g. `WhisperAction` passes `record_whisper_interaction`, whose
    ephemeral-scene branch scopes the real-time push to the writer + named target
    (`recipients=[character, target]`) instead of `record_interaction`'s room-wide broadcast;
    reusing `record_interaction` there would leak whisper content to the whole ephemeral scene.
    Any `record_fn` used here must accept `on_before_push` and invoke it immediately before its
    first delivery push, on every branch (ephemeral and persisted alike).
    """
    record_fn = record_fn or record_interaction
    existing = (
        PoseSubmission.objects.filter(persona=persona, client_request_id=client_request_id)
        .select_related("interaction")
        .first()
    )
    if existing is not None:
        stored = existing.interaction
        if stored is None:
            # Ephemeral-scene acceptance: nothing was persisted the first time either, so
            # there is nothing to compare against and nothing left to (re)execute - a clean
            # replay, never a conflict.
            return IdempotentSubmissionResult(interaction=None, replayed=True, conflict=False)
        if _comparison_fields_match(stored, comparison_fields):
            return IdempotentSubmissionResult(interaction=stored, replayed=True, conflict=False)
        return IdempotentSubmissionResult(interaction=None, replayed=False, conflict=True)

    def _write_ledger(interaction_for_ledger: Interaction | None) -> None:
        PoseSubmission.objects.create(
            persona=persona,
            client_request_id=client_request_id,
            interaction=interaction_for_ledger,
        )

    try:
        with transaction.atomic():
            interaction = record_fn(on_before_push=_write_ledger, **record_kwargs)
    except IntegrityError:
        winner = PoseSubmission.objects.select_related("interaction").get(
            persona=persona, client_request_id=client_request_id
        )
        return IdempotentSubmissionResult(
            interaction=winner.interaction, replayed=True, conflict=False
        )

    return IdempotentSubmissionResult(interaction=interaction, replayed=False, conflict=False)


def record_interaction(  # noqa: C901, PLR0913 - all fields needed for interaction creation
    *,
    character: ObjectDB,
    content: str,
    mode: str,
    scene: Scene | None = None,
    place: Place | None = None,
    receivers: list[Persona] | None = None,
    target_personas: list[Persona] | None = None,
    persona: Persona | None = None,
    pose_kind: str = PoseKind.STANDARD,
    language: Language | None = None,
    attributed_companion: Companion | None = None,
    reply_to: ReplyTarget | None = None,
    on_created: Callable[[Interaction], None] | None = None,
    on_before_push: Callable[[Interaction | None], None] | None = None,
) -> Interaction | None:
    """Record an IC interaction to the database.

    Attributes authorship to the character's **currently-worn face**
    (``active_persona_for_sheet`` — the active persona when set, else PRIMARY),
    unless an explicit ``persona`` override is supplied. Never defaults to
    ``primary_persona`` directly: a character presenting as an ESTABLISHED alt
    or TEMPORARY mask must be recorded as that face, or the permanent scene
    record unmasks the disguise (#981 alt-leak rule).
    Skips recording if no persona could be resolved either way.

    For public interactions (no place, no receivers), the interaction is
    created without receiver rows. For place-scoped or whispered interactions,
    receiver rows are created from the place presences or explicit list.

    ``pose_kind`` classifies the interaction (Spec C; only meaningful for POSE mode).
    ``language`` (#2993) stamps the spoken language; null = universal/untagged.
    When set and not universal, ``push_interaction`` renders a per-recipient
    comprehension view for the broadcast branch (writer + staff get ground truth).
    ``on_created``, if given, runs after the row is created and scene participation is
    recorded, but *before* the real-time push — the seam callers use to attach
    side effects that must exist before clients can react to the pushed payload
    (e.g. opening a reaction window, bulk-creating InteractionAction links).
    ``attributed_companion`` (#3294) stamps cosmetic pose attribution — ``persona``
    (resolved above) stays the actual writer/author for block/mute/consent purposes.

    After persisting, pushes the interaction payload to all objects in the
    room via WebSocket for real-time delivery. Ephemeral scenes never persist —
    they push in real-time and return None; ``on_created`` is never called in that
    branch (there is no row to attach anything to).
    ``on_before_push`` (#3783), if given, runs immediately before the FIRST real-time
    push on every branch — including the ephemeral-scene push and the thread-update
    push, both of which precede ``on_created``. It exists solely for
    ``idempotent_record_interaction`` to write its `PoseSubmission` ledger row inside
    this same call, before any content reaches a client: writing the ledger row only
    after this function returns let two genuinely concurrent retries each clear their
    own push before either's ledger insert could block the other, so a caller could
    see a duplicate pose even though the persisted row stayed unique.
    """
    if persona is None:
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        try:
            persona = active_persona_for_sheet(character.sheet_data)
        except ObjectDoesNotExist:
            return None

    if scene is None:
        scene = get_active_scene(character.location)

    # Ephemeral scenes cannot persist or join threads.
    if scene is not None and scene.privacy_mode == ScenePrivacyMode.EPHEMERAL:
        if reply_to is not None:
            raise InteractionThreadError
        if on_before_push is not None:
            on_before_push(None)
        push_ephemeral_interaction(
            persona=persona,
            content=content,
            mode=mode,
            scene=scene,
            attributed_companion=attributed_companion,
        )
        return None

    interaction = create_interaction(
        persona=persona,
        content=content,
        mode=mode,
        scene=scene,
        place=place,
        receivers=receivers,
        target_personas=target_personas,
        pose_kind=pose_kind,
        language=language,
        attributed_companion=attributed_companion,
        reply_to=reply_to,
    )

    if scene is not None:
        _ensure_scene_participation(scene, character)

    if on_before_push is not None:
        on_before_push(interaction)

    thread_update = pending_thread_update(interaction)
    if thread_update is not None:
        push_interaction(thread_update)

    if on_created is not None:
        on_created(interaction)

    # Pass IDs we already know to avoid re-querying rows just created.
    # For receivers: if explicitly provided use those; if place-scoped,
    # create_interaction auto-populated from PlacePresence but we don't
    # have the resolved list here, so let push_interaction query those.
    r_ids: list[int] | None = None
    r_chars: list[ObjectDB] | None = None
    if receivers is not None:
        r_ids = [p.pk for p in receivers]
        r_chars = [p.character_sheet.character for p in receivers]
    elif place is None:
        # Public interaction: no receivers
        r_ids = []
        r_chars = []

    t_ids = [p.pk for p in target_personas] if target_personas else []

    push_interaction(
        interaction,
        receiver_persona_ids=r_ids,
        target_persona_ids=t_ids,
        receiver_characters=r_chars,
    )
    return interaction


def record_whisper_interaction(  # noqa: PLR0913 - on_before_push is the #3783 ledger seam
    *,
    character: ObjectDB,
    target: ObjectDB,
    content: str,
    language: Language | None = None,
    reply_to: ReplyTarget | None = None,
    on_before_push: Callable[[Interaction | None], None] | None = None,
) -> Interaction | None:
    """Record a whisper interaction with only the target as receiver.

    ``language`` (#2993) stamps the spoken language on the persisted row; the
    whisper text itself always stays full for its receiver-scoped audience
    (never garbled -- the speaker chose this listener).
    ``on_before_push`` (#3783) mirrors ``record_interaction``'s hook of the same name --
    called immediately before the FIRST real-time push on both branches, so
    ``idempotent_record_interaction`` can write its `PoseSubmission` ledger row before any
    content reaches a client. See ``record_interaction``'s docstring for the full rationale.
    """
    try:
        persona = character.sheet_data.primary_persona
        target_persona = target.sheet_data.primary_persona
    except ObjectDoesNotExist:
        return None

    scene = get_active_scene(character.location)

    # Ephemeral scenes cannot persist or join threads.
    if scene is not None and scene.privacy_mode == ScenePrivacyMode.EPHEMERAL:
        if reply_to is not None:
            raise InteractionThreadError
        if on_before_push is not None:
            on_before_push(None)
        push_ephemeral_interaction(
            persona=persona,
            content=content,
            mode=InteractionMode.WHISPER,
            scene=scene,
            recipients=[character, target],
        )
        return None

    interaction = create_interaction(
        persona=persona,
        content=content,
        mode=InteractionMode.WHISPER,
        receivers=[target_persona],
        scene=scene,
        target_personas=[target_persona],
        language=language,
        reply_to=reply_to,
    )
    if on_before_push is not None:
        on_before_push(interaction)
    push_interaction(
        interaction,
        receiver_persona_ids=[target_persona.pk],
        target_persona_ids=[target_persona.pk],
        receiver_characters=[target_persona.character_sheet.character],
    )
    return interaction


# Rationale for the OBJECTDB_PARAM suppression below (kept above the def
# since the inline form pushes the signature past 100 chars): any character,
# PC or NPC-run, can be the one addressed here; the function just needs its
# .location, .msg and the sheet lookup.
def narrate_privately(character: ObjectDB, text: str) -> None:  # noqa: OBJECTDB_PARAM
    """Narrator-authored line addressed to ONE character, on both channels (#3574).

    The single-recipient sibling of the room-wide combat narration
    (``world.combat.services._dual_dispatch_combat_narration``). Extracted from
    ``world.covenants.perks.services.announce_dormant_perks`` so every "tell
    this one player something only they should know" caller shares one body:

    - A Narrator-authored WHISPER-mode ``Interaction``, receiver-scoped to the
      recipient's PRIMARY persona (``receivers=[persona], target_personas=[persona]``,
      mirroring ``record_whisper_interaction``). Built via ``create_interaction``
      directly with ``persona=narrator`` rather than ``record_whisper_interaction``,
      which would attribute the line to the recipient whispering to themselves.
    - The WS payload goes ONLY to ``character`` via ``_send_to_objects``, never
      ``push_interaction`` (which resolves delivery off the WRITER persona's
      location, and the Narrator has none).
    - A direct ``character.msg(text)`` telnet companion (HARD telnet parity).

    No-op when the character has no sheet or no primary persona.
    """
    try:
        persona = character.sheet_data.primary_persona
    except (AttributeError, ObjectDoesNotExist):
        return

    from world.scenes.narrator import get_or_create_narrator_persona  # noqa: PLC0415

    narrator = get_or_create_narrator_persona()
    scene = get_active_scene(character.location)
    interaction = create_interaction(
        persona=narrator,
        content=text,
        mode=InteractionMode.WHISPER,
        scene=scene,
        receivers=[persona],
    )
    # ADR-0293 decision 3: this is a Narrator-authored system record, so its target
    # row goes through `write_target_personas` rather than `create_interaction`'s
    # validated kwarg. The whisper branch of `persona_can_receive` would happen to
    # accept (the recipient is their own receiver), but only by coincidence of shape:
    # the check anchors on the WRITER's location and the Narrator's character is
    # never physically placed, so no other shape here would survive it.
    write_target_personas(interaction, [persona])
    payload = _build_interaction_payload(
        interaction_id=interaction.pk,
        persona=narrator,
        content=interaction.content,
        mode=interaction.mode,
        timestamp=interaction.timestamp.isoformat(),
        scene_id=interaction.scene_id,
        receiver_persona_ids=[persona.pk],
        target_persona_ids=[persona.pk],
    )
    _send_to_objects([character], payload)
    character.msg(text)


def mutter_fragment(text: str) -> str:
    """The room-audible fragment of a mutter (#905): random word leak.

    Delegates to the shared garbler (#2993) at the classic one-word-in-three
    ratio, nondeterministic (SystemRandom) - a fresh leak every mutter.
    """
    from world.species.language_services import garble_text  # noqa: PLC0415

    return garble_text(text, 1 / 3)


def record_mutter_interaction(
    *,
    character: ObjectDB,
    receivers: list[ObjectDB],
    content: str,
    language: Language | None = None,
    reply_to: ReplyTarget | None = None,
) -> tuple[Interaction | None, Interaction | None]:
    """Record a mutter as TWO interactions (#905): full + fragment.

    The full text persists receiver-scoped (exactly like a whisper); the
    fragment persists PUBLIC — because the fragment is what the room
    heard, and the log never shows more than the room heard (#900/#903).
    Returns (full, fragment); ephemeral scenes push without persisting and
    return (None, None) exactly like the other recorders.

    ``language`` (#2993) stamps only the full-text interaction -- the
    fragment is already garbled by the mutter mechanic itself, so it stays
    untagged.
    """
    receiver_personas: list[Persona] = []
    for receiver in receivers:
        try:
            persona = receiver.sheet_data.primary_persona
        except ObjectDoesNotExist:
            continue
        if persona is not None:
            receiver_personas.append(persona)

    full = record_interaction(
        character=character,
        content=content,
        mode=InteractionMode.MUTTER,
        receivers=receiver_personas,
        target_personas=receiver_personas or None,
        language=language,
        reply_to=reply_to,
    )
    fragment = record_interaction(
        character=character,
        content=mutter_fragment(content),
        mode=InteractionMode.MUTTER,
    )
    return full, fragment


def render_challenge_outcome_narration(
    *,
    actor_label: str,
    challenge_name: str,
    approach_name: str,
    outcome_label: str,
    success_level: int,
) -> str:
    """Render a one-line, deterministic outcome narration for a resolved challenge.

    Pure function — no DB access, no randomness. The caller supplies primitives
    extracted from the ``ChallengeResolutionResult`` and the resolving participant,
    so this stays DB-free and unit-testable.

    Examples:
        "Kira attempts Scale the Wall (Athletics) and succeeds (Decisive Success)."
        "Kira attempts Scale the Wall (Athletics) and fails (Failure)."
    """
    verb = "succeeds" if success_level > 0 else "fails"
    return (
        f"{actor_label} attempts {challenge_name} ({approach_name}) and {verb} ({outcome_label})."
    )


def broadcast_scene_outcome(
    *,
    scene_round: SceneRound,
    narration: str,
) -> Interaction | None:
    """Persist a Narrator-authored OUTCOME interaction and broadcast it to the room.

    Scene-scoped analog of ``world.combat.interaction_services.broadcast_action_outcome``.
    Uses the scene_round's scene FK (nullable) for the scene log link and broadcasts
    to the room via the existing WebSocket delivery path.

    Returns the created Interaction, or None when narration is empty.
    """
    if not narration:
        return None

    from world.scenes.narrator import get_or_create_narrator_persona  # noqa: PLC0415

    narrator = get_or_create_narrator_persona()
    interaction = create_interaction(
        persona=narrator,
        content=narration,
        mode=InteractionMode.OUTCOME,
        scene=scene_round.scene,
    )

    room = scene_round.room.objectdb
    payload = _build_interaction_payload(
        interaction_id=interaction.pk,
        persona=narrator,
        content=interaction.content,
        mode=interaction.mode,
        timestamp=interaction.timestamp.isoformat(),
        scene_id=interaction.scene_id,
    )
    _broadcast_to_location(room, payload)
    return interaction


def _break_lie_low_for_interaction(persona: Persona, scene: Scene | None) -> None:
    """End any active lie-low in the scene's area (#1826) and, at hunted tier,
    roll public-interaction guard pressure (#2378). Cheap no-op path."""
    location = scene.location if scene is not None else None
    if location is None:
        return
    from world.justice.constants import GuardTrigger  # noqa: PLC0415
    from world.justice.lifecycle import break_lie_low_for_ic_action  # noqa: PLC0415
    from world.justice.pipeline import maybe_guard_encounter  # noqa: PLC0415
    from world.justice.services import area_for_room  # noqa: PLC0415

    area = area_for_room(location)
    break_lie_low_for_ic_action(persona, area)
    from world.justice.pipeline import public_room_profile  # noqa: PLC0415

    if public_room_profile(location) is not None:
        maybe_guard_encounter(persona, area, GuardTrigger.PUBLIC_INTERACTION)

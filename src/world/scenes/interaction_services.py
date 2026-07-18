from __future__ import annotations

import contextlib
from datetime import timedelta
import itertools
from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist
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
    Scene,
)
from world.scenes.place_models import InteractionReceiver, Place
from world.scenes.types import InteractionPayload, PersonaPayload

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from evennia.objects.models import ObjectDB

    from world.magic.models import FuryTier
    from world.scenes.models import SceneRound

DELETION_WINDOW_DAYS = 30
_ephemeral_counter = itertools.count()


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
) -> Interaction:
    """Create an atomic RP interaction with optional receiver records.

    Receiver logic:
    - If receivers are explicitly provided, create InteractionReceiver rows.
    - If place is provided without receivers, auto-populate from PlacePresence.
    - If neither place nor receivers, the interaction is public (no receiver rows).

    Callers must handle ephemeral scenes before calling this function --
    ephemeral interactions should never be persisted.

    Args:
        persona: The writer's identity (non-nullable).
        content: The actual written text.
        mode: InteractionMode value (pose, emit, say, etc.).
        scene: Scene container if one was active.
        place: Sub-location where this interaction occurred.
        receivers: Explicit list of personas who should receive this.
        target_personas: Explicit IC targets for thread derivation.
        strain_committed: Strain the initiator actually committed for this
            action. Persisted onto the resulting Interaction for audit.
        fury_committed: Realized FuryTier post-resolution (null = no fury). Audit field.
        pose_kind: PoseKind classification (Spec C); ENTRY poses open a
            Make-an-Entrance reaction window (#904) at the call site.

    Returns:
        The created Interaction.
    """
    # Pin the writer's account at creation (#1219) — party identity for private-content
    # log visibility, stable across later persona hand-offs.
    interaction = Interaction.objects.create(
        persona=persona,
        writer_account_id=_get_account_for_persona(persona),
        content=content,
        mode=mode,
        scene=scene,
        place=place,
        strain_committed=strain_committed,
        fury_committed=fury_committed,
        pose_kind=pose_kind,
    )
    # #1826 — posing in a scene is IC action in its area: lie-low breaks.
    _break_lie_low_for_interaction(persona, scene)

    # Determine receiver list
    effective_receivers = receivers
    if effective_receivers is None and place is not None:
        # Auto-populate from PlacePresence, excluding the writer
        effective_receivers = list(
            Persona.objects.filter(
                place_presences__place=place,
            ).exclude(pk=persona.pk)
        )

    if effective_receivers:
        # Pin each receiver's account too (#1219), batched to one query for the whole room.
        receiver_accounts = _accounts_for_personas(effective_receivers)
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

    return interaction


def create_action_interaction_core(
    *,
    persona: Persona,
    scene: Scene | None,
    summary_label: str,
    strain_committed: int = 0,
    fury_committed: FuryTier | None = None,
) -> Interaction:
    """Create one ACTION-mode Interaction for a resolved action/cast.

    The shared core behind combat's create_action_interaction and the scene
    cast path. Keyed on persona + (nullable) scene.
    """
    return Interaction.objects.create(
        persona=persona,
        scene=scene,
        content=summary_label,
        mode=InteractionMode.ACTION,
        strain_committed=strain_committed,
        fury_committed=fury_committed,
    )


def _send_to_objects(
    objects: Iterable[ObjectDB],
    payload: InteractionPayload,
) -> None:
    """Send an interaction payload to specific objects via WebSocket."""
    for obj in objects:
        try:
            obj.msg(interaction=((), payload))
        except AttributeError:
            continue


def _broadcast_to_location(
    location: ObjectDB,
    payload: InteractionPayload,
) -> None:
    """Send an interaction payload to all objects in a location via WebSocket."""
    _send_to_objects(location.contents, payload)


def _build_interaction_payload(  # noqa: PLR0913 - payload needs all interaction fields
    *,
    interaction_id: int,
    persona: Persona,
    content: str,
    mode: str,
    timestamp: str,
    scene_id: int | None,
    place_id: int | None = None,
    place_name: str | None = None,
    receiver_persona_ids: list[int] | None = None,
    target_persona_ids: list[int] | None = None,
) -> InteractionPayload:
    """Build a structured interaction payload for WebSocket delivery."""
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
        scene_id=scene_id,
        place_id=place_id,
        place_name=place_name,
        receiver_persona_ids=receiver_persona_ids or [],
        target_persona_ids=target_persona_ids or [],
    )


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
        scene_id=interaction.scene_id,
        place_id=interaction.place_id,
        place_name=interaction.place.name if interaction.place_id else None,
        receiver_persona_ids=r_ids,
        target_persona_ids=t_ids,
    )

    if interaction.mode == InteractionMode.WHISPER or interaction.place_id is not None:
        writer_char = persona.character_sheet.character
        _send_to_objects([writer_char, *r_chars], payload)
    else:
        _broadcast_to_location(location, payload)


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
    )

    if recipients is not None:
        _send_to_objects(recipients, payload)
    else:
        location = persona.character_sheet.character.location
        if location is None:
            return
        _broadcast_to_location(location, payload)


def can_view_interaction(  # noqa: PLR0911 - visibility cascade has distinct branches
    interaction: Interaction,
    persona: Persona,
    *,
    is_staff: bool = False,
) -> bool:
    """Check if a persona can view an interaction.

    Visibility cascade:
    1. very_private -> writer + InteractionReceiver check (not staff)
    2. Whisper or place-scoped -> writer + InteractionReceiver check (+ staff),
       regardless of scene privacy — mirrors the real-time push rule so the
       persisted log never shows more than the room heard
    3. Private scene -> all scene participants (Account-based via SceneParticipation)
    4. Public -> everyone
    """
    is_writer = interaction.persona_id == persona.pk
    is_receiver = InteractionReceiver.objects.filter(
        interaction=interaction,
        persona=persona,
    ).exists()

    # Very private: only original receivers and writer, never staff
    if interaction.visibility == InteractionVisibility.VERY_PRIVATE:
        return is_receiver or is_writer

    # Staff can see everything except very_private
    if is_staff:
        return True

    # Whisper, receiver-scoped mutter, or place-scoped (table talk): only
    # writer + receivers, even inside a public or private scene. A mutter
    # WITHOUT receiver rows is the public fragment (#905) — what the room
    # heard — and falls through to scene-level visibility.
    if interaction.mode == InteractionMode.WHISPER or interaction.place_id is not None:
        return is_receiver or is_writer
    if (
        interaction.mode == InteractionMode.MUTTER
        and InteractionReceiver.objects.filter(interaction=interaction).exists()
    ):
        return is_receiver or is_writer

    # Private scene: all scene participants
    scene = interaction.scene
    if scene is not None and scene.privacy_mode == ScenePrivacyMode.PRIVATE:
        # Check if persona's account is a scene participant
        from world.scenes.models import SceneParticipation  # noqa: PLC0415

        account_id = _get_account_for_persona(persona)
        if account_id is not None:
            is_participant = SceneParticipation.objects.filter(
                scene=scene,
                account_id=account_id,
            ).exists()
            if is_participant or is_writer:
                return True
        return is_writer

    # Public scene or no scene with room-wide mode = public
    if scene is not None and scene.privacy_mode == ScenePrivacyMode.PUBLIC:
        return True

    # Default: public (pose/emit/say/shout/action without a scene)
    return True


def _get_account_for_persona(persona: Persona) -> int | None:
    """Get the account ID for a persona's character via roster tenure."""
    return _get_account_for_character(persona.character_sheet_id)


def _accounts_for_personas(personas: list[Persona]) -> dict[int, int]:
    """Map persona pk -> current account id for a batch of personas, in one query (#1219).

    The batched form of ``_get_account_for_persona`` — used when pinning receiver accounts at
    interaction creation so a place-scoped (whole-room) interaction stays O(1) queries.
    Personas whose character has no current tenure are simply absent from the map.
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


def record_interaction(  # noqa: PLR0913 - all fields needed for interaction creation
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
    on_created: Callable[[Interaction], None] | None = None,
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
    ``on_created``, if given, runs after the row is created and scene participation is
    recorded, but *before* the real-time push — the seam callers use to attach
    side effects that must exist before clients can react to the pushed payload
    (e.g. opening a reaction window, bulk-creating InteractionAction links).

    After persisting, pushes the interaction payload to all objects in the
    room via WebSocket for real-time delivery. Ephemeral scenes never persist —
    they push in real-time and return None; ``on_created`` is never called in that
    branch (there is no row to attach anything to).
    """
    if persona is None:
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        try:
            persona = active_persona_for_sheet(character.sheet_data)
        except ObjectDoesNotExist:
            return None

    if scene is None:
        scene = get_active_scene(character.location)

    # Ephemeral scenes: push in real-time but never persist
    if scene is not None and scene.privacy_mode == ScenePrivacyMode.EPHEMERAL:
        push_ephemeral_interaction(
            persona=persona,
            content=content,
            mode=mode,
            scene=scene,
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
    )

    if scene is not None:
        _ensure_scene_participation(scene, character)

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


def record_whisper_interaction(
    *,
    character: ObjectDB,
    target: ObjectDB,
    content: str,
) -> Interaction | None:
    """Record a whisper interaction with only the target as receiver."""
    try:
        persona = character.sheet_data.primary_persona
        target_persona = target.sheet_data.primary_persona
    except ObjectDoesNotExist:
        return None

    scene = get_active_scene(character.location)

    # Ephemeral scenes: push in real-time but never persist
    if scene is not None and scene.privacy_mode == ScenePrivacyMode.EPHEMERAL:
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
    )
    push_interaction(
        interaction,
        receiver_persona_ids=[target_persona.pk],
        target_persona_ids=[target_persona.pk],
        receiver_characters=[target_persona.character_sheet.character],
    )
    return interaction


def mutter_fragment(text: str) -> str:
    """The room-audible fragment of a mutter (#905): random word leak.

    Classic MUSH mutter, per Apostate's ruling: roughly one word in three
    survives; elided runs collapse to a single "...". At least one word
    always leaks (a mutter is audible, that's the point — and the risk).
    """
    import random  # noqa: PLC0415

    rng = random.SystemRandom()
    words = text.split()
    if not words:
        return "..."
    kept_flags = [rng.random() < 1 / 3 for _ in words]
    if not any(kept_flags):
        kept_flags[rng.randrange(len(words))] = True
    parts: list[str] = []
    for word, kept in zip(words, kept_flags, strict=True):
        if kept:
            parts.append(word)
        elif not parts or parts[-1] != "...":
            parts.append("...")
    return " ".join(parts)


def record_mutter_interaction(
    *,
    character: ObjectDB,
    receivers: list[ObjectDB],
    content: str,
) -> tuple[Interaction | None, Interaction | None]:
    """Record a mutter as TWO interactions (#905): full + fragment.

    The full text persists receiver-scoped (exactly like a whisper); the
    fragment persists PUBLIC — because the fragment is what the room
    heard, and the log never shows more than the room heard (#900/#903).
    Returns (full, fragment); ephemeral scenes push without persisting and
    return (None, None) exactly like the other recorders.
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

    room = scene_round.room
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

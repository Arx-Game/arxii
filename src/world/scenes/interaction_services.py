from __future__ import annotations

import contextlib
from datetime import timedelta
import itertools
from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist
from django.db import models as db_models
from django.utils import timezone

from world.scenes.constants import InteractionMode, InteractionVisibility, ScenePrivacyMode
from world.scenes.models import (
    Interaction,
    InteractionTargetPersona,
    Persona,
    Scene,
)
from world.scenes.place_models import InteractionReceiver, Place

if TYPE_CHECKING:
    from collections.abc import Iterable

    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet

DELETION_WINDOW_DAYS = 30
_ephemeral_counter = itertools.count()


def _get_active_scene(location: ObjectDB | None) -> Scene | None:
    """Get the active scene for a location, with in-memory caching.

    Caches the result on the location object (which persists in memory via
    SharedMemoryModel's identity map). Invalidated by
    invalidate_active_scene_cache() when a scene starts or ends.
    """
    if location is None:
        return None
    try:
        cached: Scene | None = location._active_scene_cache  # noqa: SLF001 — in-memory cache on identity-mapped object
        return cached
    except AttributeError:
        pass
    scene = Scene.objects.filter(location=location, is_active=True).first()
    location._active_scene_cache = scene  # noqa: SLF001 — in-memory cache on identity-mapped object
    return scene


def invalidate_active_scene_cache(location: ObjectDB) -> None:
    """Clear the cached active scene for a location.

    Call this when a scene starts or ends.
    """
    with contextlib.suppress(AttributeError):
        del location._active_scene_cache  # noqa: SLF001 — in-memory cache on identity-mapped object


def reassign_persona_interactions(
    *,
    source_persona: Persona,
    target_persona: Persona,
) -> int:
    """Reassign all interactions from source_persona to target_persona.

    Both personas must belong to the same CharacterIdentity. This is used
    when merging personas (e.g., discovering a temporary disguise is the
    same person as an established identity).

    Returns the number of interactions reassigned.
    """
    if source_persona.character_identity_id != target_persona.character_identity_id:
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

    Returns:
        The created Interaction.
    """
    interaction = Interaction.objects.create(
        persona=persona,
        content=content,
        mode=mode,
        scene=scene,
        place=place,
    )

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
        InteractionReceiver.objects.bulk_create(
            [
                InteractionReceiver(
                    interaction=interaction,
                    timestamp=interaction.timestamp,
                    persona=recv_persona,
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


def _send_to_objects(
    objects: Iterable[ObjectDB],
    payload: dict[str, object],
) -> None:
    """Send an interaction payload to specific objects via WebSocket."""
    for obj in objects:
        try:
            obj.msg(interaction=((), payload))
        except AttributeError:
            continue


def _broadcast_to_location(
    location: ObjectDB,
    payload: dict[str, object],
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
) -> dict[str, object]:
    """Build a structured interaction payload for WebSocket delivery."""
    return {
        "id": interaction_id,
        "persona": {
            "id": persona.pk,
            "name": persona.name,
            "thumbnail_url": persona.thumbnail_url or "",
        },
        "content": content,
        "mode": mode,
        "timestamp": timestamp,
        "scene_id": scene_id,
        "place_id": place_id,
        "place_name": place_name,
        "receiver_persona_ids": receiver_persona_ids or [],
        "target_persona_ids": target_persona_ids or [],
    }


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
    location = persona.character.location
    if location is None:
        return

    # Use passed IDs if available; otherwise fall back to querying.
    if receiver_persona_ids is None or receiver_characters is None:
        receivers = list(
            InteractionReceiver.objects.filter(
                interaction=interaction,
            ).select_related("persona__character")
        )
        r_ids = [r.persona_id for r in receivers]
        r_chars = [r.persona.character for r in receivers]
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
        writer_char = persona.character
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
        location = persona.character.location
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
    2. Place-scoped -> writer + InteractionReceiver check
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

    # Place-scoped: only writer + receivers
    if interaction.place_id is not None:
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

    # Only WHISPER is receiver-scoped without a scene
    if interaction.mode in (InteractionMode.WHISPER,):
        return is_receiver or is_writer

    # Default: public (pose/emit/say/shout/action without a scene)
    return True


def _get_account_for_persona(persona: Persona) -> int | None:
    """Get the account ID for a persona's character via roster tenure."""
    return _get_account_for_character(persona.character_id)


def _get_account_for_character(character_id: int) -> int | None:
    """Get the account ID for a character via roster tenure."""
    from world.roster.models import RosterEntry  # noqa: PLC0415

    try:
        entry = RosterEntry.objects.get(character_id=character_id)
        tenure = entry.tenures.filter(end_date__isnull=True).first()
        if tenure is None:
            return None
        player_data = tenure.player_data
        return player_data.account_id
    except RosterEntry.DoesNotExist:
        return None


def _ensure_scene_participation(scene: Scene, character: ObjectDB) -> None:
    """Auto-add a character's account as a SceneParticipation if not already present.

    Caches the set of known participant account IDs on the Scene object to
    avoid a get_or_create query per interaction.
    """
    from world.scenes.models import SceneParticipation  # noqa: PLC0415

    account_id = _get_account_for_character(character.pk)
    if account_id is None:
        return

    # Check in-memory cache first
    try:
        known_ids = scene._participant_account_ids  # noqa: SLF001 — in-memory cache on identity-mapped object
    except AttributeError:
        known_ids = set(
            SceneParticipation.objects.filter(scene=scene).values_list("account_id", flat=True)
        )
        scene._participant_account_ids = known_ids  # noqa: SLF001 — in-memory cache on identity-mapped object

    if account_id in known_ids:
        return

    SceneParticipation.objects.get_or_create(
        scene=scene,
        account_id=account_id,
    )
    known_ids.add(account_id)


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
    Characters without a CharacterIdentity (NPCs) are skipped.
    """
    location = character.location
    if location is None:
        return []

    from world.character_sheets.models import CharacterIdentity  # noqa: PLC0415

    other_pks = [obj.pk for obj in location.contents if obj != character]
    if not other_pks:
        return []

    identities = CharacterIdentity.objects.filter(
        character_id__in=other_pks,
    ).select_related("active_persona")
    return [identity.active_persona for identity in identities if identity.active_persona]


def record_interaction(  # noqa: PLR0913 - all fields needed for interaction creation
    *,
    character: ObjectDB,
    content: str,
    mode: str,
    scene: Scene | None = None,
    place: Place | None = None,
    receivers: list[Persona] | None = None,
    target_personas: list[Persona] | None = None,
) -> Interaction | None:
    """Record an IC interaction to the database.

    Reads the character's active_persona from CharacterIdentity. Skips
    recording if the character has no CharacterIdentity or no active persona.

    For public interactions (no place, no receivers), the interaction is
    created without receiver rows. For place-scoped or whispered interactions,
    receiver rows are created from the place presences or explicit list.

    After persisting, pushes the interaction payload to all objects in the
    room via WebSocket for real-time delivery.
    """
    try:
        identity = character.character_identity
    except ObjectDoesNotExist:
        return None

    persona = identity.active_persona
    if persona is None:
        return None

    if scene is None:
        scene = _get_active_scene(character.location)

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
    )

    if scene is not None:
        _ensure_scene_participation(scene, character)

    # Pass IDs we already know to avoid re-querying rows just created.
    # For receivers: if explicitly provided use those; if place-scoped,
    # create_interaction auto-populated from PlacePresence but we don't
    # have the resolved list here, so let push_interaction query those.
    r_ids: list[int] | None = None
    r_chars: list[ObjectDB] | None = None
    if receivers is not None:
        r_ids = [p.pk for p in receivers]
        r_chars = [p.character for p in receivers]
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
        writer_identity = character.character_identity
        target_identity = target.character_identity
    except ObjectDoesNotExist:
        return None

    persona = writer_identity.active_persona
    target_persona = target_identity.active_persona

    if persona is None or target_persona is None:
        return None

    scene = _get_active_scene(character.location)

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
        receiver_characters=[target_persona.character],
    )
    return interaction


def resolve_persona_display(
    *,
    persona: Persona,
    viewer_character_sheet: CharacterSheet,
) -> tuple[str, bool]:
    """Resolve what name to display for a persona to a specific viewer.

    Returns (display_name, is_discovered) tuple.
    - If the persona is not fake (is_fake_name=False), returns the persona name.
    - If the persona is fake and the viewer has discovered a link, returns
      the linked persona's name with annotation.
    - If the persona is fake and not discovered, returns the persona name as-is.
    """
    if not persona.is_fake_name:
        return persona.name, False

    from world.scenes.models import PersonaDiscovery  # noqa: PLC0415

    discovery = (
        PersonaDiscovery.objects.filter(
            db_models.Q(persona=persona) | db_models.Q(linked_to=persona),
            discovered_by=viewer_character_sheet,
        )
        .select_related("persona", "linked_to")
        .first()
    )

    if discovery is None:
        return persona.name, False

    linked = discovery.linked_to if discovery.persona_id == persona.pk else discovery.persona
    return f"{linked.name} (as {persona.name})", True

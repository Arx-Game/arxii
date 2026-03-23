from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist
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
    from evennia.objects.models import ObjectDB

DELETION_WINDOW_DAYS = 30
_active_scene_attr = "active_scene"


def create_interaction(  # noqa: PLR0913 - atomic creation requires all interaction fields
    *,
    persona: Persona,
    content: str,
    mode: str,
    scene: Scene | None = None,
    place: Place | None = None,
    receivers: list[Persona] | None = None,
    target_personas: list[Persona] | None = None,
) -> Interaction | None:
    """Create an atomic RP interaction with optional receiver records.

    For ephemeral scenes, returns None without persisting anything --
    the interaction is delivered in real-time but never stored.

    Receiver logic:
    - If receivers are explicitly provided, create InteractionReceiver rows.
    - If place is provided without receivers, auto-populate from PlacePresence.
    - If neither place nor receivers, the interaction is public (no receiver rows).

    Args:
        persona: The writer's identity (non-nullable).
        content: The actual written text.
        mode: InteractionMode value (pose, emit, say, etc.).
        scene: Scene container if one was active.
        place: Sub-location where this interaction occurred.
        receivers: Explicit list of personas who should receive this.
        target_personas: Explicit IC targets for thread derivation.

    Returns:
        The created Interaction, or None for ephemeral scenes.
    """
    if scene is not None and scene.privacy_mode == ScenePrivacyMode.EPHEMERAL:
        return None

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


def push_interaction(interaction: Interaction) -> None:
    """Push a structured interaction payload to connected clients via WebSocket.

    Uses Evennia's msg() which routes through the WebSocket to connected
    web clients. The message type 'interaction' will be handled by a new
    WS_MESSAGE_TYPE on the frontend.

    Sends to all objects in the interaction's location, not just audience
    members -- the frontend handles visibility filtering.
    """
    persona = interaction.persona
    location = persona.character.location
    if location is None:
        return

    payload = {
        "id": interaction.pk,
        "persona": {
            "id": persona.pk,
            "name": persona.name,
            "thumbnail_url": persona.thumbnail_url or "",
        },
        "content": interaction.content,
        "mode": interaction.mode,
        "timestamp": interaction.timestamp.isoformat(),
        "scene_id": interaction.scene_id,
    }

    for obj in location.contents:
        try:
            obj.msg(interaction=((), payload))
        except AttributeError:
            continue


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
    from world.roster.models import RosterEntry  # noqa: PLC0415

    try:
        entry = RosterEntry.objects.get(character_id=persona.character_id)
        tenure = entry.tenures.filter(end_date__isnull=True).first()
        if tenure is None:
            return None
        player_data = tenure.player_data
        return player_data.account_id
    except RosterEntry.DoesNotExist:
        return None


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

    if scene is None and character.location is not None:
        scene = getattr(character.location, _active_scene_attr, None)

    interaction = create_interaction(
        persona=persona,
        content=content,
        mode=mode,
        scene=scene,
        place=place,
        receivers=receivers,
        target_personas=target_personas,
    )
    if interaction is not None:
        push_interaction(interaction)
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

    scene: Scene | None = None
    if character.location is not None:
        scene = getattr(character.location, _active_scene_attr, None)

    interaction = create_interaction(
        persona=persona,
        content=content,
        mode=InteractionMode.WHISPER,
        receivers=[target_persona],
        scene=scene,
        target_personas=[target_persona],
    )
    if interaction is not None:
        push_interaction(interaction)
    return interaction

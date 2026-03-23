from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

from world.scenes.constants import InteractionMode, InteractionVisibility, ScenePrivacyMode
from world.scenes.models import (
    Interaction,
    InteractionAudience,
    InteractionTargetPersona,
    Persona,
    Scene,
)

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

DELETION_WINDOW_DAYS = 30
_active_scene_attr = "active_scene"


def create_interaction(  # noqa: PLR0913 - atomic creation requires all interaction fields
    *,
    persona: Persona,
    content: str,
    mode: str,
    audience_personas: list[Persona],
    scene: Scene | None = None,
    target_personas: list[Persona] | None = None,
) -> Interaction | None:
    """Create an atomic RP interaction with audience records.

    For ephemeral scenes, returns None without persisting anything --
    the interaction is delivered in real-time but never stored.

    Args:
        persona: The writer's identity (non-nullable).
        content: The actual written text.
        mode: InteractionMode value (pose, emit, say, etc.).
        audience_personas: Personas who can see this interaction.
        scene: Scene container if one was active.
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
    )

    audience_records = [
        InteractionAudience(
            interaction=interaction,
            timestamp=interaction.timestamp,
            persona=audience_persona,
        )
        for audience_persona in audience_personas
    ]
    InteractionAudience.objects.bulk_create(audience_records)

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


def can_view_interaction(
    interaction: Interaction,
    persona: Persona,
    *,
    is_staff: bool = False,
) -> bool:
    """Check if a persona can view an interaction.

    Visibility cascade:
    1. very_private -> only original audience personas (not staff)
    2. Private scene -> audience + staff
    3. Default -> audience for audience-scoped, public for public scenes
    """
    is_audience = InteractionAudience.objects.filter(
        interaction=interaction,
        persona=persona,
    ).exists()
    is_writer = interaction.persona_id == persona.pk

    # Very private: only original audience and writer, never staff
    if interaction.visibility == InteractionVisibility.VERY_PRIVATE:
        return is_audience or is_writer

    # Staff can see everything except very_private
    if is_staff:
        return True

    # Private scene: audience + staff only
    scene = interaction.scene
    if scene is not None and scene.privacy_mode == ScenePrivacyMode.PRIVATE:
        return is_audience or is_writer

    # Public scene or no scene with room-wide mode = public
    if scene is not None and scene.privacy_mode == ScenePrivacyMode.PUBLIC:
        return True

    # Only WHISPER is audience-scoped without a scene -- SAY/POSE/EMIT/SHOUT are
    # public room communication even without a formal scene.
    if interaction.mode in (InteractionMode.WHISPER,):
        return is_audience or is_writer

    # Default: public (pose/emit/say/shout/action without a scene)
    return True


def mark_very_private(
    interaction: Interaction,
    persona: Persona,
) -> None:
    """Mark an interaction as very_private. One-way operation.

    Any audience member or the writer can escalate.

    TODO: Callers should mark whole conversation threads at once, not single
    interactions. A future ``mark_thread_very_private()`` should find all
    interactions in the same thread (same target_persona pairing in both
    directions within a time window) and mark them all. Thread detection
    logic deferred as a UX concern -- the per-interaction primitive is correct.
    """
    is_audience = InteractionAudience.objects.filter(
        interaction=interaction,
        persona=persona,
    ).exists()
    is_writer = interaction.persona_id == persona.pk

    if not (is_audience or is_writer):
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


def record_interaction(
    *,
    character: ObjectDB,
    content: str,
    mode: str,
    scene: Scene | None = None,
    target_personas: list[Persona] | None = None,
) -> Interaction | None:
    """Record an IC interaction to the database.

    Reads the character's active_persona from CharacterIdentity. Resolves
    audience from other characters in the room. Skips recording if:
    - Character has no CharacterIdentity
    - No audience (character is alone)
    - Scene is ephemeral

    This is the persistence layer only -- does NOT broadcast to clients.
    Call message_location() separately for real-time delivery.
    """
    try:
        identity = character.character_identity
    except ObjectDoesNotExist:
        return None

    persona = identity.active_persona
    if persona is None:
        return None

    audience_personas = resolve_audience(character)

    if not audience_personas:
        return None

    if scene is None and character.location is not None:
        scene = getattr(character.location, _active_scene_attr, None)

    return create_interaction(
        persona=persona,
        content=content,
        mode=mode,
        audience_personas=audience_personas,
        scene=scene,
        target_personas=target_personas,
    )


def record_whisper_interaction(
    *,
    character: ObjectDB,
    target: ObjectDB,
    content: str,
) -> Interaction | None:
    """Record a whisper interaction with only the target as audience."""
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

    return create_interaction(
        persona=persona,
        content=content,
        mode=InteractionMode.WHISPER,
        audience_personas=[target_persona],
        scene=scene,
        target_personas=[target_persona],
    )

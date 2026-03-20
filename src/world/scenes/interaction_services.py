from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

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

    from world.roster.models import RosterEntry

DELETION_WINDOW_DAYS = 30


def create_interaction(  # noqa: PLR0913 - atomic creation requires all interaction fields
    *,
    character: ObjectDB,
    roster_entry: RosterEntry,
    location: ObjectDB,
    content: str,
    mode: str,
    audience_roster_entries: list[RosterEntry],
    scene: Scene | None = None,
    persona: Persona | None = None,
    target_personas: list[Persona] | None = None,
    audience_personas: dict[int, Persona] | None = None,
) -> Interaction | None:
    """Create an atomic RP interaction with audience records.

    For ephemeral scenes, returns None without persisting anything —
    the interaction is delivered in real-time but never stored.

    Args:
        character: The IC identity who wrote this interaction.
        roster_entry: The specific player (privacy binds here).
        location: Where this interaction happened.
        content: The actual written text.
        mode: InteractionMode value (pose, emit, say, etc.).
        audience_roster_entries: Roster entries who can see this interaction.
        scene: Scene container if one was active.
        persona: Disguise/alt identity if active.
        target_personas: Explicit IC targets for thread derivation.
        audience_personas: Map of roster_entry PK to Persona for audience members.

    Returns:
        The created Interaction, or None for ephemeral scenes.
    """
    if scene is not None and scene.privacy_mode == ScenePrivacyMode.EPHEMERAL:
        return None

    interaction = Interaction.objects.create(
        character=character,
        roster_entry=roster_entry,
        location=location,
        content=content,
        mode=mode,
        scene=scene,
        persona=persona,
    )

    audience_persona_map = audience_personas or {}
    audience_records = [
        InteractionAudience(
            interaction=interaction,
            timestamp=interaction.timestamp,
            roster_entry=re,
            persona=audience_persona_map.get(re.pk),
        )
        for re in audience_roster_entries
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
    roster_entry: RosterEntry,
    *,
    is_staff: bool = False,
) -> bool:
    """Check if a roster entry can view an interaction.

    Visibility cascade:
    1. very_private -> only original audience roster entries (not staff)
    2. Private scene -> audience + staff
    3. Default -> audience for audience-scoped, public for public scenes
    """
    is_audience = InteractionAudience.objects.filter(
        interaction=interaction,
        roster_entry=roster_entry,
    ).exists()
    is_writer = interaction.roster_entry_id == roster_entry.pk

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

    # Only WHISPER is audience-scoped without a scene — SAY/POSE/EMIT/SHOUT are
    # public room communication even without a formal scene.
    if interaction.mode in (InteractionMode.WHISPER,):
        return is_audience or is_writer

    # Default: public (pose/emit/say/shout/action without a scene)
    return True


def mark_very_private(
    interaction: Interaction,
    roster_entry: RosterEntry,
) -> None:
    """Mark an interaction as very_private. One-way operation.

    Any audience member or the writer can escalate.
    """
    is_audience = InteractionAudience.objects.filter(
        interaction=interaction,
        roster_entry=roster_entry,
    ).exists()
    is_writer = interaction.roster_entry_id == roster_entry.pk

    if not (is_audience or is_writer):
        return

    interaction.visibility = InteractionVisibility.VERY_PRIVATE
    interaction.save(update_fields=["visibility"])


def delete_interaction(
    interaction: Interaction,
    roster_entry: RosterEntry,
) -> bool:
    """Hard-delete an interaction if the requester is the writer and within 30 days.

    Returns True if deleted, False if not allowed.
    """
    if interaction.roster_entry_id != roster_entry.pk:
        return False

    age = timezone.now() - interaction.timestamp
    if age > timedelta(days=DELETION_WINDOW_DAYS):
        return False

    interaction.delete()
    return True

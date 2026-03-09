"""Service functions for the relationships app."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import transaction

from world.achievements.services import increment_stat
from world.relationships.models import (
    CharacterRelationship,
    RelationshipCapstone,
    RelationshipChange,
    RelationshipDevelopment,
    RelationshipTrackProgress,
    RelationshipUpdate,
)

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.relationships.constants import FirstImpressionColoring, UpdateVisibility
    from world.relationships.models import RelationshipTrack
    from world.scenes.models import Scene


def create_first_impression(  # noqa: PLR0913
    *,
    source: CharacterSheet,
    target: CharacterSheet,
    title: str,
    writeup: str,
    track: RelationshipTrack,
    points: int,
    coloring: FirstImpressionColoring,
    visibility: UpdateVisibility,
    linked_scene: Scene | None = None,
) -> CharacterRelationship:
    """
    Create a pending relationship with an initial update and track progress.

    The update adds temporary points and capacity to the track. If the target
    already has a reciprocal relationship, both become active and stats fire.
    """
    with transaction.atomic():
        relationship, _created = CharacterRelationship.objects.get_or_create(
            source=source,
            target=target,
            defaults={"is_pending": True},
        )

        RelationshipUpdate.objects.create(
            relationship=relationship,
            author=source,
            title=title,
            writeup=writeup,
            track=track,
            points_earned=points,
            coloring=coloring,
            visibility=visibility,
            is_first_impression=True,
            linked_scene=linked_scene,
        )

        progress, _created = RelationshipTrackProgress.objects.get_or_create(
            relationship=relationship,
            track=track,
            defaults={"capacity": 0, "developed_points": 0},
        )
        progress.capacity += points
        progress.save(update_fields=["capacity"])

        # Check for reciprocal relationship
        try:
            reciprocal = CharacterRelationship.objects.get(
                source=target,
                target=source,
            )
            if reciprocal.is_pending:
                reciprocal.is_pending = False
                reciprocal.save(update_fields=["is_pending"])
                relationship.is_pending = False
                relationship.save(update_fields=["is_pending"])

                increment_stat(source, "relationships.total_established")
                increment_stat(target, "relationships.total_established")
        except CharacterRelationship.DoesNotExist:
            pass

        return relationship


def redistribute_points(  # noqa: PLR0913
    *,
    relationship: CharacterRelationship,
    author: CharacterSheet,
    title: str,
    writeup: str,
    source_track: RelationshipTrack,
    target_track: RelationshipTrack,
    points: int,
    visibility: UpdateVisibility,
) -> RelationshipChange:
    """
    Move developed points from one track to another. No new value is added.

    Raises ValidationError if the source track does not have enough developed points.
    """
    with transaction.atomic():
        try:
            source_progress = RelationshipTrackProgress.objects.select_for_update().get(
                relationship=relationship,
                track=source_track,
            )
        except RelationshipTrackProgress.DoesNotExist:
            msg = "Source track has no progress to redistribute."
            raise ValidationError(msg) from None

        if source_progress.developed_points < points:
            msg = (
                f"Cannot move {points} points from {source_track.name}: "
                f"only {source_progress.developed_points} available."
            )
            raise ValidationError(msg)

        source_progress.developed_points -= points
        source_progress.save(update_fields=["developed_points"])

        target_progress, _created = RelationshipTrackProgress.objects.get_or_create(
            relationship=relationship,
            track=target_track,
            defaults={"capacity": 0, "developed_points": 0},
        )
        target_progress.developed_points += points
        target_progress.save(update_fields=["developed_points"])

        return RelationshipChange.objects.create(
            relationship=relationship,
            author=author,
            title=title,
            writeup=writeup,
            source_track=source_track,
            target_track=target_track,
            points_moved=points,
            visibility=visibility,
        )


def create_development(  # noqa: PLR0913
    *,
    relationship: CharacterRelationship,
    author: CharacterSheet,
    title: str,
    writeup: str,
    track: RelationshipTrack,
    points: int,
    xp_awarded: int = 0,
    visibility: UpdateVisibility,
    linked_scene: Scene | None = None,
) -> RelationshipDevelopment:
    """
    Add permanent (developed) points to a track, up to capacity.

    Raises ValidationError if the track has no capacity remaining or if the
    character has used all 7 weekly development updates.
    """
    with transaction.atomic():
        progress, _created = RelationshipTrackProgress.objects.get_or_create(
            relationship=relationship,
            track=track,
            defaults={"capacity": 0, "developed_points": 0},
        )

        available = progress.capacity - progress.developed_points
        if available <= 0:
            msg = f"Track {track.name} has no remaining capacity for development."
            raise ValidationError(msg)

        actual_points = min(points, available)

        progress.developed_points += actual_points
        progress.save(update_fields=["developed_points"])

        return RelationshipDevelopment.objects.create(
            relationship=relationship,
            author=author,
            title=title,
            writeup=writeup,
            track=track,
            points_earned=actual_points,
            xp_awarded=xp_awarded,
            visibility=visibility,
            linked_scene=linked_scene,
        )


def create_capstone(  # noqa: PLR0913
    *,
    relationship: CharacterRelationship,
    author: CharacterSheet,
    title: str,
    writeup: str,
    track: RelationshipTrack,
    points: int,
    visibility: UpdateVisibility,
    linked_scene: Scene | None = None,
) -> RelationshipCapstone:
    """
    Record a capstone event — adds points to both capacity and developed_points.

    Capstones are always allowed (unlimited). They represent monumental moments
    and are never gated.
    """
    with transaction.atomic():
        progress, _created = RelationshipTrackProgress.objects.get_or_create(
            relationship=relationship,
            track=track,
            defaults={"capacity": 0, "developed_points": 0},
        )

        progress.capacity += points
        progress.developed_points += points
        progress.save(update_fields=["capacity", "developed_points"])

        return RelationshipCapstone.objects.create(
            relationship=relationship,
            author=author,
            title=title,
            writeup=writeup,
            track=track,
            points=points,
            visibility=visibility,
            linked_scene=linked_scene,
        )

"""Service functions for the relationships app."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import transaction

from world.achievements.services import increment_stat
from world.relationships.models import (
    CharacterRelationship,
    RelationshipChange,
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

    If the target already has a reciprocal relationship (source=target, target=source),
    both relationships become active (is_pending=False) and achievement stats are fired.
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

        progress, created = RelationshipTrackProgress.objects.get_or_create(
            relationship=relationship,
            track=track,
            defaults={"points": 0},
        )
        if not created:
            progress.points += points
            progress.save(update_fields=["points"])
        else:
            progress.points = points
            progress.save(update_fields=["points"])

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
    Move points from one track to another. No new absolute value is added.

    Raises ValidationError if the source track does not have enough points.
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

        if source_progress.points < points:
            msg = (
                f"Cannot move {points} points from {source_track.name}: "
                f"only {source_progress.points} available."
            )
            raise ValidationError(msg)

        source_progress.points -= points
        source_progress.save(update_fields=["points"])

        target_progress, _created = RelationshipTrackProgress.objects.get_or_create(
            relationship=relationship,
            track=target_track,
            defaults={"points": 0},
        )
        target_progress.points += points
        target_progress.save(update_fields=["points"])

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

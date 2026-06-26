"""Service functions for the relationships app."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import transaction

from world.achievements.models import StatDefinition
from world.achievements.services import increment_stat
from world.progression.constants import FIRST_IMPRESSION_AUTHOR_XP, FIRST_IMPRESSION_TARGET_XP
from world.progression.models import KudosSourceCategory
from world.progression.services.awards import award_xp
from world.progression.services.kudos import award_kudos
from world.progression.types import ProgressionReason
from world.relationships.constants import (
    MAX_DEVELOPMENTS_PER_WEEK,
    RELATIONSHIP_WRITEUP_KUDOS_CATEGORY,
    WRITEUP_KUDOS_AMOUNT,
    TrackSign,
    UpdateVisibility,
)
from world.relationships.exceptions import (
    AlreadyCommendedError,
    CannotCommendOwnWriteupError,
    NotWriteupSubjectError,
    WriteupNotSharedError,
    WriteupNotVisibleError,
)
from world.relationships.models import (
    CharacterRelationship,
    RelationshipCapstone,
    RelationshipChange,
    RelationshipDevelopment,
    RelationshipTrackProgress,
    RelationshipUpdate,
    WriteupComplaint,
    WriteupKudos,
)
from world.roster.selectors import get_account_for_character

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from world.character_sheets.models import CharacterSheet
    from world.relationships.constants import FirstImpressionColoring
    from world.relationships.models import GrievanceOption, RelationshipTrack
    from world.scenes.models import Scene

logger = logging.getLogger(__name__)


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
        relationship, created = CharacterRelationship.objects.get_or_create(
            source=source,
            target=target,
            defaults={"is_pending": True},
        )

        if not created and relationship.updates.filter(is_first_impression=True).exists():
            msg = "A first impression already exists for this relationship."
            raise ValidationError(msg)

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

        # Award First Impression XP
        author_account = get_account_for_character(source.character)
        target_account = get_account_for_character(target.character)
        if author_account:
            award_xp(
                author_account,
                FIRST_IMPRESSION_AUTHOR_XP,
                reason=ProgressionReason.FIRST_IMPRESSION,
                description=f"First impression of {target.character.db_key}",
            )
        if target_account:
            award_xp(
                target_account,
                FIRST_IMPRESSION_TARGET_XP,
                reason=ProgressionReason.FIRST_IMPRESSION,
                description=f"First impression from {source.character.db_key}",
            )

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

                stat_def = StatDefinition.objects.get(key="relationships.total_established")
                increment_stat(source, stat_def)
                increment_stat(target, stat_def)
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

        target_progress, _created = (
            RelationshipTrackProgress.objects.select_for_update().get_or_create(
                relationship=relationship,
                track=target_track,
                defaults={"capacity": 0, "developed_points": 0},
            )
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
        # Enforce weekly limit — reset counters if game week has changed
        from world.game_clock.week_services import get_current_game_week

        current_week = get_current_game_week()
        if relationship.game_week_id != current_week.pk:
            relationship.developments_this_week = 0
            relationship.game_week = current_week
            relationship.save(update_fields=["developments_this_week", "game_week"])

        if relationship.developments_this_week >= MAX_DEVELOPMENTS_PER_WEEK:
            msg = f"Weekly development limit reached ({MAX_DEVELOPMENTS_PER_WEEK} per week)."
            raise ValidationError(msg)

        progress, _created = RelationshipTrackProgress.objects.select_for_update().get_or_create(
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

        relationship.developments_this_week += 1
        relationship.save(update_fields=["developments_this_week"])

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
        progress, _created = RelationshipTrackProgress.objects.select_for_update().get_or_create(
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


def _writeup_field_name(writeup) -> str:
    """Return the FK field name on WriteupFeedbackBase for this writeup type.

    Returns "update", "development", or "capstone" depending on which concrete
    writeup model the object is an instance of.
    """
    if isinstance(writeup, RelationshipUpdate):
        return "update"  # noqa: STRING_LITERAL
    if isinstance(writeup, RelationshipDevelopment):
        return "development"  # noqa: STRING_LITERAL
    if isinstance(writeup, RelationshipCapstone):
        return "capstone"  # noqa: STRING_LITERAL
    msg = f"Unknown writeup type: {type(writeup)!r}"
    raise TypeError(msg)


def _can_view_writeup(account: AccountDB, writeup) -> bool:
    """Return True if account may view this writeup.

    SHARED, GOSSIP, and PUBLIC writeups are visible to any account.
    PRIVATE writeups are visible only to the author's account or the subject's account.

    No existing visibility predicate was found in views.py, selectors.py, or
    serializers.py (grep confirmed only the ``visibility`` *field* appears there),
    so this minimal helper is authoritative.
    """
    if writeup.visibility != UpdateVisibility.PRIVATE:
        return True
    author_account = get_account_for_character(writeup.author.character)
    subject_account = get_account_for_character(writeup.relationship.target.character)
    viewable_pks = {a.pk for a in [author_account, subject_account] if a is not None}
    return account.pk in viewable_pks


def give_writeup_kudos(*, giver_account: AccountDB, writeup) -> WriteupKudos:
    """Award a non-revocable commendation to the writeup author on behalf of the subject.

    Only the subject of the writeup (relationship.target's controlling account) may
    commend. The author cannot self-commend. The writeup must not be PRIVATE.
    Each (account, writeup) pair is unique; a second attempt raises AlreadyCommendedError.

    When the ``KudosSourceCategory`` for ``RELATIONSHIP_WRITEUP_KUDOS_CATEGORY`` is
    absent (pre-seeded state), logs a warning and still records the WriteupKudos row
    without awarding kudos — mirroring the pattern in
    ``world.progression.services.engagement.grant_social_engagement_kudos``.

    Returns:
        The newly created WriteupKudos instance.

    Raises:
        WriteupNotSharedError: writeup.visibility is PRIVATE.
        CannotCommendOwnWriteupError: giver is the author of the writeup.
        NotWriteupSubjectError: giver is not the subject (relationship.target) of the writeup.
        AlreadyCommendedError: this account has already commended this writeup.
    """
    if writeup.visibility == UpdateVisibility.PRIVATE:
        raise WriteupNotSharedError

    # Author check before subject check so "I wrote this" surfaces before "you're not the subject".
    author_account = get_account_for_character(writeup.author.character)
    if author_account and author_account.pk == giver_account.pk:
        raise CannotCommendOwnWriteupError

    subject_account = get_account_for_character(writeup.relationship.target.character)
    if subject_account is None or giver_account.pk != subject_account.pk:
        raise NotWriteupSubjectError

    field = _writeup_field_name(writeup)
    if WriteupKudos.objects.filter(account=giver_account, **{field: writeup}).exists():
        raise AlreadyCommendedError

    with transaction.atomic():
        kudos = WriteupKudos.objects.create(account=giver_account, **{field: writeup})
        if author_account:
            try:
                category = KudosSourceCategory.objects.get(name=RELATIONSHIP_WRITEUP_KUDOS_CATEGORY)
            except KudosSourceCategory.DoesNotExist:
                logger.warning(
                    "give_writeup_kudos: KudosSourceCategory %r not seeded; skipping award.",
                    RELATIONSHIP_WRITEUP_KUDOS_CATEGORY,
                )
            else:
                award_kudos(
                    author_account,
                    WRITEUP_KUDOS_AMOUNT,
                    category,
                    "Relationship writeup commended",
                    awarded_by=giver_account,
                )
    return kudos


def file_writeup_complaint(
    *, complainant_account: AccountDB, writeup, reason: str
) -> WriteupComplaint:
    """File a bad-faith-RP complaint against a writeup for staff triage.

    Any account that can view the writeup may file a complaint. No player-facing
    signal is generated; complaints are staff-internal (admin-only surface).

    Returns:
        The newly created WriteupComplaint instance (resolved=False).

    Raises:
        WriteupNotVisibleError: the complainant's account cannot view the writeup.
    """
    if not _can_view_writeup(complainant_account, writeup):
        raise WriteupNotVisibleError

    field = _writeup_field_name(writeup)
    return WriteupComplaint.objects.create(
        complainant=complainant_account,
        **{field: writeup},
        reason=reason,
    )


def register_grievance(  # noqa: PLR0913 — keyword-only; each arg is a distinct grievance field
    *,
    source: CharacterSheet,
    target: CharacterSheet,
    option: GrievanceOption | None = None,
    custom_points: int | None = None,
    custom_track: RelationshipTrack | None = None,
    writeup: str = "",
    visibility: UpdateVisibility = UpdateVisibility.PRIVATE,
) -> RelationshipCapstone:
    """Register a wronged character's one-sided grievance against whoever harmed them (#1429).

    Resolves the swing from a ``GrievanceOption`` preset, or a ``custom_points`` + ``custom_track``
    pair, then applies it as a relationship **capstone** on the (source→target) relationship.
    Unilateral: it never needs the target's consent — the relationship simply stays ``is_pending``
    until/unless the target reciprocates, while the victim's feelings are recorded immediately.
    The track must be NEGATIVE-sign (a grievance is, by definition, negative).
    """
    if option is not None:
        track, points, title = option.track, option.points, option.label
    elif custom_points is not None and custom_track is not None:
        track, points, title = custom_track, custom_points, "A personal grievance"
    else:
        msg = "Provide either a GrievanceOption or both custom_points and custom_track."
        raise ValidationError(msg)
    if points <= 0:
        msg = "A grievance swing must be a positive magnitude."
        raise ValidationError(msg)
    if track.sign != TrackSign.NEGATIVE:
        msg = "A grievance must land on a negative-sign track."
        raise ValidationError(msg)

    relationship, _ = CharacterRelationship.objects.get_or_create(
        source=source, target=target, defaults={"is_pending": True}
    )
    return create_capstone(
        relationship=relationship,
        author=source,
        title=title,
        writeup=writeup,
        track=track,
        points=points,
        visibility=visibility,
    )

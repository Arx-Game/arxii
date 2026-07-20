"""Service functions for the relationships app."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from world.achievements.models import StatDefinition
from world.achievements.services import increment_stat
from world.progression.constants import FIRST_IMPRESSION_AUTHOR_XP, FIRST_IMPRESSION_TARGET_XP
from world.progression.models import KudosSourceCategory
from world.progression.services.awards import award_xp
from world.progression.services.kudos import award_kudos
from world.progression.types import ProgressionReason
from world.relationships.constants import (
    BUMP_POINTS,
    MAX_DEVELOPMENTS_PER_WEEK,
    RELATIONSHIP_WRITEUP_KUDOS_CATEGORY,
    WRITEUP_KUDOS_AMOUNT,
    TrackSign,
    TrackSystemKey,
    UpdateVisibility,
)
from world.relationships.exceptions import (
    AlreadyAcknowledgedError,
    AlreadyCommendedError,
    CannotCommendOwnWriteupError,
    NotWriteupSubjectError,
    SystemTracksNotSeededError,
    WriteupNotSharedError,
    WriteupNotVisibleError,
)
from world.relationships.models import (
    AffectionShift,
    CharacterRelationship,
    RelationshipBump,
    RelationshipCapstone,
    RelationshipChange,
    RelationshipCondition,
    RelationshipDevelopment,
    RelationshipTrack,
    RelationshipTrackProgress,
    RelationshipUpdate,
    TemporaryRelationshipCondition,
    WriteupComplaint,
    WriteupKudos,
)
from world.roster.selectors import get_account_for_character

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from evennia_extensions.models import ObjectDB
    from world.character_sheets.models import CharacterSheet
    from world.checks.models import ConsequenceEffect
    from world.checks.types import ModifierContribution
    from world.combat.models import CombatEncounter
    from world.npc_services.models import NpcRegardEvent
    from world.relationships.constants import FirstImpressionColoring
    from world.relationships.models import BondCombatConfig, GrievanceOption, RelationshipTrack
    from world.scenes.boon_models import Boon
    from world.scenes.models import Interaction, ReactionEmoji, Scene

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


def apply_relationship_bump(
    *,
    source: CharacterSheet,
    target: CharacterSheet,
    interaction: Interaction,
    valence: int,
    source_emoji: ReactionEmoji | None = None,
) -> RelationshipBump:
    """Apply an ambient ±1 bump to source's regard toward target (#1699).

    Permanent, ungated, tiny: adds BUMP_POINTS to both capacity and
    developed_points (the capstone write-shape at bump scale) on the generic
    Regard (positive) or Friction (negative) system track. The bump row's
    unique constraint per (relationship, interaction) is the only cap — the
    bump-row create runs first inside the transaction so a duplicate rolls
    back cleanly with no points applied.

    Raises ValidationError (self-target), SystemTracksNotSeededError, or
    AlreadyAcknowledgedError.
    """
    if source.pk == target.pk:
        msg = "You cannot record a relationship with yourself."
        raise ValidationError(msg)
    key = TrackSystemKey.REGARD if valence > 0 else TrackSystemKey.FRICTION
    try:
        track = RelationshipTrack.objects.get(system_key=key)
    except RelationshipTrack.DoesNotExist:
        raise SystemTracksNotSeededError from None
    try:
        with transaction.atomic():
            relationship, _ = CharacterRelationship.objects.get_or_create(
                source=source,
                target=target,
                defaults={"is_pending": True},
            )
            bump = RelationshipBump.objects.create(
                relationship=relationship,
                interaction=interaction,
                timestamp=interaction.timestamp,
                valence=1 if valence > 0 else -1,
                source_emoji=source_emoji,
            )
            progress, _ = RelationshipTrackProgress.objects.select_for_update().get_or_create(
                relationship=relationship,
                track=track,
                defaults={"capacity": 0, "developed_points": 0},
            )
            progress.capacity += BUMP_POINTS
            progress.developed_points += BUMP_POINTS
            progress.save(update_fields=["capacity", "developed_points"])
    except IntegrityError:
        raise AlreadyAcknowledgedError from None
    return bump


def apply_affection_shift(  # noqa: PLR0913 - two provenance modes share one write-shape
    *,
    source: CharacterSheet,
    target: CharacterSheet,
    scene: Scene,
    effect: ConsequenceEffect | None,
    amount: int,
    boon: Boon | None = None,
) -> AffectionShift | None:
    """Apply a social action's automatic affection shift (#1697, boon mode #2540).

    Moves ``source``'s relationship toward ``target`` by ``amount`` on the
    Regard (positive) or Friction (negative) system track, using the capstone
    write-shape (capacity + developed together — the same as ambient bumps).
    Provenance is ``effect`` (a SHIFT_AFFECTION ConsequenceEffect — deduped
    first-per-scene-per-pair, the diminishing-returns rule) or ``boon`` (a
    granted Boon — deduped on the Boon itself, so serial boons stack within a
    scene); exactly one must be passed. Returns ``None`` on the dedup no-op.
    Direction note: callers pass the social action's TARGET as ``source`` —
    it is *their* regard for the actor that moves.
    """
    if (effect is None) == (boon is None):
        msg = "An affection shift carries exactly one provenance: effect or boon."
        raise ValueError(msg)
    if amount == 0 or source.pk == target.pk:
        return None
    key = TrackSystemKey.REGARD if amount > 0 else TrackSystemKey.FRICTION
    try:
        track = RelationshipTrack.objects.get(system_key=key)
    except RelationshipTrack.DoesNotExist:
        raise SystemTracksNotSeededError from None
    try:
        with transaction.atomic():
            relationship, _ = CharacterRelationship.objects.get_or_create(
                source=source,
                target=target,
                defaults={"is_pending": True},
            )
            shift = AffectionShift.objects.create(
                relationship=relationship,
                scene=scene,
                effect=effect,
                boon=boon,
                amount=amount,
            )
            progress, _ = RelationshipTrackProgress.objects.select_for_update().get_or_create(
                relationship=relationship,
                track=track,
                defaults={"capacity": 0, "developed_points": 0},
            )
            points = abs(amount)
            progress.capacity += points
            progress.developed_points += points
            progress.save(update_fields=["capacity", "developed_points"])
    except IntegrityError:
        return None
    return shift


def mirror_npc_regard_event_to_track(event: NpcRegardEvent) -> RelationshipTrackProgress | None:
    """Mirror one NpcRegardEvent onto the PC's Regard/Friction system track (#2039).

    Reuses ``apply_affection_shift``'s track-selection + capstone write-shape, but
    dedups on the ``NpcRegardEvent`` row itself (one mirror write per event, folded
    into the same call) rather than requiring a Scene+ConsequenceEffect —
    ``apply_affection_shift`` can't be called directly here since combat/GM/chargen-
    authored events don't carry those. #2013's hated-foe surge
    (``world/combat/escalation.py``'s ``_maybe_surge_hated_foe``) reads
    ``source=<PC's own CharacterSheet>, target=<NPC's CharacterSheet>`` — so this
    helper always writes in that fixed direction regardless of which side of the
    NpcRegardEvent caused it. Returns ``None`` if the event's regard row isn't
    persona-targeted, or the amount is zero.
    """
    regard = event.regard
    target_persona = regard.target_persona
    if target_persona is None:
        # Only PERSONA-targeted regard rows have a PC to mirror onto; org/society
        # targets have no CharacterSheet and can't feed the #2013 bridge.
        return None
    npc_persona = regard.holder_persona

    pc_sheet = target_persona.character_sheet
    npc_sheet = npc_persona.character_sheet
    if pc_sheet.pk == npc_sheet.pk:
        return None

    points = abs(event.amount)
    if points == 0:
        return None

    key = TrackSystemKey.REGARD if event.amount > 0 else TrackSystemKey.FRICTION
    try:
        track = RelationshipTrack.objects.get(system_key=key)
    except RelationshipTrack.DoesNotExist:
        # Unlike apply_affection_shift/apply_relationship_bump, this bridge is
        # wired unconditionally into record_npc_regard_event's write seam — the
        # core NPC regard buildup path must not blow up just because the
        # relationships system tracks haven't been seeded yet.
        return None

    try:
        with transaction.atomic():
            relationship, _ = CharacterRelationship.objects.get_or_create(
                source=pc_sheet,
                target=npc_sheet,
                defaults={"is_pending": True},
            )
            progress, _ = RelationshipTrackProgress.objects.select_for_update().get_or_create(
                relationship=relationship,
                track=track,
                defaults={"capacity": 0, "developed_points": 0},
            )
            progress.capacity += points
            progress.developed_points += points
            progress.save(update_fields=["capacity", "developed_points"])
    except IntegrityError:
        return None
    return progress


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
        try:
            kudos = WriteupKudos.objects.create(account=giver_account, **{field: writeup})
        except IntegrityError:
            # Race: two concurrent commends from the same account both passed the
            # exists() pre-check; the second hits the DB unique constraint.
            raise AlreadyCommendedError from None
        if author_account:
            try:
                category = KudosSourceCategory.objects.get(name=RELATIONSHIP_WRITEUP_KUDOS_CATEGORY)
            except KudosSourceCategory.DoesNotExist:
                logger.warning(
                    "give_writeup_kudos: KudosSourceCategory %r not seeded; skipping award.",
                    RELATIONSHIP_WRITEUP_KUDOS_CATEGORY,
                )
            else:
                # Award anonymously — do NOT pass awarded_by=giver_account.
                # The commender is the writeup's subject; surfacing their account username
                # to the author would link an IC character to its OOC player account,
                # violating player-behind-character privacy (ADR-0033).
                award_kudos(
                    author_account,
                    WRITEUP_KUDOS_AMOUNT,
                    category,
                    "Relationship writeup commended",
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


def relationship_gated_contributions(
    *, perceiver: CharacterSheet, perceived: CharacterSheet
) -> list[ModifierContribution]:
    """Modifier contributions the perceiver's regard for the perceived injects into a check (#1696).

    Allure (and any future relationship-gated modifier) is a **directed, conditional** modifier: it
    boosts the *perceived's* social checks against the *perceiver* only when the perceiver holds a
    gating relationship-condition toward them. For the directed
    ``CharacterRelationship(source=perceiver, target=perceived)``, each active
    ``RelationshipCondition.gates_modifiers`` target folds in the **perceived's**
    ``get_modifier_total`` of that target — **once per gating condition**. So two allure-gating
    conditions (``Attracted To`` + ``Very Attracted``) count the perceived's allure twice — the
    "double" effect falls out of the count, with no allure-specific code.

    Returns ``[]`` with no active relationship or no gating condition (the common case until
    Flirt/Seduction set the conditions). **Permanent** conditions ("Attracted To") live on the
    ``conditions`` M2M; **temporary** ones ("Very Attracted") live in ``temporary_conditions`` with
    an ``expires_at`` and are unioned here only while unexpired (#1697) — so a live Very Attracted
    is the second, doubling allure application that lapses on its own.
    """
    from world.checks.constants import ModifierSourceKind
    from world.checks.types import ModifierContribution
    from world.mechanics.services import get_modifier_total

    relationship = (
        CharacterRelationship.objects.filter(source=perceiver, target=perceived, is_active=True)
        .prefetch_related(
            "conditions__gates_modifiers",  # noqa: PREFETCH_STRING
            "temporary_conditions__condition__gates_modifiers",  # noqa: PREFETCH_STRING
        )
        .first()
    )
    if relationship is None:
        return []
    now = timezone.now()
    active_conditions = list(relationship.conditions.all())
    active_conditions += [
        temp.condition for temp in relationship.temporary_conditions.all() if temp.expires_at > now
    ]
    contributions: list[ModifierContribution] = []
    for condition in active_conditions:
        for target in condition.gates_modifiers.all():
            value = get_modifier_total(perceived, target)
            if value:
                contributions.append(
                    ModifierContribution(
                        source_kind=ModifierSourceKind.RELATIONSHIP,
                        source_label=f"{condition.name}: {target.name}",
                        value=value,
                    )
                )
    return contributions


def add_relationship_condition(
    *,
    source: CharacterSheet,
    target: CharacterSheet,
    condition: RelationshipCondition,
    duration: timedelta | None = None,
) -> None:
    """Add a ``RelationshipCondition`` to the directed ``source → target`` relationship (#1697).

    ``duration is None`` → a **permanent** condition on the ``conditions`` M2M ("Attracted To").
    A ``timedelta`` → a **temporary** condition (``TemporaryRelationshipCondition`` with
    ``expires_at = now + duration``), refreshed in place if it already exists ("Very Attracted",
    re-upped each flirt). Get-or-creates the relationship (left ``is_pending`` — the gating reader
    only checks ``is_active``). The flirt/seduce TARGET becomes attracted to the actor, so callers
    pass ``source=<the flirt's target>, target=<the actor>``.
    """
    relationship, _ = CharacterRelationship.objects.get_or_create(
        source=source, target=target, defaults={"is_pending": True}
    )
    if duration is None:
        relationship.conditions.add(condition)
        return
    TemporaryRelationshipCondition.objects.update_or_create(
        relationship=relationship,
        condition=condition,
        defaults={"expires_at": timezone.now() + duration},
    )


def clear_very_attracted(sheets) -> None:
    """Drop Very Attracted for the given characters — the scene-end early clear (#1697).

    Very Attracted (the temporary allure double) lasts to **end of scene OR ~2 IC days, whichever
    first**; the duration cap is the backstop and this is the primary path. Deletes
    ``TemporaryRelationshipCondition`` rows for "Very Attracted" whose directed relationship touches
    any of ``sheets`` (source or target). Called from ``Scene.finish_scene``.
    """
    from world.seeds.social_relationships import VERY_ATTRACTED_CONDITION_NAME

    sheet_ids = [sheet.pk for sheet in sheets]
    if not sheet_ids:
        return
    TemporaryRelationshipCondition.objects.filter(
        condition__name=VERY_ATTRACTED_CONDITION_NAME
    ).filter(
        Q(relationship__source_id__in=sheet_ids) | Q(relationship__target_id__in=sheet_ids)
    ).delete()


def get_bond_combat_config() -> BondCombatConfig:
    """Get-or-create the BondCombatConfig singleton (pk=1).

    Lazy-creates the singleton on first access. Mirrors ``get_soul_tether_config()``.
    """
    from world.relationships.models import BondCombatConfig

    cfg = BondCombatConfig.objects.cached_singleton()
    if cfg is None:
        cfg, _ = BondCombatConfig.objects.get_or_create(pk=1)
    return cfg


def soul_tether_active(a_sheet: CharacterSheet, b_sheet: CharacterSheet) -> bool:
    """Check whether two characters have an active Soul Tether bond.

    Looks for a non-retired RELATIONSHIP_CAPSTONE Thread owned by either character
    whose target_capstone.relationship points at the other character. The Sinner
    owns the capstone thread; the Sineater may optionally have one too, so both
    directions are checked.
    """
    from world.magic.constants import TargetKind
    from world.magic.models import Thread

    # Check a→b direction (Sinner owns the capstone thread)
    if Thread.objects.filter(
        owner=a_sheet,
        target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
        target_capstone__relationship__source=a_sheet,
        target_capstone__relationship__target=b_sheet,
        retired_at__isnull=True,
    ).exists():
        return True

    # Check b→a direction
    return Thread.objects.filter(
        owner=b_sheet,
        target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
        target_capstone__relationship__source=b_sheet,
        target_capstone__relationship__target=a_sheet,
        retired_at__isnull=True,
    ).exists()


def bond_combat_bonus(
    sheet: CharacterSheet, encounter: CombatEncounter
) -> list[ModifierContribution]:
    """Return ModifierContribution(RELATIONSHIP) entries for each bonded co-combatant.

    For each ACTIVE co-combatant (other than ``sheet``), checks for a directed
    CharacterRelationship(source=sheet, target=ally) that is active, non-pending,
    and above the config's ``min_developed_absolute_value`` floor. If found,
    appends a contribution with ``int(mechanical_bonus)`` as the value. When the
    pair is soul-tethered, the bonus is multiplied by ``soul_tether_multiplier``.

    Directed (one-sided) by design: only the character who invested in the
    relationship gets the bonus. Mirrors the directed-allure pattern (#1696).

    Returns an empty list when there are no qualifying bonds.
    """
    from world.checks.constants import ModifierSourceKind
    from world.checks.types import ModifierContribution
    from world.combat.constants import ParticipantStatus

    config = get_bond_combat_config()
    contributions: list[ModifierContribution] = []

    participants = (
        encounter.participants.filter(status=ParticipantStatus.ACTIVE)
        .exclude(character_sheet=sheet)
        .select_related("character_sheet")
    )

    for participant in participants:
        ally_sheet = participant.character_sheet
        bond = (
            CharacterRelationship.objects.filter(
                source=sheet,
                target=ally_sheet,
                is_active=True,
                is_pending=False,
            )
            .prefetch_related("track_progress__track")  # noqa: PREFETCH_STRING
            .first()
        )
        if bond is None:
            continue
        if bond.developed_absolute_value < config.min_developed_absolute_value:
            continue

        bonus = int(bond.mechanical_bonus)
        if soul_tether_active(sheet, ally_sheet):
            bonus *= config.soul_tether_multiplier

        ally_name = str(ally_sheet)
        contributions.append(
            ModifierContribution(
                source_kind=ModifierSourceKind.RELATIONSHIP,
                source_label=f"Bond: {ally_name}",
                value=bonus,
            )
        )
    return contributions


def bond_bonus(actor: ObjectDB, protected: ObjectDB) -> int:
    """Return the bond bonus for protection checks (INTERPOSE/SUCCOR).

    Looks up the directed relationship actor→protected and returns
    ``int(mechanical_bonus)`` if above the config floor, else 0.
    """
    actor_sheet = actor.character_sheet
    protected_sheet = protected.character_sheet
    if actor_sheet is None or protected_sheet is None:
        return 0

    config = get_bond_combat_config()
    bond = CharacterRelationship.objects.filter(
        source=actor_sheet,
        target=protected_sheet,
        is_active=True,
        is_pending=False,
    ).first()
    if bond is None:
        return 0
    if bond.developed_absolute_value < config.min_developed_absolute_value:
        return 0
    return int(bond.mechanical_bonus)

"""Service functions for ties (#3957): labels, depth, tiers, gauges, predicates."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import BooleanField, Exists, ExpressionWrapper, F, OuterRef, Q
from django.utils import timezone

from world.progression.services.xp_ledger import spend_xp_for_character
from world.relationships.constants import (
    AWARENESS_RANK,
    BUMP_POINTS,
    KNOWN_AWARENESS,
    DepthSource,
    LabelAwareness,
    TypeValence,
)
from world.relationships.exceptions import (
    AllocationTooLargeError,
    AlreadyAcknowledgedError,
    AwarenessBackwardError,
    CapstoneEntryInvalidError,
    LabelAlreadyDeclaredError,
    LabelEndedError,
    SameTypeShiftError,
    TieError,
    TierNotReachedError,
)
from world.relationships.models import (
    AffectionShift,
    CharacterRelationship,
    RelationshipAllocation,
    RelationshipBump,
    RelationshipCapstone,
    RelationshipCondition,
    RelationshipDepthTransaction,
    RelationshipGrowthConfig,
    RelationshipLabel,
    RelationshipTier,
    RelationshipType,
    TemporaryRelationshipCondition,
)

if TYPE_CHECKING:
    from evennia_extensions.models import ObjectDB
    from world.character_sheets.models import CharacterSheet
    from world.checks.models import ConsequenceEffect
    from world.checks.types import ModifierContribution
    from world.combat.models import CombatEncounter
    from world.companions.models import Companion
    from world.game_clock.models import GameWeek
    from world.journals.models import JournalEntry
    from world.npc_services.models import NpcRegardEvent
    from world.relationships.models import BondCombatConfig, GrievanceOption
    from world.roster.models import RosterTenure
    from world.scenes.boon_models import Boon
    from world.scenes.models import Interaction, ReactionEmoji, Scene

logger = logging.getLogger(__name__)


# -- config --------------------------------------------------------------------


def get_growth_config() -> RelationshipGrowthConfig:
    cfg = RelationshipGrowthConfig.objects.cached_singleton()
    if cfg is None:
        cfg, _ = RelationshipGrowthConfig.objects.get_or_create(pk=1)
    return cfg


# -- sides ---------------------------------------------------------------------


def get_or_create_side(
    *,
    source: CharacterSheet,
    target: CharacterSheet | None = None,
    target_companion: Companion | None = None,
) -> CharacterRelationship:
    """One character's side of a tie, created on first touch (#3957)."""
    if (target is None) == (target_companion is None):
        msg = "Provide exactly one of target or target_companion."
        raise ValueError(msg)
    if target is not None and source.pk == target.pk:
        msg = "You cannot record a relationship with yourself."
        raise ValidationError(msg)
    if target_companion is not None:
        side, _ = CharacterRelationship.objects.get_or_create(
            source=source, target_companion=target_companion
        )
        return side
    side, _ = CharacterRelationship.objects.get_or_create(source=source, target=target)
    return side


def set_summary(*, side: CharacterRelationship, summary: str) -> CharacterRelationship:
    side.summary = summary.strip()
    side.save(update_fields=["summary", "updated_at"])
    return side


# -- labels --------------------------------------------------------------------


def declare_label(
    *,
    side: CharacterRelationship,
    type: RelationshipType,  # noqa: A002 - the model field is named type
    awareness: str = LabelAwareness.PRIVATE,
    tenure: RosterTenure | None = None,
) -> RelationshipLabel:
    """Name one type on this side, Private unless told otherwise (#3957)."""
    if awareness not in AWARENESS_RANK:
        msg = "Unknown awareness."
        raise TieError(msg)
    now = timezone.now()
    try:
        with transaction.atomic():
            return RelationshipLabel.objects.create(
                relationship=side,
                type=type,
                awareness=awareness,
                declared_by_tenure=tenure,
                since=now,
                clandestine_at=now if awareness == LabelAwareness.CLANDESTINE else None,
                public_at=now if awareness == LabelAwareness.PUBLIC else None,
            )
    except IntegrityError:
        raise LabelAlreadyDeclaredError from None


def shift_label(
    *, label: RelationshipLabel, new_type: RelationshipType, note: str = ""
) -> RelationshipLabel:
    """Change one label into another: the old row ends, the new one remembers it."""
    if label.ended_at is not None:
        raise LabelEndedError
    if new_type.pk == label.type_id:
        raise SameTypeShiftError
    now = timezone.now()
    with transaction.atomic():
        # Create the new row FIRST: if it collides with the partial unique constraint,
        # nothing has mutated yet, so there is no stale identity-map instance to leave
        # behind on rollback (ADR-0008's addendum; lint-idmapper-mutation-order).
        try:
            new_label = RelationshipLabel.objects.create(
                relationship=label.relationship,
                type=new_type,
                awareness=label.awareness,
                declared_by_tenure=label.declared_by_tenure,
                since=now,
                clandestine_at=label.clandestine_at,
                public_at=label.public_at,
                replaced=label,
                note=note.strip()[:200],
            )
        except IntegrityError:
            raise LabelAlreadyDeclaredError from None
        label.ended_at = now
        label.save(update_fields=["ended_at"])
    return new_label


def end_label(*, label: RelationshipLabel) -> RelationshipLabel:
    if label.ended_at is not None:
        raise LabelEndedError
    label.ended_at = timezone.now()
    label.save(update_fields=["ended_at"])
    return label


def advance_awareness(*, label: RelationshipLabel, to: str) -> RelationshipLabel:
    """Private -> Clandestine -> Public, or Private -> Public. Never backward."""
    if label.ended_at is not None:
        raise LabelEndedError
    if to not in AWARENESS_RANK or AWARENESS_RANK[to] <= AWARENESS_RANK[label.awareness]:
        raise AwarenessBackwardError
    now = timezone.now()
    label.awareness = to
    fields = ["awareness"]
    if to == LabelAwareness.CLANDESTINE:
        label.clandestine_at = now
        fields.append("clandestine_at")
    else:
        label.public_at = now
        fields.append("public_at")
        if label.clandestine_at is None:
            label.clandestine_at = now
            fields.append("clandestine_at")
    label.save(update_fields=fields)
    return label


def _known_label_q(
    source_id: int | OuterRef, target_ref, type_ref=None, *, awareness=KNOWN_AWARENESS
) -> Q:
    """Labels the OTHER side may see, declared under a still-open tenure.

    ``awareness`` narrows which awareness stages count as "known" — the default is
    Clandestine-or-Public (what the OTHER side of a tie may see); a caller reading what a
    THIRD PARTY may see passes ``awareness=(LabelAwareness.PUBLIC,)`` instead (#3957 review).
    """
    q = Q(
        relationship__source_id=source_id,
        relationship__target_id=target_ref,
        relationship__is_active=True,
        ended_at__isnull=True,
        awareness__in=awareness,
        declared_by_tenure__isnull=False,
        declared_by_tenure__end_date__isnull=True,
    )
    if type_ref is not None:
        q &= Q(type_id=type_ref)
    return q


def is_mutual(
    side: CharacterRelationship,
    type: RelationshipType,  # noqa: A002 - the model field is named type
    *,
    public_only: bool = False,
) -> bool:
    """Both sides hold counterpart labels at Clandestine or Public (#3957).

    ``public_only=True`` narrows both sides' required awareness to Public alone — the
    predicate a THIRD_PARTY audience reads: a stranger may only learn what both sides chose
    to make public, not what one side merely let the other side know (#3957 review).
    """
    if side.target_id is None:
        return False
    awareness = (LabelAwareness.PUBLIC,) if public_only else KNOWN_AWARENESS
    mine = RelationshipLabel.objects.filter(
        _known_label_q(side.source_id, side.target_id, type.pk, awareness=awareness)
    ).exists()
    theirs = RelationshipLabel.objects.filter(
        _known_label_q(
            side.target_id, side.source_id, type.counterpart_or_self.pk, awareness=awareness
        )
    ).exists()
    return mine and theirs


def mutual_hostile(a_sheet: CharacterSheet, b_sheet: CharacterSheet) -> bool:
    """The one predicate consent's RIVALS mode and the journals' Retort gate read."""
    hostile = Q(type__valence=TypeValence.HOSTILE)
    return (
        RelationshipLabel.objects.filter(_known_label_q(a_sheet.pk, b_sheet.pk) & hostile).exists()
        and RelationshipLabel.objects.filter(
            _known_label_q(b_sheet.pk, a_sheet.pk) & hostile
        ).exists()
    )


def mutual_hostile_expression(viewer_sheet_id: int, other_ref: str = "author_id"):
    """``mutual_hostile`` as an annotatable expression against ``OuterRef(other_ref)``."""
    hostile = Q(type__valence=TypeValence.HOSTILE)
    mine = RelationshipLabel.objects.filter(
        _known_label_q(viewer_sheet_id, OuterRef(other_ref)) & hostile
    )
    theirs = RelationshipLabel.objects.filter(
        _known_label_q(OuterRef(other_ref), viewer_sheet_id) & hostile
    )
    return ExpressionWrapper(Q(Exists(mine)) & Q(Exists(theirs)), output_field=BooleanField())


# -- depth ---------------------------------------------------------------------


def set_allocation(*, side: CharacterRelationship, ap_amount: int) -> RelationshipAllocation:
    from world.action_points.models import ActionPointPool
    from world.game_clock.week_services import get_current_game_week

    if ap_amount < 0:
        msg = "AP cannot be negative."
        raise TieError(msg)
    pool = ActionPointPool.get_or_create_for_character(side.source.character)
    if pool is None or (ap_amount and not pool.can_afford(ap_amount)):
        raise AllocationTooLargeError
    allocation, _ = RelationshipAllocation.objects.update_or_create(
        relationship=side,
        defaults={"ap_amount": ap_amount, "game_week": get_current_game_week()},
    )
    return allocation


def _award_depth(  # noqa: PLR0913 - the batch-vs-single-award split needs all six
    side: CharacterRelationship,
    amount: int,
    source: str,
    *,
    week: GameWeek,
    scene: Scene | None = None,
    refresh: bool = True,
) -> None:
    """Add depth to one side and record the audit row (#3957).

    ``refresh=False`` skips the post-write ``refresh_from_db()`` for batch callers
    that discard ``side`` immediately after (``credit_scene_depth``'s fan-out) --
    ``flush_from_cache`` still runs unconditionally so a stale in-memory instance is
    never left in the idmapper identity map for a later reader to pick up.
    """
    field = "invested_depth" if source == DepthSource.ALLOCATION else "scene_depth"
    with transaction.atomic():
        CharacterRelationship.objects.filter(pk=side.pk).update_with_reason(
            reason="issue #3957: intentional atomic write", **{field: F(field) + amount}
        )
        RelationshipDepthTransaction.objects.create(
            relationship=side,
            amount=amount,
            source=source,
            scene=scene,
            game_week=week,
        )
    # Full (not fields=[...]) refresh: idmapper's __call__ re-caches whatever partial
    # instance a .only()-style refresh constructs, so a single-field refresh right after
    # flush_from_cache would leave the OTHER fields permanently deferred on the cached
    # object (world/npc_services/regard.py's mirror_npc_regard_event bridge uses the same
    # flush-then-full-refresh pairing for the same reason).
    side.flush_from_cache(force=True)
    if refresh:
        side.refresh_from_db()


def process_weekly_relationship_allocations() -> int:
    """The weekly turn: every allocation the pool can pay becomes depth (#3957).

    Idempotent per game week: a side that already has an ALLOCATION-sourced depth
    transaction for the current week is skipped, so a repeat call in the same week
    (the weekly orchestrator plus the standalone 24h fallback registration both firing)
    never spends the same standing AP allocation, or awards its depth, more than once.
    """
    from world.action_points.models import ActionPointPool
    from world.game_clock.week_services import get_current_game_week

    cfg = get_growth_config()
    week = get_current_game_week()
    already_credited = set(
        RelationshipDepthTransaction.objects.filter(
            source=DepthSource.ALLOCATION, game_week=week
        ).values_list("relationship_id", flat=True)
    )
    processed = 0
    allocations = (
        RelationshipAllocation.objects.filter(ap_amount__gt=0, relationship__is_active=True)
        .exclude(relationship_id__in=already_credited)
        .select_related("relationship__source")
    )
    for allocation in allocations:
        side = allocation.relationship
        # ActionPointPool.character FKs the CharacterSheet directly, and CharacterSheet
        # shares its pk with side.source -- no need to walk sheet -> character -> sheet
        # through get_or_create_for_character (set_allocation already required the pool
        # to exist before an allocation with ap_amount > 0 could be set).
        pool = ActionPointPool.objects.filter(character_id=side.source_id).first()
        if pool is None or not pool.spend(allocation.ap_amount):
            continue
        _award_depth(
            side, allocation.ap_amount * cfg.depth_per_ap, DepthSource.ALLOCATION, week=week
        )
        processed += 1
    return processed


def credit_scene_depth(scene: Scene) -> int:
    """First scene together in a game week credits each side ``scene_base_gain`` (#3957).

    Both characters must have POSED in the scene. Returns the number of sides credited.
    Every posed-together pair opens a row on each side (spec) -- the already-credited
    set is fetched once up front so the per-pair loop costs no extra query per side.
    """
    from world.game_clock.week_services import get_current_game_week
    from world.scenes.models import Interaction

    sheet_ids = sorted(
        {
            sid
            for sid in Interaction.objects.filter(scene=scene).values_list(
                "persona__character_sheet_id", flat=True
            )
            if sid is not None
        }
    )
    if len(sheet_ids) < 2:  # noqa: PLR2004
        return 0
    from world.character_sheets.models import CharacterSheet

    sheets = {s.pk: s for s in CharacterSheet.objects.filter(pk__in=sheet_ids)}
    cfg = get_growth_config()
    week = get_current_game_week()
    already_credited = set(
        RelationshipDepthTransaction.objects.filter(
            source=DepthSource.SCENE, game_week=week, relationship__source_id__in=sheet_ids
        ).values_list("relationship_id", flat=True)
    )
    credited = 0
    for i, a_id in enumerate(sheet_ids):
        for b_id in sheet_ids[i + 1 :]:
            for src, tgt in ((a_id, b_id), (b_id, a_id)):
                side = get_or_create_side(source=sheets[src], target=sheets[tgt])
                if not side.is_active or side.pk in already_credited:
                    continue
                _award_depth(
                    side,
                    cfg.scene_base_gain,
                    DepthSource.SCENE,
                    week=week,
                    scene=scene,
                    refresh=False,
                )
                already_credited.add(side.pk)
                credited += 1
    return credited


# -- tiers ---------------------------------------------------------------------


def advance_tier(
    *, side: CharacterRelationship, journal_entry: JournalEntry
) -> RelationshipCapstone:
    """Claim the next tier with a capstone entry and XP (#3957). Cost = xp_per_tier x new tier."""
    nxt = side.next_tier()
    if nxt is None or side.pair_depth() < nxt.depth_threshold:
        raise TierNotReachedError
    if (
        journal_entry.author_id != side.source_id
        or side.target_id is None
        or journal_entry.about_id != side.target_id
        or journal_entry.parent_id is not None
    ):
        raise CapstoneEntryInvalidError
    if RelationshipCapstone.objects.filter(journal_entry=journal_entry).exists():
        raise CapstoneEntryInvalidError
    cost = get_growth_config().xp_per_tier * nxt.tier_number
    with transaction.atomic():
        spend_xp_for_character(side.source, cost, f"Relationship tier {nxt.tier_number}")
        receipt = RelationshipCapstone.objects.create(
            relationship=side,
            journal_entry=journal_entry,
            tier_claimed=nxt.tier_number,
            xp_spent=cost,
        )
        side.tier = nxt.tier_number
        side.save(update_fields=["tier", "updated_at"])
    return receipt


# -- gauges --------------------------------------------------------------------


def move_gauges(*, side: CharacterRelationship, amount: int) -> None:
    """Positive adds Affection, negative adds Conflict; both floors are zero."""
    if amount > 0:
        CharacterRelationship.objects.filter(pk=side.pk).update_with_reason(
            reason="issue #3957: intentional atomic write", affection=F("affection") + amount
        )
    elif amount < 0:
        CharacterRelationship.objects.filter(pk=side.pk).update_with_reason(
            reason="issue #3957: intentional atomic write", conflict=F("conflict") + (-amount)
        )
    # Full refresh, same reason as _award_depth: a fields=[...] refresh right after
    # flush_from_cache leaves every OTHER field permanently deferred on the re-cached
    # instance (idmapper's __call__ caches whatever partial instance the refresh builds).
    side.flush_from_cache(force=True)
    side.refresh_from_db()


def companion_target_error(source: CharacterSheet, companion: Companion) -> str:
    """Why ``source`` may not hold a relationship toward ``companion``, else "" (#3575).

    Only the bonded owner may hold one (a companion has no player to consent, so
    the bind is the consent), and never toward a released companion. App layer
    only: a CheckConstraint cannot compare ``source`` with ``target_companion.owner``
    across tables, so this and the action preflight are the two enforcement points.
    """
    if companion.owner_id != source.pk:
        return "That companion is not bonded to you."
    if companion.released_at is not None:
        return "That companion has been released."
    return ""


def apply_relationship_bump(
    *,
    source: CharacterSheet,
    target: CharacterSheet,
    interaction: Interaction,
    valence: int,
    source_emoji: ReactionEmoji | None = None,
) -> RelationshipBump:
    """Ambient +/-1 on source's Affection or Conflict toward target (#1699, #3957)."""
    if source.pk == target.pk:
        msg = "You cannot record a relationship with yourself."
        raise ValidationError(msg)
    try:
        with transaction.atomic():
            side = get_or_create_side(source=source, target=target)
            bump = RelationshipBump.objects.create(
                relationship=side,
                interaction=interaction,
                timestamp=interaction.timestamp,
                valence=1 if valence > 0 else -1,
                source_emoji=source_emoji,
            )
            move_gauges(side=side, amount=BUMP_POINTS if valence > 0 else -BUMP_POINTS)
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
    """A social action's automatic shift on the target's gauges (#1697, #2540, #3957)."""
    if (effect is None) == (boon is None):
        msg = "An affection shift carries exactly one provenance: effect or boon."
        raise ValueError(msg)
    if amount == 0 or source.pk == target.pk:
        return None
    try:
        with transaction.atomic():
            side = get_or_create_side(source=source, target=target)
            shift = AffectionShift.objects.create(
                relationship=side, scene=scene, effect=effect, boon=boon, amount=amount
            )
            move_gauges(side=side, amount=amount)
    except IntegrityError:
        return None
    return shift


def mirror_npc_regard_event(event: NpcRegardEvent) -> CharacterRelationship | None:
    """Mirror one NpcRegardEvent onto the PC's gauges toward the NPC (#2039, #3957)."""
    regard = event.regard
    target_persona = regard.target_persona
    if target_persona is None:
        return None
    pc_sheet = target_persona.character_sheet
    npc_sheet = regard.holder_persona.character_sheet
    if pc_sheet.pk == npc_sheet.pk or event.amount == 0:
        return None
    side = get_or_create_side(source=pc_sheet, target=npc_sheet)
    move_gauges(side=side, amount=event.amount)
    return side


def register_grievance(
    *,
    source: CharacterSheet,
    target: CharacterSheet,
    option: GrievanceOption | None = None,
    custom_points: int | None = None,
) -> CharacterRelationship:
    """A wronged character's one-sided grievance: Conflict added on their side (#1429, #3957)."""
    if (option is None) == (custom_points is None):
        msg = "A grievance needs exactly one of option or custom_points."
        raise ValidationError(msg)
    points = option.conflict_points if option is not None else custom_points
    if points <= 0:
        msg = "A grievance must add a positive amount of conflict."
        raise ValidationError(msg)
    side = get_or_create_side(source=source, target=target)
    move_gauges(side=side, amount=-points)
    return side


def relationship_gated_contributions(
    *, perceiver: CharacterSheet, perceived: CharacterSheet
) -> list[ModifierContribution]:
    """Modifier contributions the perceiver's regard for the perceived injects into a check (#1696).

    Allure (and any future relationship-gated modifier) is a **directed, conditional** modifier: it
    boosts the *perceived's* social checks against the *perceiver* only when the perceiver holds a
    gating relationship-condition toward them. For the directed
    ``CharacterRelationship(source=perceiver, target=perceived)``, each active
    ``RelationshipCondition.gates_modifiers`` target folds in the **perceived's**
    ``get_modifier_total`` of that target -- **once per gating condition**. So two allure-gating
    conditions (``Attracted To`` + ``Very Attracted``) count the perceived's allure twice -- the
    "double" effect falls out of the count, with no allure-specific code.

    Returns ``[]`` with no active relationship or no gating condition (the common case until
    Flirt/Seduction set the conditions). **Permanent** conditions ("Attracted To") live on the
    ``conditions`` M2M; **temporary** ones ("Very Attracted") live in ``temporary_conditions`` with
    an ``expires_at`` and are unioned here only while unexpired (#1697) -- so a live Very Attracted
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
    """Add a ``RelationshipCondition`` to the directed ``source -> target`` relationship (#1697).

    ``duration is None`` -> a **permanent** condition on the ``conditions`` M2M ("Attracted To").
    A ``timedelta`` -> a **temporary** condition (``TemporaryRelationshipCondition`` with
    ``expires_at = now + duration``), refreshed in place if it already exists ("Very Attracted",
    re-upped each flirt). Get-or-creates the side. The flirt/seduce TARGET becomes attracted to
    the actor, so callers pass ``source=<the flirt's target>, target=<the actor>``.
    """
    relationship = get_or_create_side(source=source, target=target)
    if duration is None:
        relationship.conditions.add(condition)
        return
    TemporaryRelationshipCondition.objects.update_or_create(
        relationship=relationship,
        condition=condition,
        defaults={"expires_at": timezone.now() + duration},
    )


def clear_very_attracted(sheets) -> None:
    """Drop Very Attracted for the given characters -- the scene-end early clear (#1697).

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

    # Check a->b direction (Sinner owns the capstone thread)
    if Thread.objects.filter(
        owner=a_sheet,
        target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
        target_capstone__relationship__source=a_sheet,
        target_capstone__relationship__target=b_sheet,
        retired_at__isnull=True,
    ).exists():
        return True

    # Check b->a direction
    return Thread.objects.filter(
        owner=b_sheet,
        target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
        target_capstone__relationship__source=b_sheet,
        target_capstone__relationship__target=a_sheet,
        retired_at__isnull=True,
    ).exists()


def _tier_bonus(tier_number: int) -> int:
    tier = RelationshipTier.objects.filter(tier_number=tier_number).first()
    return tier.combat_bonus if tier is not None else 0


def bond_combat_bonus(
    sheet: CharacterSheet, encounter: CombatEncounter
) -> list[ModifierContribution]:
    """One contribution per bonded ACTIVE co-combatant, valued by this side's tier (#2021)."""
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
        bond = CharacterRelationship.objects.filter(
            source=sheet, target=ally_sheet, is_active=True
        ).first()
        if bond is None or bond.tier < config.min_tier:
            continue
        bonus = _tier_bonus(bond.tier)
        if bonus == 0:
            continue
        if soul_tether_active(sheet, ally_sheet):
            bonus *= config.soul_tether_multiplier
        contributions.append(
            ModifierContribution(
                source_kind=ModifierSourceKind.RELATIONSHIP,
                source_label=f"Bond: {ally_sheet}",
                value=bonus,
            )
        )
    return contributions


def bond_bonus(actor: ObjectDB, protected: ObjectDB) -> int:
    actor_sheet = actor.character_sheet
    protected_sheet = protected.character_sheet
    if actor_sheet is None or protected_sheet is None:
        return 0
    config = get_bond_combat_config()
    bond = CharacterRelationship.objects.filter(
        source=actor_sheet, target=protected_sheet, is_active=True
    ).first()
    if bond is None or bond.tier < config.min_tier:
        return 0
    return _tier_bonus(bond.tier)

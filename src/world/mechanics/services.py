"""
Mechanics Service Functions

Service layer for modifier aggregation, calculation, and management.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import Prefetch

from world.checks.services import chart_has_success_outcomes, preview_check_difficulty
from world.conditions.services import get_all_capability_values
from world.distinctions.models import CharacterDistinction
from world.magic.constants import EffectKind, TargetKind
from world.magic.models import Resonance, TechniqueCapabilityGrant, ThreadPullEffect
from world.mechanics.constants import (
    EQUIPMENT_RELEVANT_CATEGORIES,
    CapabilitySourceType,
    DifficultyIndicator,
)
from world.mechanics.models import (
    Application,
    ChallengeApproach,
    ChallengeInstance,
    ChallengeTemplate,
    CharacterModifier,
    ModifierSource,
    ModifierTarget,
    Property,
    TraitCapabilityDerivation,
)
from world.mechanics.types import (
    AvailableAction,
    CapabilitySource,
    ModifierBreakdown,
    ModifierSourceDetail,
    PrerequisiteEvaluation,
)
from world.traits.models import CharacterTraitValue

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.checks.models import CheckType
    from world.covenants.models import CovenantRole
    from world.items.models import ItemInstance


def get_modifier_breakdown(character, modifier_target: ModifierTarget) -> ModifierBreakdown:
    """
    Get detailed breakdown of all modifiers for a target.

    Applies amplification and immunity rules:
    - Amplifying sources add their bonus to all OTHER sources
    - Immunity blocks all negative modifiers

    Args:
        character: CharacterSheet instance
        modifier_target: The ModifierTarget to aggregate

    Returns:
        ModifierBreakdown with sources, calculations, and total
    """
    # Get all modifiers for this character and target
    modifiers = CharacterModifier.objects.filter(
        character=character,
        target=modifier_target,
    ).select_related("source__distinction_effect__distinction")

    if not modifiers.exists():
        return ModifierBreakdown(
            modifier_target_name=modifier_target.name,
            sources=[],
            total=0,
            has_immunity=False,
            negatives_blocked=0,
        )

    # Collect amplifiers and check for immunity
    amplifiers: list[tuple[int, int]] = []  # (modifier_id, amplify_bonus)
    has_immunity = False

    for mod in modifiers:
        effect = mod.source.distinction_effect
        if effect.amplifies_sources_by:
            amplifiers.append((mod.id, effect.amplifies_sources_by))
        if effect.grants_immunity_to_negative:
            has_immunity = True

    # Calculate each source's contribution
    sources: list[ModifierSourceDetail] = []
    total = 0
    negatives_blocked = 0

    for mod in modifiers:
        effect = mod.source.distinction_effect
        base_value = mod.value
        is_amplifier = bool(effect.amplifies_sources_by)

        # Calculate amplification from OTHER sources
        amplification = 0
        for amp_id, amp_bonus in amplifiers:
            if amp_id != mod.id:
                amplification += amp_bonus

        final_value = base_value + amplification

        # Check if blocked by immunity
        blocked = has_immunity and final_value < 0

        if blocked:
            negatives_blocked += 1
        else:
            total += final_value

        sources.append(
            ModifierSourceDetail(
                source_name=effect.distinction.name,
                base_value=base_value,
                amplification=amplification,
                final_value=final_value,
                is_amplifier=is_amplifier,
                blocked_by_immunity=blocked,
            )
        )

    return ModifierBreakdown(
        modifier_target_name=modifier_target.name,
        sources=sources,
        total=total,
        has_immunity=has_immunity,
        negatives_blocked=negatives_blocked,
    )


def get_modifier_total(character, modifier_target: ModifierTarget) -> int:
    """Get total modifier value for a target.

    Combines the eager modifier total (CharacterModifier rows, distinctions, etc.) with the
    equipment walk (Spec D §5.5) for equipment-relevant categories. The equipment walk adds
    passive_facet_bonuses and covenant_role_bonus when the target's category is in
    EQUIPMENT_RELEVANT_CATEGORIES (stat, magic, affinity, resonance).

    Args:
        character: CharacterSheet instance
        modifier_target: The ModifierTarget to aggregate

    Returns:
        Total modifier value (eager + equipment contributions, amplification/immunity applied)
    """
    eager_total = get_modifier_breakdown(character, modifier_target).total
    equipment_total = 0
    if modifier_target.category.name in EQUIPMENT_RELEVANT_CATEGORIES:
        equipment_total = passive_facet_bonuses(character, modifier_target)
        equipment_total += covenant_role_bonus(character, modifier_target)
    return eager_total + equipment_total


# =============================================================================
# Passive Facet Bonuses (Spec D §5.2)
# =============================================================================


def passive_facet_bonuses(sheet: object, target: ModifierTarget) -> int:
    """Sum tier-0 FLAT_BONUS contributions from equipped item facets (Spec D §5.2).

    For each FACET-kind thread the character owns, look up equipped items that
    carry the thread's anchor facet. For each matching (item, item_facet) pair,
    compute the contribution from every tier-0 FLAT_BONUS ThreadPullEffect that
    maps this thread's resonance to ``target`` via the ModifierTarget.target_resonance
    OneToOne. Sum all contributions and return the integer total.

    This composes with the existing ``passive_vital_bonuses`` pattern — same shape,
    keyed by ModifierTarget instead of vital_target. See CharacterThreadHandler in
    world/magic/handlers.py for the parallel.

    Args:
        sheet: CharacterSheet instance (the character whose threads and items are used).
        target: The ModifierTarget to aggregate bonuses for.

    Returns:
        Integer total of all passive facet contributions for ``target``.
    """
    char = sheet.character
    # Defensive: raw ObjectDB fixtures (without _typeclass_path) don't have
    # Character typeclass handlers. Skip the walk gracefully.
    if not hasattr(char, "threads") or not hasattr(char, "equipped_items"):
        return 0
    total = 0
    for thread in char.threads.threads_of_kind(TargetKind.FACET):
        matching = char.equipped_items.item_facets_for(thread.target_facet)
        if not matching:
            continue
        effects = _facet_pull_effects_for(thread.resonance, target, tier=0)
        for effect in effects:
            for item_facet in matching:
                total += _facet_effect_contribution(
                    effect=effect,
                    thread=thread,
                    item=item_facet.item_instance,
                    item_facet=item_facet,
                )
    return total


def _facet_pull_effects_for(
    resonance: object,
    target: ModifierTarget,
    tier: int,
) -> list[ThreadPullEffect]:
    """Return tier-0 FACET FLAT_BONUS effects gated by resonance→target link.

    Gate: a ModifierTarget contributes only when its ``target_resonance`` OneToOne
    points to ``resonance``. Targets in the stat/magic/affinity categories lack
    this link and return [] — PR3 may add other linking mechanisms.

    Args:
        resonance: The Resonance instance from the thread.
        target: The ModifierTarget being aggregated.
        tier: Effect tier to filter on (0 = passive always-on).

    Returns:
        List of ThreadPullEffect rows (may be empty).
    """
    # ModifierTarget owns the FK; .target_resonance_id is the FK column, so
    # this is a direct PK compare with no extra query.
    if target.target_resonance_id is None or target.target_resonance_id != resonance.pk:
        return []
    return list(
        ThreadPullEffect.objects.filter(
            target_kind=TargetKind.FACET,
            resonance=resonance,
            tier=tier,
            effect_kind=EffectKind.FLAT_BONUS,
        ).exclude(flat_bonus_amount__isnull=True)
    )


def _facet_effect_contribution(
    *,
    effect: ThreadPullEffect,
    thread: object,
    item: object,
    item_facet: object,
) -> int:
    """Compute one (item, facet) contribution to a tier-0 FLAT_BONUS effect.

    Formula: base × item_quality_multiplier × attachment_quality_multiplier × max(1, level).

    Decimal(str(...)) coercion guards against float stat_multiplier values from
    factories or .values() queries; DecimalField normally returns Decimal, but
    this is belt-and-suspenders consistent with the resonance.py FACET branch.

    Args:
        effect: The ThreadPullEffect row (FLAT_BONUS, tier 0).
        thread: The Thread instance (supplies ``level``).
        item: The ItemInstance (supplies ``quality_tier.stat_multiplier``).
        item_facet: The ItemFacet (supplies ``attachment_quality_tier.stat_multiplier``).

    Returns:
        Integer contribution (truncated via int()).
    """
    base = effect.flat_bonus_amount or 0
    item_mult = (
        Decimal(str(item.quality_tier.stat_multiplier))
        if item.quality_tier is not None
        else Decimal(1)
    )
    # Non-nullable FK — always present
    attach_mult = Decimal(str(item_facet.attachment_quality_tier.stat_multiplier))
    level_mult = max(1, thread.level)
    return int(base * item_mult * attach_mult * level_mult)


# =============================================================================
# Covenant Role Bonus (Spec D §5.6)
# =============================================================================


def covenant_role_bonus(sheet: object, target: ModifierTarget) -> int:
    """Sum covenant-role contributions across equipped items for a ModifierTarget (Spec D §5.6).

    Per slot:
    - Compatible gear (GearArchetypeCompatibility row exists): role_bonus + gear_stat (additive)
    - Incompatible gear (no row): max(role_bonus, gear_stat) (highest wins)

    At low character levels gear_stat dominates; incompatible gear costs nothing.
    At high levels role_bonus dominates; incompatible gear's mundane stat is wasted.

    Args:
        sheet: CharacterSheet instance.
        target: The ModifierTarget to aggregate bonuses for.

    Returns:
        Integer total of all covenant-role contributions across equipped items.
    """
    from world.covenants.services import (  # noqa: PLC0415 — PR3 wires covenant callbacks
        is_gear_compatible,  # defer import to break future cycle
    )

    char = sheet.character
    # Defensive: raw ObjectDB fixtures (without _typeclass_path) don't have
    # Character typeclass handlers. Skip the walk gracefully.
    if not hasattr(char, "covenant_roles") or not hasattr(char, "equipped_items"):
        return 0
    role = char.covenant_roles.currently_held()
    if role is None:
        return 0
    role_bonus = role_base_bonus_for_target(role, target, sheet.current_level)
    total = 0
    for equipped in char.equipped_items:
        item = equipped.item_instance
        gear_stat = item_mundane_stat_for_target(item, target)
        archetype = item.template.gear_archetype
        if is_gear_compatible(role, archetype):
            total += role_bonus + gear_stat
        else:
            total += max(role_bonus, gear_stat)
    return total


def role_base_bonus_for_target(
    role: CovenantRole,  # noqa: ARG001 — placeholder; PR3 wires real computation
    target: ModifierTarget,  # noqa: ARG001 — placeholder; PR3 wires real computation
    character_level: int,  # noqa: ARG001 — placeholder; PR3 wires real computation
) -> int:
    """PLACEHOLDER — returns 0 in PR1. PR3 wires authored values."""
    return 0


def item_mundane_stat_for_target(
    item: ItemInstance,  # noqa: ARG001 — placeholder; PR3 wires real computation
    target: ModifierTarget,  # noqa: ARG001 — placeholder; PR3 wires real computation
) -> int:
    """PLACEHOLDER — returns 0 in PR1. PR3 reads ItemCombatStat."""
    return 0


def create_distinction_modifiers(
    character_distinction: CharacterDistinction,
) -> list[CharacterModifier]:
    """
    Create ModifierSource + CharacterModifier records for all effects of a distinction.

    Called when a CharacterDistinction is created.

    Args:
        character_distinction: The character's distinction instance

    Returns:
        List of created CharacterModifier records
    """
    distinction = character_distinction.distinction
    rank = character_distinction.rank
    character = character_distinction.character.sheet_data

    created_modifiers = []

    for effect in distinction.effects.all():
        # Create the source linking effect template to character instance
        source = ModifierSource.objects.create(
            distinction_effect=effect,
            character_distinction=character_distinction,
        )

        # Calculate value at current rank
        value = effect.get_value_at_rank(rank)

        # Create the modifier. CharacterModifier rows targeting resonances are
        # the source of truth for the aura calc (see magic.services.get_aura_percentages);
        # no denormalized resonance-total update is needed.
        modifier = CharacterModifier.objects.create(
            character=character,
            target=effect.target,
            value=value,
            source=source,
        )
        created_modifiers.append(modifier)

    return created_modifiers


@transaction.atomic
def delete_distinction_modifiers(character_distinction: CharacterDistinction) -> int:
    """
    Delete all modifier records for a distinction.

    Called when a CharacterDistinction is removed.

    Args:
        character_distinction: The character's distinction instance

    Returns:
        Count of deleted CharacterModifier records
    """
    # Get modifiers BEFORE deleting (evaluate queryset once). Aura percentages
    # are derived from these CharacterModifier rows directly, so no separate
    # denormalized resonance-total bookkeeping is required.
    modifiers = list(
        CharacterModifier.objects.filter(
            source__character_distinction=character_distinction
        ).select_related("target__category", "source__distinction_effect")
    )

    # Delete sources (which cascades to modifiers)
    sources = ModifierSource.objects.filter(character_distinction=character_distinction)
    sources.delete()
    return len(modifiers)


@transaction.atomic
def update_distinction_rank(character_distinction: CharacterDistinction) -> None:
    """
    Update CharacterModifier values when rank changes.

    Recalculates value for each effect using the new rank.

    Args:
        character_distinction: The character's distinction instance (with updated rank)
    """
    new_rank = character_distinction.rank

    # Get all modifiers for this distinction
    modifiers = CharacterModifier.objects.filter(
        source__character_distinction=character_distinction
    ).select_related("target__category", "source__distinction_effect")

    for modifier in modifiers:
        effect = modifier.source.distinction_effect
        new_value = effect.get_value_at_rank(new_rank)

        # Update modifier — the aura calc reads from these rows directly,
        # so no denormalized resonance-total adjustment is required.
        modifier.value = new_value
        modifier.save()


# =============================================================================
# Capability Source Aggregation
# =============================================================================


def get_capability_sources_for_character(
    character: ObjectDB,
) -> list[CapabilitySource]:
    """Collect all Capability sources for a character (per-source, not aggregated)."""
    sources: list[CapabilitySource] = []
    sources.extend(_get_technique_sources(character))
    sources.extend(_get_trait_sources(character))
    sources.extend(_get_condition_sources(character))
    return sources


def _get_technique_sources(character: ObjectDB) -> list[CapabilitySource]:
    """Get Capability sources from character's known Techniques."""
    grants = (
        TechniqueCapabilityGrant.objects.filter(
            technique__character_grants__character__character=character,
        )
        .select_related(
            "technique",
            "technique__gift",
            "capability",
            "prerequisite",
            "prerequisite__property",
        )
        .prefetch_related(
            Prefetch(
                "technique__gift__resonances",
                queryset=Resonance.objects.prefetch_related(
                    Prefetch(
                        "properties",
                        queryset=Property.objects.all(),
                        to_attr="cached_properties",
                    ),
                ),
                to_attr="cached_resonances",
            ),
        )
    )

    sources: list[CapabilitySource] = []
    for grant in grants:
        value = grant.calculate_value()
        if value <= 0:
            continue

        # Effect property IDs come from the Gift's resonances' modifier_target links
        effect_property_ids = _get_technique_effect_property_ids(grant.technique)

        sources.append(
            CapabilitySource(
                capability_name=grant.capability.name,
                capability_id=grant.capability_id,
                value=value,
                source_type=CapabilitySourceType.TECHNIQUE,
                source_name=grant.technique.name,
                source_id=grant.technique_id,
                effect_property_ids=effect_property_ids,
                prerequisite=grant.prerequisite,
            )
        )

    return sources


def _get_technique_effect_property_ids(technique: object) -> list[int]:
    """
    Derive effect Property IDs from a Technique's Gift resonances.

    Each Resonance has a M2M to Property. Collects all Property IDs
    from the technique's gift's resonances via prefetched cached_properties.

    Expects technique.gift.cached_resonances[*].cached_properties to be
    pre-populated via the _get_technique_sources() prefetch chain.
    """
    if not hasattr(technique, "gift_id") or not technique.gift_id:
        return []

    property_ids: list[int] = []
    for resonance in technique.gift.cached_resonances:
        property_ids.extend(p.id for p in resonance.cached_properties)
    return property_ids


def _get_trait_sources(character: ObjectDB) -> list[CapabilitySource]:
    """Get Capability sources derived from character traits."""
    derivations = TraitCapabilityDerivation.objects.select_related("trait", "capability").all()

    if not derivations:
        return []

    trait_ids = [d.trait_id for d in derivations]
    trait_values = dict(
        CharacterTraitValue.objects.filter(
            character=character,
            trait_id__in=trait_ids,
        ).values_list("trait_id", "value")
    )

    sources: list[CapabilitySource] = []
    for derivation in derivations:
        tv = trait_values.get(derivation.trait_id)
        if not tv or tv <= 0:
            continue

        value = derivation.calculate_value(tv)
        if value <= 0:
            continue

        sources.append(
            CapabilitySource(
                capability_name=derivation.capability.name,
                capability_id=derivation.capability_id,
                value=value,
                source_type=CapabilitySourceType.TRAIT,
                source_name=derivation.trait.name,
                source_id=derivation.trait_id,
            )
        )

    return sources


def _get_condition_sources(character: ObjectDB) -> list[CapabilitySource]:
    """Get Capability sources from active conditions."""
    cap_values = get_all_capability_values(character)

    sources: list[CapabilitySource] = []
    for cap_id, value in cap_values.items():
        if value <= 0:
            continue

        sources.append(
            CapabilitySource(
                capability_name="",  # Not needed for PK-based matching
                capability_id=cap_id,
                value=value,
                source_type=CapabilitySourceType.CONDITION,
                source_name="",  # Conditions aggregate; no single source name
                source_id=0,
            )
        )

    return sources


# =============================================================================
# Action Generation
# =============================================================================


def get_available_actions(
    character: ObjectDB,
    location: ObjectDB,
    capability_sources: list[CapabilitySource] | None = None,
) -> list[AvailableAction]:
    """Generate available Actions for a character at a location."""
    if capability_sources is None:
        capability_sources = get_capability_sources_for_character(character)

    if not capability_sources:
        return []

    # Build lookup: capability_id -> list of sources
    cap_id_to_sources: dict[int, list[CapabilitySource]] = {}
    for src in capability_sources:
        cap_id_to_sources.setdefault(src.capability_id, []).append(src)

    challenge_instances = (
        ChallengeInstance.objects.filter(
            location=location,
            is_active=True,
            is_revealed=True,
        )
        .select_related("template", "target_object")
        .prefetch_related(
            Prefetch(
                "template__properties",
                queryset=Property.objects.all(),
                to_attr="cached_properties",
            ),
            Prefetch(
                "template__approaches",
                queryset=ChallengeApproach.objects.select_related(
                    "application__capability",
                    "application__capability__prerequisite",
                    "application__capability__prerequisite__property",
                    "application__target_property",
                    "application__required_effect_property",
                    "check_type",
                    "required_effect_property",
                ),
                to_attr="cached_approaches",
            ),
        )
    )

    actions: list[AvailableAction] = []

    for ci in challenge_instances:
        template = ci.template
        challenge_property_ids = {p.id for p in template.cached_properties}
        _match_approaches(
            character, ci, template, challenge_property_ids, cap_id_to_sources, actions
        )

    return actions


def _match_approaches(  # noqa: PLR0913
    character: ObjectDB,
    ci: ChallengeInstance,
    template: ChallengeTemplate,
    challenge_property_ids: set[int],
    cap_id_to_sources: dict[int, list[CapabilitySource]],
    actions: list[AvailableAction],
) -> None:
    """Match approaches on a challenge to capability sources and append actions."""
    cap_prereq_cache: dict[int, PrerequisiteEvaluation | None] = {}

    for approach in template.cached_approaches:
        app = approach.application
        if app.target_property_id not in challenge_property_ids:
            continue

        matching_sources = cap_id_to_sources.get(app.capability_id, [])

        for source in matching_sources:
            if not _source_meets_effect_requirements(app, approach, source):
                continue

            reasons: list[str] = []
            prereq_met = _evaluate_prerequisites(
                character,
                ci,
                app,
                source,
                cap_prereq_cache,
                reasons,
            )

            difficulty = None
            if prereq_met:
                difficulty = _get_difficulty_indicator_for_check(
                    character,
                    approach.check_type,
                    template.severity,
                )
                if difficulty == DifficultyIndicator.IMPOSSIBLE:
                    continue

            actions.append(
                AvailableAction(
                    application_id=app.id,
                    application_name=app.name,
                    capability_source=source,
                    challenge_instance_id=ci.id,
                    challenge_name=template.name,
                    approach_id=approach.id,
                    check_type_name=approach.check_type.name,
                    display_name=approach.display_name or app.name,
                    custom_description=approach.custom_description,
                    difficulty_indicator=difficulty,
                    prerequisite_met=prereq_met,
                    prerequisite_reasons=reasons,
                )
            )


def _evaluate_prerequisites(  # noqa: PLR0913
    character: ObjectDB,
    ci: ChallengeInstance,
    app: Application,
    source: CapabilitySource,
    cap_prereq_cache: dict[int, PrerequisiteEvaluation | None],
    reasons: list[str],
) -> bool:
    """Evaluate capability-level and source-level prerequisites.

    Returns True if all prerequisites are met. Appends failure reasons.
    Uses cap_prereq_cache to avoid re-evaluating the same capability prerequisite.

    Note: source-level prerequisites each trigger an ObjectProperty query.
    For future optimization, consider bulk-fetching ObjectProperty records
    for all relevant entities upfront.
    """
    all_met = True

    # Capability-level prerequisite (shared across all sources of this capability)
    cap_id = app.capability_id
    if cap_id not in cap_prereq_cache:
        cap_prereq = app.capability.prerequisite
        if cap_prereq is not None:
            cap_prereq_cache[cap_id] = cap_prereq.evaluate(
                character,
                ci.target_object,
                ci.location,
            )
        else:
            cap_prereq_cache[cap_id] = None

    cap_result = cap_prereq_cache[cap_id]
    if cap_result is not None and not cap_result.met:
        reasons.append(cap_result.reason)
        all_met = False

    # Source-level prerequisite (specific to this technique grant)
    if source.prerequisite is not None:
        src_result = source.prerequisite.evaluate(
            character,
            ci.target_object,
            ci.location,
        )
        if not src_result.met:
            reasons.append(src_result.reason)
            all_met = False

    return all_met


def _source_meets_effect_requirements(
    app: Application,
    approach: ChallengeApproach,
    source: CapabilitySource,
) -> bool:
    """Check if a source meets the effect property requirements of app and approach."""
    if app.required_effect_property_id:
        if app.required_effect_property_id not in source.effect_property_ids:
            return False

    if approach.required_effect_property_id:
        if approach.required_effect_property_id not in source.effect_property_ids:
            return False

    return True


# Rank difference thresholds for difficulty indicator.
# These use the actual check pipeline's rank system.
_RANK_DIFF_EASY = 3
_RANK_DIFF_MODERATE = 1
_RANK_DIFF_HARD = -1


def _get_difficulty_indicator_for_check(
    character: ObjectDB,
    check_type: CheckType,
    target_difficulty: int,
) -> DifficultyIndicator:
    """
    Determine difficulty indicator using the real check pipeline.

    Calculates the rank difference that would result from a check,
    then classifies it. IMPOSSIBLE means the ResultChart has no success outcomes.
    """
    rank_diff = preview_check_difficulty(character, check_type, target_difficulty)

    if not chart_has_success_outcomes(rank_diff):
        return DifficultyIndicator.IMPOSSIBLE
    if rank_diff >= _RANK_DIFF_EASY:
        return DifficultyIndicator.EASY
    if rank_diff >= _RANK_DIFF_MODERATE:
        return DifficultyIndicator.MODERATE
    if rank_diff >= _RANK_DIFF_HARD:
        return DifficultyIndicator.HARD
    return DifficultyIndicator.VERY_HARD

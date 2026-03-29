"""
Mechanics Service Functions

Service layer for modifier aggregation, calculation, and management.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import Prefetch

from world.checks.services import chart_has_success_outcomes, preview_check_difficulty
from world.conditions.services import get_all_capability_values
from world.distinctions.models import CharacterDistinction
from world.magic.models import Resonance, TechniqueCapabilityGrant
from world.magic.services import add_resonance_total
from world.mechanics.constants import (
    RESONANCE_CATEGORY_NAME,
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
)
from world.traits.models import CharacterTraitValue

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.checks.models import CheckType


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
    """
    Get total modifier value for a target.

    Convenience wrapper around get_modifier_breakdown.

    Args:
        character: CharacterSheet instance
        modifier_target: The ModifierTarget to aggregate

    Returns:
        Total modifier value (with amplification/immunity applied)
    """
    return get_modifier_breakdown(character, modifier_target).total


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

        # Create the modifier
        modifier = CharacterModifier.objects.create(
            character=character,
            target=effect.target,
            value=value,
            source=source,
        )
        created_modifiers.append(modifier)

        # If targeting a resonance, update CharacterResonanceTotal
        target = effect.target
        if target.category.name == RESONANCE_CATEGORY_NAME and target.target_resonance_id:
            add_resonance_total(character, target.target_resonance, value)

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
    # Get modifiers BEFORE deleting (evaluate queryset once)
    modifiers = list(
        CharacterModifier.objects.filter(
            source__character_distinction=character_distinction
        ).select_related("target__category", "source__distinction_effect")
    )

    # Subtract from resonance totals
    for modifier in modifiers:
        target = modifier.target
        if target.category.name == RESONANCE_CATEGORY_NAME and target.target_resonance_id:
            add_resonance_total(
                character_distinction.character.sheet_data,
                target.target_resonance,
                -modifier.value,  # Negative to subtract
            )

    # Then delete sources (which cascades to modifiers)
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
        old_value = modifier.value
        new_value = effect.get_value_at_rank(new_rank)

        # Update modifier
        modifier.value = new_value
        modifier.save()

        # If resonance, adjust total by the difference
        target = modifier.target
        if target.category.name == RESONANCE_CATEGORY_NAME and target.target_resonance_id:
            add_resonance_total(
                character_distinction.character.sheet_data,
                target.target_resonance,
                new_value - old_value,
            )


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
        .select_related("template")
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
    for approach in template.cached_approaches:
        app = approach.application
        if app.target_property_id not in challenge_property_ids:
            continue

        matching_sources = cap_id_to_sources.get(app.capability_id, [])

        for source in matching_sources:
            if not _source_meets_effect_requirements(app, approach, source):
                continue

            difficulty = _get_difficulty_indicator_for_check(
                character, approach.check_type, template.severity
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
                )
            )


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

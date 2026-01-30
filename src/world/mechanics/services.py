"""
Mechanics Service Functions

Service layer for modifier aggregation, calculation, and management.
"""

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction

from world.distinctions.models import CharacterDistinction
from world.magic.services import add_resonance_total
from world.mechanics.models import CharacterModifier, ModifierSource, ModifierType
from world.mechanics.types import ModifierBreakdown, ModifierSourceDetail


def get_modifier_breakdown(character, modifier_type: ModifierType) -> ModifierBreakdown:
    """
    Get detailed breakdown of all modifiers for a type.

    Applies amplification and immunity rules:
    - Amplifying sources add their bonus to all OTHER sources
    - Immunity blocks all negative modifiers

    Args:
        character: CharacterSheet instance
        modifier_type: The ModifierType to aggregate

    Returns:
        ModifierBreakdown with sources, calculations, and total
    """
    # Get all modifiers for this character and type
    modifiers = CharacterModifier.objects.filter(
        character=character,
        source__distinction_effect__target=modifier_type,
    ).select_related("source__distinction_effect__distinction")

    if not modifiers.exists():
        return ModifierBreakdown(
            modifier_type_name=modifier_type.name,
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
        modifier_type_name=modifier_type.name,
        sources=sources,
        total=total,
        has_immunity=has_immunity,
        negatives_blocked=negatives_blocked,
    )


def get_modifier_total(character, modifier_type: ModifierType) -> int:
    """
    Get total modifier value for a type.

    Convenience wrapper around get_modifier_breakdown.

    Args:
        character: CharacterSheet instance
        modifier_type: The ModifierType to aggregate

    Returns:
        Total modifier value (with amplification/immunity applied)
    """
    return get_modifier_breakdown(character, modifier_type).total


def get_modifier_for_character(
    character,
    category_name: str,
    modifier_type_name: str,
) -> int:
    """
    Get total modifier value for a character by category and type names.

    Handles missing CharacterSheets and missing ModifierTypes gracefully.
    This is the recommended helper for looking up modifiers when you have
    a character object (ObjectDB) rather than a CharacterSheet.

    Args:
        character: Character ObjectDB instance (with sheet_data attribute)
        category_name: Modifier category name (e.g., "stat", "action_points")
        modifier_type_name: Modifier type name (e.g., "strength", "ap_daily_regen")

    Returns:
        Total modifier value (can be negative). Returns 0 if:
        - Character has no sheet_data
        - ModifierType doesn't exist
        - No modifiers apply
    """
    try:
        sheet = character.sheet_data
    except ObjectDoesNotExist:
        # Character has no CharacterSheet - return 0 (no modifiers)
        return 0

    try:
        modifier_type = ModifierType.objects.get(
            category__name=category_name,
            name=modifier_type_name,
        )
        return get_modifier_total(sheet, modifier_type)
    except ModifierType.DoesNotExist:
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

        # Create the modifier
        modifier = CharacterModifier.objects.create(
            character=character,
            value=value,
            source=source,
        )
        created_modifiers.append(modifier)

        # If targeting a resonance, update CharacterResonanceTotal
        if effect.target.category.name == "resonance":
            add_resonance_total(character, effect.target, value)

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
        ).select_related("source__distinction_effect__target__category")
    )

    # Subtract from resonance totals
    for modifier in modifiers:
        effect = modifier.source.distinction_effect
        if effect.target.category.name == "resonance":
            add_resonance_total(
                character_distinction.character.sheet_data,
                effect.target,
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
    ).select_related("source__distinction_effect__target__category")

    for modifier in modifiers:
        effect = modifier.source.distinction_effect
        old_value = modifier.value
        new_value = effect.get_value_at_rank(new_rank)

        # Update modifier
        modifier.value = new_value
        modifier.save()

        # If resonance, adjust total by the difference
        if effect.target.category.name == "resonance":
            add_resonance_total(
                character_distinction.character.sheet_data,
                effect.target,
                new_value - old_value,
            )

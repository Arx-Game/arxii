"""
Award services for the progression system.

This module handles awarding XP and development points to characters and accounts.
"""

from typing import cast

from django.db import transaction

from world.progression.models import (
    DevelopmentPoints,
    DevelopmentTransaction,
    ExperiencePointsData,
    XPTransaction,
)
from world.progression.types import DevelopmentSource, ProgressionReason


def get_or_create_xp_tracker(account):
    """Get or create XP tracker for an account."""
    xp_tracker, _created = ExperiencePointsData.objects.get_or_create(
        account=account,
        defaults={
            "total_earned": 0,
            "total_spent": 0,
        },
    )
    return xp_tracker


def award_xp(
    account,
    amount,
    reason=ProgressionReason.SYSTEM_AWARD,
    description="",
    gm=None,
):
    """
    Award XP to an account.

    Args:
        account: Account to award XP to
        amount: Amount of XP to award
        reason: Reason for the award
        description: Detailed description
        gm: GM making the award (if applicable)

    Returns:
        XPTransaction: The created transaction record
    """
    if amount <= 0:
        msg = "XP award amount must be positive"
        raise ValueError(msg)

    with transaction.atomic():
        xp_tracker = get_or_create_xp_tracker(account)
        xp_tracker.award_xp(amount)

        # Record transaction
        return XPTransaction.objects.create(
            account=account,
            amount=amount,
            reason=reason,
            description=description,
            gm=gm,
        )


def _get_development_rate_modifier(character, trait) -> int:
    """
    Get the development rate modifier percentage for a trait.

    Checks character's modifiers for development rate bonuses/penalties
    based on the trait's category (physical, social, mental).

    Args:
        character: Character to check modifiers for
        trait: Trait being developed

    Returns:
        Percentage modifier (-20 = 20% slower, +10 = 10% faster).
        Returns 0 if no modifiers apply.
    """
    try:
        sheet = character.sheet_data
    except AttributeError:
        return 0

    from world.mechanics.models import ModifierType
    from world.mechanics.services import get_modifier_total
    from world.traits.models import TraitCategory

    total_modifier = 0

    # Check for all-skill development rate modifier first
    try:
        all_rate = ModifierType.objects.get(
            category__name="development",
            name="all_skill_development_rate",
        )
        total_modifier += get_modifier_total(sheet, all_rate)
    except ModifierType.DoesNotExist:
        pass

    # Determine category-specific modifier based on trait category
    category_to_modifier = {
        TraitCategory.PHYSICAL: "physical_skill_development_rate",
        TraitCategory.COMBAT: "physical_skill_development_rate",
        TraitCategory.SOCIAL: "social_skill_development_rate",
        TraitCategory.GENERAL: "social_skill_development_rate",
        TraitCategory.MENTAL: "mental_skill_development_rate",
        TraitCategory.CRAFTING: "mental_skill_development_rate",
    }

    modifier_name = category_to_modifier.get(trait.category)
    if modifier_name:
        try:
            category_rate = ModifierType.objects.get(
                category__name="development",
                name=modifier_name,
            )
            total_modifier += get_modifier_total(sheet, category_rate)
        except ModifierType.DoesNotExist:
            pass

    return total_modifier


def _apply_rate_modifier(base_amount: int, rate_modifier: int) -> int:
    """
    Apply a percentage rate modifier to a base amount.

    Args:
        base_amount: Original amount of points
        rate_modifier: Percentage modifier (-20 = 20% slower, +10 = 10% faster)

    Returns:
        Modified amount, minimum 1 (always get at least 1 point)
    """
    if rate_modifier == 0:
        return base_amount

    # rate_modifier is a percentage: -20 means 80% effectiveness
    multiplier = (100 + rate_modifier) / 100.0
    modified = int(base_amount * multiplier)

    # Always award at least 1 point (can't reduce to 0)
    return max(1, modified)


def award_development_points(  # noqa: PLR0913 - Service signature exposes optional context fields
    character,
    trait,
    source,
    amount,
    scene=None,
    reason=ProgressionReason.SCENE_AWARD,
    description="",
    gm=None,
):
    """
    Award development points to a character and automatically apply them.

    Development rate modifiers from distinctions are automatically applied.
    For example, the Spoiled distinction reduces physical skill development
    by 20%.

    Args:
        character: Character receiving points
        trait: Trait to develop
        source: Source category for the points
        amount: Amount to award (before rate modifiers)
        scene: Scene where points were earned (if applicable)
        reason: Reason for the award
        description: Detailed description
        gm: GM making the award (if applicable)

    Returns:
        DevelopmentTransaction: The created transaction record
    """
    if amount <= 0:
        msg = "Development point award amount must be positive"
        raise ValueError(msg)

    # Apply development rate modifiers
    rate_modifier = _get_development_rate_modifier(character, trait)
    modified_amount = _apply_rate_modifier(amount, rate_modifier)

    with transaction.atomic():
        # Get or create development tracker
        dev_tracker, _created = DevelopmentPoints.objects.get_or_create(
            character=character,
            trait=trait,
            defaults={"total_earned": 0},
        )

        # Award and automatically apply the modified points
        dev_tracker.award_points(modified_amount)

        # Record transaction with original amount (for audit purposes)
        # The modified_amount is what actually gets applied
        return DevelopmentTransaction.objects.create(
            character=character,
            trait=trait,
            source=source,
            amount=modified_amount,  # Record actual awarded amount
            reason=reason,
            description=description,
            scene=scene,
            gm=gm,
        )


def get_development_suggestions_for_character(character):
    """
    Get development suggestions for a character based on their current traits.

    Args:
        character: Character to analyze

    Returns:
        Dict mapping development sources to suggested traits
    """
    from world.traits.models import Trait

    suggestions: dict[str, list[str]] = {
        cast(str, DevelopmentSource.COMBAT): [],
        cast(str, DevelopmentSource.SOCIAL): [],
        cast(str, DevelopmentSource.CRAFTING): [],
        cast(str, DevelopmentSource.SCENE): [],
    }

    # Get character's current trait values
    trait_values = character.trait_values.all()
    trait_dict = {tv.trait.name: tv.value for tv in trait_values}

    # Get all developable traits
    all_traits = Trait.objects.filter(is_public=True)

    # Trait rating constants
    MAX_TRAIT_VALUE = 100

    for trait in all_traits:
        current_value = trait_dict.get(trait.name, 0)
        if current_value >= MAX_TRAIT_VALUE:  # Already maxed
            continue

        # With simplified system, trait ratings auto-apply through development points
        # No need to check for rating unlocks anymore

        # Suggest based on trait category
        if trait.category in ["combat"]:
            suggestions[cast(str, DevelopmentSource.COMBAT)].append(trait.name)
        elif trait.category in ["social", "general"]:
            suggestions[cast(str, DevelopmentSource.SOCIAL)].append(trait.name)
        elif trait.category in ["crafting"]:
            suggestions[cast(str, DevelopmentSource.CRAFTING)].append(trait.name)
        else:
            suggestions[cast(str, DevelopmentSource.SCENE)].append(trait.name)

    return suggestions

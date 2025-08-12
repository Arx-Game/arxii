"""
Award services for the progression system.

This module handles awarding XP and development points to characters and accounts.
"""

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
    xp_tracker, created = ExperiencePointsData.objects.get_or_create(
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
        raise ValueError("XP award amount must be positive")

    with transaction.atomic():
        xp_tracker = get_or_create_xp_tracker(account)
        xp_tracker.award_xp(amount)

        # Record transaction
        xp_transaction = XPTransaction.objects.create(
            account=account,
            amount=amount,
            reason=reason,
            description=description,
            gm=gm,
        )

        return xp_transaction


def award_development_points(
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

    Args:
        character: Character receiving points
        trait: Trait to develop
        source: Source category for the points
        amount: Amount to award
        scene: Scene where points were earned (if applicable)
        reason: Reason for the award
        description: Detailed description
        gm: GM making the award (if applicable)

    Returns:
        DevelopmentTransaction: The created transaction record
    """
    if amount <= 0:
        raise ValueError("Development point award amount must be positive")

    with transaction.atomic():
        # Get or create development tracker
        dev_tracker, created = DevelopmentPoints.objects.get_or_create(
            character=character, trait=trait, defaults={"total_earned": 0}
        )

        # Award and automatically apply the points
        dev_tracker.award_points(amount)

        # Record transaction
        dev_transaction = DevelopmentTransaction.objects.create(
            character=character,
            trait=trait,
            source=source,
            amount=amount,
            reason=reason,
            description=description,
            scene=scene,
            gm=gm,
        )

        return dev_transaction


def get_development_suggestions_for_character(character):
    """
    Get development suggestions for a character based on their current traits.

    Args:
        character: Character to analyze

    Returns:
        Dict mapping development sources to suggested traits
    """
    from world.traits.models import Trait

    suggestions = {
        DevelopmentSource.COMBAT: [],
        DevelopmentSource.SOCIAL: [],
        DevelopmentSource.CRAFTING: [],
        DevelopmentSource.SCENE: [],
    }

    # Get character's current trait values
    trait_values = character.trait_values.all()
    trait_dict = {tv.trait.name: tv.value for tv in trait_values}

    # Get all developable traits
    all_traits = Trait.objects.filter(is_public=True)

    for trait in all_traits:
        current_value = trait_dict.get(trait.name, 0)
        if current_value >= 100:  # Already maxed
            continue

        # With simplified system, trait ratings auto-apply through development points
        # No need to check for rating unlocks anymore

        # Suggest based on trait category
        if trait.category in ["combat"]:
            suggestions[DevelopmentSource.COMBAT].append(trait.name)
        elif trait.category in ["social", "general"]:
            suggestions[DevelopmentSource.SOCIAL].append(trait.name)
        elif trait.category in ["crafting"]:
            suggestions[DevelopmentSource.CRAFTING].append(trait.name)
        else:
            suggestions[DevelopmentSource.SCENE].append(trait.name)

    return suggestions

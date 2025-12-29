"""
Spending services for the progression system.

This module handles spending XP on unlocks and checking requirements.
"""

from django.db import transaction

from world.progression.models import CharacterUnlock, ClassLevelUnlock, XPTransaction
from world.progression.services.awards import get_or_create_xp_tracker
from world.progression.types import ProgressionReason


def spend_xp_on_unlock(character, unlock_target, gm=None):
    """
    Spend XP to unlock something for a character.

    Args:
        character: Character gaining the unlock
        unlock_target: The unlock object (ClassLevelUnlock, TraitRatingUnlock, etc.)
        gm: GM making the purchase (if applicable)

    Returns:
        tuple: (success: bool, message: str, unlock: CharacterUnlock or None)
    """
    account = character.account

    # Check if already unlocked (only works for ClassLevelUnlock now)
    if isinstance(unlock_target, ClassLevelUnlock):
        if CharacterUnlock.objects.filter(
            character=character,
            character_class=unlock_target.character_class,
            target_level=unlock_target.target_level,
        ).exists():
            return False, "Already unlocked", None
    else:
        # For other unlock types, we'd need different logic
        # For now, assume trait ratings don't need unlock tracking
        pass

    # Check requirements linked to this unlock
    requirements_met, failed_requirements = check_requirements_for_unlock(
        character,
        unlock_target,
    )

    if not requirements_met:
        return False, f"Requirements not met: {'; '.join(failed_requirements)}", None

    # Calculate XP cost
    xp_cost = 0
    if hasattr(unlock_target, "get_xp_cost_for_character"):
        xp_cost = unlock_target.get_xp_cost_for_character(character)

    with transaction.atomic():
        # Spend the XP if there's a cost
        if xp_cost > 0:
            xp_tracker = get_or_create_xp_tracker(account)
            success = xp_tracker.spend_xp(xp_cost)

            if not success:
                return (
                    False,
                    f"Insufficient XP (need {xp_cost}, have {xp_tracker.current_available})",
                    None,
                )

            # Record XP transaction
            XPTransaction.objects.create(
                account=account,
                amount=-xp_cost,
                reason=ProgressionReason.XP_PURCHASE,
                description=f"Unlocked {unlock_target}",
                character=character,
                gm=gm,
            )

        # Create unlock record (only for ClassLevelUnlock now)
        if isinstance(unlock_target, ClassLevelUnlock):
            unlock = CharacterUnlock.objects.create(
                character=character,
                character_class=unlock_target.character_class,
                target_level=unlock_target.target_level,
                xp_spent=xp_cost,
            )
        else:
            # For trait ratings or other unlocks, we'd handle differently
            unlock = None

        return True, f"Successfully unlocked {unlock_target}", unlock


def check_requirements_for_unlock(character, unlock_target):
    """
    Check if a character meets all requirements for an unlock.

    Args:
        character: Character to check
        unlock_target: The unlock object to check requirements for

    Returns:
        tuple: (all_met: bool, failed_messages: list)
    """
    from world.progression.models import (
        AchievementRequirement,
        ClassLevelRequirement,
        LevelRequirement,
        MultiClassRequirement,
        RelationshipRequirement,
        TierRequirement,
        TraitRequirement,
    )

    failed_messages = []

    # Get all requirements that point to this unlock (only works for ClassLevelUnlock
    # now)
    if isinstance(unlock_target, ClassLevelUnlock):
        requirement_types = [
            TraitRequirement,
            LevelRequirement,
            ClassLevelRequirement,
            TierRequirement,
            AchievementRequirement,
            RelationshipRequirement,
            MultiClassRequirement,
        ]

        for req_type in requirement_types:
            requirements = req_type.objects.filter(
                class_level_unlock=unlock_target,
                is_active=True,
            )

            for requirement in requirements:
                is_met, message = requirement.is_met_by_character(character)
                if not is_met:
                    failed_messages.append(message)
    else:
        # For other unlock types, no requirements checking for now
        pass

    return len(failed_messages) == 0, failed_messages


def get_available_unlocks_for_character(character):
    """
    Get all unlocks that a character could potentially purchase.

    Args:
        character: Character to check

    Returns:
        dict: Dict with 'available', 'locked', and 'already_unlocked' lists
    """
    # Get character's current class level unlocks
    unlocked_class_levels = set()
    for unlock in CharacterUnlock.objects.filter(character=character):
        unlocked_class_levels.add((unlock.character_class.id, unlock.target_level))

    available = []
    locked = []
    already_unlocked = []

    # Check class level unlocks
    for class_unlock in ClassLevelUnlock.objects.all():
        unlock_key = (class_unlock.character_class.id, class_unlock.target_level)

        if unlock_key in unlocked_class_levels:
            already_unlocked.append(
                {
                    "unlock": class_unlock,
                    "type": "class_level",
                },
            )
            continue

        requirements_met, failed_requirements = check_requirements_for_unlock(
            character,
            class_unlock,
        )
        xp_cost = class_unlock.get_xp_cost_for_character(character)

        unlock_info = {
            "unlock": class_unlock,
            "type": "class_level",
            "xp_cost": xp_cost,
            "requirements_met": requirements_met,
            "failed_requirements": failed_requirements,
        }

        if requirements_met:
            available.append(unlock_info)
        else:
            locked.append(unlock_info)

    # Note: Trait rating unlocks are handled differently now
    # They auto-apply through development points, so no need to track here

    return {
        "available": available,
        "locked": locked,
        "already_unlocked": already_unlocked,
    }


def calculate_level_up_requirements(character, character_class, target_level):
    """
    Calculate what's required to level up a character in a specific class.

    Args:
        character: Character to check
        character_class: Class to level up in
        target_level: Desired level

    Returns:
        dict: Requirements breakdown
    """
    # Get current level in this class
    try:
        current_class_level = character.character_class_levels.get(
            character_class=character_class,
        )
        current_level = current_class_level.level
    except Exception:  # noqa: BLE001
        current_level = 0

    if target_level <= current_level:
        msg = f"Character is already level {current_level} in {character_class.name}"
        return {
            "error": msg,
        }

    # Get the unlock for this class/level combination
    try:
        class_unlock = ClassLevelUnlock.objects.get(
            character_class=character_class,
            target_level=target_level,
        )
    except ClassLevelUnlock.DoesNotExist:
        return {
            "error": f"No unlock found for {character_class.name} level {target_level}",
        }

    # Check requirements for this unlock
    requirements_met, failed_requirements = check_requirements_for_unlock(
        character,
        class_unlock,
    )
    xp_cost = class_unlock.get_xp_cost_for_character(character)

    return {
        "character_class": character_class.name,
        "current_level": current_level,
        "target_level": target_level,
        "xp_cost": xp_cost,
        "requirements_met": requirements_met,
        "failed_requirements": failed_requirements,
        "unlock": class_unlock,
    }

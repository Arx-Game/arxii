"""
Spending services for the progression system.

This module handles spending XP on unlocks and checking requirements.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from evennia.objects.models import ObjectDB

from world.character_sheets.models import CharacterSheet
from world.magic.services.alterations import enforce_advancement_gate
from world.progression.models import CharacterUnlock, ClassLevelUnlock, XPTransaction
from world.progression.services.awards import get_or_create_xp_tracker
from world.progression.types import (
    AvailableUnlocks,
    DetailedUnlockEntry,
    LevelUpRequirements,
    ProgressionReason,
    UnlockEntry,
)

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from world.classes.models import CharacterClass, Path
    from world.magic.models import ThreadCrossingThreshold


def spend_xp_on_unlock(
    character: ObjectDB,
    unlock_target: ClassLevelUnlock,
    gm: AccountDB | None = None,
) -> tuple[bool, str, CharacterUnlock | None]:
    """
    Spend XP to unlock something for a character.

    Args:
        character: Character gaining the unlock
        unlock_target: The unlock object (ClassLevelUnlock, TraitRatingUnlock, etc.)
        gm: GM making the purchase (if applicable)

    Returns:
        tuple: (success: bool, message: str, unlock: CharacterUnlock or None)

    Raises:
        AlterationGateError: If the character has unresolved Mage Scars.
    """
    try:
        sheet = character.sheet_data
    except (CharacterSheet.DoesNotExist, AttributeError):
        sheet = None
    if sheet is not None:
        enforce_advancement_gate(sheet)

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


def _check_requirements(
    character: ObjectDB,
    unlock_target: object,
    fk_name: str,
) -> tuple[bool, list[str]]:
    """Check if a character meets all active requirements pointing at a target.

    Shared loop used by both ``check_requirements_for_unlock`` (Durance path,
    FK ``class_level_unlock``) and ``check_requirements_for_thread_crossing``
    (thread crossing gate, FK ``thread_crossing_threshold``).

    Args:
        character: Character to check.
        unlock_target: The unlock/threshold object requirements point to.
        fk_name: The FK field name to filter on
            (``"class_level_unlock"`` or ``"thread_crossing_threshold"``).

    Returns:
        tuple: (all_met: bool, failed_messages: list)
    """
    from world.progression.models import (
        AchievementRequirement,
        ClassLevelRequirement,
        ItemRequirement,
        LegendRequirement,
        LevelRequirement,
        MajorGiftTechniqueRequirement,
        MultiClassRequirement,
        RelationshipRequirement,
        TierRequirement,
        TraitRequirement,
    )

    requirement_types = [
        TraitRequirement,
        LevelRequirement,
        ClassLevelRequirement,
        TierRequirement,
        AchievementRequirement,
        RelationshipRequirement,
        MultiClassRequirement,
        LegendRequirement,
        ItemRequirement,
        MajorGiftTechniqueRequirement,
    ]

    failed_messages: list[str] = []
    filter_kwargs = {fk_name: unlock_target, "is_active": True}

    for req_type in requirement_types:
        requirements = req_type.objects.filter(**filter_kwargs)
        for requirement in requirements:
            is_met, message = requirement.is_met_by_character(character)
            if not is_met:
                failed_messages.append(message)

    return len(failed_messages) == 0, failed_messages


def check_requirements_for_unlock(
    character: ObjectDB,
    unlock_target: ClassLevelUnlock,
) -> tuple[bool, list[str]]:
    """
    Check if a character meets all requirements for an unlock.

    Args:
        character: Character to check
        unlock_target: The unlock object to check requirements for

    Returns:
        tuple: (all_met: bool, failed_messages: list)
    """
    if isinstance(unlock_target, ClassLevelUnlock):
        return _check_requirements(character, unlock_target, "class_level_unlock")

    # For other unlock types, no requirements checking for now
    return True, []


def check_requirements_for_thread_crossing(
    character: ObjectDB,
    threshold: ThreadCrossingThreshold,
) -> tuple[bool, list[str]]:
    """Check if a character meets all requirements for a thread crossing.

    Mirrors ``check_requirements_for_unlock`` but filters on the
    ``thread_crossing_threshold`` FK. Returns ``(True, [])`` when no
    requirements are authored on the threshold (fail-open).

    Args:
        character: Character to check.
        threshold: The ``ThreadCrossingThreshold`` to check requirements for.

    Returns:
        tuple: (all_met: bool, failed_messages: list)
    """
    return _check_requirements(character, threshold, "thread_crossing_threshold")


def check_requirements_for_path(
    character: ObjectDB,
    path: Path,
) -> tuple[bool, list[str]]:
    """Check if a character meets all requirements for a path (#2538).

    Mirrors ``check_requirements_for_unlock`` and
    ``check_requirements_for_thread_crossing`` but filters on the ``path``
    FK. Returns ``(True, [])`` when no requirements are authored on the path
    (fail-open). Used by ``cross_into_path`` (hybrid path entry gate) and
    ``can_learn_technique`` (cross-path technique learning).

    Args:
        character: Character to check.
        path: The ``Path`` to check requirements for.

    Returns:
        tuple: (all_met: bool, failed_messages: list)
    """
    return _check_requirements(character, path, "path")


def get_available_unlocks_for_character(
    character: ObjectDB,
) -> AvailableUnlocks:
    """
    Get all unlocks that a character could potentially purchase.

    Args:
        character: Character to check

    Returns:
        AvailableUnlocks with 'available', 'locked', and 'already_unlocked' lists.
    """
    # Get character's current class level unlocks
    unlocked_class_levels = set()
    for unlock in CharacterUnlock.objects.filter(character=character):
        unlocked_class_levels.add((unlock.character_class.id, unlock.target_level))

    available: list[DetailedUnlockEntry] = []
    locked: list[DetailedUnlockEntry] = []
    already_unlocked: list[UnlockEntry] = []

    # Check class level unlocks
    for class_unlock in ClassLevelUnlock.objects.all():
        unlock_key = (class_unlock.character_class.id, class_unlock.target_level)

        if unlock_key in unlocked_class_levels:
            already_unlocked.append(
                UnlockEntry(
                    unlock=class_unlock,
                    type="class_level",
                ),
            )
            continue

        requirements_met, failed_requirements = check_requirements_for_unlock(
            character,
            class_unlock,
        )
        xp_cost = class_unlock.get_xp_cost_for_character(character)

        unlock_info = DetailedUnlockEntry(
            unlock=class_unlock,
            type="class_level",
            xp_cost=xp_cost,
            requirements_met=requirements_met,
            failed_requirements=failed_requirements,
        )

        if requirements_met:
            available.append(unlock_info)
        else:
            locked.append(unlock_info)

    # Note: Trait rating unlocks (skill XP-boundary breakthroughs, #2115) are handled
    # by world.skills.services.skills_at_boundary + purchase_skill_breakthrough — a
    # separate seam from this ClassLevelUnlock-only listing/purchase pair, since a
    # skill breakthrough's precondition ("parked at a boundary") isn't expressed as
    # an AbstractUnlockRequirement. ProgressionUnlockViewSet.list() calls
    # skills_at_boundary() directly to fold skill_breakthrough items into the same
    # paginated response.

    return AvailableUnlocks(
        available=available,
        locked=locked,
        already_unlocked=already_unlocked,
    )


def calculate_level_up_requirements(
    character: ObjectDB,
    character_class: CharacterClass,
    target_level: int,
) -> LevelUpRequirements | dict[str, str]:
    """
    Calculate what's required to level up a character in a specific class.

    Args:
        character: Character to check
        character_class: Class to level up in
        target_level: Desired level

    Returns:
        LevelUpRequirements on success, or ``{"error": str}`` on failure.
    """
    # Get current level in this class
    try:
        current_class_level = character.character_class_levels.get(
            character_class=character_class,
        )
        current_level = current_class_level.level
    except ObjectDoesNotExist:
        current_level = 0

    if target_level <= current_level:
        msg = f"Character is already level {current_level} in {character_class.name}"
        error: dict[str, str] = {"error": msg}
        return error

    # Get the unlock for this class/level combination
    try:
        class_unlock = ClassLevelUnlock.objects.get(
            character_class=character_class,
            target_level=target_level,
        )
    except ClassLevelUnlock.DoesNotExist:
        not_found: dict[str, str] = {
            "error": f"No unlock found for {character_class.name} level {target_level}",
        }
        return not_found

    # Check requirements for this unlock
    requirements_met, failed_requirements = check_requirements_for_unlock(
        character,
        class_unlock,
    )
    xp_cost = class_unlock.get_xp_cost_for_character(character)

    return LevelUpRequirements(
        character_class=character_class.name,
        current_level=current_level,
        target_level=target_level,
        xp_cost=xp_cost,
        requirements_met=requirements_met,
        failed_requirements=failed_requirements,
        unlock=class_unlock,
    )

"""
Award services for the progression system.

This module handles awarding XP and development points to characters and accounts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from django.db import transaction
from evennia.accounts.models import AccountDB
from evennia.objects.models import ObjectDB

from world.character_sheets.models import CharacterSheet
from world.progression.models import (
    DevelopmentPoints,
    DevelopmentTransaction,
    ExperiencePointsData,
    XPTransaction,
)
from world.progression.services.maturation import stat_cap_for
from world.progression.types import DevelopmentSource, ProgressionReason
from world.traits.constants import STAT_DISPLAY_DIVISOR
from world.traits.models import (
    CharacterTraitChange,
    CharacterTraitValue,
    Trait,
    TraitChangeSource,
    TraitType,
)

if TYPE_CHECKING:
    from world.roster.models import RosterTenure
    from world.scenes.models import Scene


def get_or_create_xp_tracker(account: AccountDB) -> ExperiencePointsData:
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
    account: AccountDB,
    amount: int,
    reason: str = ProgressionReason.SYSTEM_AWARD,
    description: str = "",
    gm: AccountDB | None = None,
) -> XPTransaction:
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


def _get_development_rate_modifier(character: ObjectDB, trait: Trait) -> int:  # noqa: ARG001
    """
    Get development rate modifier for a trait's category.

    TODO: Development rate modifier system not yet built. When the progression
    system tracks development rates, add a target FK on ModifierTarget for
    development-category entries and replace this stub with FK-based lookup.
    See TECH_DEBT.md.

    The mapping from trait categories to modifier names will be:
      PHYSICAL/COMBAT → physical_skill_development_rate
      SOCIAL/GENERAL → social_skill_development_rate
      MENTAL/CRAFTING → mental_skill_development_rate
    """
    return 0


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
    character_sheet: CharacterSheet,
    trait: Trait,
    source: str,
    amount: int,
    scene: Scene | None = None,
    reason: str = ProgressionReason.SCENE_AWARD,
    description: str = "",
    gm: AccountDB | None = None,
) -> DevelopmentTransaction:
    """
    Award development points to a character and automatically apply them.

    Development rate modifiers from distinctions are automatically applied.

    Args:
        character_sheet: Character sheet receiving points.
        trait: Trait to develop.
        source: Source category for the points.
        amount: Amount to award (before rate modifiers).
        scene: Scene where points were earned (if applicable).
        reason: Reason for the award.
        description: Detailed description.
        gm: GM making the award (if applicable).

    Returns:
        DevelopmentTransaction: The created transaction record.
    """
    if amount <= 0:
        msg = "Development point award amount must be positive"
        raise ValueError(msg)

    # Apply development rate modifiers
    rate_modifier = _get_development_rate_modifier(character_sheet.character, trait)
    modified_amount = _apply_rate_modifier(amount, rate_modifier)

    with transaction.atomic():
        dev_tracker, _created = DevelopmentPoints.objects.select_for_update().get_or_create(
            character_sheet=character_sheet,
            trait=trait,
            defaults={"total_earned": 0},
        )

        dev_tracker.award_points(modified_amount)

        return DevelopmentTransaction.objects.create(
            character_sheet=character_sheet,
            trait=trait,
            source=source,
            amount=modified_amount,
            reason=reason,
            description=description,
            scene=scene,
            gm=gm,
        )


@transaction.atomic
def award_stat_raise(
    sheet: CharacterSheet,
    trait: Trait,
    *,
    granting_tenure: RosterTenure | None,
) -> CharacterTraitChange:
    """Raise ``trait`` by exactly one display dot as a GM story reward (#3055 slice 1c).

    Mirrors ``spend_level_stat_point`` (``world.progression.services.stat_points``) --
    same cap enforcement (``stat_cap_for``, authored in display dots; storage is
    internal x10 via ``STAT_DISPLAY_DIVISOR``) and the same
    get_or_create-then-save-then-CharacterTraitChange shape -- but this is pure GM
    fiat: no ``LevelStatPointSpend`` row is created or consumed, and the provenance
    record carries ``source=GM_GRANT`` + the GM's own tenure (``granting_tenure``,
    ``None`` for a staff-piloted GM with no tenure -- the grant still succeeds).

    Raises:
        ValueError: ``trait`` is not a STAT, or the trait is already at the
            character's stage cap.
    """
    if trait.trait_type != TraitType.STAT:
        msg = "Only stat traits can be raised by a GM story reward."
        raise ValueError(msg)

    trait_value, _created = CharacterTraitValue.objects.get_or_create(
        character=sheet, trait=trait, defaults={"value": 0}
    )
    # Caps are authored in display dots; stat storage is internal x10 (#2894).
    cap = stat_cap_for(sheet)
    if cap is not None and trait_value.value >= cap * STAT_DISPLAY_DIVISOR:
        msg = f"{trait.name} is already at the maximum {sheet.character.key}'s stage allows."
        raise ValueError(msg)

    old_value = trait_value.value
    trait_value.value += STAT_DISPLAY_DIVISOR
    trait_value.save()
    return CharacterTraitChange.objects.create(
        character_sheet=sheet,
        trait=trait,
        old_value=old_value,
        new_value=trait_value.value,
        source=TraitChangeSource.GM_GRANT,
        granting_tenure=granting_tenure,
    )


def get_development_suggestions_for_character(character: ObjectDB) -> dict[str, list[str]]:
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
    from world.traits.models import CharacterTraitValue

    trait_values = CharacterTraitValue.objects.filter(character_id=character.pk)
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

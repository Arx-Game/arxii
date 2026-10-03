"""Language training tuning, XP locks and breakthroughs (#4090 amendment).

Trained fluency advances through weekly ``TrainLanguageAction`` sessions whose dp rates
staff tune on ``LanguageTrainingConfig``, and stops one rating below an authored
``TraitRatingUnlock`` until the character spends XP on the breakthrough, the same way
skills park at their XP boundaries (``world.skills.services``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from world.species.models import LanguageTrainingConfig
from world.species.types import LanguageBreakthroughProspect

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.species.models import Language


def get_language_training_config() -> LanguageTrainingConfig:
    """Lazily create and return the singleton LanguageTrainingConfig (pk=1)."""
    config = LanguageTrainingConfig.objects.cached_singleton()
    if config is None:
        config, _ = LanguageTrainingConfig.objects.get_or_create(pk=1)
    return config


def language_lock_rating(sheet: CharacterSheet, language: Language) -> int | None:
    """The authored XP-lock rating *sheet* is parked one below in *language*, else None."""
    if language.trait_id is None:
        return None
    from world.progression.models import TraitRatingUnlock  # noqa: PLC0415
    from world.traits.models import CharacterTraitValue  # noqa: PLC0415

    row = CharacterTraitValue.objects.filter(character=sheet, trait_id=language.trait_id).first()
    if row is None:
        return None
    next_rating = row.value + 1
    exists = TraitRatingUnlock.objects.filter(
        trait_id=language.trait_id, target_rating=next_rating
    ).exists()
    return next_rating if exists else None


def languages_at_lock(sheet: CharacterSheet) -> list[LanguageBreakthroughProspect]:
    """Every language *sheet* is parked at an XP lock in, with its breakthrough cost."""
    from world.progression.models import TraitRatingUnlock  # noqa: PLC0415
    from world.traits.models import CharacterTraitValue, TraitType  # noqa: PLC0415

    values = list(
        CharacterTraitValue.objects.filter(
            character=sheet,
            trait__trait_type=TraitType.LANGUAGE,
            trait__language__isnull=False,
        ).select_related("trait__language")
    )
    if not values:
        return []
    unlocks = {
        (unlock.trait_id, unlock.target_rating): unlock
        for unlock in TraitRatingUnlock.objects.filter(
            trait_id__in=[row.trait_id for row in values],
            target_rating__in=[row.value + 1 for row in values],
        )
    }
    prospects: list[LanguageBreakthroughProspect] = []
    for row in values:
        unlock = unlocks.get((row.trait_id, row.value + 1))
        if unlock is None:
            continue
        prospects.append(
            LanguageBreakthroughProspect(
                language=row.trait.language,
                next_rating=unlock.target_rating,
                xp_cost=unlock.get_xp_cost_for_character(sheet.character),
            )
        )
    return prospects


def purchase_language_breakthrough(sheet: CharacterSheet, language: Language) -> tuple[bool, str]:
    """Spend XP to clear the XP lock *sheet* is parked at in *language* (#4090).

    Mirrors ``world.skills.services.purchase_skill_breakthrough``: XP buys the unlock,
    the value rises to the lock's rating, and training resumes from zero toward the next
    rating (the dp tracker is raised to that rating's cumulative floor).
    """
    from world.progression.exceptions import (  # noqa: PLC0415
        InsufficientXPError,
        NoAccountForCharacterError,
    )
    from world.progression.models import TraitRatingUnlock  # noqa: PLC0415
    from world.progression.models.rewards import (  # noqa: PLC0415
        DevelopmentPoints,
        cumulative_dp_for_level,
    )
    from world.progression.services.xp_ledger import spend_xp_for_character  # noqa: PLC0415
    from world.traits.models import (  # noqa: PLC0415
        CharacterTraitChange,
        CharacterTraitValue,
        TraitChangeSource,
    )

    not_parked = (False, f"Your {language.name} is not waiting at a breakthrough.")
    if language.trait_id is None:
        return not_parked
    trait_value = CharacterTraitValue.objects.filter(
        character=sheet, trait_id=language.trait_id
    ).first()
    if trait_value is None:
        return not_parked
    unlock = TraitRatingUnlock.objects.filter(
        trait_id=language.trait_id, target_rating=trait_value.value + 1
    ).first()
    if unlock is None:
        return not_parked

    xp_cost = unlock.get_xp_cost_for_character(sheet.character)
    with transaction.atomic():
        # Re-read under lock: another purchase (or training) may have moved the value
        # between the read above and this transaction, so re-check the lock still
        # holds before spending XP (double-spend guard). Write through the locked
        # instance so the identity map isn't left holding the stale, unlocked one.
        trait_value = CharacterTraitValue.objects.select_for_update().get(pk=trait_value.pk)
        if trait_value.value + 1 != unlock.target_rating:
            return not_parked

        try:
            spend_xp_for_character(
                sheet, xp_cost, f"Breakthrough: {language.name} to {unlock.target_rating}"
            )
        except InsufficientXPError as exc:
            return False, f"Insufficient XP (need {exc.required}, have {exc.available})."
        except NoAccountForCharacterError as exc:
            return False, exc.user_message

        old_value = trait_value.value
        trait_value.value = unlock.target_rating
        trait_value.save(update_fields=["value"])
        CharacterTraitChange.objects.create(
            character_sheet=sheet,
            trait_id=language.trait_id,
            old_value=old_value,
            new_value=unlock.target_rating,
            source=TraitChangeSource.XP_BREAKTHROUGH,
        )
        tracker, _created = DevelopmentPoints.objects.get_or_create(
            character_sheet=sheet, trait_id=language.trait_id
        )
        floor = cumulative_dp_for_level(unlock.target_rating)
        if tracker.total_earned < floor:
            tracker.total_earned = floor
            tracker.save(update_fields=["total_earned"])

    return (
        True,
        f"Breakthrough! Your {language.name} rises to {unlock.target_rating}; study resumes.",
    )

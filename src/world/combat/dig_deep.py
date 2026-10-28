"""Digging deep (#4738, slice 2 of #4727): a player character raises her own intensity.

In combat a player character may dig deep: she rolls the checks staff set on the
``DUG_DEEP`` ``SurgeTuning`` and her combat engagement's intensity rises by the band her
outcome picks. It is an immediate act, not the round's declared action, and she may do it
once a round. It costs fatigue from the pool ``StrainConfig`` names, unless she holds a free
dig deep (an ally's successful Rally grants them), which is spent instead. A failed roll still
costs what it cost.

Player characters roll; a non-player opponent never digs deep.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from world.combat.constants import ParticipantStatus, SurgeTriggerKind
from world.combat.models import CombatEncounter
from world.combat.services.encounter.config import get_strain_config
from world.combat.surge_rolls import (
    apply_rolled_surge,
    persona_name_of,
    rolled_surge_possible,
    surge_roll_for_participant,
    surge_tuning_for,
)
from world.combat.types import DigDeepResult
from world.fatigue.constants import EffortLevel
from world.fatigue.services import apply_fatigue, get_or_create_fatigue_pool
from world.mechanics.constants import EngagementType
from world.mechanics.engagement import CharacterEngagement
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.combat.models import CombatParticipant

NOT_IN_A_FIGHT_MESSAGE = "You are not in a fight you can dig deep in."
ALREADY_DUG_DEEP_MESSAGE = "You have already dug deep this round."
NO_DIG_DEEP_TUNING_MESSAGE = "There is nothing to dig deep with yet."
NO_PRESSURE_MESSAGE = "Nothing in this fight is pressing you to dig deep."


class DigDeepRefusedError(Exception):
    """A dig deep the rules refuse; ``user_message`` is safe to show the player."""

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


def combat_engagement_of(participant: CombatParticipant) -> CharacterEngagement | None:
    """The participant's COMBAT engagement sourced to her encounter, or None."""
    return CharacterEngagement.objects.filter(
        character=participant.character_sheet,
        engagement_type=EngagementType.COMBAT,
        source_content_type=ContentType.objects.get_for_model(CombatEncounter),
        source_id=participant.encounter_id,
    ).first()


def grant_free_dig_deeps(
    engagement: CharacterEngagement, count: int, giver: CharacterSheet
) -> None:
    """Add ``count`` free dig deeps credited to ``giver`` (identity-mapped row, saved narrowly)."""
    if count <= 0:
        return
    engagement.free_dig_deeps += count
    engagement.free_dig_deeps_given_by = giver
    engagement.save(update_fields=["free_dig_deeps", "free_dig_deeps_given_by"])


def _spend_free_dig_deep(engagement: CharacterEngagement) -> bool:
    """Spend one free dig deep if the engagement holds one; True when it did."""
    if engagement.free_dig_deeps <= 0:
        return False
    engagement.free_dig_deeps -= 1
    fields = ["free_dig_deeps"]
    if engagement.free_dig_deeps == 0:
        engagement.free_dig_deeps_given_by = None
        fields.append("free_dig_deeps_given_by")
    engagement.save(update_fields=fields)
    return True


def _lock_and_mark_round(engagement: CharacterEngagement, round_number: int) -> None:
    """Lock the engagement row, refuse a second dig deep this round, and mark this one.

    Read as values, never an instance: the identity map would hand back the cached row
    as it was, and a dig deep another request just took would be missed.
    """
    marker, free_dig_deeps = (
        CharacterEngagement.objects.select_for_update()
        .filter(pk=engagement.pk)
        .values_list("last_dug_deep_round", "free_dig_deeps")
        .get()
    )
    if marker == round_number:
        raise DigDeepRefusedError(ALREADY_DUG_DEEP_MESSAGE)
    engagement.free_dig_deeps = free_dig_deeps
    engagement.last_dug_deep_round = round_number
    engagement.save(update_fields=["last_dug_deep_round"])


def dig_deep(participant: CombatParticipant) -> DigDeepResult:
    """Dig deep for ``participant``: pay, roll resolve, surge her intensity by the outcome's band.

    Refuses (``DigDeepRefusedError``) when she is not an active participant in a declaring
    round with a COMBAT engagement, when the fight has no escalation curve to surge on,
    when she already dug deep this round, or when staff have not set the ``DUG_DEEP``
    tuning. Nothing is spent on a refusal. Otherwise, in one transaction: a free dig deep is
    spent if she holds one, else the configured fatigue is charged (whatever the roll
    gives); the tuning's check is rolled against its ``potency_base``; and the outcome's
    band is written through ``apply_rolled_surge``.
    """
    encounter = participant.encounter
    if participant.status != ParticipantStatus.ACTIVE or encounter.status != RoundStatus.DECLARING:
        raise DigDeepRefusedError(NOT_IN_A_FIGHT_MESSAGE)
    engagement = combat_engagement_of(participant)
    if engagement is None:
        raise DigDeepRefusedError(NOT_IN_A_FIGHT_MESSAGE)
    if encounter.escalation_curve is None:
        raise DigDeepRefusedError(NO_PRESSURE_MESSAGE)
    tuning = surge_tuning_for(SurgeTriggerKind.DUG_DEEP)
    if tuning is None:
        raise DigDeepRefusedError(NO_DIG_DEEP_TUNING_MESSAGE)
    # An early, friendly refusal; the locked re-check inside the transaction is the gate.
    if engagement.last_dug_deep_round == encounter.round_number or not rolled_surge_possible(
        encounter, participant, SurgeTriggerKind.DUG_DEEP, None
    ):
        raise DigDeepRefusedError(ALREADY_DUG_DEEP_MESSAGE)

    config = get_strain_config()
    pool = get_or_create_fatigue_pool(participant.character_sheet)
    held_pool = pool.get_current(config.dig_deep_fatigue_category)
    held = (
        engagement.free_dig_deeps,
        engagement.free_dig_deeps_given_by,
        engagement.last_dug_deep_round,
        engagement.intensity_modifier,
        engagement.control_modifier,
    )
    committed = False
    try:
        with transaction.atomic():
            _lock_and_mark_round(engagement, encounter.round_number)
            used_free = _spend_free_dig_deep(engagement)
            fatigue_spent = 0
            if not used_free:
                fatigue_spent = apply_fatigue(
                    participant.character_sheet,
                    config.dig_deep_fatigue_category,
                    config.dig_deep_fatigue_cost,
                    EffortLevel.MEDIUM,
                )
            result = surge_roll_for_participant(participant, tuning.check_type, tuning.potency_base)
            beat = apply_rolled_surge(
                encounter=encounter,
                participant=participant,
                trigger_kind=SurgeTriggerKind.DUG_DEEP,
                outcome=result.outcome,
                potency=tuning.potency_base,
                source_character=participant.character_sheet.character,
                tuning=tuning,
                cause=f"{persona_name_of(participant)} digs deep.",
            )
        committed = True
    finally:
        if not committed:
            # The database rolled back; the identity-mapped engagement and fatigue pool
            # must say the same. (An outer transaction that rolls back later is not
            # covered; the dig deep itself commits with the request.)
            (
                engagement.free_dig_deeps,
                engagement.free_dig_deeps_given_by,
                engagement.last_dug_deep_round,
                engagement.intensity_modifier,
                engagement.control_modifier,
            ) = held
            pool.set_current(config.dig_deep_fatigue_category, held_pool)
    return DigDeepResult(
        outcome=result.outcome,
        surge_amount=beat.amount if beat is not None else 0,
        used_free_dig_deep=used_free,
        fatigue_spent=fatigue_spent,
        fatigue_category=config.dig_deep_fatigue_category,
    )

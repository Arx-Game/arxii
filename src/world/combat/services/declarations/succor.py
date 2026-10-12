"""Declaring and dispatching succor."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.constants import CombatManeuver, ParticipantStatus
from world.combat.models import CombatParticipant, CombatRoundAction
from world.fatigue.constants import EffortLevel
from world.mechanics.types import ChallengeResolutionResult
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


def declare_succor(
    participant: CombatParticipant,
    ally: CombatParticipant,
) -> CombatRoundAction:
    """Declare a sheltering maneuver for a specific ally — passives-only, auto-ready.

    Unlike Interpose (which can guard "any ally" against whichever attack lands),
    Succor always names a specific ally: environmental shelter is "I'm sheltering
    THIS person," not "I'll block whichever hazard lands on someone." Resolution
    happens later, at round-tick DoT application (#1744).
    """
    from world.vitals.services import is_dead  # noqa: PLC0415

    encounter = participant.encounter
    if encounter.status != RoundStatus.DECLARING:
        msg = (
            f"Cannot succor: encounter status is "
            f"'{encounter.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)
    if participant.status != ParticipantStatus.ACTIVE:
        msg = "Cannot succor: participant is no longer active in this encounter."
        raise ValueError(msg)
    if is_dead(participant.character_sheet):
        msg = "Cannot succor: character is dead."
        raise ValueError(msg)
    if ally.pk == participant.pk:
        msg = "Cannot succor yourself."
        raise ValueError(msg)
    if ally.encounter_id != encounter.pk or ally.status != ParticipantStatus.ACTIVE:
        msg = "Succor target must be an active participant in this encounter."
        raise ValueError(msg)

    action, _ = CombatRoundAction.objects.update_or_create(
        participant=participant,
        round_number=encounter.round_number,
        defaults={
            "focused_action": None,
            "focused_category": None,
            "effort_level": EffortLevel.VERY_LOW,
            "focused_opponent_target": None,
            "focused_ally_target": ally,
            "maneuver": CombatManeuver.SUCCOR,
            "physical_passive": None,
            "social_passive": None,
            "mental_passive": None,
            "combo_upgrade": None,
            "is_ready": True,
            "succor_resolution": None,
        },
    )
    return action


def dispatch_succor(
    succorer: ObjectDB,  # noqa: OBJECTDB_PARAM
    protected: ObjectDB,  # noqa: OBJECTDB_PARAM
    *,
    approach: str | None,
    extra_modifiers: int = 0,
) -> float:
    """Resolve *succorer*'s Succor attempt against *protected* and return the multiplier.

    Thin wrapper over dispatch_capability_reaction, mirroring dispatch_interpose.
    Returns 1.0 (no cover) when no active Succor challenge is bound to *protected*.
    """
    from world.combat.succor_content import SUCCOR_CHALLENGE_NAME  # noqa: PLC0415
    from world.mechanics.reactions import dispatch_capability_reaction  # noqa: PLC0415
    from world.mechanics.succor_shared import apply_succor_outcome  # noqa: PLC0415

    outcome = {"multiplier": 1.0}

    def _capture(result: ChallengeResolutionResult) -> None:
        outcome["multiplier"] = apply_succor_outcome(result)

    result = dispatch_capability_reaction(
        succorer,
        protected,
        challenge_name=SUCCOR_CHALLENGE_NAME,
        approach=approach,
        error_msg=(
            f"No succor approach is available to {succorer!r} for protected target {protected!r}."
        ),
        outcome_fn=_capture,
        extra_modifiers=extra_modifiers,
    )
    if result is None:
        return 1.0
    return outcome["multiplier"]

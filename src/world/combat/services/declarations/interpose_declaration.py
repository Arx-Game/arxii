"""Declaring an interpose."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.constants import CombatManeuver, ParticipantStatus
from world.combat.models import CombatOpponent, CombatParticipant, CombatRoundAction
from world.combat.services.declarations.redirect import _validate_redirect_declaration
from world.fatigue.constants import EffortLevel
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.magic.models import Technique


def declare_interpose(  # noqa: PLR0913 - interpose declaration requires all redirect/consent fields
    participant: CombatParticipant,
    ally: CombatParticipant | None = None,
    technique: Technique | None = None,
    redirect_opponent_target: CombatOpponent | None = None,
    redirect_object_target: ObjectDB | None = None,  # noqa: OBJECTDB_PARAM
    *,
    confirm_soulfray_risk: bool = False,
) -> CombatRoundAction:
    """Declare an interposing maneuver — passives-only, auto-ready.

    ``ally=None`` means the participant will guard any ally hit this round;
    when a specific ally is given they must be active and in the same encounter.

    ``technique=None`` (default) declares a plain interpose exactly as before
    #2207 — passives only, ``focused_action`` zeroed. Supplying a *technique*
    carries a protective reactive-trigger technique into the declaration: the
    participant must know it (``CharacterTechnique``) and it must classify to a
    protective flavor via ``protective_flavor`` (barrier/blink/redirect,
    `world/magic/services/targeting.py`).

    ``redirect_opponent_target``/``redirect_object_target`` (#2210) declare the
    destination for saved damage when the guardian's technique resolves as a
    REDIRECT flavor (Mirror Ward-style reflection) — declaration-time choice
    per ADR-0032. Mutually exclusive; both ``None`` means "away," the universal
    fallback destination. ``redirect_opponent_target`` must be an active
    (not-defeated) opponent in this same encounter. ``redirect_object_target``
    must be an ObjectDB located in the encounter's room AND "volatile" — it
    carries an ``ObjectProperty`` whose ``Property`` has a ``PropertyDetonation``
    row (see ``world.mechanics.services.volatile_object_property``). These
    kwargs are accepted regardless of the declared technique's flavor (harmless
    no-ops for non-REDIRECT declarations); resolution
    (``_try_technique_interpose``) only reads them on the REDIRECT branch.

    ``confirm_soulfray_risk`` (#3573) records the guardian's consent to keep the
    reaction firing past zero anima at the cost of Soulfray; read by
    ``_try_technique_interpose``.
    """
    from world.magic.models import CharacterTechnique  # noqa: PLC0415
    from world.magic.services.targeting import protective_flavor  # noqa: PLC0415
    from world.vitals.services import is_dead  # noqa: PLC0415

    encounter = participant.encounter
    if encounter.status != RoundStatus.DECLARING:
        msg = (
            f"Cannot interpose: encounter status is "
            f"'{encounter.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)

    if participant.status != ParticipantStatus.ACTIVE:
        msg = "Cannot interpose: participant is no longer active in this encounter."
        raise ValueError(msg)

    if is_dead(participant.character_sheet):
        msg = "Cannot interpose: character is dead."
        raise ValueError(msg)

    if ally is not None:
        if ally.pk == participant.pk:
            msg = "Cannot interpose yourself."
            raise ValueError(msg)
        if ally.encounter_id != encounter.pk or ally.status != ParticipantStatus.ACTIVE:
            msg = "Interpose target must be an active participant in this encounter."
            raise ValueError(msg)

    if technique is not None:
        knows_technique = CharacterTechnique.objects.filter(
            character=participant.character_sheet,
            technique=technique,
        ).exists()
        if not knows_technique:
            msg = "Cannot interpose: character does not know that technique."
            raise ValueError(msg)
        flavor = protective_flavor(technique)
        if flavor is None:
            msg = "Cannot interpose: that technique cannot guard yet."
            raise ValueError(msg)

    _validate_redirect_declaration(encounter, redirect_opponent_target, redirect_object_target)

    action, _ = CombatRoundAction.objects.update_or_create(
        participant=participant,
        round_number=encounter.round_number,
        defaults={
            "focused_action": technique,
            "focused_category": None,
            "effort_level": EffortLevel.VERY_LOW,
            "focused_opponent_target": None,
            "focused_ally_target": ally,
            "maneuver": CombatManeuver.INTERPOSE,
            "physical_passive": None,
            "social_passive": None,
            "mental_passive": None,
            "combo_upgrade": None,
            "is_ready": True,
            "redirect_opponent_target": redirect_opponent_target,
            "redirect_object_target": redirect_object_target,
            "confirm_soulfray_risk": confirm_soulfray_risk,
        },
    )
    return action

"""The declare_action entry point."""

from __future__ import annotations

from typing import TYPE_CHECKING

from actions.errors import ActionDispatchError
from world.combat.constants import EncounterType, OpponentStatus
from world.combat.models import (
    CombatOpponent,
    CombatParticipant,
    CombatRoundAction,
    EncounterRiskAcknowledgement,
)
from world.combat.services.declarations.declaration_validation import (
    DeclarationRefusedError,
    _validate_no_pending_sustained,
    _validate_passive_slot,
    _validate_strain_commitment,
    _validate_target_kind_alignment,
    _validate_technique_reach,
)
from world.combat.services.declarations.sustained_declaration import (
    _sync_sustained_technique_declaration,
)
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from world.areas.positioning.models import Position
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import FuryTier, Technique


def declare_action(  # noqa: PLR0913 - action declaration requires all slot fields
    participant: CombatParticipant,
    *,
    focused_action: Technique | None = None,
    focused_category: str | None = None,
    effort_level: str,
    focused_opponent_target: CombatOpponent | None = None,
    focused_ally_target: CombatParticipant | None = None,
    physical_passive: Technique | None = None,
    social_passive: Technique | None = None,
    mental_passive: Technique | None = None,
    confirm_soulfray_risk: bool = False,
    strain_commitment: int = 0,
    fury_commitment: FuryTier | None = None,
    fury_anchor: CharacterSheet | None = None,
    cast_destination: Position | None = None,
    cast_position_a: Position | None = None,
    cast_position_b: Position | None = None,
) -> CombatRoundAction:
    """Declare a PC's action for the current round.

    Validations:
    - Participant must be able to act (not dead and not incapacitated) — see can_act.
      A dying-but-conscious character keeps awareness and passes naturally.
    - Encounter must be in DECLARING status.
    - Round number must match encounter's current round.
    - The passive slot matching the focused_category must be None.
    - focused_opponent_target and focused_ally_target are mutually exclusive.
    - focused_action's condition_applications target_kinds must match the supplied target.
    - A pure-damage technique (base_power, no condition rows) requires focused_opponent_target.

    ``cast_destination``/``cast_position_a``/``cast_position_b`` are pre-validated
    (see ``resolve_cast_position_params``, #2206) — this function only persists them.

    Raises ValueError with clear messages for validation failures.
    """

    from world.vitals.services import can_act  # noqa: PLC0415

    encounter = participant.encounter

    # The focused technique's authored category is authoritative (#614): it drives
    # which passive slot must stay empty. Override any client-supplied value.
    if focused_action is not None:
        focused_category = focused_action.action_category

    # Agency check — not dead and not incapacitated. A dying-but-conscious
    # character keeps awareness and passes naturally (no dying_final_round concept).
    if not can_act(participant.character_sheet):
        msg = "Cannot declare action: character is dead or incapacitated."
        raise DeclarationRefusedError(msg, code=ActionDispatchError.CANNOT_ACT)

    _validate_strain_commitment(participant, strain_commitment)

    # Encounter status check
    if encounter.status != RoundStatus.DECLARING:
        msg = (
            f"Cannot declare action: encounter status is "
            f"'{encounter.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)

    # Lethal-duel risk-acknowledgement gate (#568 Task 12b). A PC placed into a
    # lethal DUEL by create_lethal_duel is deliberately not auto-acknowledged, and
    # the #777 outsider gate does not cover an already-active participant — so block
    # declaration until an EncounterRiskAcknowledgement exists. Scoped to DUEL only:
    # lethal party-combat PCs self-join via join_encounter (which records an ack),
    # and GM-placed party-combat PCs (add_participant, no ack) must not be blocked.
    if encounter.encounter_type == EncounterType.DUEL and encounter.is_lethal:
        has_ack = EncounterRiskAcknowledgement.objects.filter(
            encounter=encounter,
            character_sheet=participant.character_sheet,
        ).exists()
        if not has_ack:
            msg = "You must acknowledge the lethal risk of this duel before acting."
            raise DeclarationRefusedError(msg, code=ActionDispatchError.LETHAL_RISK_UNACKNOWLEDGED)

    # Sustaining occupies your action (#2705, D2) — see _validate_no_pending_sustained.
    _validate_no_pending_sustained(participant, encounter)

    # Passive slot validation (only when a focused category is declared)
    _validate_passive_slot(
        focused_category,
        physical_passive=physical_passive,
        social_passive=social_passive,
        mental_passive=mental_passive,
    )

    if focused_opponent_target and focused_opponent_target.status != OpponentStatus.ACTIVE:
        msg = "Cannot target a defeated opponent."
        raise DeclarationRefusedError(msg, code=ActionDispatchError.TARGET_DEFEATED)

    # XOR target validation
    if focused_opponent_target and focused_ally_target:
        msg = "Action cannot target both an opponent and an ally."
        raise DeclarationRefusedError(msg, code=ActionDispatchError.TARGET_CONFLICT)

    # Target-kind alignment with technique authoring
    if focused_action is not None:
        _validate_target_kind_alignment(
            participant,
            focused_action,
            focused_ally_target,
            focused_opponent_target,
        )

    # Positional reach gate: enforce technique.reach against the declared target.
    # Only fires when there is a technique and a resolved target. Lenient when
    # either combatant is unpositioned (technique_can_reach returns True).
    if focused_action is not None:
        _validate_technique_reach(
            participant,
            focused_action,
            focused_opponent_target=focused_opponent_target,
            focused_ally_target=focused_ally_target,
        )

    action, _created = CombatRoundAction.objects.update_or_create(
        participant=participant,
        round_number=encounter.round_number,
        defaults={
            "focused_action": focused_action,
            "focused_category": focused_category,
            "effort_level": effort_level,
            "focused_opponent_target": focused_opponent_target,
            "focused_ally_target": focused_ally_target,
            "physical_passive": physical_passive,
            "social_passive": social_passive,
            "mental_passive": mental_passive,
            "maneuver": None,  # Reset maneuver on re-declaration
            "combo_upgrade": None,  # Reset combo on re-declaration
            "is_ready": False,  # Reset ready on re-declaration
            "confirm_soulfray_risk": confirm_soulfray_risk,
            "strain_commitment": strain_commitment,
            "fury_commitment": fury_commitment,
            "fury_anchor": fury_anchor,
            "cast_destination": cast_destination,
            "cast_position_a": cast_position_a,
            "cast_position_b": cast_position_b,
        },
    )

    _sync_sustained_technique_declaration(participant, action, focused_action)

    return action

"""Declaring a clash contribution."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from world.combat.models import Clash, ClashContributionDeclaration, CombatParticipant

if TYPE_CHECKING:
    from world.magic.models import Technique


# ---------------------------------------------------------------------------
# Player-facing clash contribution declaration (Task 7.1a)
# ---------------------------------------------------------------------------


@transaction.atomic
def declare_clash_contribution(
    *,
    participant: CombatParticipant,
    clash: Clash,
    action_slot: str,
    technique: Technique,
    strain_commitment: int,
) -> ClashContributionDeclaration:
    """Write (or overwrite) a PC's clash contribution declaration for the current round.

    Performs the atomic write.  All user-input validation lives in
    ``DeclareClashContributionSerializer`` — this function trusts its inputs and
    performs only defensive programmer-error assertions.

    The declaration is keyed on ``(encounter, round_number, participant, clash)``.
    Calling a second time in the same round replaces the prior declaration
    (idempotent re-declaration).

    Args:
        participant: The PC participant making the contribution.
        clash: The active ``Clash`` the contribution targets.
        action_slot: ``ClashActionSlot`` value (FOCUSED or PASSIVE).
        technique: The ``Technique`` the PC commits to the clash.
        strain_commitment: Extra anima committed on top of the technique cost floor.

    Returns:
        The created-or-updated ``ClashContributionDeclaration`` instance.

    Raises:
        ValueError: If ``clash.encounter`` does not match ``participant.encounter``
            (programmer error — the serializer enforces this for user input).
    """
    round_number = participant.encounter.round_number

    # Defensive assertion: catches programmer errors where the wrong clash or
    # participant is passed (the serializer already validates this for user input).
    if clash.encounter_id != participant.encounter_id:
        msg = (
            f"declare_clash_contribution: clash.encounter_id ({clash.encounter_id}) "
            f"does not match participant.encounter_id ({participant.encounter_id}). "
            "This is a programmer error — pass clashes and participants from the same encounter."
        )
        raise ValueError(msg)

    declaration, _ = ClashContributionDeclaration.objects.update_or_create(
        encounter=participant.encounter,
        round_number=round_number,
        participant=participant,
        clash=clash,
        defaults={
            "action_slot": action_slot,
            "technique": technique,
            "strain_commitment": strain_commitment,
        },
    )
    return declaration

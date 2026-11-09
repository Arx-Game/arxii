"""Calling up a gift's substance with no technique (#5018).

A shadow caster lets the room dim around her as a small touch of play: no roll, no power,
only the room reading (for everyone, while she stays) and an unattributed room line. It is
priced by her own control alone, so outside a fight it is usually free.

In a fight it is an immediate act, once a round, never the round's declared action: the
shape of Dig deep (``DigDeepAction``), with its own once-a-round marker
(``CharacterEngagement.last_called_up_round``). REGISTRY actions are never round-declared.

Never refused, greyed out or hidden for lack of anima (owner ruling, #5023): a call-up past
her anima goes through ``deduct_anima`` and the soulfray path. When she already carries
soulfray and the move costs anima, the first press shows the existing soulfray warning and
asks for confirmation (``confirm_soulfray_risk``), as a cast does.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.db import transaction

from actions.base import Action
from actions.kwarg_parsing import truthy_kwarg
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext
    from world.combat.models import CombatParticipant
    from world.magic.types.substance import CallUpOffer

NO_GIFT_MESSAGE = "You hold no gift whose substance you can call up."
WHICH_GIFT_MESSAGE = "Which gift's substance? Name it (for example: callup shadow)."
ALREADY_THIS_ROUND_MESSAGE = "You have already called up your gift this round."
NOT_DECLARING_MESSAGE = "Wait for the next round to open before calling up your gift."


def _sheet(actor: ObjectDB):  # noqa: OBJECTDB_PARAM - the acting character
    from world.magic.services.techniques import _get_character_sheet  # noqa: PLC0415

    return _get_character_sheet(actor)


def fight_participant(actor: ObjectDB) -> CombatParticipant | None:  # noqa: OBJECTDB_PARAM
    """Her ACTIVE participant in a fight that has not finished, newest first, or None."""
    from world.combat.constants import ParticipantStatus  # noqa: PLC0415
    from world.combat.models import CombatParticipant  # noqa: PLC0415
    from world.scenes.constants import RoundStatus  # noqa: PLC0415

    sheet = _sheet(actor)
    if sheet is None:
        return None
    return (
        CombatParticipant.objects.filter(
            character_sheet=sheet,
            status=ParticipantStatus.ACTIVE,
        )
        .exclude(encounter__status=RoundStatus.COMPLETED)
        .select_related("encounter")
        .order_by("-encounter__created_at")
        .first()
    )


def _pick_offer(
    offers: list[CallUpOffer], gift_id: int | None, substance: str
) -> CallUpOffer | None:
    if gift_id is not None:
        return next((o for o in offers if o.gift_id == int(gift_id)), None)
    if substance:
        wanted = substance.strip().lower()
        return next((o for o in offers if o.plan.label.lower() == wanted), None)
    return offers[0] if len(offers) == 1 else None


def _mark_round(participant: CombatParticipant) -> str | None:
    """Lock her engagement and take this round's call-up; a refusal message if spent."""
    from world.combat.dig_deep import combat_engagement_of  # noqa: PLC0415
    from world.mechanics.engagement import CharacterEngagement  # noqa: PLC0415

    engagement = combat_engagement_of(participant)
    if engagement is None:
        return None
    round_number = participant.encounter.round_number
    # Read as a value under lock, never the identity-mapped instance (the dig deep rule).
    marker = (
        CharacterEngagement.objects.select_for_update()
        .filter(pk=engagement.pk)
        .values_list("last_called_up_round", flat=True)
        .get()
    )
    if marker == round_number:
        return ALREADY_THIS_ROUND_MESSAGE
    engagement.last_called_up_round = round_number
    engagement.save(update_fields=["last_called_up_round"])
    return None


def _charge_and_apply(
    actor: ObjectDB,  # noqa: OBJECTDB_PARAM - the acting character
    offer: CallUpOffer,
    participant: CombatParticipant | None,
    *,
    lethal: bool,
) -> ActionResult:
    """Take this round's call-up (in a fight), charge it, and write it. One transaction."""
    from world.magic.models import CharacterAnima, SoulfrayConfig  # noqa: PLC0415
    from world.magic.services.anima import deduct_anima  # noqa: PLC0415
    from world.magic.services.soulfray import accumulate_soulfray  # noqa: PLC0415
    from world.magic.services.substance import apply_substance_plan  # noqa: PLC0415

    sheet = _sheet(actor)
    with transaction.atomic():
        if participant is not None:
            refusal = _mark_round(participant)
            if refusal is not None:
                return ActionResult(success=False, message=refusal)
        deficit = deduct_anima(actor, offer.effective_cost, lethal=lethal)
        anima = CharacterAnima.objects.filter(character_id=actor.pk).first()
        if anima is not None and offer.effective_cost > 0:
            accumulate_soulfray(
                character=actor,
                anima=anima,
                deficit=deficit,
                soulfray_config=SoulfrayConfig.objects.cached_singleton(),
                check_result=None,
                lethal=lethal,
            )
        done = apply_substance_plan(offer.plan, sheet=sheet)
    resonance = done.resonance if done is not None else 0
    if offer.effective_cost == 0 and resonance == 0:
        cost_text = "free"
    else:
        cost_text = f"{offer.effective_cost} anima"
        if resonance and done is not None:
            cost_text += f", {resonance} {done.resonance_name} resonance"
    return ActionResult(
        success=True,
        message=f"You call up {offer.plan.label}. Cost: {cost_text}.",
        data={"cost": offer.effective_cost, "resonance": resonance, "gift_id": offer.gift_id},
    )


@dataclass
class CallUpSubstanceAction(Action):
    """Call up her gift's substance with no technique: the room dims around her (#5018)."""

    key: str = "call_up_substance"
    name: str = "Call up your gift"
    icon: str = "sparkles"
    category: str = "magic"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        gift_id: int | None = None,
        substance: str = "",
        confirm_soulfray_risk: object = False,
        **kwargs: Any,
    ) -> ActionResult:
        from world.magic.services.soulfray import get_soulfray_warning  # noqa: PLC0415
        from world.magic.services.substance import call_up_offers  # noqa: PLC0415
        from world.scenes.constants import RoundStatus  # noqa: PLC0415

        if _sheet(actor) is None:
            return ActionResult(success=False, message=NO_GIFT_MESSAGE)
        participant = fight_participant(actor)
        lethal = participant.encounter.is_lethal if participant is not None else True
        offers = call_up_offers(actor, lethal=lethal)
        if not offers:
            return ActionResult(success=False, message=NO_GIFT_MESSAGE)
        offer = _pick_offer(offers, gift_id, substance)
        if offer is None:
            return ActionResult(success=False, message=WHICH_GIFT_MESSAGE)
        label = offer.plan.label
        if offer.plan.already_present:
            return ActionResult(
                success=True,
                message=f"{label.capitalize()} is already here. Nothing to call up.",
                data={"cost": 0, "resonance": 0, "already_present": True},
            )
        if not offer.plan.calls_up:
            return ActionResult(
                success=False, message=f"You cannot call up {label}: {offer.cost_line}."
            )
        if participant is not None and participant.encounter.status != RoundStatus.DECLARING:
            return ActionResult(success=False, message=NOT_DECLARING_MESSAGE)
        warning = get_soulfray_warning(actor) if offer.effective_cost > 0 else None
        if warning is not None and not truthy_kwarg(confirm_soulfray_risk):
            return ActionResult(
                success=False,
                message=(
                    f"Calling up {label} will cost {offer.effective_cost} anima and may worsen "
                    "your condition. Confirm to call it up anyway."
                ),
                data={"needs_soulfray_confirm": True, "cost": offer.effective_cost},
            )
        return _charge_and_apply(actor, offer, participant, lethal=lethal)

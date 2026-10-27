"""Drift correction actions (#4733, slice 4 of #4672).

``PerformDriftCorrectionAction`` performs the rite under an open ``DriftConversionOffer``;
``DeclineDriftCorrectionAction`` lets the character let the offer go. Telnet ``drift`` and the
REST ``/api/magic/drift-correction/`` endpoints converge here.

World imports are lazy inside ``execute()``: the action registry is imported very early and
the magic models pull in much of the world graph.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext

_NOT_YOUR_OFFER = "That chance to correct drift is not yours."
_NOT_CARRIED = "You are not carrying everything you offered."


def _actor_sheet_pk(actor: ObjectDB) -> int | None:
    sheet = actor.character_sheet
    return None if sheet is None else sheet.pk


@dataclass
class PerformDriftCorrectionAction(Action):
    """Perform the drift correction rite: convert drift toward a resonance the offer caps.

    kwargs:
        offer: The ``DriftConversionOffer`` (the actor's own).
        source_resonance: The drift resonance to convert from.
        target_resonance: The resonance to convert toward (one the offer has a cap for).
        amount: How much of the source to attempt to convert.
        components_provided: ``ItemInstance`` rows the actor offers up; each must be held
            by the actor's own sheet.
    """

    key: str = "perform_drift_correction"
    name: str = "Correct Drift"
    icon: str = "sparkles"
    category: str = "magic"
    target_type: TargetType = TargetType.SELF

    def execute(  # noqa: PLR0913 - the rite's named inputs, mirrored by the REST body
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        *,
        offer: Any,
        source_resonance: Any,
        target_resonance: Any,
        amount: int,
        components_provided: list[Any] | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.magic.exceptions import (  # noqa: PLC0415
            ConversionMappingError,
            DriftCorrectionError,
            RitualComponentError,
        )
        from world.magic.services.drift_correction import (  # noqa: PLC0415
            perform_drift_correction_rite,
        )

        sheet_pk = _actor_sheet_pk(actor)
        if sheet_pk is None or offer.character_sheet_id != sheet_pk:
            return ActionResult(success=False, message=_NOT_YOUR_OFFER)
        components = list(components_provided or [])
        if any(item.holder_character_sheet_id != sheet_pk for item in components):
            return ActionResult(success=False, message=_NOT_CARRIED)
        try:
            result = perform_drift_correction_rite(
                offer,
                source_resonance=source_resonance,
                target_resonance=target_resonance,
                amount=amount,
                components=components,
            )
        except (DriftCorrectionError, ConversionMappingError, RitualComponentError) as exc:
            return ActionResult(success=False, message=exc.user_message)
        if result.converted_amount == 0:
            message = "The rite fails; nothing is converted."
        else:
            message = (
                f"{result.converted_amount} {source_resonance.name} became "
                f"{result.granted_amount} {target_resonance.name}."
            )
        return ActionResult(
            success=True,
            message=message,
            data={"drift_correction_result": result},
        )


@dataclass
class DeclineDriftCorrectionAction(Action):
    """Let an open drift conversion offer go. Free; the offer is deleted."""

    key: str = "decline_drift_correction"
    name: str = "Decline Drift Correction"
    icon: str = "x"
    category: str = "magic"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        *,
        offer: Any,
        **kwargs: Any,
    ) -> ActionResult:
        sheet_pk = _actor_sheet_pk(actor)
        if sheet_pk is None or offer.character_sheet_id != sheet_pk:
            return ActionResult(success=False, message=_NOT_YOUR_OFFER)
        offer.delete()
        return ActionResult(success=True, message="You let the chance to correct drift pass.")

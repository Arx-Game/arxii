"""The anima ritual's two actions (#5280): ``endorse_anima_ritual`` and ``attune_anima_ritual``.

A partner's answer to a ritual that reached for them: telnet (``ritual endorse|withhold
<performer>``) and the web (the answer route of ``AnimaRitualEndorsementViewSet``) both converge
on ``EndorseAnimaRitualAction``, which calls
``world.magic.services.anima_ritual_endorsement.answer_anima_ritual``.

Changing the ritual's picks after the free first setup: telnet (``ritual attune``) and the web
(``POST /api/magic/anima-ritual/attune/``) converge on ``AttuneAnimaRitualAction``, which calls
``world.magic.services.anima_ritual_attunement.attune_anima_ritual``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext


@dataclass
class EndorseAnimaRitualAction(Action):
    """Say whether a ritual that reached for the actor took hold of them.

    kwargs:
        performance_id: The ``AnimaRitualPerformance`` pk the answer is for.
        endorse: True to endorse (the performer's outward resonance grows), False to withhold.
    """

    key: str = "endorse_anima_ritual"
    name: str = "Answer an anima ritual"
    icon: str = "sparkles"
    category: str = "magic"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        performance_id: object = None,
        endorse: bool = False,
        **kwargs: Any,
    ) -> ActionResult:
        from world.magic.exceptions import AnimaRitualAnswerError  # noqa: PLC0415
        from world.magic.models import AnimaRitualPerformance  # noqa: PLC0415
        from world.magic.services.anima_ritual_endorsement import (  # noqa: PLC0415
            NOT_WAITING,
            answer_anima_ritual,
        )

        performance = (
            AnimaRitualPerformance.objects.filter(pk=int(str(performance_id))).first()
            if str(performance_id).isdigit()
            else None
        )
        if performance is None:
            return ActionResult(success=False, message=NOT_WAITING)
        try:
            line = answer_anima_ritual(actor.sheet_data, performance, endorse=bool(endorse))
        except AnimaRitualAnswerError as err:
            return ActionResult(success=False, message=err.user_message)
        return ActionResult(success=True, message=line, data={"endorsed": bool(endorse)})


@dataclass
class AttuneAnimaRitualAction(Action):
    """Pay to change the resonances the actor's anima ritual grows.

    kwargs:
        primal_resonance_id: The Primal resonance the ritual should grow, or None for no pick.
        outward_resonance_id: The Celestial or Abyssal resonance it should reach for, or None.

    ``ap_cost`` stays 0 on purpose: the action points are staff-set on ``AnimaConfig`` and an
    attunement she cannot pay for in action points must be refused before anything else is
    spent, so the service spends them itself rather than ``Action._charge_costs``.
    """

    key: str = "attune_anima_ritual"
    name: str = "Attune your anima ritual"
    icon: str = "sparkles"
    category: str = "magic"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        primal_resonance_id: object = None,
        outward_resonance_id: object = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.magic.exceptions import (  # noqa: PLC0415
            AnimaRitualPickError,
            ResonanceInsufficient,
        )
        from world.magic.models import Resonance  # noqa: PLC0415
        from world.magic.services.anima_ritual_attunement import (  # noqa: PLC0415
            attune_anima_ritual,
        )

        picks: list[Resonance | None] = []
        for resonance_id in (primal_resonance_id, outward_resonance_id):
            if resonance_id is None:
                picks.append(None)
                continue
            pick = (
                Resonance.objects.select_related("affinity")
                .filter(pk=int(str(resonance_id)))
                .first()
                if str(resonance_id).isdigit()
                else None
            )
            if pick is None:
                return ActionResult(success=False, message="That is not a resonance.")
            picks.append(pick)
        try:
            result = attune_anima_ritual(actor.sheet_data, picks[0], picks[1])
        except (AnimaRitualPickError, ResonanceInsufficient) as err:
            return ActionResult(success=False, message=err.user_message)
        return ActionResult(success=True, message=result.message, data={"changed": result.changed})

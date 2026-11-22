"""A partner's answer to an anima ritual that reached for them (#5280): ``endorse_anima_ritual``.

Telnet (``ritual endorse|withhold <performer>``) and the web (the answer route of
``AnimaRitualEndorsementViewSet``) both converge on this action. The service
``world.magic.services.anima_ritual_endorsement.answer_anima_ritual`` takes the answer.
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

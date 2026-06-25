"""Identity actions — the ``set_active_persona`` REGISTRY action (#1347).

Wraps ``world.scenes.services.set_active_persona`` (the sole mutator of
``CharacterSheet.active_persona``) so telnet (``CmdPersona``) and the web
``PersonaViewSet.set_active`` share one ``action.run()`` path instead of the web
calling the service directly.
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
class SetActivePersonaAction(Action):
    """Switch the actor's active persona (identity they present as).

    The ``persona_id`` kwarg must be the pk of a ``Persona`` owned by the
    actor's sheet. A foreign or unknown id returns a uniform failure message
    to avoid leaking identity information.
    """

    key: str = "set_active_persona"
    name: str = "Wear Face"
    icon: str = "mask"
    category: str = "identity"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.scenes.models import Persona  # noqa: PLC0415
        from world.scenes.services import ActivePersonaError, set_active_persona  # noqa: PLC0415

        sheet = actor.sheet_data
        persona = Persona.objects.filter(
            pk=kwargs.get("persona_id"), character_sheet_id=sheet.pk
        ).first()
        if persona is None:
            return ActionResult(success=False, message=ActivePersonaError.user_message)
        try:
            set_active_persona(sheet, persona)
        except ActivePersonaError:
            return ActionResult(success=False, message=ActivePersonaError.user_message)
        return ActionResult(
            success=True,
            message=f"You present as {persona.name}.",
            data={"active_persona_id": persona.pk},
        )

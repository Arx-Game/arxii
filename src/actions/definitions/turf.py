"""Gang turf actions (#2862): the player face of the turf war.

`start_gang_turf` finally wires the orphaned `start_gang_turf_project`
machinery (#2418): a leader-rank member of a criminal org opens the
TIERED_PERIOD project whose graded completion pushes `NeighborhoodTurf`
grip — missions feed the same project through PROJECT reward lines.
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
class StartGangTurfAction(Action):
    """Open a turf push project for your gang (#2862).

    Kwargs: ``organization_id``, ``area_id`` (the contested neighborhood).
    Leadership-gated by the service (leader-rank active membership).
    """

    key: str = "start_gang_turf"
    name: str = "Push Turf"
    icon: str = "swords"
    category: str = "crime"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.areas.models import Area  # noqa: PLC0415
        from world.scenes.persona_display import active_persona_for_sheet  # noqa: PLC0415
        from world.societies.gang_turf import start_gang_turf_project  # noqa: PLC0415
        from world.societies.models import Organization  # noqa: PLC0415

        sheet = actor.character_sheet
        persona = active_persona_for_sheet(sheet) if sheet is not None else None
        if persona is None:
            return ActionResult(success=False, message="You need a persona to push turf.")
        organization = Organization.objects.filter(pk=kwargs.get("organization_id")).first()
        if organization is None:
            return ActionResult(success=False, message="Push turf for which crew?")
        area = Area.objects.filter(pk=kwargs.get("area_id")).first()
        if area is None:
            return ActionResult(success=False, message="Push into which neighborhood?")
        try:
            project = start_gang_turf_project(
                organization=organization,
                owner_persona=persona,
                target_area=area,
            )
        except ValueError as exc:
            return ActionResult(success=False, message=str(exc))
        return ActionResult(
            success=True,
            message=(
                f"The push into {area.name} begins — feed the project and the corners change hands."
            ),
            data={"project_id": project.pk},
        )

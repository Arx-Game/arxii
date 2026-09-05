"""In-play area management actions (#696 gap 3): the earned elevation declaration.

``EditAreaAction`` (``actions/definitions/world_builder.py``) is the warrant-gated
staff/GM override that can set ``area.level`` directly; ``DeclareElevationAction`` is
the parallel path any effective owner can walk without a build warrant, gated on
``elevation_services.elevation_eligibility`` (held BUILDING-level descendants + the
area's ORDER stat, both checked against the authored ``AreaElevationRequirement`` row
for the area's next level).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

_MSG_NO_ACTIVE_CHARACTER = "No active character."
_MSG_NO_AREA = "No such area."
_MSG_NOT_AUTHORIZED = "You are not this area's effective owner."
_MSG_NO_ORGANIZATION = "No such organization."
_MSG_NOT_AUTHORIZED_TREASURY = "You don't have spend authority over that organization's treasury."


def _resolve_active_persona(actor: ObjectDB) -> Any:
    """Return the actor's active persona, or ``None`` if unavailable."""
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    try:
        sheet = actor.sheet_data
    except (AttributeError, ObjectDoesNotExist):
        return None
    try:
        return active_persona_for_sheet(sheet)
    except ObjectDoesNotExist:
        return None


def _resolve_area(area_id: Any) -> Any:
    """Resolve an ``Area`` from an int pk (REST) or pass an instance through."""
    from world.areas.models import Area  # noqa: PLC0415

    if isinstance(area_id, Area):
        return area_id
    return Area.objects.filter(pk=area_id).first()


def _resolve_elevation_source(persona: Any, organization_id: Any) -> Any | str:
    """The purse or treasury to charge for an elevation, or an error message.

    No ``organization_id`` spends from the declarer's own purse; naming one spends
    from that organization's treasury, gated on ``can_spend_treasury`` here at the
    Action layer, never silently in the service. Mirrors
    ``events._resolve_grandeur_source``.
    """
    from world.currency.services import (  # noqa: PLC0415
        can_spend_treasury,
        get_or_create_purse,
        get_or_create_treasury,
    )
    from world.societies.models import Organization  # noqa: PLC0415

    if organization_id is None:
        return get_or_create_purse(persona.character_sheet)
    organization = Organization.objects.filter(pk=organization_id).first()
    if organization is None:
        return _MSG_NO_ORGANIZATION
    treasury = get_or_create_treasury(organization)
    if not can_spend_treasury(treasury, persona):
        return _MSG_NOT_AUTHORIZED_TREASURY
    return treasury


@dataclass
class DeclareElevationAction(Action):
    """Declare an area's elevation to its next level in play (#696 gap 3).

    Kwargs: ``area_id``, optional ``organization_id`` (spend from that org's treasury
    instead of the declarer's own purse). Thin over
    ``areas.elevation_services.declare_elevation``: resolves the area and coin
    source, gates on the declarer being the area's effective owner (Task 1's
    ``effective_owner_for_area``), and lets the service's own re-check raise the
    detailed eligibility refusal.
    """

    key: str = "declare_elevation"
    name: str = "Declare Area Elevation"
    icon: str = "arrow-up-circle"
    category: str = "areas"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: Any = None,
        **kwargs: Any,
    ) -> ActionResult:
        from django.core.exceptions import ValidationError  # noqa: PLC0415

        from world.areas.elevation_services import declare_elevation  # noqa: PLC0415
        from world.locations.constants import HolderType  # noqa: PLC0415
        from world.locations.services import effective_owner_for_area  # noqa: PLC0415
        from world.societies.houses.services import is_org_leader  # noqa: PLC0415

        persona = _resolve_active_persona(actor)
        if persona is None:
            return ActionResult(success=False, message=_MSG_NO_ACTIVE_CHARACTER)
        area = _resolve_area(kwargs.get("area_id"))
        if area is None:
            return ActionResult(success=False, message=_MSG_NO_AREA)

        owner_row = effective_owner_for_area(area)
        owns_directly = (
            owner_row is not None
            and owner_row.holder_type == HolderType.PERSONA
            and owner_row.holder_persona_id == persona.pk
        )
        owns_via_org = (
            owner_row is not None
            and owner_row.holder_type == HolderType.ORGANIZATION
            and is_org_leader(persona, owner_row.holder_organization)
        )
        if not (owns_directly or owns_via_org):
            return ActionResult(success=False, message=_MSG_NOT_AUTHORIZED)

        treasury_or_purse = _resolve_elevation_source(persona, kwargs.get("organization_id"))
        if isinstance(treasury_or_purse, str):
            return ActionResult(success=False, message=treasury_or_purse)

        try:
            declare_elevation(area, declarer=persona, treasury_or_purse=treasury_or_purse)
        except ValidationError as exc:
            return ActionResult(success=False, message="; ".join(exc.messages))

        return ActionResult(
            success=True,
            message=f"{area.name} is elevated to {area.get_level_display()}.",
            data={"area_id": area.pk, "level": area.level},
        )

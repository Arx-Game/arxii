"""Leader favor/disfavor declaration action (#3290).

A single action, ``DeclareStandingAction``, backs both the ``org favor`` and
``org disfavor`` telnet subverbs and the equivalent web dispatch — the direction
is a kwarg, not a separate action, mirroring how ``_run_membership_management``
in ``organizations.py`` shares one code path for promote/demote.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ObjectDoesNotExist

from actions.base import Action
from actions.constants import ActionCategory, TargetKind
from actions.types import ActionContext, ActionResult, TargetFilters, TargetType
from world.societies.constants import StandingDirection
from world.societies.exceptions import StandingDeclarationError

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.scenes.models import Persona
    from world.societies.models import Organization

_TARGET_FILTERS = TargetFilters(in_same_scene=False, exclude_self=True)

_MSG_NO_CHARACTER_IDENTITY = "You have no character identity."
_MSG_WHICH_ORGANIZATION = "Which organization?"
_MSG_WHICH_TARGET = "Declare standing for whom?"
_MSG_NO_CITATION = "A public citation is required."


def _actor_persona(actor: ObjectDB) -> Persona | None:
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    try:
        sheet = actor.sheet_data
    except (AttributeError, ObjectDoesNotExist):
        return None
    if sheet is None:
        return None
    try:
        return active_persona_for_sheet(sheet)
    except ObjectDoesNotExist:
        return None


def _resolve_target_persona(value: Any) -> Persona | None:
    from world.scenes.models import Persona  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    if value is None:
        return None
    if isinstance(value, Persona):
        return value
    from evennia.objects.models import ObjectDB  # noqa: PLC0415

    if isinstance(value, ObjectDB):
        try:
            sheet = value.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            return None
        if sheet is None:
            return None
        try:
            return active_persona_for_sheet(sheet)
        except ObjectDoesNotExist:
            return None
    try:
        return Persona.objects.filter(pk=int(value)).select_related("character_sheet").first()
    except (TypeError, ValueError):
        return None


def _resolve_organization(value: Any) -> Organization | None:
    from world.societies.models import Organization  # noqa: PLC0415

    if value is None:
        return None
    if isinstance(value, Organization):
        return value
    try:
        return Organization.objects.filter(pk=int(value)).first()
    except (TypeError, ValueError):
        return None


@dataclass
class DeclareStandingAction(Action):
    """Officially declare a persona favored or disfavored with an organization.

    ``kwargs``: ``target`` (Persona/ObjectDB/pk), ``organization_id``,
    ``direction`` (``StandingDirection.FAVOR``/``DISFAVOR``), ``citation`` (str).
    Not room-scoped — a leader's declaration is an official act, not a
    face-to-face interaction, so the target need not be co-located.
    """

    key: str = "declare_standing"
    name: str = "Declare Standing"
    icon: str = "gavel"
    category: str = "social"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SINGLE
    target_kind: TargetKind = TargetKind.PERSONA
    target_filters: TargetFilters = field(default=_TARGET_FILTERS)
    costs_turn: bool = True

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.societies.standing_services import declare_standing  # noqa: PLC0415

        actor_persona = _actor_persona(actor)
        if actor_persona is None:
            return ActionResult(success=False, message=_MSG_NO_CHARACTER_IDENTITY)

        target_persona = _resolve_target_persona(kwargs.get("target"))
        if target_persona is None:
            return ActionResult(success=False, message=_MSG_WHICH_TARGET)

        organization = _resolve_organization(kwargs.get("organization_id"))
        if organization is None:
            return ActionResult(success=False, message=_MSG_WHICH_ORGANIZATION)

        direction = kwargs.get("direction")
        if direction not in StandingDirection.values:
            return ActionResult(success=False, message="Favor or disfavor?")

        citation = (kwargs.get("citation") or "").strip()
        if not citation:
            return ActionResult(success=False, message=_MSG_NO_CITATION)

        try:
            declaration = declare_standing(
                organization=organization,
                target_persona=target_persona,
                declared_by_persona=actor_persona,
                direction=direction,
                citation=citation,
            )
        except StandingDeclarationError as exc:
            return ActionResult(success=False, message=exc.user_message)

        verb = "favored" if declaration.direction == StandingDirection.FAVOR else "disfavored"
        return ActionResult(
            success=True,
            message=(
                f"You declare {target_persona.name} {verb} by {organization.name}: {citation}"
            ),
        )


# Module-level singleton — registered in actions/registry.py
declare_standing_action = DeclareStandingAction()

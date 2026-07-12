"""In-play domain management actions (#2239) — the surface the deterministic
domain-growth machinery never had.

``add_holding`` / ``start_domain_improvement`` were callable only from CG and seeds;
these Actions make them reachable in play, gated on ``can_administer_domain`` (an org
leader OR the ``domain-steward`` office holder). The office lifecycle verbs
(``appoint``/``vacate``) are leadership-only — appointing a steward is a rank act.
All four are thin over the existing, correct services (wiring, not new logic).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

_MSG_NO_ACTIVE_CHARACTER = "No active character."
_MSG_NO_DOMAIN = "No such domain."
_MSG_NOT_AUTHORIZED = "You don't have standing to run this domain."
_MSG_NOT_LEADER = "Only a house leader may appoint or vacate an office."
_MSG_NO_HOLDING_KIND = "No such holding kind."
_MSG_NO_HOLDER = "No such persona to appoint."


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


def _resolve_domain(domain_id: Any) -> Any:
    """Resolve a ``Domain`` from an int pk (REST) or pass an instance through."""
    from world.societies.houses.models import Domain  # noqa: PLC0415

    if isinstance(domain_id, Domain):
        return domain_id
    return Domain.objects.filter(pk=domain_id).select_related("owner_org").first()


@dataclass
class AddDomainHoldingAction(Action):
    """Attach a working holding to a domain in play (#2239).

    Thin over ``houses.services.add_holding`` — resolves the domain + holding kind,
    gates on ``can_administer_domain``, and materializes the ``OrgIncomeStream``-backed
    holding through the untouched currency pipeline.
    """

    key: str = "add_domain_holding"
    name: str = "Add Domain Holding"
    icon: str = "landmark"
    category: str = "domains"
    target_type: TargetType = TargetType.SELF

    def execute(self, actor: ObjectDB, context: Any = None, **kwargs: Any) -> ActionResult:
        from world.societies.houses.models import HoldingKind  # noqa: PLC0415
        from world.societies.houses.services import (  # noqa: PLC0415
            add_holding,
            can_administer_domain,
        )

        persona = _resolve_active_persona(actor)
        if persona is None:
            return ActionResult(success=False, message=_MSG_NO_ACTIVE_CHARACTER)
        domain = _resolve_domain(kwargs.get("domain_id"))
        if domain is None:
            return ActionResult(success=False, message=_MSG_NO_DOMAIN)
        if not can_administer_domain(persona, domain):
            return ActionResult(success=False, message=_MSG_NOT_AUTHORIZED)
        kind = HoldingKind.objects.filter(pk=kwargs.get("holding_kind_id")).first()
        if kind is None:
            return ActionResult(success=False, message=_MSG_NO_HOLDING_KIND)

        holding = add_holding(domain=domain, kind=kind, name=kwargs.get("name", ""))
        return ActionResult(
            success=True,
            message=f"{domain.name} gains a new holding: {holding.name}.",
            data={"holding_id": holding.pk},
        )


@dataclass
class StartDomainImprovementAction(Action):
    """Commission a domain improvement in play (#2239).

    Thin over ``houses.services.start_domain_improvement`` — creates the funding
    Project + details row; the actor's active persona owns the project. Gated on
    ``can_administer_domain``.
    """

    key: str = "start_domain_improvement"
    name: str = "Start Domain Improvement"
    icon: str = "trending-up"
    category: str = "domains"
    target_type: TargetType = TargetType.SELF

    def execute(self, actor: ObjectDB, context: Any = None, **kwargs: Any) -> ActionResult:
        from world.societies.houses.models import DomainHolding  # noqa: PLC0415
        from world.societies.houses.services import (  # noqa: PLC0415
            HousesServiceError,
            can_administer_domain,
            start_domain_improvement,
        )

        persona = _resolve_active_persona(actor)
        if persona is None:
            return ActionResult(success=False, message=_MSG_NO_ACTIVE_CHARACTER)
        domain = _resolve_domain(kwargs.get("domain_id"))
        if domain is None:
            return ActionResult(success=False, message=_MSG_NO_DOMAIN)
        if not can_administer_domain(persona, domain):
            return ActionResult(success=False, message=_MSG_NOT_AUTHORIZED)

        holding = None
        holding_id = kwargs.get("holding_id")
        if holding_id is not None:
            holding = DomainHolding.objects.filter(pk=holding_id).first()

        try:
            project = start_domain_improvement(
                domain=domain,
                persona=persona,
                cost=int(kwargs.get("cost", 0)),
                gross_increase=int(kwargs.get("gross_increase", 0)),
                prosperity_increase=int(kwargs.get("prosperity_increase", 0)),
                holding=holding,
            )
        except HousesServiceError as exc:
            return ActionResult(success=False, message=exc.user_message)

        return ActionResult(
            success=True,
            message=f"An improvement project for {domain.name} begins.",
            data={"project_id": project.pk},
        )


@dataclass
class AppointDomainOfficeAction(Action):
    """Appoint a member to a house's domain-steward office (#2239).

    Leadership-only — installing a steward is a rank act, not a delegated one, so
    this gates on ``is_org_leader`` rather than ``can_administer_domain`` (an office
    holder can't name their own successor). Thin over ``office_services.appoint_office``.
    """

    key: str = "appoint_domain_office"
    name: str = "Appoint Domain Steward"
    icon: str = "user-check"
    category: str = "domains"
    target_type: TargetType = TargetType.SELF

    def execute(self, actor: ObjectDB, context: Any = None, **kwargs: Any) -> ActionResult:
        from world.scenes.models import Persona  # noqa: PLC0415
        from world.societies.houses.constants import DOMAIN_STEWARD_OFFICE  # noqa: PLC0415
        from world.societies.houses.services import is_org_leader  # noqa: PLC0415
        from world.societies.office_services import appoint_office  # noqa: PLC0415
        from world.traits.models import Trait  # noqa: PLC0415

        persona = _resolve_active_persona(actor)
        if persona is None:
            return ActionResult(success=False, message=_MSG_NO_ACTIVE_CHARACTER)
        domain = _resolve_domain(kwargs.get("domain_id"))
        if domain is None:
            return ActionResult(success=False, message=_MSG_NO_DOMAIN)
        org = domain.owner_org
        if not is_org_leader(persona, org):
            return ActionResult(success=False, message=_MSG_NOT_LEADER)
        holder = Persona.objects.filter(pk=kwargs.get("holder_persona_id")).first()
        if holder is None:
            return ActionResult(success=False, message=_MSG_NO_HOLDER)
        feeds_check = None
        feeds_check_id = kwargs.get("feeds_check_id")
        if feeds_check_id is not None:
            feeds_check = Trait.objects.filter(pk=feeds_check_id).first()

        office = appoint_office(
            organization=org,
            slug=DOMAIN_STEWARD_OFFICE,
            holder=holder,
            title=kwargs.get("title", ""),
            feeds_check=feeds_check,
        )
        return ActionResult(
            success=True,
            message=f"{holder.name} is appointed {office.title or office.slug}.",
            data={"office_id": office.pk},
        )


@dataclass
class VacateDomainOfficeAction(Action):
    """Clear a house's domain-steward office (#2239). Leadership-only."""

    key: str = "vacate_domain_office"
    name: str = "Vacate Domain Steward"
    icon: str = "user-x"
    category: str = "domains"
    target_type: TargetType = TargetType.SELF

    def execute(self, actor: ObjectDB, context: Any = None, **kwargs: Any) -> ActionResult:
        from world.societies.houses.constants import DOMAIN_STEWARD_OFFICE  # noqa: PLC0415
        from world.societies.houses.services import is_org_leader  # noqa: PLC0415
        from world.societies.office_services import vacate_office  # noqa: PLC0415

        persona = _resolve_active_persona(actor)
        if persona is None:
            return ActionResult(success=False, message=_MSG_NO_ACTIVE_CHARACTER)
        domain = _resolve_domain(kwargs.get("domain_id"))
        if domain is None:
            return ActionResult(success=False, message=_MSG_NO_DOMAIN)
        org = domain.owner_org
        if not is_org_leader(persona, org):
            return ActionResult(success=False, message=_MSG_NOT_LEADER)

        vacate_office(organization=org, slug=DOMAIN_STEWARD_OFFICE)
        return ActionResult(success=True, message="The domain-steward office is vacated.")

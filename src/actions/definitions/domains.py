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
_MSG_NO_UNIT = "No such military unit."
_MSG_NO_ORG = "No such organization."
_MSG_NO_MATERIAL_CATEGORY = "No such material category."


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


def _resolve_unit(unit_id: Any) -> Any:
    """Resolve a ``MilitaryUnit`` from an int pk (REST) or pass an instance through."""
    from world.military.models import MilitaryUnit  # noqa: PLC0415

    if isinstance(unit_id, MilitaryUnit):
        return unit_id
    return MilitaryUnit.objects.filter(pk=unit_id).first()


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


@dataclass
class AssignGarrisonAction(Action):
    """Post a military unit to garrison a domain (#696 gap 5).

    Thin over ``houses.services.assign_garrison`` - gates on
    ``can_administer_domain``, and the service itself re-checks the unit's
    ``owner_org`` matches the domain's before creating the post. Combat
    semantics for what a garrison contributes are TehomCD's; this only wires
    the domain<->unit link.
    """

    key: str = "assign_garrison"
    name: str = "Assign Garrison"
    icon: str = "shield"
    category: str = "domains"
    target_type: TargetType = TargetType.SELF

    def execute(self, actor: ObjectDB, context: Any = None, **kwargs: Any) -> ActionResult:
        from world.societies.houses.services import (  # noqa: PLC0415
            HousesServiceError,
            assign_garrison,
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
        unit = _resolve_unit(kwargs.get("unit_id"))
        if unit is None:
            return ActionResult(success=False, message=_MSG_NO_UNIT)

        try:
            post = assign_garrison(domain=domain, unit=unit)
        except HousesServiceError as exc:
            return ActionResult(success=False, message=exc.user_message)

        return ActionResult(
            success=True,
            message=f"{unit.name} now garrisons {domain.name}.",
            data={"post_id": post.pk},
        )


@dataclass
class RelieveGarrisonAction(Action):
    """Pull a military unit off garrison duty (#696 gap 5).

    Thin over ``houses.services.relieve_garrison`` - gates on
    ``can_administer_domain`` for the domain the unit currently garrisons.
    """

    key: str = "relieve_garrison"
    name: str = "Relieve Garrison"
    icon: str = "shield-off"
    category: str = "domains"
    target_type: TargetType = TargetType.SELF

    def execute(self, actor: ObjectDB, context: Any = None, **kwargs: Any) -> ActionResult:
        from world.societies.houses.models import DomainGarrisonPost  # noqa: PLC0415
        from world.societies.houses.services import (  # noqa: PLC0415
            can_administer_domain,
            relieve_garrison,
        )

        persona = _resolve_active_persona(actor)
        if persona is None:
            return ActionResult(success=False, message=_MSG_NO_ACTIVE_CHARACTER)
        unit = _resolve_unit(kwargs.get("unit_id"))
        if unit is None:
            return ActionResult(success=False, message=_MSG_NO_UNIT)
        post = DomainGarrisonPost.objects.filter(unit=unit).select_related("domain").first()
        if post is None:
            return ActionResult(success=False, message="That unit isn't garrisoning anywhere.")
        if not can_administer_domain(persona, post.domain):
            return ActionResult(success=False, message=_MSG_NOT_AUTHORIZED)

        domain_name = post.domain.name
        relieve_garrison(unit=unit)
        return ActionResult(
            success=True,
            message=f"{unit.name} is relieved from garrisoning {domain_name}.",
        )


@dataclass
class TransferFoodAction(Action):
    """Transfer food between domains (#2219).

    Gated on ``can_administer_domain`` for the source domain. Thin over
    ``transfer_food()`` — resolves source + target domains from pks
    (REST-safe), checks authorization, delegates to the service.
    """

    key: str = "transfer_food"
    name: str = "Transfer Food"
    icon: str = "arrow-left-right"
    category: str = "domains"
    target_type: TargetType = TargetType.SELF

    def execute(self, actor: ObjectDB, context: Any = None, **kwargs: Any) -> ActionResult:
        from world.agriculture.services import transfer_food  # noqa: PLC0415
        from world.societies.houses.services import can_administer_domain  # noqa: PLC0415

        persona = _resolve_active_persona(actor)
        source = _resolve_domain(kwargs.get("source_domain_id"))
        target = _resolve_domain(kwargs.get("target_domain_id"))
        amount = int(kwargs.get("amount", 0))

        error = self._validate(persona, source, target, amount, can_administer_domain)
        if error is not None:
            return error

        try:
            result = transfer_food(
                source_domain=source,
                target_domain=target,
                amount=amount,
                acting_persona=persona,
                character=actor,
            )
        except ValueError as exc:
            return ActionResult(success=False, message=str(exc))

        if result.cancelled:
            return ActionResult(
                success=False,
                message="The transfer was thwarted; the food remains in the granary.",
                data={"cancelled": True},
            )

        msg = f"Transferred {result.landed} food from {source.name} to {target.name}."
        if result.overflow > 0:
            msg += f" ({result.overflow} lost to overflow — granary full)."

        return ActionResult(
            success=True,
            message=msg,
            data={
                "amount": result.amount,
                "landed": result.landed,
                "overflow": result.overflow,
            },
        )

    @staticmethod
    def _validate(persona, source, target, amount, can_administer_fn) -> ActionResult | None:
        """Return a failure ActionResult if preconditions are unmet, else None."""
        if persona is None:
            return ActionResult(success=False, message=_MSG_NO_ACTIVE_CHARACTER)
        if source is None:
            return ActionResult(success=False, message="No such source domain.")
        if target is None:
            return ActionResult(success=False, message="No such target domain.")
        if not can_administer_fn(persona, source):
            return ActionResult(success=False, message=_MSG_NOT_AUTHORIZED)
        if amount <= 0:
            return ActionResult(success=False, message="Amount must be positive.")
        return None


def _resolve_org(organization_id: Any) -> Any:
    """Resolve an ``Organization`` from an int pk (REST) or pass an instance through."""
    from world.societies.models import Organization  # noqa: PLC0415

    if isinstance(organization_id, Organization):
        return organization_id
    return Organization.objects.filter(pk=organization_id).first()


def _resolve_material_category(material_category_id: Any) -> Any:
    """Resolve a ``MaterialCategory`` from an int pk (REST) or pass an instance through."""
    from world.items.models import MaterialCategory  # noqa: PLC0415

    if isinstance(material_category_id, MaterialCategory):
        return material_category_id
    return MaterialCategory.objects.filter(pk=material_category_id).first()


@dataclass
class GrantMaterialAction(Action):
    """Grant house material stock to one chosen member (#696 gap 6).

    The steward's discretionary sibling of the automatic materials allowance -
    thin over ``items.services.org_materials.grant_material_stock`` (which gates on
    ``can_steward_org`` and re-checks the recipient's active membership). Kwargs:
    ``organization_id``, ``material_category_id``, ``amount``, ``recipient_sheet_id``.
    Copies the shape of the shipped personal ``sell_materials`` action (#2540 slice 2).
    """

    key: str = "grant_materials"
    name: str = "Grant Materials"
    icon: str = "hand-heart"
    category: str = "domains"
    target_type: TargetType = TargetType.SELF

    def execute(self, actor: ObjectDB, context: Any = None, **kwargs: Any) -> ActionResult:
        from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
        from world.items.exceptions import ItemError  # noqa: PLC0415
        from world.items.services.org_materials import grant_material_stock  # noqa: PLC0415

        persona = _resolve_active_persona(actor)
        if persona is None:
            return ActionResult(success=False, message=_MSG_NO_ACTIVE_CHARACTER)
        organization = _resolve_org(kwargs.get("organization_id"))
        if organization is None:
            return ActionResult(success=False, message=_MSG_NO_ORG)
        category = _resolve_material_category(kwargs.get("material_category_id"))
        if category is None:
            return ActionResult(success=False, message=_MSG_NO_MATERIAL_CATEGORY)
        amount = kwargs.get("amount")
        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
            return ActionResult(success=False, message="Grant how much?")
        recipient = CharacterSheet.objects.filter(pk=kwargs.get("recipient_sheet_id")).first()
        if recipient is None:
            return ActionResult(success=False, message="No such character to grant to.")
        try:
            entry = grant_material_stock(
                organization=organization,
                material_category=category,
                value=amount,
                to_sheet=recipient,
                granted_by=persona,
            )
        except ItemError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True,
            message=f"You grant {amount} worth of {category.name} from the house stock.",
            data={"ledger_entry_id": entry.pk},
        )


@dataclass
class SetAskingPriceAction(Action):
    """Set the house's asking price for a material category (#696 gap 6).

    Thin over ``items.services.org_materials.set_asking_price`` (which gates on
    ``can_steward_org`` and bounds the pct) - the rate the auto-sell liquidates
    that category's excess at; 0 means never sell. Kwargs: ``organization_id``,
    ``material_category_id``, ``pct``.
    """

    key: str = "set_asking_price"
    name: str = "Set Asking Price"
    icon: str = "badge-percent"
    category: str = "domains"
    target_type: TargetType = TargetType.SELF

    def execute(self, actor: ObjectDB, context: Any = None, **kwargs: Any) -> ActionResult:
        from world.items.exceptions import ItemError  # noqa: PLC0415
        from world.items.services.org_materials import set_asking_price  # noqa: PLC0415

        persona = _resolve_active_persona(actor)
        if persona is None:
            return ActionResult(success=False, message=_MSG_NO_ACTIVE_CHARACTER)
        organization = _resolve_org(kwargs.get("organization_id"))
        if organization is None:
            return ActionResult(success=False, message=_MSG_NO_ORG)
        category = _resolve_material_category(kwargs.get("material_category_id"))
        if category is None:
            return ActionResult(success=False, message=_MSG_NO_MATERIAL_CATEGORY)
        pct = kwargs.get("pct")
        if not isinstance(pct, int) or isinstance(pct, bool):
            return ActionResult(success=False, message="Set the price to what percent?")
        try:
            stock = set_asking_price(
                organization=organization,
                material_category=category,
                pct=pct,
                by=persona,
            )
        except ItemError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True,
            message=(
                f"The house's asking price for {category.name} is now {stock.asking_price_pct}%."
            ),
            data={"stock_id": stock.pk},
        )

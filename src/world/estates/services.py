"""Estate settlement services (#1985).

``open_settlement`` is called from the single death writer
(``world.vitals.services._mark_dead``); ``execute_settlement`` is the ONE
idempotent execution path all three doors call (funeral finish, executor
will-reading, deadline sweeper). Spec: issue #1985 body.
"""

from datetime import timedelta
import logging

from django.db import transaction
from django.utils import timezone

from world.character_sheets.models import CharacterSheet
from world.estates.constants import BequestKind, SettlementStatus
from world.estates.exceptions import EscheatUnresolvableError
from world.estates.models import (
    EstateClaim,
    EstateSettlement,
    Will,
    WillExecutor,
    get_estate_config,
)

logger = logging.getLogger(__name__)


def will_is_frozen(character_sheet: CharacterSheet) -> bool:
    """True once a settlement window exists — the will can no longer be edited."""
    return EstateSettlement.objects.filter(character_sheet=character_sheet).exists()


def open_settlement(character_sheet: CharacterSheet) -> EstateSettlement:
    """Open the settlement window at death; idempotent per sheet.

    Called from ``_mark_dead``. The deadline arms the sweeper door
    (``settlement_window_days`` real days, config PLACEHOLDER); the funeral
    and will-reading doors may execute any time before it.
    """
    config = get_estate_config()
    settlement, created = EstateSettlement.objects.get_or_create(
        character_sheet=character_sheet,
        defaults={"deadline": timezone.now() + timedelta(days=config.settlement_window_days)},
    )
    if created:
        _notify_executors(settlement)
    return settlement


def resolve_intestate_heir(character_sheet: CharacterSheet):
    """The Decision-6 cascade: family-org head, then public-record next of kin.

    Returns a ``Persona`` or ``Organization`` recipient, or ``None`` (escheat
    is the caller's next link). Kinship reads use ``viewer=None`` (public
    record only) — hidden kin never auto-inherit; they must reveal to claim.
    """
    heir = _family_org_head(character_sheet)
    if heir is not None:
        return heir
    return _next_of_kin(character_sheet)


def _family_org_head(character_sheet: CharacterSheet):
    """Head of house: top-ranked active org member who is also family (not vassal).

    Qualifying orgs anchor a ``Family`` the deceased holds a live
    ``FamilyMembership`` in (any basis — vassalage is org-level fealty and
    never a family basis). Orgs the deceased actually held membership in are
    preferred by the deceased's rank tier; remaining ties break on org pk.
    The head is the qualifying org's lowest-tier active member persona whose
    kinsperson is living family of that same Family, excluding the deceased;
    ties break on earliest membership row.
    """
    from world.roster.models.families import FamilyMembership, Kinsperson  # noqa: PLC0415
    from world.societies.models import Organization, OrganizationMembership  # noqa: PLC0415

    kinsperson = Kinsperson.objects.filter(sheet=character_sheet).first()
    if kinsperson is None:
        return None
    family_ids = list(
        FamilyMembership.objects.filter(kinsperson=kinsperson, ended_at__isnull=True).values_list(
            "family_id", flat=True
        )
    )
    if not family_ids:
        return None
    orgs = list(Organization.objects.filter(family_id__in=family_ids))
    if not orgs:
        return None

    def org_preference(org: Organization) -> tuple[int, int]:
        own = (
            OrganizationMembership.objects.filter(
                organization=org,
                persona__character_sheet=character_sheet,
                left_at__isnull=True,
                exiled_at__isnull=True,
            )
            .select_related("rank")
            .order_by("rank__tier")
            .first()
        )
        return (own.rank.tier if own is not None else 99, org.pk)

    for org in sorted(orgs, key=org_preference):
        head = (
            OrganizationMembership.objects.filter(
                organization=org,
                left_at__isnull=True,
                exiled_at__isnull=True,
                persona__character_sheet__kinsperson__is_deceased=False,
                persona__character_sheet__kinsperson__family_memberships__family_id=(org.family_id),
                persona__character_sheet__kinsperson__family_memberships__ended_at__isnull=True,
            )
            .exclude(persona__character_sheet=character_sheet)
            .select_related("persona")
            .order_by("rank__tier", "id")
            .first()
        )
        if head is not None:
            return head.persona
    return None


def _next_of_kin(character_sheet: CharacterSheet):
    """Fixed kin walk (INTESTATE_KIN_ORDER, PLACEHOLDER): wedlock spouse ->
    eldest child -> elder living parent -> eldest sibling. Public record only;
    only sheeted, living kin qualify (NPC name-nodes are skipped)."""
    from world.roster.models.families import Kinsperson  # noqa: PLC0415
    from world.roster.services.kinship import (  # noqa: PLC0415
        children_of,
        parents_of,
        siblings_of,
        unions_of,
    )

    person = Kinsperson.objects.filter(sheet=character_sheet).first()
    if person is None:
        return None

    def eldest_first(people):
        return sorted(people, key=lambda p: (-(p.age or 0), p.pk))

    wedlock_spouses = [
        member
        for union in unions_of(person, None)
        if union.ended_at is None and union.kind.confers_wedlock
        for member in union.members.all()
        if member.pk != person.pk
    ]
    rungs = (
        wedlock_spouses,
        [edge.child for edge in children_of(person, None)],
        [edge.parent for edge in parents_of(person, None)],
        list(Kinsperson.objects.filter(pk__in=siblings_of(person, None).keys())),
    )
    for rung in rungs:
        for candidate in eldest_first(rung):
            persona = _living_persona_for(candidate)
            if persona is not None:
                return persona
    return None


def _living_persona_for(kinsperson):
    """The canonical (primary) persona of a living, sheeted kinsperson, else None.

    Ownership assignment targets the sheet's persistent primary persona — this
    is a property-record write, not an IC-display read, so the
    active-persona-resolution rule for viewers does not apply.
    """
    if kinsperson.is_deceased or kinsperson.sheet_id is None:
        return None
    from world.vitals.services import is_dead  # noqa: PLC0415

    sheet = kinsperson.sheet
    if is_dead(sheet):
        return None
    return sheet.primary_persona


def resolve_escheat_org(character_sheet: CharacterSheet):
    """The regional controlling org: primary-home region's Domain owner, else
    the death location's. ``None`` parks the settlement for staff.

    A ``Domain`` may decorate an Area at any level (no level constraint on the
    model), so the walk is level-agnostic: the NEAREST ancestor (self first)
    carrying a domain with an owner wins. Deliberately a plain ``parent``
    chain walk, not ``get_ancestry`` — the AreaClosure materialized view is
    PG-only (absent on the SQLite tier) and this path is nowhere near hot.
    """
    from world.locations.models import LocationTenancy  # noqa: PLC0415
    from world.societies.houses.models import Domain  # noqa: PLC0415

    areas = []
    home = (
        LocationTenancy.objects.filter(
            tenant_persona__character_sheet=character_sheet,
            is_primary_home=True,
            ends_at__isnull=True,
        )
        .select_related("room_profile__area")
        .first()
    )
    if home is not None and home.room_profile is not None and home.room_profile.area is not None:
        areas.append(home.room_profile.area)
    character = character_sheet.character
    location = getattr(character, "location", None)  # noqa: GETATTR_LITERAL
    room_profile = getattr(location, "room_profile", None) if location else None  # noqa: GETATTR_LITERAL
    if room_profile is not None and room_profile.area is not None:
        areas.append(room_profile.area)
    for area in areas:
        node = area
        while node is not None:
            domain = Domain.objects.filter(area=node).select_related("owner_org").first()
            if domain is not None and domain.owner_org is not None:
                return domain.owner_org
            node = node.parent
    return None


_KIND_SEQUENCE = (
    BequestKind.SPECIFIC_ITEM,
    BequestKind.COIN_AMOUNT,
    BequestKind.ALL_COIN,
    BequestKind.BUILDING,
    BequestKind.BUSINESS,
)


def execute_settlement(character_sheet: CharacterSheet, *, via: str) -> EstateSettlement | None:
    """The ONE execution path (spec Decision 2) — idempotent, first door wins.

    Atomicity contract: the estate applies fully or not at all. A PARKED
    outcome (escheat unresolvable while assets need a home) rolls back every
    estate mutation and records only the PARKED status for staff.
    """
    with transaction.atomic():
        settlement = (
            EstateSettlement.objects.select_for_update()
            .filter(character_sheet=character_sheet)
            .first()
        )
        if settlement is None or settlement.status != SettlementStatus.PENDING:
            return settlement
        try:
            with transaction.atomic():
                _apply_estate(settlement)
        except EscheatUnresolvableError:
            settlement.status = SettlementStatus.PARKED
            settlement.save(update_fields=["status"])
            logger.warning("Estate settlement %s PARKED — no escheat org.", settlement.pk)
            return settlement
        settlement.status = SettlementStatus.SETTLED
        settlement.settled_via = via
        settlement.settled_at = timezone.now()
        settlement.save(update_fields=["status", "settled_via", "settled_at"])
        return settlement


def _apply_estate(settlement: EstateSettlement) -> None:
    """Debts -> bequests (kind-major) -> residuary sweep -> substitution -> claims."""
    sheet = settlement.character_sheet
    will = Will.objects.filter(character_sheet=sheet).first()
    bequests = list(will.bequests.all()) if will is not None else []
    residuary = next((b for b in bequests if b.kind == BequestKind.RESIDUARY), None)

    heir_persona, heir_org = _resolve_estate_heir(sheet, residuary)
    has_assets = _estate_has_assets(sheet)
    if has_assets and heir_persona is None and heir_org is None:
        raise EscheatUnresolvableError

    _settle_debts(sheet)

    delivered_item_ids: set[int] = set()
    for kind in _KIND_SEQUENCE:
        for bequest in sorted(
            (b for b in bequests if b.kind == kind), key=lambda b: (b.order, b.pk)
        ):
            item_id = _deliver_bequest(sheet, bequest, heir_persona, heir_org)
            if item_id is not None:
                delivered_item_ids.add(item_id)

    _sweep_residuary(sheet, heir_persona, heir_org, delivered_item_ids)
    _substitute_contracts(sheet, heir_persona, heir_org)
    _end_residency_and_work(sheet)
    _mint_claims(sheet, settlement, bequests, heir_persona, heir_org)


def _resolve_estate_heir(sheet: CharacterSheet, residuary):
    """The estate-heir chain: valid RESIDUARY recipient -> intestate -> escheat.

    Returns ``(persona, organization)`` — exactly one set, or both ``None``
    when even escheat resolves nothing.
    """
    from world.societies.models import Organization  # noqa: PLC0415

    if residuary is not None:
        if residuary.recipient_organization_id is not None:
            return None, residuary.recipient_organization
        if _persona_recipient_is_valid(residuary.recipient_persona):
            return residuary.recipient_persona, None
    heir = resolve_intestate_heir(sheet)
    if heir is not None:
        if isinstance(heir, Organization):
            return None, heir
        return heir, None
    escheat_org = resolve_escheat_org(sheet)
    if escheat_org is not None:
        return None, escheat_org
    return None, None


def _persona_recipient_is_valid(persona) -> bool:
    """A persona can receive only while its character is alive and unretired."""
    if persona is None:
        return False
    from world.vitals.services import is_dead, is_retired  # noqa: PLC0415

    recipient_sheet = persona.character_sheet
    return not is_dead(recipient_sheet) and not is_retired(recipient_sheet)


def _persona_can_receive_item(persona, item_instance) -> bool:
    """Validity + the hot-goods consent gate (system delivery: no actor tenure)."""
    if not _persona_recipient_is_valid(persona):
        return False
    from world.items.services.provenance import has_unresolved_stolen_provenance  # noqa: PLC0415

    if not has_unresolved_stolen_provenance(item_instance):
        return True
    from flows.service_functions.inventory import _active_tenure_for_sheet  # noqa: PLC0415
    from world.consent.services import (  # noqa: PLC0415
        consent_blocks_targeting,
        receiving_stolen_goods_category,
    )

    tenure = _active_tenure_for_sheet(persona.character_sheet)
    if tenure is None:
        return True  # NPC recipients are not consent-protected
    return not consent_blocks_targeting(
        owner_tenure=tenure,
        category=receiving_stolen_goods_category(),
        actor_tenure=None,
    )


def _estate_has_assets(sheet: CharacterSheet) -> bool:
    from world.currency.models import Business, CharacterPurse  # noqa: PLC0415
    from world.items.models import ItemInstance  # noqa: PLC0415
    from world.locations.models import LocationOwnership  # noqa: PLC0415

    if ItemInstance.objects.filter(holder_character_sheet=sheet).exists():
        return True
    purse = CharacterPurse.objects.filter(character_sheet=sheet).first()
    if purse is not None and purse.balance > 0:
        return True
    if Business.objects.filter(owner_persona__character_sheet=sheet, active=True).exists():
        return True
    return LocationOwnership.objects.filter(
        holder_persona__character_sheet=sheet, ended_at__isnull=True
    ).exists()


def _settle_debts(sheet: CharacterSheet) -> None:
    """Debts before bequests (spec Decision 7): NOTARIZED one-shots + arrears.

    Pays in row order until the purse runs dry; a partially-payable term gets
    a partial transfer and stays unfulfilled.
    """
    from world.buildings.models import Building  # noqa: PLC0415
    from world.currency.constants import ContractFormality, ContractStatus  # noqa: PLC0415
    from world.currency.models import ContractTerm  # noqa: PLC0415
    from world.currency.services import (  # noqa: PLC0415
        get_or_create_purse,
        get_or_create_treasury,
        transfer,
    )

    purse = get_or_create_purse(sheet)
    terms = (
        ContractTerm.objects.filter(
            contract__formality=ContractFormality.NOTARIZED,
            contract__status=ContractStatus.ACTIVE,
            recurring=False,
            fulfilled=False,
        )
        .select_related("contract")
        .order_by("id")
    )
    for term in terms:
        contract = term.contract
        deceased_is_proposer = (
            contract.proposer_persona is not None
            and contract.proposer_persona.character_sheet_id == sheet.pk
        )
        deceased_is_counterparty = (
            contract.counterparty_persona is not None
            and contract.counterparty_persona.character_sheet_id == sheet.pk
        )
        payer_is_deceased = (term.payer_is_proposer and deceased_is_proposer) or (
            not term.payer_is_proposer and deceased_is_counterparty
        )
        if not payer_is_deceased:
            continue
        purse.refresh_from_db()
        payable = min(term.amount, purse.balance)
        if payable <= 0:
            continue
        payee_persona = (
            contract.counterparty_persona if term.payer_is_proposer else contract.proposer_persona
        )
        payee_org = (
            contract.counterparty_organization
            if term.payer_is_proposer
            else contract.proposer_organization
        )
        kwargs = {}
        if payee_persona is not None:
            kwargs["to_purse"] = get_or_create_purse(payee_persona.character_sheet)
        elif payee_org is not None:
            kwargs["to_treasury"] = get_or_create_treasury(payee_org)
        transfer(
            amount=payable,
            reason=f"estate debt settlement (contract {contract.pk})",
            from_purse=purse,
            **kwargs,
        )
        if payable == term.amount:
            term.fulfilled = True
            term.save(update_fields=["fulfilled"])

    for building in Building.objects.filter(
        owner_persona__character_sheet=sheet, upkeep_arrears__gt=0
    ):
        purse.refresh_from_db()
        payable = min(building.upkeep_arrears, purse.balance)
        if payable <= 0:
            break
        transfer(
            amount=payable,
            reason=f"estate arrears settlement (building {building.pk})",
            from_purse=purse,
        )
        building.upkeep_arrears -= payable
        building.save(update_fields=["upkeep_arrears"])


def _deliver_bequest(  # noqa: PLR0911 - one return per bequest kind, deliberately flat
    sheet, bequest, heir_persona, heir_org
) -> int | None:
    """Deliver one line; invalid/refusing recipients fall through the heir chain.

    Returns the delivered item id for SPECIFIC_ITEM lines (so the sweep can
    skip it), else None.
    """
    from world.currency.services import get_or_create_purse  # noqa: PLC0415

    recipient_persona = bequest.recipient_persona
    recipient_org = bequest.recipient_organization

    if bequest.kind == BequestKind.SPECIFIC_ITEM:
        item = bequest.item
        if item is None or item.holder_character_sheet_id != sheet.pk:
            return None  # ademption — the estate no longer owns it
        target = (
            recipient_persona
            if _persona_can_receive_item(recipient_persona, item)
            else (heir_persona if _persona_can_receive_item(heir_persona, item) else None)
        )
        if target is None:
            _clear_item_ownership(item, sheet)
        else:
            _flip_item(item, sheet, target)
        return item.pk

    if bequest.kind in (BequestKind.COIN_AMOUNT, BequestKind.ALL_COIN):
        purse = get_or_create_purse(sheet)
        purse.refresh_from_db()
        amount = bequest.amount if bequest.kind == BequestKind.COIN_AMOUNT else purse.balance
        payable = min(amount, purse.balance)
        if payable <= 0:
            return None
        _deliver_coin(sheet, payable, recipient_persona, recipient_org, heir_persona, heir_org)
        return None

    if bequest.kind == BequestKind.BUILDING:
        if bequest.building is None:
            return None
        _deliver_building(
            sheet, bequest.building, recipient_persona, recipient_org, heir_persona, heir_org
        )
        return None

    if bequest.kind == BequestKind.BUSINESS:
        if bequest.business is None:
            return None
        _deliver_business(sheet, bequest.business, recipient_persona, heir_persona)
        return None

    return None  # RESIDUARY is handled by the sweep


def _deliver_coin(  # noqa: PLR0913 - recipient pair + heir pair are co-equal by design
    sheet, amount, recipient_persona, recipient_org, heir_persona, heir_org
):
    from world.currency.services import (  # noqa: PLC0415
        get_or_create_purse,
        get_or_create_treasury,
        transfer,
    )

    purse = get_or_create_purse(sheet)
    if recipient_org is not None:
        transfer(
            amount=amount,
            reason="estate bequest",
            from_purse=purse,
            to_treasury=get_or_create_treasury(recipient_org),
        )
        return
    target = recipient_persona if _persona_recipient_is_valid(recipient_persona) else heir_persona
    if target is not None:
        transfer(
            amount=amount,
            reason="estate bequest",
            from_purse=purse,
            to_purse=get_or_create_purse(target.character_sheet),
        )
    elif heir_org is not None:
        transfer(
            amount=amount,
            reason="estate escheat",
            from_purse=purse,
            to_treasury=get_or_create_treasury(heir_org),
        )
    # No heir at all: coin stays in the dead purse (settlement without assets
    # never reaches here; with assets the PARK guard fired earlier).


def _deliver_building(  # noqa: PLR0913 - recipient pair + heir pair are co-equal by design
    sheet, building, recipient_persona, recipient_org, heir_persona, heir_org
):
    from world.locations.services import transfer_ownership  # noqa: PLC0415

    if building.owner_persona is None or building.owner_persona.character_sheet_id != sheet.pk:
        return  # ademption — no longer the estate's
    target_persona = recipient_persona if _persona_recipient_is_valid(recipient_persona) else None
    target_org = recipient_org
    if target_persona is None and target_org is None:
        target_persona, target_org = heir_persona, heir_org
    if target_persona is None and target_org is None:
        return
    building.owner_persona = target_persona  # None for org owners (prestige is persona-scoped)
    building.save(update_fields=["owner_persona"])
    transfer_ownership(
        area=building.area,
        to_persona=target_persona,
        to_organization=target_org,
        notes="estate transfer (#1985)",
    )


def _deliver_business(sheet, business, recipient_persona, heir_persona):
    if business.owner_persona.character_sheet_id != sheet.pk:
        return  # ademption
    target = recipient_persona if _persona_recipient_is_valid(recipient_persona) else heir_persona
    if target is not None:
        business.owner_persona = target
        business.save(update_fields=["owner_persona"])
    else:
        # Org heirs / escheat can't hold a Business (persona-scoped) — it winds down.
        business.active = False
        business.save(update_fields=["active"])


def _flip_item(item, sheet, target_persona) -> None:
    from world.items.constants import OwnershipEventType  # noqa: PLC0415
    from world.items.models import OwnershipEvent  # noqa: PLC0415

    target_sheet = target_persona.character_sheet
    item.holder_character_sheet = target_sheet
    item.save(update_fields=["holder_character_sheet"])
    OwnershipEvent.objects.create(
        item_instance=item,
        event_type=OwnershipEventType.INHERITED,
        from_character_sheet=sheet,
        to_character_sheet=target_sheet,
        from_persona_display=sheet.primary_persona,
        to_persona_display=target_persona,
    )


def _clear_item_ownership(item, sheet) -> None:
    """Escheat / no valid holder: the record clears — the item is free loot."""
    from world.items.constants import OwnershipEventType  # noqa: PLC0415
    from world.items.models import OwnershipEvent  # noqa: PLC0415

    item.holder_character_sheet = None
    item.save(update_fields=["holder_character_sheet"])
    OwnershipEvent.objects.create(
        item_instance=item,
        event_type=OwnershipEventType.INHERITED,
        from_character_sheet=sheet,
        to_character_sheet=None,
        from_persona_display=sheet.primary_persona,
        to_persona_display=None,
    )


def _sweep_residuary(sheet, heir_persona, heir_org, delivered_item_ids) -> None:
    """Everything unbequeathed lands on the estate heir (spec Decision 6/8)."""
    from world.currency.models import Business  # noqa: PLC0415
    from world.currency.services import get_or_create_purse  # noqa: PLC0415
    from world.items.models import ItemInstance  # noqa: PLC0415
    from world.locations.models import LocationOwnership  # noqa: PLC0415
    from world.locations.services import transfer_ownership  # noqa: PLC0415

    items = ItemInstance.objects.filter(holder_character_sheet=sheet).exclude(
        pk__in=delivered_item_ids
    )
    for item in items:
        if heir_persona is not None and _persona_can_receive_item(heir_persona, item):
            _flip_item(item, sheet, heir_persona)
        else:
            # Org heirs and escheat can't hold items — free loot (Decision 6c).
            _clear_item_ownership(item, sheet)

    purse = get_or_create_purse(sheet)
    purse.refresh_from_db()
    if purse.balance > 0 and (heir_persona is not None or heir_org is not None):
        _deliver_coin(sheet, purse.balance, heir_persona, heir_org, heir_persona, heir_org)

    for ownership in LocationOwnership.objects.filter(
        holder_persona__character_sheet=sheet, ended_at__isnull=True
    ).select_related("area", "room_profile"):
        if heir_persona is None and heir_org is None:
            continue
        transfer_ownership(
            area=ownership.area,
            room_profile=ownership.room_profile,
            to_persona=heir_persona,
            to_organization=heir_org if heir_persona is None else None,
            notes="estate transfer (#1985)",
        )

    from world.buildings.models import Building  # noqa: PLC0415

    for building in Building.objects.filter(owner_persona__character_sheet=sheet):
        building.owner_persona = heir_persona
        building.save(update_fields=["owner_persona"])

    for business in Business.objects.filter(owner_persona__character_sheet=sheet, active=True):
        _deliver_business(sheet, business, None, heir_persona)


def _substitute_contracts(sheet, heir_persona, heir_org) -> None:
    """Owed-to-the-deceased survives: the heir steps into the contract seat.

    NOTARIZED + ACTIVE only (HANDSHAKE is RP-only by #928 design). With no
    heir at all the contract cancels — nobody remains to hold the seat.
    """
    from world.currency.constants import ContractFormality, ContractStatus  # noqa: PLC0415
    from world.currency.models import Contract  # noqa: PLC0415

    contracts = Contract.objects.filter(
        formality=ContractFormality.NOTARIZED, status=ContractStatus.ACTIVE
    )
    for contract in contracts:
        update_fields = []
        for side in ("proposer", "counterparty"):
            persona_field = f"{side}_persona"
            persona = getattr(contract, persona_field)
            if persona is None or persona.character_sheet_id != sheet.pk:
                continue
            if heir_persona is not None:
                setattr(contract, persona_field, heir_persona)
                update_fields.append(persona_field)
            elif heir_org is not None:
                setattr(contract, persona_field, None)
                setattr(contract, f"{side}_organization", heir_org)
                update_fields.extend([persona_field, f"{side}_organization"])
            else:
                contract.status = ContractStatus.CANCELLED
                update_fields.append("status")
        if update_fields:
            contract.save(update_fields=sorted(set(update_fields)))


def _end_residency_and_work(sheet) -> None:
    from world.currency.models import CharacterEmployment  # noqa: PLC0415
    from world.locations.models import LocationTenancy  # noqa: PLC0415
    from world.locations.services import end_tenancy  # noqa: PLC0415

    for tenancy in LocationTenancy.objects.filter(
        tenant_persona__character_sheet=sheet, ends_at__isnull=True
    ):
        end_tenancy(tenancy)
    CharacterEmployment.objects.filter(character_sheet=sheet, active=True).update(active=False)


def _mint_claims(sheet, settlement, bequests, heir_persona, heir_org) -> None:
    """Items stolen from the deceased, never recovered: the grievance passes on.

    A stolen item that was ALSO bequeathed by name sends its claim to the
    named recipient (the sword was left to you — go get it); everything else
    goes to the estate heir. Holders are never notified (leak table).
    """
    from world.items.constants import OwnershipEventType  # noqa: PLC0415
    from world.items.models import ItemInstance, OwnershipEvent  # noqa: PLC0415
    from world.items.services.provenance import stolen_victim  # noqa: PLC0415

    named = {
        b.item_id: b.recipient_persona
        for b in bequests
        if b.kind == BequestKind.SPECIFIC_ITEM and b.item_id is not None
    }
    item_ids = (
        OwnershipEvent.objects.filter(
            event_type=OwnershipEventType.STOLEN, from_character_sheet=sheet
        )
        .values_list("item_instance_id", flat=True)
        .distinct()
    )
    for item in ItemInstance.objects.filter(pk__in=list(item_ids)):
        if stolen_victim(item) != sheet:
            continue
        claimant_persona = named.get(item.pk)
        if claimant_persona is None or not _persona_recipient_is_valid(claimant_persona):
            claimant_persona = heir_persona
        claimant_org = heir_org if claimant_persona is None else None
        if claimant_persona is None and claimant_org is None:
            continue
        EstateClaim.objects.create(
            settlement=settlement,
            item=item,
            claimant_persona=claimant_persona,
            claimant_organization=claimant_org,
        )


def _notify_executors(settlement: EstateSettlement) -> None:
    """Tell each executor the window opened — best-effort, never blocks death."""
    will = Will.objects.filter(character_sheet=settlement.character_sheet).first()
    if will is None:
        return
    deceased_name = str(settlement.character_sheet)
    # PLACEHOLDER player-facing copy — Apostate rewrite pending (#1985).
    body = (
        f"You are named an executor of {deceased_name}'s will. Their estate may be "
        f"settled at a will-reading or funeral; if neither happens it settles on its own."
    )
    for executor in WillExecutor.objects.filter(will=will).select_related("persona"):
        character = executor.persona.character_sheet.character
        try:
            character.msg(body)
        except Exception:
            logger.exception("executor notify character.msg failed for %s", executor.pk)
        account = character.db_account
        if account is None:
            continue
        payload = {"deceased": deceased_name, "deadline": settlement.deadline.isoformat()}
        try:
            account.msg(estate_settlement_opened=((), payload))
        except Exception:
            logger.exception("estate_settlement_opened push failed for %s", account.pk)

"""Estate settlement services (#1985).

``open_settlement`` is called from the single death writer
(``world.vitals.services._mark_dead``); ``execute_settlement`` is the ONE
idempotent execution path all three doors call (funeral finish, executor
will-reading, deadline sweeper). Spec: issue #1985 body.
"""

from datetime import timedelta
import logging

from django.utils import timezone

from world.character_sheets.models import CharacterSheet
from world.estates.models import EstateSettlement, Will, WillExecutor, get_estate_config

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

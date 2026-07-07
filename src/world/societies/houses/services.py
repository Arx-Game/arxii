"""Houses services (#1884): naming, recognition, succession, pacts, domains.

Houses ARE Organizations; kinship truth lives in ``world.roster`` (#2062) and
these services read it through the same visibility layer (``OMNISCIENT`` for
mechanical derivations — succession and recognition run on the *true public
record*, not any one viewer's knowledge).

Anti-dependency tenet: everything here is the automated floor. Heads of house
create opportunities on top of it; nothing gates on a head being online.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.roster.constants import MembershipBasis
from world.roster.models import Family, FamilyMembership, Kinsperson, Union
from world.roster.services.kinship import (
    OMNISCIENT,
    add_membership,
    children_of,
    parents_of,
)
from world.societies.houses.constants import (
    PactCommitmentKind,
    PactDissolutionReason,
    RecognitionRuleKind,
    SuccessionDerivation,
    SuccessionOrdering,
)
from world.societies.houses.models import (
    Domain,
    DomainHolding,
    FealtyEdge,
    HoldingKind,
    HouseRecognitionRule,
    MarriagePact,
    NobiliaryParticle,
    PactCommitment,
    SuccessionLaw,
    Title,
)
from world.societies.models import Organization

if TYPE_CHECKING:
    from world.areas.models import Area
    from world.currency.models import OrgObligation
    from world.realms.models import Realm

_FEMALE_GENDER_KEY = "female"
_MALE_GENDER_KEY = "male"


class HousesServiceError(Exception):
    """Raised on invalid house operations; carries a player-safe message."""

    def __init__(self, message: str, *, user_message: str = "") -> None:
        super().__init__(message)
        self.user_message = user_message or "That cannot be done."


# ---------------------------------------------------------------------------
# Naming — First + nobiliary particle + House (#1884)
# ---------------------------------------------------------------------------


def house_for_family(family: Family | None) -> Organization | None:
    """The Organization rooted in ``family``, if one exists."""
    if family is None:
        return None
    return family.organizations.first()


def realm_for_house(house: Organization | None) -> Realm | None:
    """The realm a house sits in, via its society."""
    if house is None or house.society is None:
        return None
    return house.society.realm


def full_display_name(person: Kinsperson) -> str:
    """``first_name [particle] house_name`` when the person has a housed family.

    The particle comes from the family's realm × family-type row (e.g.
    former-Luxen houses carry "du"); with no particle row, the plain
    ``first family`` form renders. People without a housed family keep their
    bare node name.
    """
    base = person.display_name
    first = base.split()[0] if base else ""
    family = person.family
    if family is None or not first:
        return base
    realm = realm_for_house(house_for_family(family))
    particle = ""
    if realm is not None:
        row = NobiliaryParticle.objects.filter(realm=realm, family_type=family.family_type).first()
        if row is not None:
            particle = row.particle
    pieces = [first, particle, family.name] if particle else [first, family.name]
    return " ".join(pieces)


# ---------------------------------------------------------------------------
# Recognition — a realm's law applied to a birth (#1884)
# ---------------------------------------------------------------------------


def _edge_in_wedlock(edge) -> bool:
    union = edge.born_within_union
    return union is not None and union.kind.confers_wedlock


def _parent_gender_key(parent: Kinsperson) -> str:
    if parent.gender is None:
        return ""
    return parent.gender.key


def recognize_birth(child: Kinsperson) -> FamilyMembership | None:
    """Apply the parents' realms' recognition rules to a newborn node.

    Walks the child's public-record true parent edges; the first rule that
    fires enrolls the child (``BORN`` basis, primary). Umbral matrilineality:
    a noblewoman's in-wedlock children auto-recognize; out of wedlock it is
    the mother's option (``acknowledge_into_family`` is that option's seam,
    so this returns ``None`` rather than deciding for her). Inferna: a female
    titleholder's children by consorts are recognized regardless of wedlock.
    """
    if child.family is not None:
        return None
    for edge in parents_of(child, OMNISCIENT):
        if not (edge.is_public_record and edge.is_true):
            continue
        parent = edge.parent
        family = parent.family
        house = house_for_family(family)
        realm = realm_for_house(house)
        if family is None or realm is None:
            continue
        rules = {r.kind for r in HouseRecognitionRule.objects.filter(realm=realm)}
        gender = _parent_gender_key(parent)
        in_wedlock = _edge_in_wedlock(edge)
        matrilineal_hit = (
            RecognitionRuleKind.MATRILINEAL_AUTO_WEDLOCK in rules
            and gender == _FEMALE_GENDER_KEY
            and in_wedlock
        )
        patrilineal_hit = (
            RecognitionRuleKind.PATRILINEAL_AUTO_WEDLOCK in rules
            and gender == _MALE_GENDER_KEY
            and in_wedlock
        )
        consort_hit = (
            RecognitionRuleKind.CONSORT_CHILDREN_ENNOBLED in rules
            and gender == _FEMALE_GENDER_KEY
            and Title.objects.filter(holder=parent).exists()
        )
        if matrilineal_hit or patrilineal_hit or consort_hit:
            return add_membership(
                kinsperson=child,
                family=family,
                basis=MembershipBasis.BORN,
                is_primary=True,
            )
    return None


def acknowledge_into_family(child: Kinsperson, family: Family) -> FamilyMembership:
    """The mother's-option / legitimization seam: explicit recognition.

    Used where the realm rule leaves recognition to a person (Umbral
    out-of-wedlock) or a house legitimizes later.
    """
    if child.family_id == family.pk:
        msg = f"kinsperson {child.pk} already belongs to family {family.pk}"
        raise HousesServiceError(msg, user_message="They already belong to that family.")
    return add_membership(
        kinsperson=child,
        family=family,
        basis=MembershipBasis.LEGITIMIZED,
        is_primary=True,
    )


# ---------------------------------------------------------------------------
# Succession — candidate derivation per law (#1884)
# ---------------------------------------------------------------------------

GiftedPowerRater = Callable[[Kinsperson], int]

_gifted_power_rater: GiftedPowerRater | None = None


def register_gifted_power_rater(rater: GiftedPowerRater) -> None:
    """Plug in the real 'most powerful Gifted' measure when magic exposes one.

    PLACEHOLDER default: with no rater registered, MOST_POWERFUL_GIFTED
    ordering falls back to eldest-first — never a hardcoded power formula.
    """
    global _gifted_power_rater  # noqa: PLW0603 — module-level registry, mirrors projects handlers
    _gifted_power_rater = rater


def resolve_succession_law(title: Title) -> SuccessionLaw | None:
    """Per-title override first (Imperial Tanistry), else the house default."""
    if title.succession_law is not None:
        return title.succession_law
    if title.house is not None:
        return title.house.default_succession_law
    return None


def _living_family_members(family: Family) -> list[Kinsperson]:
    memberships = FamilyMembership.objects.filter(
        family=family, ended_at__isnull=True
    ).select_related("kinsperson")
    return [m.kinsperson for m in memberships if not m.kinsperson.is_deceased]


def _order_candidates(candidates: list[Kinsperson], ordering: str) -> list[Kinsperson]:
    if ordering == SuccessionOrdering.MOST_POWERFUL_GIFTED and _gifted_power_rater is not None:
        return sorted(candidates, key=_gifted_power_rater, reverse=True)
    return sorted(candidates, key=lambda p: p.age or 0, reverse=True)


def derive_succession_candidates(  # noqa: C901 — one branch per derivation law, irreducible
    title: Title,
) -> list[Kinsperson]:
    """The ordered candidate list for ``title`` under its resolved law.

    Runs on the omniscient public record (succession is a legal fact, not a
    viewer's belief). TANISTRY_ELECTION returns the eligible pool unordered —
    the election itself is play, not a formula. An empty list means a
    succession crisis: story fuel, deliberately not auto-resolved.
    """
    law = resolve_succession_law(title)
    if law is None:
        return []
    if law.derivation == SuccessionDerivation.CHOSEN_HEIR:
        heir = law.chosen_heir
        return [heir] if heir is not None and not heir.is_deceased else []

    family = title.house.family if title.house is not None else None
    if law.derivation == SuccessionDerivation.TANISTRY_ELECTION:
        return _living_family_members(family) if family is not None else []

    holder = title.holder
    if holder is None:
        # Vacant seat with no line to walk: the recognized family pool, ordered.
        pool = _living_family_members(family) if family is not None else []
        return _order_candidates(pool, law.ordering_rule)

    candidates: list[Kinsperson] = []
    for edge in children_of(holder, OMNISCIENT):
        if not (edge.is_public_record and edge.is_true):
            continue
        child = edge.child
        if child.is_deceased:
            continue
        if law.require_wedlock and not _edge_in_wedlock(edge):
            continue
        if law.derivation == SuccessionDerivation.MATRILINEAL_RECOGNITION and (
            family is None or child.family_id != family.pk
        ):
            continue
        if child not in candidates:
            candidates.append(child)

    ordered = _order_candidates(candidates, law.ordering_rule)
    if law.derivation == SuccessionDerivation.FEMALE_LINE_CONSORTS_ENNOBLED or (
        law.enatic_tiebreak
    ):
        # Enatic preference: daughters ahead of sons at equal age (stable sort).
        ordered.sort(key=lambda p: _parent_gender_key(p) != _FEMALE_GENDER_KEY)
    return ordered


@transaction.atomic
def pass_title(title: Title, *, to_holder: Kinsperson) -> Title:
    """Seat ``to_holder`` on ``title`` (succession applied, or staff fiat)."""
    if to_holder.is_deceased:
        msg = f"kinsperson {to_holder.pk} is deceased"
        raise HousesServiceError(msg, user_message="The dead hold no titles.")
    title.holder = to_holder
    title.save(update_fields=["holder"])
    return title


# ---------------------------------------------------------------------------
# Fealty (#1884)
# ---------------------------------------------------------------------------


def swear_fealty(*, vassal: Organization, liege: Organization) -> FealtyEdge:
    """Bind ``vassal`` under ``liege``, refusing cycles (the tree stays a tree)."""
    if vassal.pk == liege.pk:
        msg = "an org cannot swear fealty to itself"
        raise HousesServiceError(msg, user_message="A house cannot swear fealty to itself.")
    seen: set[int] = {vassal.pk}
    probe: Organization | None = liege
    while probe is not None:
        if probe.pk in seen:
            msg = f"fealty cycle: {vassal.pk} -> {liege.pk}"
            raise HousesServiceError(msg, user_message="That oath would make a circle of lieges.")
        seen.add(probe.pk)
        edge = FealtyEdge.objects.filter(vassal=probe).select_related("liege").first()
        probe = edge.liege if edge is not None else None
    existing = FealtyEdge.objects.filter(vassal=vassal).first()
    if existing is not None:
        existing.delete()
    return FealtyEdge.objects.create(vassal=vassal, liege=liege)


def vassals_of(liege: Organization, *, recursive: bool = False) -> list[Organization]:
    """Direct vassals, or the whole subtree with ``recursive=True`` (BFS)."""
    frontier = [liege]
    found: list[Organization] = []
    seen: set[int] = {liege.pk}
    while frontier:
        current = frontier.pop(0)
        edges = FealtyEdge.objects.filter(liege=current).select_related("vassal")
        for edge in edges:
            if edge.vassal_id in seen:
                continue
            seen.add(edge.vassal_id)
            found.append(edge.vassal)
            if recursive:
                frontier.append(edge.vassal)
    return found


def liege_chain_of(vassal: Organization) -> list[Organization]:
    """The chain of lieges from ``vassal`` upward to the crown."""
    chain: list[Organization] = []
    seen: set[int] = {vassal.pk}
    probe = FealtyEdge.objects.filter(vassal=vassal).select_related("liege").first()
    while probe is not None and probe.liege_id not in seen:
        chain.append(probe.liege)
        seen.add(probe.liege_id)
        probe = FealtyEdge.objects.filter(vassal=probe.liege).select_related("liege").first()
    return chain


# ---------------------------------------------------------------------------
# Marriage pacts — union-bound, coded commitments (#1884)
# ---------------------------------------------------------------------------


@dataclass
class CommitmentSpec:
    """One coded commitment to record (and, where coded, execute) at signing."""

    kind: str
    owed_by_senior: bool = True
    committed_person: Kinsperson | None = None
    amount: int = 0
    percent: int = 0
    notes: str = ""


def _pact_parties(
    pact_or_spec_owed_by_senior: bool,
    senior: Organization,
    junior: Organization,
) -> tuple[Organization, Organization]:
    payer = senior if pact_or_spec_owed_by_senior else junior
    payee = junior if pact_or_spec_owed_by_senior else senior
    return payer, payee


def _execute_dowry(spec: CommitmentSpec, payer: Organization, payee: Organization) -> None:
    from world.currency.services import get_or_create_treasury, transfer  # noqa: PLC0415

    transfer(
        amount=spec.amount,
        reason=f"Dowry: {payer.name} to {payee.name}",
        from_treasury=get_or_create_treasury(payer),
        to_treasury=get_or_create_treasury(payee),
    )


def _execute_subsidy(
    spec: CommitmentSpec, payer: Organization, payee: Organization
) -> OrgObligation:
    from world.currency.models import OrgObligation  # noqa: PLC0415

    return OrgObligation.objects.create(
        from_organization=payer,
        to_organization=payee,
        name=f"Marriage subsidy: {payer.name} to {payee.name}",
        percent=spec.percent,
    )


def _execute_residency(spec: CommitmentSpec, senior: Organization) -> None:
    person = spec.committed_person
    if person is None:
        msg = "RESIDENCY commitment needs a committed_person"
        raise HousesServiceError(msg, user_message="Residency names who moves.")
    if senior.family is None:
        msg = f"senior house {senior.pk} has no family to marry into"
        raise HousesServiceError(msg, user_message="That house has no family line.")
    add_membership(
        kinsperson=person,
        family=senior.family,
        basis=MembershipBasis.MARRIED_IN,
        is_primary=True,
    )


@transaction.atomic
def sign_marriage_pact(
    *,
    union: Union,
    senior_house: Organization,
    junior_house: Organization,
    commitments: list[CommitmentSpec] | None = None,
) -> MarriagePact:
    """Record the pact and fire its coded commitments.

    DOWRY moves treasury coin now; SUBSIDY materializes a recurring
    ``OrgObligation`` (settled by the existing weekly obligations pass);
    RESIDENCY marries the junior spouse into the senior family (name change
    via the surname denorm). CRISIS_RESPONSE and CUSTOM are recorded and
    fire socially — breach machinery watches them all.
    """
    if senior_house.pk == junior_house.pk:
        msg = "a pact needs two houses"
        raise HousesServiceError(msg, user_message="A house cannot ally with itself.")
    if MarriagePact.objects.filter(union=union).exists():
        msg = f"union {union.pk} already has a pact"
        raise HousesServiceError(msg, user_message="That union is already under pact.")
    pact = MarriagePact.objects.create(
        union=union,
        senior_house=senior_house,
        junior_house=junior_house,
    )
    for spec in commitments or []:
        payer, payee = _pact_parties(spec.owed_by_senior, senior_house, junior_house)
        obligation = None
        if spec.kind == PactCommitmentKind.DOWRY:
            _execute_dowry(spec, payer, payee)
        elif spec.kind == PactCommitmentKind.SUBSIDY:
            obligation = _execute_subsidy(spec, payer, payee)
        elif spec.kind == PactCommitmentKind.RESIDENCY:
            _execute_residency(spec, senior_house)
        PactCommitment.objects.create(
            pact=pact,
            kind=spec.kind,
            owed_by_senior=spec.owed_by_senior,
            committed_person=spec.committed_person,
            amount=spec.amount,
            percent=spec.percent,
            obligation=obligation,
            notes=spec.notes,
        )
    return pact


@transaction.atomic
def dissolve_pact(pact: MarriagePact, *, reason: str) -> MarriagePact:
    """End the pact (CK2 rule: it dies with the union) and stop its machinery."""
    if pact.dissolved_at is not None:
        return pact
    pact.dissolved_at = timezone.now()
    pact.dissolution_reason = reason
    pact.save(update_fields=["dissolved_at", "dissolution_reason"])
    for commitment in pact.commitments.select_related("obligation"):
        if commitment.obligation is not None and commitment.obligation.active:
            commitment.obligation.active = False
            commitment.obligation.save(update_fields=["active"])
    return pact


def handle_death_for_pacts(person: Kinsperson) -> list[MarriagePact]:
    """A spouse died: every active pact bound to their unions dies instantly.

    Call seam: the death/lifecycle flow (roster cannot import societies, so
    the action layer that marks a character dead calls this explicitly).
    """
    pacts = MarriagePact.objects.filter(
        union__members=person, dissolved_at__isnull=True
    ).select_related("union")
    return [dissolve_pact(pact, reason=PactDissolutionReason.DEATH) for pact in pacts]


def breach_commitment(commitment: PactCommitment) -> PactCommitment:
    """Mark a commitment broken: machinery stops; the scandal seam fires.

    The wired scandal channel is Secrets → tidings: when the breaching side
    has a sheeted principal, staff mint the scandal secret through the normal
    ``author_secret`` flow (breach is social dynamite, not an auto-formula).
    This service records the mechanical fact and stops any obligation.
    """
    if commitment.breached_at is not None:
        return commitment
    commitment.breached_at = timezone.now()
    commitment.save(update_fields=["breached_at"])
    if commitment.obligation is not None and commitment.obligation.active:
        commitment.obligation.active = False
        commitment.obligation.save(update_fields=["active"])
    return commitment


# ---------------------------------------------------------------------------
# Domains — abstract areas feeding the org books (#1884, #930 ruling)
# ---------------------------------------------------------------------------


def create_domain(*, area: Area, name: str, owner_org: Organization) -> Domain:
    """Decorate a DOMAIN-level area as a landholding of ``owner_org``."""
    if Domain.objects.filter(area=area).exists():
        msg = f"area {area.pk} is already a domain"
        raise HousesServiceError(msg, user_message="That land is already held.")
    return Domain.objects.create(area=area, name=name, owner_org=owner_org)


def add_holding(*, domain: Domain, kind: HoldingKind, name: str = "") -> DomainHolding:
    """Attach a working holding, materializing its income stream.

    The stream is the existing ``OrgIncomeStream`` spine — collection,
    graft, and settlement all reuse the audited currency pipeline untouched.
    """
    from world.currency.models import OrgIncomeStream  # noqa: PLC0415

    stream_name = name or f"{domain.name}: {kind.name}"
    stream = OrgIncomeStream.objects.create(
        organization=domain.owner_org,
        name=stream_name,
        kind=kind.stream_kind,
        gross_amount=kind.base_gross,
        area=domain.area,
    )
    return DomainHolding.objects.create(
        domain=domain,
        kind=kind,
        name=stream_name,
        income_stream=stream,
    )


# ---------------------------------------------------------------------------
# Domain improvement projects — the projects framework does the lifting
# ---------------------------------------------------------------------------

_COPPERS_PER_PROGRESS_POINT = 100
IMPROVEMENT_PROJECT_DAYS = 60  # PLACEHOLDER pacing


def start_domain_improvement(  # noqa: PLR0913 — keyword-only; each arg is a distinct term
    *,
    domain: Domain,
    persona,
    cost: int,
    gross_increase: int = 0,
    prosperity_increase: int = 0,
    holding: DomainHolding | None = None,
) -> object:
    """Commission an improvement: fund it, check it forward, reap the upgrade.

    Reuses the projects framework end-to-end (donations at 100c/point, AP
    check contributions to speed it — the #1930 preparation precedent). On
    resolution the kind handler applies ``gross_increase`` to the holding's
    stream and ``prosperity_increase`` to the domain; a badly failed outcome
    opens a ``DomainCrisis`` instead (story fuel, never a silent no-op).
    """
    from datetime import timedelta  # noqa: PLC0415

    from world.projects.constants import (  # noqa: PLC0415
        CompletionMode,
        ProjectKind,
        ProjectStatus,
    )
    from world.projects.models import Project  # noqa: PLC0415
    from world.societies.houses.models import DomainImprovementDetails  # noqa: PLC0415

    if holding is not None and holding.domain_id != domain.pk:
        msg = f"holding {holding.pk} is not part of domain {domain.pk}"
        raise HousesServiceError(msg, user_message="That holding is not on this domain.")
    if gross_increase and holding is None:
        msg = "a gross increase needs a target holding"
        raise HousesServiceError(msg, user_message="Choose which holding to improve.")
    now = timezone.now()
    project = Project.objects.create(
        kind=ProjectKind.DOMAIN_IMPROVEMENT,
        completion_mode=CompletionMode.SINGLE_THRESHOLD,
        status=ProjectStatus.ACTIVE,
        owner_persona=persona,
        started_at=now,
        time_limit=now + timedelta(days=IMPROVEMENT_PROJECT_DAYS),
        threshold_target=max(1, cost // _COPPERS_PER_PROGRESS_POINT),
        description=f"Improvement of {domain.name}",
    )
    DomainImprovementDetails.objects.create(
        project=project,
        domain=domain,
        holding=holding,
        gross_increase=gross_increase,
        prosperity_increase=prosperity_increase,
    )
    return project


def complete_domain_improvement(project) -> None:
    """Kind handler for DOMAIN_IMPROVEMENT (registered at societies app-ready).

    Success applies the improvement; a failed resolution (negative outcome
    tier) opens a TROUBLE-severity crisis on the domain instead.
    """
    from world.societies.houses.constants import DomainCrisisSeverity  # noqa: PLC0415
    from world.societies.houses.models import (  # noqa: PLC0415
        DomainCrisis,
        DomainImprovementDetails,
    )

    details = (
        DomainImprovementDetails.objects.filter(project=project)
        .select_related("domain", "holding__income_stream")
        .first()
    )
    if details is None or details.applied_at is not None:
        return
    outcome = project.outcome_tier
    failed = outcome is not None and outcome.success_level < 0
    if failed:
        DomainCrisis.objects.create(
            domain=details.domain,
            severity=DomainCrisisSeverity.TROUBLE,
            description=(
                "PLACEHOLDER: the improvement works went badly wrong — "
                "spoiled materials, angry laborers, a debt of favors."
            ),
        )
    else:
        domain = details.domain
        if details.prosperity_increase:
            domain.prosperity += details.prosperity_increase
            domain.save(update_fields=["prosperity"])
        if details.gross_increase and details.holding is not None:
            stream = details.holding.income_stream
            stream.gross_amount += details.gross_increase
            stream.save(update_fields=["gross_amount"])
    details.applied_at = timezone.now()
    details.save(update_fields=["applied_at"])


# ---------------------------------------------------------------------------
# House channel — the household's line, vassal cascade included (#1884)
# ---------------------------------------------------------------------------


def _house_audience(house: Organization, *, include_vassals: bool) -> list:
    """Accounts currently playing an active member of the house (and, with
    the cascade, of its vassal houses) — the channel's rightful listeners."""
    from evennia.accounts.models import AccountDB  # noqa: PLC0415

    orgs = [house, *(vassals_of(house, recursive=True) if include_vassals else [])]
    membership_path = (
        "player_data__tenures__roster_entry__character_sheet__personas__organization_memberships"
    )
    return list(
        AccountDB.objects.filter(
            **{
                "player_data__tenures__end_date__isnull": True,
                f"{membership_path}__organization__in": orgs,
                f"{membership_path}__left_at__isnull": True,
                f"{membership_path}__exiled_at__isnull": True,
            }
        ).distinct()
    )


def sync_house_channel(house: Organization, *, include_vassals: bool = True):
    """Create the house channel if needed and connect the current audience.

    Idempotent: run after membership or fealty changes (explicit call, no
    signals). Leaves manual disconnections alone except for members — a
    member is always (re)connected.
    """
    from evennia.comms.models import ChannelDB  # noqa: PLC0415
    from evennia.utils.create import create_channel  # noqa: PLC0415

    key = f"house_{house.pk}"
    channel = ChannelDB.objects.filter(db_key=key).first()
    if channel is None:
        channel = create_channel(
            key,
            aliases=[house.name],
            desc=f"The house line of {house.name} (#1884).",
        )
    for account in _house_audience(house, include_vassals=include_vassals):
        if not channel.has_connection(account):
            channel.connect(account)
    return channel

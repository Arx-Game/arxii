"""House Stature (#3091): perceived-vs-true deterrence services.

True stature = renown + military + economic + allied - crisis penalty,
recomputed weekly. Perceived converges toward true with lag; deaths, pact
changes, surfaced crises and whisper campaigns move it immediately. Bands
are percentile cohorts of (continent x org category); prestige ranks are
contextual across ALL orgs and pay through bounded domain prosperity.

Legend totals ride a Postgres materialized view, so every entry point takes
an injectable ``legend_reader`` (SQLite-tier tests inject a stub).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import models

from world.covenants.constants import CovenantType
from world.covenants.models import Covenant
from world.currency.models import OrganizationTreasury, OrgIncomeStream
from world.military.models import MilitaryUnit
from world.roster.models import FamilyMembership, Kinsperson, Union
from world.scenes.models import Persona
from world.societies.houses.constants import (
    CRISIS_STATURE_PENALTIES,
    GIFTED_RATING_LEVEL_EQUIV,
    GIFTED_RATING_RENOWN,
    INCOME_GROSS_STATURE_WEIGHT,
    PRESTIGE_PROSPERITY_DRIFT_MAX,
    STATURE_ALLY_FACTOR,
    STATURE_CONVERGENCE_RATE,
    STATURE_DEATH_SHOCK_SHARE,
    STATURE_ECONOMIC_WEIGHT,
    STATURE_FAME_WEIGHT,
    STATURE_LEGEND_WEIGHT,
    STATURE_MILITARY_WEIGHT,
    STATURE_RENOWN_WEIGHT,
    STATURE_WHISPER_MAX_DISPLACEMENT,
    TREASURY_STATURE_DIVISOR,
    UNIT_QUALITY_STATURE_MULTIPLIERS,
    StatureShiftCause,
)
from world.societies.houses.models import (
    Domain,
    DomainCrisis,
    HouseStature,
    MarriagePact,
    OrgPrestigeRank,
    PrestigeRankBand,
    StatureBand,
    StatureShift,
    Title,
)
from world.societies.models import Organization, OrganizationMembership
from world.societies.services import get_persona_legend_total

if TYPE_CHECKING:
    from django.db.models import QuerySet

LegendReader = Callable[[Persona], int]


def resilient_legend_reader(persona: Persona) -> int:
    """Legend total, degrading to 0 where the matview is absent.

    The Postgres matview backs this in CI/production; the SQLite fast tier
    has no matview table, and seam callers (death, pacts, crises) must not
    explode there. Tests that care about legend inject their own reader.
    """
    from django.db import OperationalError, ProgrammingError  # noqa: PLC0415

    try:
        return get_persona_legend_total(persona)
    except (OperationalError, ProgrammingError):
        return 0


@dataclass(frozen=True)
class StatureComponents:
    """One org's computed strength, raw per component (#3091)."""

    renown: int
    military: int
    economic: int
    allied: int
    crisis_penalty: int

    @property
    def gross(self) -> int:
        """Weighted own strength before allies and penalty."""
        return round(
            self.renown * STATURE_RENOWN_WEIGHT
            + self.military * STATURE_MILITARY_WEIGHT
            + self.economic * STATURE_ECONOMIC_WEIGHT
        )

    @property
    def true_total(self) -> int:
        return max(0, self.gross + self.allied - self.crisis_penalty)


def persona_renown_score(
    persona: Persona, *, legend_reader: LegendReader = resilient_legend_reader
) -> int:
    """Prestige + weighted fame + weighted legend for one persona."""
    return round(
        persona.total_prestige
        + persona.fame_points * STATURE_FAME_WEIGHT
        + legend_reader(persona) * STATURE_LEGEND_WEIGHT
    )


def kinsperson_renown_score(
    kin: Kinsperson, *, legend_reader: LegendReader = resilient_legend_reader
) -> int:
    """Sheet-bound kin rate from their active persona; sheetless from gifted_rating."""
    if kin.sheet_id is not None:
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        persona = active_persona_for_sheet(kin.sheet)
        if persona is not None:
            return persona_renown_score(persona, legend_reader=legend_reader)
    return kin.gifted_rating * GIFTED_RATING_RENOWN


def landed_orgs() -> QuerySet[Organization]:
    """Orgs owning at least one Domain — the stature-bearing cohort."""
    return Organization.objects.filter(domains__isnull=False).distinct()


def _active_memberships(org: Organization) -> QuerySet[OrganizationMembership]:
    return org.memberships.filter(left_at__isnull=True, exiled_at__isnull=True).select_related(
        "persona", "rank"
    )


def _court_member_personas(org: Organization) -> Iterable[Persona]:
    """Members of COURT covenants led by this org's rank-1 leaders (#3091)."""
    leader_sheet_ids = [
        m.persona.character_sheet_id
        for m in _active_memberships(org)
        if m.rank is not None and m.rank.tier == 1 and m.persona.character_sheet_id is not None
    ]
    if not leader_sheet_ids:
        return []
    courts = Covenant.objects.filter(
        covenant_type=CovenantType.COURT,
        dissolved_at__isnull=True,
        leader_id__in=leader_sheet_ids,
    ).select_related("organization")
    personas: list[Persona] = []
    for court in courts:
        if court.organization_id is None:
            continue
        personas.extend(
            m.persona for m in _active_memberships(court.organization) if m.persona is not None
        )
    return personas


def _house_kin(org: Organization) -> list[Kinsperson]:
    if org.family_id is None:
        return []
    rows = FamilyMembership.objects.filter(
        family_id=org.family_id, ended_at__isnull=True
    ).select_related("kinsperson")
    return [row.kinsperson for row in rows if not row.kinsperson.is_deceased]


def _holds_landed_title(kin: Kinsperson) -> bool:
    return Title.objects.filter(holder=kin, seat_domain__isnull=False).exists()


def _union_membership(
    unions: list[Union], house_ids: set[int], house_kin: list[Kinsperson]
) -> tuple[dict[int, list[int]], dict[int, Kinsperson]]:
    """Union membership via the through table, NEVER prefetch_related("members").

    Kinsperson rows are identity-mapped SharedMemoryModel instances, and
    Django's prefetch grouping stamps the m2m join value ON the instance — a
    person in two unions keeps only the LAST join value, corrupting both
    unions' member lists (found the hard way, #2999).
    """
    pairs = Union.members.through.objects.filter(union__in=unions).values_list(
        "union_id", "kinsperson_id"
    )
    members_by_union: dict[int, list[int]] = {}
    for union_id, kin_id in pairs:
        members_by_union.setdefault(union_id, []).append(kin_id)
    kin_by_id = {
        k.pk: k
        for k in Kinsperson.objects.filter(pk__in={kin_id for _, kin_id in pairs} - house_ids)
    }
    kin_by_id.update({k.pk: k for k in house_kin})
    return members_by_union, kin_by_id


def _union_partner_scores(
    house_kin: list[Kinsperson],
    seen_kin_ids: set[int],
    seen_sheet_ids: set[int],
    *,
    legend_reader: LegendReader,
) -> int:
    """Renown flowing in through unions: marriage full both-ways, consort gated.

    Marriage-class kinds (``contributes_to_origin_house=True``) count the
    outside partner at full share. Consort-class kinds gate on the house-side
    senior holding a landed Title, cap at ``max_concurrent`` per senior
    (earliest unions first), and never flow back to the origin house.
    """
    house_ids = {k.pk for k in house_kin}
    unions = list(
        Union.objects.filter(
            members__pk__in=house_ids, ended_at__isnull=True, kind__stature_share_pct__gt=0
        )
        .select_related("kind")
        .distinct()
    )
    members_by_union, kin_by_id = _union_membership(unions, house_ids, house_kin)
    total = 0
    consorts_per_senior: dict[int, list[Union]] = {}
    for union in unions:
        member_ids = members_by_union.get(union.pk, [])
        inside = [kin_by_id[m] for m in member_ids if m in house_ids and m in kin_by_id]
        outside = [kin_by_id[m] for m in member_ids if m not in house_ids and m in kin_by_id]
        if not inside or not outside:
            continue
        kind = union.kind
        if kind.requires_landed_title:
            seniors = [k for k in inside if _holds_landed_title(k)]
            if not seniors:
                continue
            consorts_per_senior.setdefault(seniors[0].pk, []).append(union)
            continue
        for partner in outside:
            total += _partner_contribution(
                partner, kind.stature_share_pct, seen_kin_ids, seen_sheet_ids, legend_reader
            )
    for unions_for_senior in consorts_per_senior.values():
        ordered = sorted(
            unions_for_senior, key=lambda u: (u.started_at is None, u.started_at, u.pk)
        )
        for union in _capped(ordered):
            for kin_id in members_by_union.get(union.pk, []):
                if kin_id in house_ids or kin_id not in kin_by_id:
                    continue
                total += _partner_contribution(
                    kin_by_id[kin_id],
                    union.kind.stature_share_pct,
                    seen_kin_ids,
                    seen_sheet_ids,
                    legend_reader,
                )
    return total


def _capped(ordered: list[Union]) -> list[Union]:
    cap = ordered[0].kind.max_concurrent if ordered else None
    return ordered if cap is None else ordered[:cap]


def _partner_contribution(
    partner: Kinsperson,
    share_pct: int,
    seen_kin_ids: set[int],
    seen_sheet_ids: set[int],
    legend_reader: LegendReader,
) -> int:
    if partner.pk in seen_kin_ids:
        return 0
    if partner.sheet_id is not None and partner.sheet_id in seen_sheet_ids:
        return 0
    seen_kin_ids.add(partner.pk)
    if partner.sheet_id is not None:
        seen_sheet_ids.add(partner.sheet_id)
    score = kinsperson_renown_score(partner, legend_reader=legend_reader)
    return round(score * share_pct / 100)


def _sum_personas(
    personas: Iterable[Persona],
    seen_persona_ids: set[int],
    seen_sheet_ids: set[int],
    *,
    legend_reader: LegendReader,
) -> int:
    total = 0
    for persona in personas:
        if persona is None or persona.pk in seen_persona_ids:
            continue
        seen_persona_ids.add(persona.pk)
        if persona.character_sheet_id is not None:
            seen_sheet_ids.add(persona.character_sheet_id)
        total += persona_renown_score(persona, legend_reader=legend_reader)
    return total


def _renown_component(org: Organization, *, legend_reader: LegendReader) -> int:
    """Sum the people who stand with the house; each person counts once."""
    seen_persona_ids: set[int] = set()
    seen_sheet_ids: set[int] = set()
    seen_kin_ids: set[int] = set()
    member_personas = [m.persona for m in _active_memberships(org)]
    total = _sum_personas(
        member_personas, seen_persona_ids, seen_sheet_ids, legend_reader=legend_reader
    )
    total += _sum_personas(
        _court_member_personas(org), seen_persona_ids, seen_sheet_ids, legend_reader=legend_reader
    )
    house_kin = _house_kin(org)
    for kin in house_kin:
        if kin.pk in seen_kin_ids:
            continue
        seen_kin_ids.add(kin.pk)
        if kin.sheet_id is not None:
            if kin.sheet_id in seen_sheet_ids:
                continue
            seen_sheet_ids.add(kin.sheet_id)
        total += kinsperson_renown_score(kin, legend_reader=legend_reader)
    total += _union_partner_scores(
        house_kin, seen_kin_ids, seen_sheet_ids, legend_reader=legend_reader
    )
    total += _betrothal_scores(org, seen_kin_ids, seen_sheet_ids, legend_reader=legend_reader)
    return total


def _betrothal_scores(
    org: Organization,
    seen_kin_ids: set[int],
    seen_sheet_ids: set[int],
    *,
    legend_reader: LegendReader,
) -> int:
    """A promised match previews the alliance at a fraction (#2999).

    Both houses count the OTHER side's betrothed at the betrothal share —
    the world already treats the wedding as likely.
    """
    from django.utils import timezone as _tz  # noqa: PLC0415

    from world.societies.houses.constants import BETROTHAL_STATURE_SHARE_PCT  # noqa: PLC0415
    from world.societies.houses.models import Betrothal  # noqa: PLC0415

    now = _tz.now()
    rows = Betrothal.objects.filter(
        models.Q(senior_house=org) | models.Q(junior_house=org),
        broken_at__isnull=True,
        wed_at__isnull=True,
    ).filter(models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=now))
    total = 0
    for betrothal in rows.select_related("kinsperson_a", "kinsperson_b"):
        ours_is_senior = betrothal.senior_house_id == org.pk
        partner = betrothal.kinsperson_b if ours_is_senior else betrothal.kinsperson_a
        total += _partner_contribution(
            partner, BETROTHAL_STATURE_SHARE_PCT, seen_kin_ids, seen_sheet_ids, legend_reader
        )
    return total


def _military_component(org: Organization) -> int:
    total = 0.0
    for unit in MilitaryUnit.objects.filter(owner_org=org):
        total += unit.strength * UNIT_QUALITY_STATURE_MULTIPLIERS.get(unit.quality, 1.0)
    return round(total)


def _economic_component(org: Organization) -> int:
    treasury = OrganizationTreasury.objects.filter(organization=org).first()
    balance = treasury.balance if treasury is not None else 0
    gross = (
        OrgIncomeStream.objects.filter(organization=org, active=True).aggregate(
            total=models.Sum("gross_amount")
        )["total"]
        or 0
    )
    return balance // TREASURY_STATURE_DIVISOR + round(gross * INCOME_GROSS_STATURE_WEIGHT)


def open_threats(org: Organization) -> list[DomainCrisis]:
    """Unresolved threat-valence crises against the org or its domains."""
    rows = DomainCrisis.objects.filter(
        models.Q(org=org) | models.Q(domain__owner_org=org), resolved_at__isnull=True
    ).select_related("crisis_type", "domain")
    from world.societies.houses.constants import CrisisValence  # noqa: PLC0415

    return [c for c in rows if c.valence == CrisisValence.THREAT]


def _crisis_penalty(org: Organization, gross: int) -> int:
    total = 0
    for crisis in open_threats(org):
        total += round(gross * CRISIS_STATURE_PENALTIES.get(crisis.severity, 0.0))
    return total


def _standing_pacts(org: Organization) -> QuerySet[MarriagePact]:
    return MarriagePact.objects.filter(
        models.Q(senior_house=org) | models.Q(junior_house=org), dissolved_at__isnull=True
    ).select_related("senior_house", "junior_house")


def _own_net_strength(org: Organization, *, legend_reader: LegendReader) -> int:
    """Weighted own strength minus crisis drag; NO allied term (one hop only)."""
    renown = _renown_component(org, legend_reader=legend_reader)
    military = _military_component(org)
    economic = _economic_component(org)
    gross = round(
        renown * STATURE_RENOWN_WEIGHT
        + military * STATURE_MILITARY_WEIGHT
        + economic * STATURE_ECONOMIC_WEIGHT
    )
    return max(0, gross - _crisis_penalty(org, gross))


def _allied_component(org: Organization, *, legend_reader: LegendReader) -> int:
    """Counterpart NET strength x share: strength and woe both propagate.

    Marriage pacts contribute at the ally factor; ratified OrgPacts (#2999)
    contribute at their authored ``allied_share_pct``. One hop, no chains.
    """
    total = 0
    for pact in _standing_pacts(org):
        other = pact.junior_house if pact.senior_house_id == org.pk else pact.senior_house
        total += round(_own_net_strength(other, legend_reader=legend_reader) * STATURE_ALLY_FACTOR)
    from world.societies.houses.models import OrgPact  # noqa: PLC0415

    org_pacts = OrgPact.objects.filter(
        models.Q(party_a=org) | models.Q(party_b=org),
        ratified_at__isnull=False,
        dissolved_at__isnull=True,
        kind__allied_share_pct__gt=0,
    ).select_related("kind", "party_a", "party_b")
    for pact in org_pacts:
        other = pact.party_b if pact.party_a_id == org.pk else pact.party_a
        share = pact.kind.allied_share_pct / 100
        total += round(_own_net_strength(other, legend_reader=legend_reader) * share)
    return total


def compute_components(
    org: Organization, *, legend_reader: LegendReader = resilient_legend_reader
) -> StatureComponents:
    """All five component values for one org (raw, unweighted per component)."""
    renown = _renown_component(org, legend_reader=legend_reader)
    military = _military_component(org)
    economic = _economic_component(org)
    gross = round(
        renown * STATURE_RENOWN_WEIGHT
        + military * STATURE_MILITARY_WEIGHT
        + economic * STATURE_ECONOMIC_WEIGHT
    )
    return StatureComponents(
        renown=renown,
        military=military,
        economic=economic,
        allied=_allied_component(org, legend_reader=legend_reader),
        crisis_penalty=_crisis_penalty(org, gross),
    )


def recompute_stature(
    org: Organization, *, legend_reader: LegendReader = resilient_legend_reader
) -> HouseStature:
    """Upsert the true side of an org's stature row (perceived untouched)."""
    parts = compute_components(org, legend_reader=legend_reader)
    stature, _ = HouseStature.objects.get_or_create(
        organization=org, defaults={"perceived_total": parts.true_total}
    )
    stature.renown_strength = parts.renown
    stature.military_strength = parts.military
    stature.economic_strength = parts.economic
    stature.allied_strength = parts.allied
    stature.crisis_penalty = parts.crisis_penalty
    stature.true_total = parts.true_total
    stature.save(
        update_fields=[
            "renown_strength",
            "military_strength",
            "economic_strength",
            "allied_strength",
            "crisis_penalty",
            "true_total",
            "updated_at",
        ]
    )
    return stature


# ---------------------------------------------------------------------------
# Perception, shifts, bands, ranks, prosperity drift
# ---------------------------------------------------------------------------


def record_shift(  # noqa: PLR0913 — one ledger row; both deltas + both subject legs
    org: Organization,
    *,
    cause: str,
    delta_true: int = 0,
    delta_perceived: int = 0,
    kinsperson: Kinsperson | None = None,
    persona: Persona | None = None,
) -> StatureShift:
    """One row in the 'why it moved' ledger (#3091)."""
    return StatureShift.objects.create(
        organization=org,
        cause=cause,
        delta_true=delta_true,
        delta_perceived=delta_perceived,
        subject_kinsperson=kinsperson,
        subject_persona=persona,
    )


def converge_perceived(stature: HouseStature) -> int:
    """Word travels: perceived drifts toward true by the convergence share."""
    delta = round((stature.true_total - stature.perceived_total) * STATURE_CONVERGENCE_RATE)
    if delta == 0:
        return 0
    stature.perceived_total += delta
    stature.save(update_fields=["perceived_total", "updated_at"])
    record_shift(stature.organization, cause=StatureShiftCause.CONVERGENCE, delta_perceived=delta)
    return delta


def _shift_perceived(
    org: Organization,
    amount: int,
    *,
    cause: str,
    kinsperson: Kinsperson | None = None,
    floor_to_zero: bool = True,
) -> int:
    stature = HouseStature.objects.filter(organization=org).first()
    if stature is None or amount == 0:
        return 0
    stature.perceived_total = (
        max(0, stature.perceived_total + amount)
        if floor_to_zero
        else (stature.perceived_total + amount)
    )
    stature.save(update_fields=["perceived_total", "updated_at"])
    record_shift(org, cause=cause, delta_perceived=amount, kinsperson=kinsperson)
    return amount


def apply_death_shock(
    kin: Kinsperson, *, legend_reader: LegendReader = resilient_legend_reader
) -> None:
    """A contributor died: their houses' perceived stature drops NOW (#3091).

    The full loss arrives via the weekly recompute; a public death is news,
    so a share of the lost weight propagates immediately to every org whose
    family the person belonged to.
    """
    score = kinsperson_renown_score(kin, legend_reader=legend_reader)
    if score <= 0:
        return
    shock = -round(score * STATURE_RENOWN_WEIGHT * STATURE_DEATH_SHOCK_SHARE)
    family_ids = set(
        FamilyMembership.objects.filter(kinsperson=kin).values_list("family_id", flat=True)
    )
    if not family_ids:
        return
    for org in Organization.objects.filter(family_id__in=family_ids):
        _shift_perceived(org, shock, cause=StatureShiftCause.DEATH, kinsperson=kin)


def apply_pact_shift(
    pact: MarriagePact,
    *,
    signed: bool,
    legend_reader: LegendReader = resilient_legend_reader,
) -> None:
    """A pact formed or dissolved: both houses reprice immediately (#3091)."""
    cause = StatureShiftCause.PACT_SIGNED if signed else StatureShiftCause.PACT_DISSOLVED
    for org in (pact.senior_house, pact.junior_house):
        stature = HouseStature.objects.filter(organization=org).first()
        before = stature.true_total if stature is not None else 0
        stature = recompute_stature(org, legend_reader=legend_reader)
        delta = stature.true_total - before
        stature.perceived_total = max(0, stature.perceived_total + delta)
        stature.save(update_fields=["perceived_total", "updated_at"])
        record_shift(org, cause=cause, delta_true=delta, delta_perceived=delta)


def apply_whisper(org: Organization, magnitude: int) -> int:
    """Push perceived below true, bounded by the max displacement (#3091)."""
    stature = HouseStature.objects.filter(organization=org).first()
    if stature is None or magnitude <= 0:
        return 0
    floor = round(stature.true_total * (1 - STATURE_WHISPER_MAX_DISPLACEMENT))
    room = stature.perceived_total - floor
    applied = -min(magnitude, max(0, room))
    if applied == 0:
        return 0
    return _shift_perceived(org, applied, cause=StatureShiftCause.WHISPERS)


def crisis_stature_shift(
    crisis: DomainCrisis,
    *,
    cause: str,
    legend_reader: LegendReader = resilient_legend_reader,
) -> None:
    """Reprice the target org when a threat opens or resolves (#3091).

    True stature carries the penalty from the moment the threat opens.
    Perceived moves immediately only when the world can see the event — a
    threat that opens already surfaced, or any resolution. A covert threat's
    perceived drop arrives via weekly convergence after it surfaces
    (ADR-0177 covert window), and revealing it early is spycraft's job.
    """
    org = crisis.org if crisis.org_id is not None else crisis.domain.owner_org
    if org is None:
        return
    stature = HouseStature.objects.filter(organization=org).first()
    before = stature.true_total if stature is not None else 0
    stature = recompute_stature(org, legend_reader=legend_reader)
    delta_true = stature.true_total - before
    delta_perceived = 0
    is_public = cause == StatureShiftCause.CRISIS_RESOLVED or crisis.is_surfaced
    if is_public and delta_true:
        delta_perceived = delta_true
        stature.perceived_total = max(0, stature.perceived_total + delta_perceived)
        stature.save(update_fields=["perceived_total", "updated_at"])
    record_shift(org, cause=cause, delta_true=delta_true, delta_perceived=delta_perceived)


def gifted_power_rating(kin: Kinsperson) -> int:
    """Succession's MOST_POWERFUL_GIFTED measure (#3091).

    Sheet-bound kin rate by their best class level (1-30); sheetless kin by
    the authored gifted_rating on a comparable scale. Registered as the
    first live gifted power rater at societies ready().
    """
    if kin.sheet_id is not None:
        best = kin.sheet.character_class_levels.aggregate(best=models.Max("level"))["best"]
        if best:
            return best
    return kin.gifted_rating * GIFTED_RATING_LEVEL_EQUIV


def band_for_percentile(percentile: int) -> StatureBand | None:
    return (
        StatureBand.objects.filter(min_percentile__lte=percentile)
        .order_by("-min_percentile")
        .first()
    )


def assign_bands() -> int:
    """Percentile-band every landed org within its (continent, category) cohort.

    The continent is CONTINENT_CATENYS until more continents exist; the
    category cohort key is the org type name, so crime families band against
    crime families and noble houses against noble houses (#3091 ruling).
    The continent key (CONTINENT_CATENYS in constants) is implicit while
    Catenys is the only defined continent.
    """
    changed = 0
    cohorts: dict[str, list[HouseStature]] = {}
    rows = HouseStature.objects.filter(organization__in=landed_orgs()).select_related(
        "organization__org_type", "band"
    )
    for row in rows:
        org_type = row.organization.org_type
        key = org_type.name if org_type is not None else ""
        cohorts.setdefault(key, []).append(row)
    for members in cohorts.values():
        members.sort(key=lambda r: r.perceived_total)
        size = len(members)
        for index, row in enumerate(members):
            percentile = round(index * 100 / (size - 1)) if size > 1 else 100
            band = band_for_percentile(percentile)
            if band is None or band.pk == row.band_id:
                continue
            row.previous_band = row.band
            row.band = band
            row.save(update_fields=["band", "previous_band", "updated_at"])
            # A band change is public news — the tidings feeds read this row.
            record_shift(row.organization, cause=StatureShiftCause.BAND_CHANGE)
            changed += 1
    return changed


def assign_realm_ranks() -> int:
    """Store each landed org's perceived-stature rank among its realm's polities.

    Stored weekly so the org page reads ranking with zero extra queries
    ("3rd of 11 polities of Inferna" — the ruling's display ask).
    """
    realms: dict[int | None, list[HouseStature]] = {}
    rows = HouseStature.objects.filter(organization__in=landed_orgs()).select_related(
        "organization__society"
    )
    for row in rows:
        society = row.organization.society
        realm_id = society.realm_id if society is not None else None
        realms.setdefault(realm_id, []).append(row)
    updated = 0
    for members in realms.values():
        members.sort(key=lambda r: (-r.perceived_total, r.organization_id))
        size = len(members)
        for index, row in enumerate(members, start=1):
            if row.realm_rank == index and row.realm_cohort_size == size:
                continue
            row.realm_rank = index
            row.realm_cohort_size = size
            row.save(update_fields=["realm_rank", "realm_cohort_size", "updated_at"])
            updated += 1
    return updated


def recompute_org_prestige_ranks() -> int:
    """Rank ALL orgs on the prestige standing aggregate (#3091, rank-relative)."""
    scored = list(
        Organization.objects.annotate(
            standing=models.F("base_prestige")
            + models.F("accumulated_prestige")
            + models.F("accumulated_fame")
        ).order_by("-standing", "pk")
    )
    stature_rows = {s.organization_id: s for s in HouseStature.objects.all()}
    count = 0
    for rank, org in enumerate(scored, start=1):
        stature = stature_rows.get(org.pk)
        if stature is not None:
            if stature.prestige_rank != rank:
                stature.prestige_rank = rank
                stature.save(update_fields=["prestige_rank", "updated_at"])
        else:
            OrgPrestigeRank.objects.update_or_create(
                organization=org, defaults={"prestige_rank": rank}
            )
        count += 1
    return count


def prestige_rank_band(rank: int | None, *, negative: bool = False) -> PrestigeRankBand | None:
    """The authored benefit band for a rank (or the negative-prestige band)."""
    if negative:
        return PrestigeRankBand.objects.filter(
            negative_only=True, scope=PrestigeRankBand.Scope.ORG
        ).first()
    if rank is None:
        return None
    return (
        PrestigeRankBand.objects.filter(
            negative_only=False,
            scope=PrestigeRankBand.Scope.ORG,
            min_rank__lte=rank,
        )
        .filter(models.Q(max_rank__gte=rank) | models.Q(max_rank__isnull=True))
        .order_by("min_rank")
        .first()
    )


def apply_prestige_prosperity_drift() -> int:
    """Prestige pays through bounded prosperity (#3091 ruling).

    A landed org in a benefit band with ZERO open threats drifts its domains'
    prosperity up (clamped 0-100, capped per week); negative standing drags
    it down regardless of threats. Predators breaking the no-threats gate is
    the counterplay.
    """
    touched = 0
    rows = HouseStature.objects.filter(organization__in=landed_orgs()).select_related(
        "organization"
    )
    for stature in rows:
        org = stature.organization
        standing = org.base_prestige + org.accumulated_prestige + org.accumulated_fame
        band = prestige_rank_band(stature.prestige_rank, negative=standing < 0)
        if band is None or band.prosperity_bonus == 0:
            continue
        bonus = band.prosperity_bonus
        if bonus > 0:
            if open_threats(org):
                continue
            bonus = min(bonus, PRESTIGE_PROSPERITY_DRIFT_MAX)
        for domain in Domain.objects.filter(owner_org=org):
            new_value = max(0, min(100, domain.prosperity + bonus))
            if new_value != domain.prosperity:
                domain.prosperity = new_value
                domain.save(update_fields=["prosperity"])
                touched += 1
    return touched


def weekly_stature_tick(*, legend_reader: LegendReader = resilient_legend_reader) -> dict[str, int]:
    """The weekly orchestration: recompute -> ranks -> drift -> converge -> bands."""
    recomputed = 0
    for org in landed_orgs():
        recompute_stature(org, legend_reader=legend_reader)
        recomputed += 1
    ranked = recompute_org_prestige_ranks()
    drifted = apply_prestige_prosperity_drift()
    converged = 0
    for stature in HouseStature.objects.filter(organization__in=landed_orgs()):
        converged += 1 if converge_perceived(stature) else 0
    banded = assign_bands()
    realm_ranked = assign_realm_ranks()
    return {
        "recomputed": recomputed,
        "ranked": ranked,
        "prosperity_touched": drifted,
        "converged": converged,
        "bands_changed": banded,
        "realm_ranked": realm_ranked,
    }


def _house_tier_index(org: Organization) -> int | None:
    """Best (lowest) TitleTier ladder index among the house's titles."""
    from world.societies.houses.constants import TitleTier  # noqa: PLC0415

    ladder = [choice[0] for choice in TitleTier.choices]
    indexes = [
        ladder.index(tier)
        for tier in Title.objects.filter(house=org).values_list("tier", flat=True)
        if tier in ladder
    ]
    return min(indexes) if indexes else None


def award_marriage_tier_prestige(
    union: Union, *, senior_house: Organization, junior_house: Organization
) -> int:
    """Flat permanent prestige for marrying up, by house tier gap (#3091).

    The sheeted spouses from the lower-tier house earn ``gap x step``
    permanent prestige through the deed channel. Fires at marriage formation
    (phase 3) and from seed backfills; a zero gap awards nothing.
    """
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415
    from world.societies.houses.constants import (  # noqa: PLC0415
        MARRIAGE_TIER_PRESTIGE_AWARD_STEP,
    )
    from world.societies.renown import award_deed_prestige  # noqa: PLC0415

    senior_idx = _house_tier_index(senior_house)
    junior_idx = _house_tier_index(junior_house)
    if senior_idx is None or junior_idx is None or senior_idx == junior_idx:
        return 0
    gap = abs(senior_idx - junior_idx)
    lower_house = senior_house if senior_idx > junior_idx else junior_house
    if lower_house.family_id is None:
        return 0
    amount = gap * MARRIAGE_TIER_PRESTIGE_AWARD_STEP
    awarded = 0
    for member in union.members.filter(sheet__isnull=False, family=lower_house.family):
        persona = active_persona_for_sheet(member.sheet)
        if persona is None:
            continue
        award_deed_prestige(persona, amount)
        awarded += amount
    return awarded


def apply_grand_display(org: Organization, quality_score: int) -> int:
    """A grand display (#3093): hosting done lavishly inflates perceived stature.

    The upward half of the bluffing game (whispers are the downward half).
    An event whose catering PROVISION score clears the bar pushes the host
    org's perceived total up, bounded above true by the bluff elevation cap
    — a house can look somewhat stronger than it is, never absurdly so.
    """
    from world.societies.houses.constants import (  # noqa: PLC0415
        GRAND_DISPLAY_ELEVATION_PER_POINT,
        GRAND_DISPLAY_MIN_QUALITY,
        STATURE_BLUFF_MAX_ELEVATION,
    )

    if quality_score < GRAND_DISPLAY_MIN_QUALITY:
        return 0
    stature = HouseStature.objects.filter(organization=org).first()
    if stature is None:
        return 0
    ceiling = round(stature.true_total * (1 + STATURE_BLUFF_MAX_ELEVATION))
    room = ceiling - stature.perceived_total
    if room <= 0:
        return 0
    applied = min(room, quality_score * GRAND_DISPLAY_ELEVATION_PER_POINT)
    stature.perceived_total += applied
    stature.save(update_fields=["perceived_total", "updated_at"])
    record_shift(org, cause=StatureShiftCause.GRAND_DISPLAY, delta_perceived=applied)
    return applied

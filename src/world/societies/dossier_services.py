"""Match-review dossier assembly (#2999).

The ruled hard requirement: anyone weighing a potential match sees exactly
what the candidate house brings — stature, standing instruments and their
commitments, known troubles — with covert troubles included only when the
VIEWER'S org has paid spycraft to know them (CrisisIntel). A concealed
crisis is precisely what due diligence exists to find.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist
from django.db import models

if TYPE_CHECKING:
    from world.scenes.models import Persona
    from world.societies.models import Organization


def _viewer_org_ids(persona: Persona | None) -> set[int]:
    from world.societies.models import OrganizationMembership  # noqa: PLC0415

    if persona is None:
        return set()
    return set(
        OrganizationMembership.objects.filter(
            persona=persona, left_at__isnull=True, exiled_at__isnull=True
        ).values_list("organization_id", flat=True)
    )


def _stature_block(org: Organization) -> dict:
    try:
        stature = org.stature
    except ObjectDoesNotExist:
        return {
            "band_name": "",
            "headline": "",
            "trend": "steady",
            "perceived_total": None,
            "prestige_rank": None,
            "realm_rank": None,
            "realm_cohort_size": None,
        }
    band = stature.band
    previous = stature.previous_band
    if band is None or previous is None or band.rank == previous.rank:
        trend = "steady"
    else:
        trend = "rising" if band.rank < previous.rank else "falling"
    headline = ""
    if band is not None and band.headline_template:
        headline = band.headline_template.replace("{org}", org.name)
    return {
        "band_name": band.name if band is not None else "",
        "headline": headline,
        "trend": trend,
        "perceived_total": stature.perceived_total,
        "prestige_rank": stature.prestige_rank,
        "realm_rank": stature.realm_rank,
        "realm_cohort_size": stature.realm_cohort_size,
    }


def _pact_rows(org: Organization) -> list[dict]:
    from world.societies.houses.models import MarriagePact  # noqa: PLC0415
    from world.societies.houses.pact_services import standing_org_pacts  # noqa: PLC0415

    rows = []
    for pact in standing_org_pacts(org):
        other = pact.party_b if pact.party_a_id == org.pk else pact.party_a
        levers = []
        if pact.kind.allied_share_pct:
            levers.append(f"allied {pact.kind.allied_share_pct}%")
        if pact.kind.income_share_pct:
            levers.append(f"tithe {pact.kind.income_share_pct}%")
        if pact.kind.non_aggression:
            levers.append("non-aggression")
        if pact.kind.mutual_defense:
            levers.append("mutual defense")
        rows.append(
            {
                "kind": pact.kind.name,
                "counterpart": other.name,
                "since": pact.ratified_at,
                "commitments": levers,
            }
        )
    marriages = MarriagePact.objects.filter(
        models.Q(senior_house=org) | models.Q(junior_house=org), dissolved_at__isnull=True
    ).select_related("senior_house", "junior_house")
    for pact in marriages:
        other = pact.junior_house if pact.senior_house_id == org.pk else pact.senior_house
        kinds = [c.get_kind_display() for c in pact.commitments.all()]
        rows.append(
            {
                "kind": "Marriage",
                "counterpart": other.name,
                "since": pact.signed_at,
                "commitments": kinds,
            }
        )
    return rows


def _betrothal_rows(org: Organization) -> list[str]:
    from world.societies.houses.models import Betrothal  # noqa: PLC0415

    rows = Betrothal.objects.filter(
        models.Q(senior_house=org) | models.Q(junior_house=org),
        broken_at__isnull=True,
        wed_at__isnull=True,
    ).select_related("kinsperson_a", "kinsperson_b", "senior_house", "junior_house")
    return [
        (
            f"{b.kinsperson_a.display_name} to {b.kinsperson_b.display_name} "
            f"({b.senior_house.name} & {b.junior_house.name})"
        )
        for b in rows
        if b.is_active
    ]


def _crisis_rows(org: Organization, viewer_org_ids: set[int]) -> list[dict]:
    from world.societies.houses.models import CrisisIntel, DomainCrisis  # noqa: PLC0415

    known_covert_ids = set(
        CrisisIntel.objects.filter(org_id__in=viewer_org_ids).values_list("crisis_id", flat=True)
    )
    rows = []
    crises = DomainCrisis.objects.filter(
        models.Q(domain__owner_org=org) | models.Q(org=org), resolved_at__isnull=True
    ).select_related("domain", "crisis_type")
    for crisis in crises:
        surfaced = crisis.is_surfaced
        if not surfaced and crisis.pk not in known_covert_ids:
            continue
        rows.append(
            {
                "domain_name": crisis.domain.name if crisis.domain_id else "",
                "severity": crisis.severity,
                "type_name": crisis.crisis_type.name if crisis.crisis_type_id else "",
                "known_covertly": not surfaced,
            }
        )
    return rows


def _shift_rows(org: Organization) -> list[dict]:
    from world.societies.houses.constants import StatureShiftCause  # noqa: PLC0415
    from world.societies.houses.models import StatureShift  # noqa: PLC0415

    quiet = (StatureShiftCause.CONVERGENCE, StatureShiftCause.RECOMPUTE)
    rows = (
        StatureShift.objects.filter(organization=org)
        .exclude(cause__in=quiet)
        .select_related("subject_kinsperson", "subject_persona")
        .order_by("-created_at")[:10]
    )
    out = []
    for row in rows:
        subject = ""
        if row.subject_kinsperson is not None:
            subject = row.subject_kinsperson.display_name
        elif row.subject_persona is not None:
            subject = row.subject_persona.name
        out.append(
            {
                "cause": row.get_cause_display(),
                "delta_perceived": row.delta_perceived,
                "subject": subject,
                "occurred_at": row.created_at,
            }
        )
    return out


def _consort_rows(org: Organization) -> list[dict]:
    """Consort capacity for the house's landed title holders (#2999)."""
    from world.roster.models import Union, UnionKind  # noqa: PLC0415
    from world.societies.houses.models import Title  # noqa: PLC0415

    rows = []
    holders = (
        Title.objects.filter(house=org, seat_domain__isnull=False, holder__isnull=False)
        .select_related("holder", "realm")
        .distinct()
    )
    for title in holders:
        kind = (
            UnionKind.objects.filter(
                realm=title.realm, requires_landed_title=True, stature_share_pct__gt=0
            )
            .order_by("pk")
            .first()
        )
        count = (
            Union.objects.filter(
                members=title.holder,
                ended_at__isnull=True,
                kind__requires_landed_title=True,
                kind__stature_share_pct__gt=0,
            ).count()
            if kind is not None
            else 0
        )
        rows.append(
            {
                "holder": title.holder.display_name,
                "consorts": count,
                "cap": kind.max_concurrent if kind is not None else None,
            }
        )
    return rows


def build_dossier(org: Organization, *, viewer: Persona | None) -> dict:
    """Assemble the dossier payload the serializer renders."""
    payload = {
        "name": org.name,
        "org_type_name": org.org_type.name if org.org_type_id else "",
        "family_name": org.family.name if org.family_id else "",
        "pacts": _pact_rows(org),
        "betrothals": _betrothal_rows(org),
        "open_crises": _crisis_rows(org, _viewer_org_ids(viewer)),
        "recent_shifts": _shift_rows(org),
        "consorts": _consort_rows(org),
    }
    payload.update(_stature_block(org))
    return payload

"""Association: whether the world sees a persona as tied to an organization (#4361).

Association is perception, not formal membership, and not the organization's own
opinion (that is reputation). A persona is associated with organization X, or with any
organization below X in the ``parent_org`` tree, through any of:

- **membership**: a member now; a member who left within
  ``AssociationConfig.former_member_years`` in-game years; an exile, always;
- **kinship**: X is a house rooted in the character's family, counted only while the
  character presents their primary persona;
- **work**: ``work_missions`` missions completed in the last ``work_days`` in-game days,
  accepted as this persona from an offer whose NPC role fronts for X.

Covert organizations never count: their membership is a secret learned only through
clues, checks or techniques. Only the persona passed in is read, so an alternate persona
never leaks its main's ties. A persona is associated with a society when it is associated
with any non-covert organization whose ``society`` is that society.

``association_with_org`` returns the first reason found (for staff, never players), or
None.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from django.utils import timezone

if TYPE_CHECKING:
    from world.scenes.models import Persona
    from world.societies.models import Organization, Society

_DAYS_PER_YEAR = 365


class AssociationKind:
    MEMBER = "member"
    FORMER_MEMBER = "former_member"
    EXILE = "exile"
    KIN = "kin"
    WORK = "work"


@dataclass(frozen=True)
class AssociationReason:
    """Why a persona is seen as tied to an organization (staff-facing)."""

    kind: str
    organization: Organization
    detail: str


def _ic(moment: datetime) -> datetime:
    """``moment`` on the in-game calendar; real time when no game clock runs."""
    from world.game_clock.services import get_ic_date_for_real_time  # noqa: PLC0415

    return get_ic_date_for_real_time(moment) or moment


def _ic_now() -> datetime:
    return _ic(timezone.now())


def _visible_orgs(org_ids: set[int]) -> dict[int, Organization]:
    from world.societies.models import Organization  # noqa: PLC0415

    return {
        org.pk: org
        for org in Organization.objects.filter(pk__in=org_ids).select_related("org_type")
        if not org.org_type.is_covert
    }


def _membership_reason(
    persona: Persona, orgs: dict[int, Organization], years: int
) -> AssociationReason | None:
    from world.societies.models import OrganizationMembership  # noqa: PLC0415

    now = _ic_now()
    for row in OrganizationMembership.objects.filter(
        persona=persona, organization_id__in=list(orgs)
    ).order_by("left_at"):
        org = orgs[row.organization_id]
        if row.exiled_at is not None:
            return AssociationReason(AssociationKind.EXILE, org, f"exiled from {org.name}")
        if row.left_at is None:
            return AssociationReason(AssociationKind.MEMBER, org, f"a member of {org.name}")
        if now - _ic(row.left_at) <= timedelta(days=_DAYS_PER_YEAR * years):
            return AssociationReason(
                AssociationKind.FORMER_MEMBER, org, f"formerly a member of {org.name}"
            )
    return None


def _kin_reason(persona: Persona, orgs: dict[int, Organization]) -> AssociationReason | None:
    from world.scenes.constants import PersonaType  # noqa: PLC0415

    if persona.persona_type != PersonaType.PRIMARY:
        return None
    family_id = persona.character_sheet.family.pk if persona.character_sheet.family else None
    if family_id is None:
        return None
    for org in orgs.values():
        if org.family_id == family_id:
            return AssociationReason(AssociationKind.KIN, org, f"kin of {org.name}")
    return None


def _work_reason(
    persona: Persona, orgs: dict[int, Organization], missions: int, days: int
) -> AssociationReason | None:
    from world.missions.constants import MissionStatus  # noqa: PLC0415
    from world.missions.models import MissionInstance  # noqa: PLC0415

    cutoff = _ic_now() - timedelta(days=days)
    counts: dict[int, int] = {}
    for org_id, completed_at in MissionInstance.objects.filter(
        accepted_as_persona=persona,
        status=MissionStatus.COMPLETE,
        completed_at__isnull=False,
        source_offer__role__faction_affiliation_id__in=list(orgs),
    ).values_list("source_offer__role__faction_affiliation_id", "completed_at"):
        if _ic(completed_at) >= cutoff:
            counts[org_id] = counts.get(org_id, 0) + 1
    for org_id, count in counts.items():
        if count >= missions:
            org = orgs[org_id]
            return AssociationReason(
                AssociationKind.WORK, org, f"{count} recent missions for {org.name}'s people"
            )
    return None


def _association(persona: Persona, org_ids: set[int]) -> AssociationReason | None:
    from world.societies.models import AssociationConfig  # noqa: PLC0415

    orgs = _visible_orgs(org_ids)
    if not orgs:
        return None
    config = AssociationConfig.load()
    return (
        _membership_reason(persona, orgs, config.former_member_years)
        or _kin_reason(persona, orgs)
        or _work_reason(persona, orgs, config.work_missions, config.work_days)
    )


def org_and_descendant_ids(organization: Organization) -> set[int]:
    """The organization's pk and every organization below it in the ``parent_org`` tree."""
    from world.societies.models import Organization  # noqa: PLC0415

    found = {organization.pk}
    frontier = {organization.pk}
    while frontier:
        frontier = (
            set(
                Organization.objects.filter(parent_org_id__in=frontier).values_list("pk", flat=True)
            )
            - found
        )
        found |= frontier
    return found


def association_with_org(
    persona: Persona | None, organization: Organization
) -> AssociationReason | None:
    """Why ``persona`` is seen as tied to ``organization`` (or one below it), or None."""
    if persona is None:
        return None
    return _association(persona, org_and_descendant_ids(organization))


def association_with_society(persona: Persona | None, society: Society) -> AssociationReason | None:
    """Why ``persona`` is seen as tied to one of ``society``'s organizations, or None."""
    from world.societies.models import Organization  # noqa: PLC0415

    if persona is None:
        return None
    org_ids = set(Organization.objects.filter(society=society).values_list("pk", flat=True))
    return _association(persona, org_ids)

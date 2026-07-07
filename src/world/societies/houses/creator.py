"""House creator (#1884 Phase D): CG-defined houses on set-aside titles.

CG-only by design (Apostate ruling): the applicant enters play as a
representative of a house that has always existed — the claim defines it
retroactively. Founding a brand-new house *in play* (ennoblement, new lands)
is a separate future gameplay loop, deliberately not this.

Flow: submit (automated thematic gates) → staff review in admin →
materialize at CG finalization (an approved-but-abandoned application never
leaves a ghost house).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.roster.models import Family
from world.societies.houses.constants import HouseClaimStatus
from world.societies.houses.models import HouseClaim, HouseTemplate, Title
from world.societies.houses.services import (
    HousesServiceError,
    add_holding,
    swear_fealty,
    sync_house_channel,
)
from world.societies.models import Organization

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from world.character_creation.models import CharacterDraft
    from world.character_sheets.models import CharacterSheet

_PRINCIPLE_AXES = ("mercy", "method", "status", "change", "allegiance", "power")
# HouseClaim stores the status axis as ``status_principle`` (``status`` is the
# claim lifecycle); this maps axis name → claim field name.
_CLAIM_FIELD = {axis: axis for axis in _PRINCIPLE_AXES} | {"status": "status_principle"}


def claimable_titles(realm=None) -> list[Title]:
    """Vacant set-aside titles open to CG house definition."""
    qs = Title.objects.filter(
        is_claimable=True, house__isnull=True, holder__isnull=True
    ).select_related("realm", "seat_domain")
    if realm is not None:
        qs = qs.filter(realm=realm)
    return list(qs)


def templates_for_title(title: Title) -> list[HouseTemplate]:
    """The realm's templates a claim on ``title`` may build from."""
    return list(HouseTemplate.objects.filter(realm=title.realm))


def _validate_claim(  # noqa: PLR0913 — keyword-only; one arg per gate input
    *,
    draft: CharacterDraft,
    title: Title,
    template: HouseTemplate,
    house_name: str,
    backstory: str,
    principles: dict[str, int],
) -> None:
    """The automated thematic gates. Staff review is the human gate after."""
    if HouseClaim.objects.filter(draft=draft).exists():
        msg = f"draft {draft.pk} already has a house claim"
        raise HousesServiceError(msg, user_message="This application already defines a house.")
    if not (title.is_claimable and title.house is None and title.holder is None):
        msg = f"title {title.pk} is not claimable"
        raise HousesServiceError(msg, user_message="That title is not open to definition.")
    if template.realm_id != title.realm_id:
        msg = f"template {template.pk} realm mismatch for title {title.pk}"
        raise HousesServiceError(msg, user_message="That template belongs to another realm.")
    if HouseClaim.objects.filter(
        title=title, status__in=[HouseClaimStatus.PENDING, HouseClaimStatus.APPROVED]
    ).exists():
        msg = f"title {title.pk} already has a live claim"
        raise HousesServiceError(msg, user_message="Another application is defining that house.")
    if not re.fullmatch(template.name_pattern, house_name):
        msg = f"house name {house_name!r} fails pattern {template.name_pattern!r}"
        raise HousesServiceError(
            msg,
            user_message="That name does not fit the realm's naming conventions.",
        )
    if (
        Family.objects.filter(name__iexact=house_name).exists()
        or Organization.objects.filter(name__iexact=f"House {house_name}").exists()
    ):
        msg = f"house name {house_name!r} collides with an existing family/org"
        raise HousesServiceError(msg, user_message="A house by that name already exists.")
    if not backstory.strip():
        msg = "empty backstory"
        raise HousesServiceError(msg, user_message="The house needs its story.")
    for axis in _PRINCIPLE_AXES:
        value = principles.get(axis, 0)
        low = getattr(template, f"{axis}_min")
        high = getattr(template, f"{axis}_max")
        if not (low <= value <= high):
            msg = f"principle {axis}={value} outside [{low}, {high}]"
            raise HousesServiceError(
                msg,
                user_message=(
                    f"The {axis} principle must sit between {low} and {high} "
                    "for houses of this realm."
                ),
            )


def submit_house_claim(  # noqa: PLR0913 — keyword-only; one arg per gate input
    *,
    draft: CharacterDraft,
    title: Title,
    template: HouseTemplate,
    house_name: str,
    backstory: str,
    principles: dict[str, int] | None = None,
) -> HouseClaim:
    """Run the automated gates and file the claim for staff review."""
    principles = principles or {}
    _validate_claim(
        draft=draft,
        title=title,
        template=template,
        house_name=house_name,
        backstory=backstory,
        principles=principles,
    )
    field_values = {_CLAIM_FIELD[axis]: principles.get(axis, 0) for axis in _PRINCIPLE_AXES}
    return HouseClaim.objects.create(
        draft=draft,
        title=title,
        template=template,
        house_name=house_name,
        backstory=backstory,
        **field_values,
    )


def approve_house_claim(claim: HouseClaim, *, reviewer: AccountDB) -> HouseClaim:
    """Staff greenlight — materialization waits for CG finalization."""
    claim.status = HouseClaimStatus.APPROVED
    claim.reviewed_by = reviewer
    claim.reviewed_at = timezone.now()
    claim.save(update_fields=["status", "reviewed_by", "reviewed_at"])
    return claim


def reject_house_claim(claim: HouseClaim, *, reviewer: AccountDB, note: str = "") -> HouseClaim:
    claim.status = HouseClaimStatus.REJECTED
    claim.reviewed_by = reviewer
    claim.reviewed_at = timezone.now()
    claim.review_note = note
    claim.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note"])
    return claim


@transaction.atomic
def materialize_house_claim(claim: HouseClaim, *, sheet: CharacterSheet):
    """Build the full package at CG finalization (approved claims only).

    Family + org (+rank ladder) + fealty to the template's liege + the title
    seated on the founder + the template's holdings on the seat domain + a
    kin slot pool for the new family + the house channel. The founder's node
    is created here (in the new family) so the later self-serve bind is a
    no-op get.
    """
    from world.roster.constants import MembershipBasis  # noqa: PLC0415
    from world.roster.models import KinSlotPool  # noqa: PLC0415
    from world.roster.services.kinship import add_membership, ensure_node_for_sheet  # noqa: PLC0415
    from world.societies.membership_services import ensure_default_rank_ladder  # noqa: PLC0415

    if claim.status != HouseClaimStatus.APPROVED:
        msg = f"claim {claim.pk} is not approved"
        raise HousesServiceError(msg, user_message="That house is not approved.")
    template = claim.template
    family = Family.objects.create(
        name=claim.house_name,
        family_type=template.family_type,
        description=claim.backstory,
        is_playable=True,
    )
    org_name = (
        f"House {claim.house_name}"
        if template.family_type == Family.FamilyType.NOBLE
        else claim.house_name
    )
    org = Organization.objects.create(
        name=org_name,
        description=claim.backstory,
        society=template.society,
        org_type=template.liege.org_type,
        family=family,
        default_succession_law=template.default_succession_law,
        mercy_override=claim.mercy,
        method_override=claim.method,
        status_override=claim.status_principle,
        change_override=claim.change,
        allegiance_override=claim.allegiance,
        power_override=claim.power,
    )
    ensure_default_rank_ladder(org)
    swear_fealty(vassal=org, liege=template.liege)

    # ``family`` is a forwarding property onto the sheet's true Profile
    # (#1270); a plain save() persists the profile first.
    sheet.family = family
    sheet.save()
    founder = ensure_node_for_sheet(sheet, family=family)
    add_membership(
        kinsperson=founder, family=family, basis=MembershipBasis.FOUNDING, is_primary=True
    )
    title = claim.title
    title.house = org
    title.holder = founder
    title.is_claimable = False
    title.save(update_fields=["house", "holder", "is_claimable"])

    if title.seat_domain is not None:
        domain = title.seat_domain
        domain.owner_org = org
        domain.save(update_fields=["owner_org"])
        for kind in template.holdings.all():
            add_holding(domain=domain, kind=kind)

    if template.starting_kin_slots:
        KinSlotPool.objects.create(
            family=family,
            description=f"Kin of House {claim.house_name} (CG-defined, #1884)",
            count_remaining=template.starting_kin_slots,
        )
    sync_house_channel(org)
    return org

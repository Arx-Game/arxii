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
from world.societies.houses.models import (
    HouseClaim,
    HouseClaimAspect,
    HouseTemplate,
    OrganizationAspect,
    OrganizationFeature,
    Title,
)
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


def family_name_is_taken(name: str) -> bool:
    """A family or house org already wears this name (case-insensitive) (#3617)."""
    return (
        Family.objects.filter(name__iexact=name).exists()
        or Organization.objects.filter(name__iexact=f"House {name}").exists()
        or Organization.objects.filter(name__iexact=name).exists()
    )


def _validate_claim(  # noqa: PLR0913 — keyword-only; one arg per gate input
    *,
    draft: CharacterDraft,
    title: Title,
    template: HouseTemplate,
    house_name: str,
    backstory: str,
    principles: dict[str, int],
    words: str,
    colors: str,
    sigil_description: str,
    lands_writeup: str,
    aspect_picks: dict[int, list[int]],
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
    if family_name_is_taken(house_name):
        msg = f"house name {house_name!r} collides with an existing family/org"
        raise HousesServiceError(msg, user_message="A house by that name already exists.")
    if not backstory.strip():
        msg = "empty backstory"
        raise HousesServiceError(msg, user_message="The house needs its story.")
    _validate_stylings(
        title=title,
        words=words,
        colors=colors,
        sigil_description=sigil_description,
        lands_writeup=lands_writeup,
    )
    _validate_aspect_picks(template=template, aspect_picks=aspect_picks)
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


def _validate_stylings(
    *,
    title: Title,
    words: str,
    colors: str,
    sigil_description: str,
    lands_writeup: str,
) -> None:
    """Shared stylings are required prose (#2079); lands only for landed titles."""
    for label, value in (
        ("words", words),
        ("colors", colors),
        ("sigil", sigil_description),
    ):
        if not value.strip():
            msg = f"empty {label}"
            raise HousesServiceError(msg, user_message=f"The house needs its {label}.")
    if title.seat_domain is not None and not lands_writeup.strip():
        msg = "empty lands writeup for landed title"
        raise HousesServiceError(msg, user_message="Describe the house's lands.")


# Module-private, but world.character_creation.validators._get_aspect_pick_errors
# also calls it (#3648) - same cross-module pattern already used for
# family_name_is_taken.
def _validate_aspect_picks(*, template: HouseTemplate, aspect_picks: dict[int, list[int]]) -> None:
    """The catalog fence (#2079, ADR-0101): picks only, counted, from the template."""
    definitions = {d.pk: d for d in template.aspect_definitions.all()}
    unknown = set(aspect_picks) - set(definitions)
    if unknown:
        msg = f"aspect picks for definitions {sorted(unknown)} not on template {template.pk}"
        raise HousesServiceError(
            msg, user_message="One of those choices does not apply to this charter."
        )
    for definition in definitions.values():
        picks = aspect_picks.get(definition.pk, [])
        if len(set(picks)) != len(picks):
            msg = f"duplicate picks for definition {definition.pk}"
            raise HousesServiceError(msg, user_message=f"{definition.name}: duplicate choice.")
        if not (definition.min_picks <= len(picks) <= definition.max_picks):
            msg = (
                f"definition {definition.pk} needs "
                f"[{definition.min_picks}, {definition.max_picks}] picks, got {len(picks)}"
            )
            raise HousesServiceError(
                msg,
                user_message=(
                    f"{definition.name}: choose between {definition.min_picks} "
                    f"and {definition.max_picks}."
                ),
            )
        valid_ids = {option.pk for option in definition.options.all() if option.is_active}
        bad = set(picks) - valid_ids
        if bad:
            msg = f"options {sorted(bad)} invalid for definition {definition.pk}"
            raise HousesServiceError(
                msg, user_message=f"{definition.name}: that is not one of the choices."
            )


def submit_house_claim(  # noqa: PLR0913 — keyword-only; one arg per gate input
    *,
    draft: CharacterDraft,
    title: Title,
    template: HouseTemplate,
    house_name: str,
    backstory: str,
    principles: dict[str, int] | None = None,
    words: str = "",
    colors: str = "",
    sigil_description: str = "",
    lands_writeup: str = "",
    aspect_picks: dict[int, list[int]] | None = None,
) -> HouseClaim:
    """Run the automated gates and file the claim for staff review."""
    principles = principles or {}
    aspect_picks = aspect_picks or {}
    _validate_claim(
        draft=draft,
        title=title,
        template=template,
        house_name=house_name,
        backstory=backstory,
        principles=principles,
        words=words,
        colors=colors,
        sigil_description=sigil_description,
        lands_writeup=lands_writeup,
        aspect_picks=aspect_picks,
    )
    field_values = {_CLAIM_FIELD[axis]: principles.get(axis, 0) for axis in _PRINCIPLE_AXES}
    with transaction.atomic():
        claim = HouseClaim.objects.create(
            draft=draft,
            title=title,
            template=template,
            house_name=house_name,
            backstory=backstory,
            words=words,
            colors=colors,
            sigil_description=sigil_description,
            lands_writeup=lands_writeup,
            **field_values,
        )
        for definition_id, option_ids in aspect_picks.items():
            for option_id in option_ids:
                HouseClaimAspect.objects.create(
                    claim=claim, definition_id=definition_id, option_id=option_id
                )
    return claim


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


def _claim_aspect_picks(claim: HouseClaim) -> dict[int, list[int]]:
    picks: dict[int, list[int]] = {}
    for picked in claim.aspects.all():
        picks.setdefault(picked.definition_id, []).append(picked.option_id)
    return picks


def build_family_org(  # noqa: PLR0913 - keyword-only; one arg per package input
    template: HouseTemplate,
    name: str,
    *,
    description: str = "",
    aspect_picks: dict[int, list[int]] | None = None,
    served_house: Organization | None = None,
    created_by: AccountDB | None = None,
    origin_realm=None,
    influence: int = 0,
) -> tuple[Family, Organization]:
    """Family + org + rank ladder + fealty + aspects + features, from a Family Template.

    Shared by the noble title claim (which then seats the title, domain and
    holdings) and the CG name path (which adds nothing more). ``aspect_picks``
    is ``{definition_id: [option_id, ...]}``; ``served_house`` (else the
    template's liege) receives the new org's fealty.
    """
    from world.roster.models import KinSlotPool  # noqa: PLC0415
    from world.societies.membership_services import ensure_default_rank_ladder  # noqa: PLC0415

    org_type = template.org_type or (template.liege.org_type if template.liege_id else None)
    if org_type is None:
        msg = f"template {template.pk} has no org_type and no liege to derive one from"
        raise HousesServiceError(msg, user_message="That family template is not ready.")
    family = Family.objects.create(
        name=name,
        kind=template.kind,
        description=description,
        is_playable=True,
        influence=influence,
        created_by_cg=created_by is not None,
        created_by=created_by,
        origin_realm=origin_realm,
    )
    org_name = f"House {name}" if template.kind.styles_as_house else name
    org = Organization.objects.create(
        name=org_name,
        description=description,
        society=template.society,
        org_type=org_type,
        family=family,
        default_succession_law=template.default_succession_law,
    )
    ensure_default_rank_ladder(org)
    liege = served_house or template.liege
    if liege is not None:
        swear_fealty(vassal=org, liege=liege)
    for definition_id, option_ids in (aspect_picks or {}).items():
        for option_id in option_ids:
            OrganizationAspect.objects.create(
                organization=org, definition_id=definition_id, option_id=option_id
            )
    for feature in template.features.all():
        OrganizationFeature.objects.create(organization=org, feature=feature)
    if template.starting_kin_slots:
        KinSlotPool.objects.create(
            family=family,
            description=f"Kin of {org_name} (CG-defined)",
            count_remaining=template.starting_kin_slots,
        )
    return family, org


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
    from world.roster.services.kinship import add_membership, ensure_node_for_sheet  # noqa: PLC0415

    if claim.status != HouseClaimStatus.APPROVED:
        msg = f"claim {claim.pk} is not approved"
        raise HousesServiceError(msg, user_message="That house is not approved.")
    template = claim.template
    family, org = build_family_org(
        template,
        claim.house_name,
        description=claim.backstory,
        aspect_picks=_claim_aspect_picks(claim),
    )
    org.words = claim.words
    org.colors = claim.colors
    org.sigil_description = claim.sigil_description
    org.mercy_override = claim.mercy
    org.method_override = claim.method
    org.status_override = claim.status_principle
    org.change_override = claim.change
    org.allegiance_override = claim.allegiance
    org.power_override = claim.power
    org.save()

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
        if claim.lands_writeup.strip():
            domain.description = claim.lands_writeup
            domain.save(update_fields=["owner_org", "description"])
        else:
            domain.save(update_fields=["owner_org"])
        for kind in template.holdings.all():
            add_holding(domain=domain, kind=kind)

    sync_house_channel(org)
    return org

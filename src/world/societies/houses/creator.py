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

from world.areas.models import Area
from world.roster.constants import MembershipBasis
from world.roster.models import Family, Kinsperson, UnionKind
from world.seeds.kinship import MARRIAGE_KIND_NAME
from world.societies.houses.almanach import (
    _require_chain_top,
    _rung_area,
    assign_holder,
    claim_grants,
    describe_demesne,
    liege_for_title,
    name_rung,
    plan_estate,
    record_kin,
)
from world.societies.houses.constants import TITLE_TIER_RANK, ClaimKinRelation, HouseClaimStatus
from world.societies.houses.models import (
    Domain,
    HouseClaim,
    HouseClaimAspect,
    HouseClaimKin,
    HouseClaimLand,
    HouseTemplate,
    LandShape,
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
from world.societies.houses.types import ClaimKinDraft, ClaimLandDraft
from world.societies.models import Organization

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from world.character_creation.models import CharacterDraft, OriginTemplate
    from world.character_sheets.models import CharacterSheet

_PRINCIPLE_AXES = ("mercy", "method", "status", "change", "allegiance", "power")
# HouseClaim stores the status axis as ``status_principle`` (``status`` is the
# claim lifecycle); this maps axis name → claim field name.
_CLAIM_FIELD = {axis: axis for axis in _PRINCIPLE_AXES} | {"status": "status_principle"}


def claimable_titles(realm=None) -> list[Title]:
    """Vacant set-aside titles open to CG house definition.

    Also excludes a title whose containment liege is unpublished (#3983), so
    this legacy flat list agrees with the founder ladder's own gate in
    ``_validate_claim``. A landless title (no ``seat_domain``) has no
    containment liege to check. A title that is only an internal member of
    its own chain (a county/barony under an unclaimed duchy, #3983 Plan B —
    ``plant_rung`` marks every rung of an unclaimed chain individually
    claimable) is never independently listed: it would refuse
    ``_validate_seat_gates``'s chain-top check the moment it were submitted,
    so it is not a real target here either.
    """
    qs = Title.objects.filter(
        is_claimable=True, house__isnull=True, holder__isnull=True
    ).select_related("realm", "seat_domain")
    if realm is not None:
        qs = qs.filter(realm=realm)
    titles = []
    for title in qs:
        if title.seat_domain_id is not None:
            try:
                liege = liege_for_title(title)
            except HousesServiceError:
                continue
            if liege is not None and liege.published_at is None:
                continue
        titles.append(title)
    return titles


def permitted_tier_rank(template: OriginTemplate | None) -> int:
    """The highest ``TitleTier`` rank a founder raised on ``template`` may
    define; 99 when unbounded (#3983)."""
    if template is None or not template.max_claim_tier:
        return 99
    return TITLE_TIER_RANK[template.max_claim_tier]


def templates_for_title(title: Title) -> list[HouseTemplate]:
    """The realm's templates a claim on ``title`` may build from: the rows at
    the title's tier, else the realm's tier-less fallback rows (#3983)."""
    rows = list(HouseTemplate.objects.filter(realm=title.realm))
    tiered = [t for t in rows if t.tier == title.tier]
    return tiered or [t for t in rows if not t.tier]


def _validate_seat_gates(*, title: Title, draft: CharacterDraft) -> None:
    """Refuse a title that is only an internal member of its own chain, one
    whose containment liege is unpublished, or one outranking the founder's
    Upbringing (#3983). A landless title (no ``seat_domain``) has no chain or
    containment liege to check."""
    if title.seat_domain_id is not None:
        try:
            _require_chain_top(title)
        except HousesServiceError:
            msg = f"title {title.pk} is not a chain top"
            raise HousesServiceError(
                msg, user_message="That land comes with another seat."
            ) from None
        liege = liege_for_title(title)
        if liege is not None and liege.published_at is None:
            msg = f"liege {liege.pk} unpublished"
            raise HousesServiceError(msg, user_message="That seat is not open yet.")
    if TITLE_TIER_RANK[title.tier] > permitted_tier_rank(draft.selected_origin_template):
        msg = f"tier {title.tier} above the upbringing"
        raise HousesServiceError(msg, user_message="Your upbringing does not reach that seat.")


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
    aspect_picks: dict[int, list[int]],
    kin: list[ClaimKinDraft],
    lands: list[ClaimLandDraft],
    estate_name: str,
    founder_relation: str,
) -> None:
    """The automated thematic gates. Staff review is the human gate after."""
    if HouseClaim.objects.filter(draft=draft).exists():
        msg = f"draft {draft.pk} already has a house claim"
        raise HousesServiceError(msg, user_message="This application already defines a house.")
    if not (title.is_claimable and title.house is None and title.holder is None):
        msg = f"title {title.pk} is not claimable"
        raise HousesServiceError(msg, user_message="That title is not open to definition.")
    _validate_seat_gates(title=title, draft=draft)
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
    _validate_stylings(words=words, colors=colors, sigil_description=sigil_description)
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
    _validate_kin_and_lands(
        draft=draft,
        title=title,
        kin=kin,
        lands=lands,
        estate_name=estate_name,
        founder_relation=founder_relation,
    )


def _validate_stylings(*, words: str, colors: str, sigil_description: str) -> None:
    """Shared stylings are required prose (#2079)."""
    for label, value in (
        ("words", words),
        ("colors", colors),
        ("sigil", sigil_description),
    ):
        if not value.strip():
            msg = f"empty {label}"
            raise HousesServiceError(msg, user_message=f"The house needs its {label}.")


_FOUNDER_NEEDS_HEAD = (ClaimKinRelation.CHILD, ClaimKinRelation.SIBLING, ClaimKinRelation.SPOUSE)


def _validate_kin_and_lands(  # noqa: C901, PLR0913 — keyword-only; one arg per gate input
    *,
    draft: CharacterDraft,
    title: Title,
    kin: list[ClaimKinDraft],
    lands: list[ClaimLandDraft],
    estate_name: str,
    founder_relation: str,
) -> None:
    """The founder-written kin/land gates (#3983 Plan B)."""
    head_count = sum(1 for row in kin if row.relation == ClaimKinRelation.HEAD)
    if head_count > 1:
        msg = "more than one head-of-house row"
        raise HousesServiceError(msg, user_message="A house has only one head.")
    has_head = head_count == 1
    if founder_relation == ClaimKinRelation.HEAD and has_head:
        msg = "kin includes a head-of-house row when the founder is the head"
        raise HousesServiceError(msg, user_message="The founder is the head of house.")
    if founder_relation in _FOUNDER_NEEDS_HEAD and not has_head:
        msg = f"founder_relation {founder_relation} needs a head-of-house row"
        raise HousesServiceError(msg, user_message="Write the head of house first.")
    has_parent = any(
        row.relation in (ClaimKinRelation.MOTHER, ClaimKinRelation.FATHER) for row in kin
    )
    if any(row.relation == ClaimKinRelation.GRANDPARENT for row in kin) and not has_parent:
        msg = "grandparent row without a mother or father row"
        raise HousesServiceError(msg, user_message="A grandparent needs a parent written in first.")
    if lands:
        if title.seat_domain_id is None:
            msg = f"lands given for landless title {title.pk}"
            raise HousesServiceError(msg, user_message="That title has no land to describe.")
        grants_by_pk = {t.pk: t for t in claim_grants(title)}
        for land in lands:
            granted = grants_by_pk.get(land.title_id)
            if granted is None:
                msg = f"land row for title {land.title_id} is not part of this claim's grant"
                raise HousesServiceError(msg, user_message="That land is not part of this claim.")
            if not granted.name and not land.land_name:
                msg = f"undefined title {granted.pk} needs a land_name"
                raise HousesServiceError(msg, user_message="Name that land before describing it.")
            effective_name = land.land_name or granted.name
            if land.hall_name and land.hall_name.strip().lower() == effective_name.strip().lower():
                msg = f"hall name repeats land name for title {granted.pk}"
                raise HousesServiceError(msg, user_message="The hall needs a name of its own.")
    if estate_name:
        realm = draft.selected_area.realm if draft.selected_area_id else None
        if realm is None or not Area.objects.filter(realm=realm, is_capital=True).exists():
            msg = f"draft {draft.pk} realm has no capital"
            raise HousesServiceError(msg, user_message="That realm has no capital yet.")


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
    aspect_picks: dict[int, list[int]] | None = None,
    kin: list[ClaimKinDraft] = (),
    lands: list[ClaimLandDraft] = (),
    estate_name: str = "",
    estate_description: str = "",
    founder_relation: str = ClaimKinRelation.HEAD,
    founder_is_heir: bool = False,
) -> HouseClaim:
    """Run the automated gates and file the claim (+ its kin/land rows) for
    staff review (#3983 Plan B)."""
    principles = principles or {}
    aspect_picks = aspect_picks or {}
    kin = list(kin)
    lands = list(lands)
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
        aspect_picks=aspect_picks,
        kin=kin,
        lands=lands,
        estate_name=estate_name,
        founder_relation=founder_relation,
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
            estate_name=estate_name,
            estate_description=estate_description,
            founder_relation=founder_relation,
            founder_is_heir=founder_is_heir,
            **field_values,
        )
        for definition_id, option_ids in aspect_picks.items():
            for option_id in option_ids:
                HouseClaimAspect.objects.create(
                    claim=claim, definition_id=definition_id, option_id=option_id
                )
        for index, row in enumerate(kin):
            if row.relation == ClaimKinRelation.SPOUSE:
                row_basis = row.basis or MembershipBasis.MARRIED_IN
            else:
                row_basis = row.basis or MembershipBasis.BORN
            HouseClaimKin.objects.create(
                claim=claim,
                name=row.name,
                relation=row.relation,
                gender_id=row.gender_id,
                age=row.age,
                is_deceased=row.is_deceased,
                born_into_id=row.born_into_id,
                basis=row_basis,
                is_household=row.is_household,
                sort_order=index,
            )
        for land in lands:
            land_row = HouseClaimLand.objects.create(
                claim=claim,
                title_id=land.title_id,
                land_name=land.land_name,
                description=land.description,
                hall_name=land.hall_name,
            )
            if land.land_shape_names:
                land_row.land_shapes.set(LandShape.objects.filter(name__in=land.land_shape_names))
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


def _place_claim_row(*, org: Organization, row: HouseClaimKin, **kin_kwargs) -> Kinsperson:
    """Place one ``HouseClaimKin`` row via ``record_kin`` (#3983 Plan B).

    WARD/POSITION rows are household retainers, never family members
    (#3983 Decision 1, ``almanach.record_kin``'s own docstring) — never
    forward the row's own ``basis`` for them, even though
    ``HouseClaimKin.basis`` defaults non-blank (``MembershipBasis.BORN``),
    or they'd pick up a family membership a household placement must not get.
    """
    row_basis = (
        "" if row.relation in (ClaimKinRelation.WARD, ClaimKinRelation.POSITION) else row.basis
    )
    node, _vacancy = record_kin(
        house=org,
        name=row.name,
        relation=row.relation,
        gender=row.gender,
        age=row.age,
        is_deceased=row.is_deceased,
        born_into=row.born_into,
        basis=row_basis,
        is_household=row.is_household,
        **kin_kwargs,
    )
    return node


@transaction.atomic
def materialize_house_claim(  # noqa: C901, PLR0912, PLR0915 — one straight-line finalize sequence
    claim: HouseClaim, *, sheet: CharacterSheet
) -> Organization:
    """Build the full package at CG finalization (approved claims only).

    Family + org (+rank ladder) + fealty to the template's liege + the whole
    claimed seat chain (plus any loose baronies it swallows, #3983 Plan B)
    seated on the house + the founder-written kin tree placed relative to
    the head of house + the founder's own node placed by
    ``claim.founder_relation`` + the template's holdings on the seat domain
    + a kin slot pool for the new family + an optional estate + the house
    channel.

    ``claim.founder_is_heir`` stays a claim fact only: ``Title`` has no heir
    field of its own (``SuccessionLaw.chosen_heir`` is a different,
    law-level concept), so nothing here writes it anywhere (#3983 Plan B
    ruling).
    """
    from world.roster.services.kinship import ensure_node_for_sheet  # noqa: PLC0415

    if claim.status != HouseClaimStatus.APPROVED:
        msg = f"claim {claim.pk} is not approved"
        raise HousesServiceError(msg, user_message="That house is not approved.")
    # Validated here, before the first mutation below: a raise found only
    # mid-function would leave already-mutated, identity-mapped instances
    # (org/sheet/top) poisoned in the cache if the transaction rolls back
    # (IDMAPPER_MUTATE_ORDER; ADR-0008's addendum).
    if (
        claim.founder_relation != ClaimKinRelation.HEAD
        and not claim.kin.filter(relation=ClaimKinRelation.HEAD).exists()
    ):
        msg = f"claim {claim.pk} has no head-of-house row for a non-head founder"
        raise HousesServiceError(msg, user_message="The house needs a head of house.")
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

    top = claim.title
    if top.seat_domain_id is not None:
        grants = claim_grants(top)
        own_chain_pks = {t.pk for t in _require_chain_top(top)}
        for granted in grants:
            # ``assign_holder`` wants chain tops only: the claimed chain is
            # seated once as a whole (via ``top``); each loose barony extra
            # is its own one-title chain top and gets its own call.
            if granted.pk == top.pk or granted.pk not in own_chain_pks:
                assign_holder(granted, org)
        # No ``.prefetch_related("land_shapes")``: ``LandShape`` is identity-
        # mapped and the same row can sit on more than one ``HouseClaimLand``
        # "parent" in this very query, which corrupts Django's m2m-join
        # grouping on a shared instance (feedback_prefetch_to_attr_leaks.md's
        # second failure mode). The claim's own land rows are a small, fixed
        # set (one per granted rung at most), so the per-row
        # ``land_shapes.all()`` calls below stay cheap.
        land_rows = {row.title_id: row for row in claim.lands.select_related("title")}
        for granted in grants:
            row = land_rows.get(granted.pk)
            if row is None:
                continue
            if row.land_name and not granted.name:
                name_rung(granted, row.land_name)
            domain = Domain.objects.filter(area=_rung_area(granted)).first()
            has_writing = row.description or row.hall_name or row.land_shapes.exists()
            if domain is not None and has_writing:
                describe_demesne(
                    domain=domain,
                    description=row.description,
                    hall_name=row.hall_name,
                    land_shape_names=[s.name for s in row.land_shapes.all()],
                )
        # Re-fetch rather than trust ``top.seat_domain``'s cached FK
        # reference: ``assign_holder`` above mutated the row through its own
        # ``_require_chain_top``-fetched instance, a DIFFERENT Python object
        # than ``top`` even at the same pk (idmapper corollary — see
        # ``reference_idmapper_rollback_staleness.md``), so ``top``'s own
        # cached ``seat_domain`` attribute never picked up the write.
        seat_domain = Domain.objects.get(pk=top.seat_domain_id)
        for kind in template.holdings.all():
            add_holding(domain=seat_domain, kind=kind)
    # For a landed title, ``assign_holder`` above already wrote ``house``/
    # ``is_claimable`` to the DB through its own fetched instance; this
    # mirrors it directly onto ``top`` too — the exact object the caller
    # holds (``claim.title``) — for the same idmapper-staleness reason. For
    # a landless title (no seat chain to walk), this is the only write.
    top.house = org
    top.is_claimable = False
    top.save(update_fields=["house", "is_claimable"])

    # Kin, relative to the head of house (#3983 Plan B). ``family=None``:
    # the founder's own membership is written by whichever placement below
    # actually applies (HEAD/CHILD/etc.) — pre-seeding it here would make
    # the family non-empty before the head-of-house row is even placed
    # (wrong FOUNDING/BORN call) and would pre-set the founder's own
    # ``family`` FK, which makes the CHILD-relation fallback
    # (``acknowledge_into_family``) refuse outright.
    rows = list(claim.kin.select_related("gender", "born_into"))
    by_relation: dict[str, list[HouseClaimKin]] = {}
    for row in rows:
        by_relation.setdefault(row.relation, []).append(row)
    marriage_kind = UnionKind.objects.filter(name=MARRIAGE_KIND_NAME).first()
    founder = ensure_node_for_sheet(sheet, family=None)

    # The founder_relation != HEAD case is guaranteed a head_row by the gate
    # at the top of this function (before the first mutation).
    head_row = next(iter(by_relation.get(ClaimKinRelation.HEAD, ())), None)
    if claim.founder_relation == ClaimKinRelation.HEAD:
        head_node, _vacancy = record_kin(
            house=org, name="", relation=ClaimKinRelation.HEAD, node=founder
        )
    else:
        head_node = _place_claim_row(org=org, row=head_row)

    mother_node = father_node = None
    for row in by_relation.get(ClaimKinRelation.MOTHER, ()):
        mother_node = _place_claim_row(org=org, row=row, child=head_node)
    for row in by_relation.get(ClaimKinRelation.FATHER, ()):
        father_node = _place_claim_row(org=org, row=row, child=head_node)
    for row in by_relation.get(ClaimKinRelation.GRANDPARENT, ()):
        _place_claim_row(org=org, row=row, child=mother_node or father_node)

    spouse_node = None
    for row in by_relation.get(ClaimKinRelation.SPOUSE, ()):
        spouse_node = _place_claim_row(
            org=org, row=row, spouse=head_node, marriage_kind=marriage_kind
        )

    head_parents = [p for p in (mother_node, father_node) if p is not None]
    for row in by_relation.get(ClaimKinRelation.SIBLING, ()):
        _place_claim_row(org=org, row=row, parents=head_parents)
    for row in by_relation.get(ClaimKinRelation.CHILD, ()):
        _place_claim_row(
            org=org, row=row, parent=head_node, parents=[spouse_node] if spouse_node else ()
        )
    for row in by_relation.get(ClaimKinRelation.WARD, ()):
        _place_claim_row(org=org, row=row)
    for row in by_relation.get(ClaimKinRelation.POSITION, ()):
        _place_claim_row(org=org, row=row)

    if claim.founder_relation == ClaimKinRelation.CHILD:
        record_kin(
            house=org,
            name="",
            relation=ClaimKinRelation.CHILD,
            node=founder,
            parent=head_node,
            parents=[spouse_node] if spouse_node else (),
        )
    elif claim.founder_relation == ClaimKinRelation.SIBLING:
        record_kin(
            house=org,
            name="",
            relation=ClaimKinRelation.SIBLING,
            node=founder,
            parents=head_parents,
            basis=MembershipBasis.BORN,
        )
    elif claim.founder_relation == ClaimKinRelation.SPOUSE:
        record_kin(
            house=org,
            name="",
            relation=ClaimKinRelation.SPOUSE,
            node=founder,
            spouse=head_node,
            marriage_kind=marriage_kind,
        )
    elif claim.founder_relation in (ClaimKinRelation.MOTHER, ClaimKinRelation.FATHER):
        record_kin(
            house=org,
            name="",
            relation=claim.founder_relation,
            node=founder,
            child=head_node,
            basis=MembershipBasis.BORN,
        )
    elif claim.founder_relation == ClaimKinRelation.GRANDPARENT:
        record_kin(
            house=org,
            name="",
            relation=ClaimKinRelation.GRANDPARENT,
            node=founder,
            child=mother_node or father_node,
            basis=MembershipBasis.BORN,
        )
    elif claim.founder_relation in (ClaimKinRelation.WARD, ClaimKinRelation.POSITION):
        record_kin(
            house=org, name="", relation=claim.founder_relation, node=founder, is_household=True
        )
    # else: founder_relation == HEAD, already placed as head_node above.

    top.holder = head_node
    top.save(update_fields=["holder"])

    if claim.estate_name:
        # Draft-realm first (the founder's own selected origin), sheet-realm
        # only as a fallback when the draft never picked one.
        realm = claim.draft.selected_area.realm if claim.draft.selected_area_id else None
        realm = realm or sheet.origin_realm
        capital = Area.objects.filter(realm=realm, is_capital=True).first() if realm else None
        if capital is not None:
            plan_estate(
                house=org,
                city_area=capital,
                name=claim.estate_name,
                description=claim.estate_description,
                district=claim.estate_district,
            )

    sync_house_channel(org)
    return org

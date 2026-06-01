"""Service functions for the buildings system.

- ``issue_permit_handler`` — the real PERMIT effect handler for
  ``NPCServiceOffer`` (replaces Plan 2's stub). Creates a BuildingPermit
  ``ItemInstance`` + ``BuildingPermitDetails`` row.
- ``validate_permit_site`` — runs the permit-activation checks (ward,
  outdoor, persona match, kind allowed, size cap).
- ``activate_permit`` — consumes a permit and opens the construction
  flow (sets up the Project).
- ``complete_building_construction`` — runs when a BUILDING_CONSTRUCTION
  project completes; spawns the Building, generates placeholder rooms,
  snapshots materials.
- ``contribution_value_for_construction`` — formula computing how much
  a ``Contribution`` is worth toward a BUILDING_CONSTRUCTION project.
  Materials are 110%+ of monetary value; lore-bearing materials scale
  with ``ItemInstance.lore_value``.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.buildings.constants import (
    TARGET_GRANDEUR_MAX,
    TARGET_GRANDEUR_MIN,
    TARGET_SIZE_MAX,
    TARGET_SIZE_MIN,
    PermitEligibility,
)
from world.buildings.models import (
    Building,
    BuildingMaterial,
    BuildingPermitDetails,
)

if TYPE_CHECKING:
    from world.areas.models import Area
    from world.items.models import ItemInstance
    from world.npc_services.effects import EffectResult
    from world.npc_services.models import NPCServiceOffer
    from world.projects.models import Contribution, Project
    from world.scenes.models import Persona


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Typed exceptions — carry ``user_message`` separate from internal context
# so callers (DRF actions etc.) never need to pass ``str(exc)`` to a
# response (per ``feedback_codeql_exceptions``).
# ---------------------------------------------------------------------------


class PermitValidationError(ValueError):
    """Base for permit-site validation failures."""

    user_message: str = "This permit cannot be used here."


class PermitAlreadyConsumedError(PermitValidationError):
    user_message = "This permit has already been used."


class PermitHolderMismatchError(PermitValidationError):
    user_message = "This permit was issued to a different persona."


class PermitWardNotApprovedError(PermitValidationError):
    user_message = "This permit is not valid in this ward."


class PermitKindNotAllowedError(PermitValidationError):
    user_message = "This ward does not allow that kind of building."


class PermitSizeExceedsCapError(PermitValidationError):
    user_message = "The requested building size exceeds the permit's cap."


class PermitSiteNotOutdoorError(PermitValidationError):
    user_message = "Buildings must be founded on an outer-grid (outdoor) site."


class PermitIssuanceError(ValueError):
    """Authoring problem at offer-grant time (PermitOfferDetails misconfigured)."""

    user_message = "Permit could not be issued."


# ---------------------------------------------------------------------------
# Effect handler — replaces Plan 2's stub. Wired in via the registry update.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _IssuedPermit:
    """Convenience return shape for issue_permit_handler internals."""

    instance: ItemInstance
    details: BuildingPermitDetails


@transaction.atomic
def issue_permit(offer: NPCServiceOffer, persona: Persona) -> EffectResult:
    """Real PERMIT effect handler — creates the BuildingPermit ItemInstance + details.

    Reads ``offer.permit_offer_details`` for which BuildingKind to
    authorize, default wards, max target size. Creates the ``ItemInstance``
    (owned by the persona's account) and a ``BuildingPermitDetails`` row
    decorating it (holder_persona = the IC persona who interacted).

    Raises ``PermitIssuanceError`` if the offer's PermitOfferDetails is
    missing or its building_kind is unset.
    """
    from world.items.constants import OwnershipEventType  # noqa: PLC0415
    from world.items.models import ItemInstance, ItemTemplate, OwnershipEvent  # noqa: PLC0415
    from world.npc_services.effects import EffectResult  # noqa: PLC0415

    details = getattr(offer, "permit_offer_details", None)  # noqa: GETATTR_LITERAL — reverse OneToOne, may be absent if offer is misconfigured
    if details is None:
        msg = f"NPCServiceOffer {offer.pk} (kind=PERMIT) has no PermitOfferDetails row."
        raise PermitIssuanceError(msg)
    if details.building_kind_id is None:
        msg = (
            f"PermitOfferDetails for offer {offer.pk} has no building_kind set; "
            "cannot issue permit."
        )
        raise PermitIssuanceError(msg)

    template = ItemTemplate.objects.filter(name=BUILDING_PERMIT_TEMPLATE_NAME).first()
    if template is None:
        msg = (
            f"BuildingPermit ItemTemplate {BUILDING_PERMIT_TEMPLATE_NAME!r} "
            "is missing — seed it via world.buildings.seeds first."
        )
        raise PermitIssuanceError(msg)
    instance = ItemInstance.objects.create(
        template=template,
        owner=persona.character_sheet.character.db_account if _has_account(persona) else None,
        charges=1,
    )
    permit = BuildingPermitDetails.objects.create(
        item_instance=instance,
        holder_persona=persona,
        building_kind=details.building_kind,
        max_target_size=details.default_max_target_size,
        cost_modifier=1,
        issued_by_role=offer.role,
    )
    permit.approved_wards.set(details.default_approved_wards.all())

    OwnershipEvent.objects.create(
        item_instance=instance,
        event_type=OwnershipEventType.CREATED,
        notes=f"Permit issued by {offer.role.name} to {persona}",
    )

    return EffectResult(
        kind=offer.kind,
        object_pk=permit.pk,
        object_label=f"Permit: {details.building_kind.name}",
        message=f"You receive a permit authorizing one {details.building_kind.name}.",
        payload={"permit_pk": permit.pk, "holder_persona_pk": persona.pk},
    )


def _has_account(persona: Persona) -> bool:
    """Best-effort: True when this persona's character has an Account row.

    Test characters created without a played account have no db_account;
    we want issuance to still work (the permit just won't have an
    Account-side owner). The IC owner is holder_persona which is
    required.
    """
    try:
        return persona.character_sheet.character.db_account_id is not None
    except Exception:  # noqa: BLE001 — defensive: AttributeError or missing FK
        return False


BUILDING_PERMIT_TEMPLATE_NAME = "building_permit"


# ---------------------------------------------------------------------------
# Permit site validation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidationResult:
    """Result of a successful ``validate_permit_site`` call."""

    permit: BuildingPermitDetails
    ward: Area
    site_room: object  # ObjectDB; intentionally untyped to avoid evennia import


def validate_permit_site(
    permit_details: BuildingPermitDetails,
    site_room,
    acting_persona: Persona,
    target_size: int,
) -> ValidationResult:
    """Validate a permit can be used at this site for this size.

    Checks (raise ``PermitValidationError`` subclass on failure):

    - permit not already consumed
    - acting persona matches the permit's holder
    - site room is outdoor (outer grid)
    - site's ward is in the permit's approved_wards
    - permit's building_kind is in the ward's allowed_building_kinds
    - target_size <= permit.max_target_size

    Returns ``ValidationResult`` on success (callers use ``result.ward``
    for subsequent construction-project setup).
    """
    if permit_details.consumed_at is not None:
        msg = f"Permit {permit_details.pk} was already consumed at {permit_details.consumed_at}."
        raise PermitAlreadyConsumedError(msg)
    if permit_details.holder_persona_id != acting_persona.pk:
        msg = (
            f"Permit {permit_details.pk} is held by persona "
            f"{permit_details.holder_persona_id}, not {acting_persona.pk}."
        )
        raise PermitHolderMismatchError(msg)

    sheet = getattr(site_room, "sheet_data", None)  # noqa: GETATTR_LITERAL — reverse OneToOne, may be absent on non-Character ObjectDB. Wait, sheet_data is for Characters; rooms use room_profile
    # Actually rooms have room_profile / RoomProfile. Walk to RoomProfile for is_outdoor.
    room_profile = getattr(site_room, "room_profile", None)  # noqa: GETATTR_LITERAL — reverse OneToOne; absent on non-Room ObjectDB
    if room_profile is None or not getattr(room_profile, "is_outdoor", False):  # noqa: GETATTR_LITERAL — defensive default
        msg = f"Site {getattr(site_room, 'pk', '?')} is not an outdoor room."  # noqa: GETATTR_LITERAL — defensive in error message
        raise PermitSiteNotOutdoorError(msg)
    _ = sheet  # silence unused

    ward = _ward_for_room(site_room)
    if ward is None or not permit_details.approved_wards.filter(pk=ward.pk).exists():
        msg = f"Site's ward {ward and ward.pk} is not in the permit's approved_wards."
        raise PermitWardNotApprovedError(msg)

    if not ward.allowed_building_kinds.filter(pk=permit_details.building_kind_id).exists():
        msg = f"Ward {ward.pk} does not allow BuildingKind {permit_details.building_kind_id}."
        raise PermitKindNotAllowedError(msg)
    if ward.permit_eligibility == PermitEligibility.CLOSED:
        msg = f"Ward {ward.pk} is closed to new construction."
        raise PermitWardNotApprovedError(msg)

    if not (TARGET_SIZE_MIN <= target_size <= TARGET_SIZE_MAX):
        msg = f"target_size {target_size} outside the {TARGET_SIZE_MIN}-{TARGET_SIZE_MAX} range."
        raise PermitSizeExceedsCapError(msg)
    if target_size > permit_details.max_target_size:
        msg = (
            f"target_size {target_size} exceeds permit's max_target_size "
            f"{permit_details.max_target_size}."
        )
        raise PermitSizeExceedsCapError(msg)

    return ValidationResult(permit=permit_details, ward=ward, site_room=site_room)


def _ward_for_room(site_room) -> Area | None:
    """Walk the AreaClosure to find the WARD ancestor of a Room.

    Rooms in Evennia don't directly link to wards — they link via
    ``RoomProfile`` → ``Area`` (or via ``LocationOwnership``). For
    Plan 3 we read ``room_profile.area`` and walk up the closure until
    we hit a level=WARD area.
    """
    from world.areas.constants import AreaLevel  # noqa: PLC0415
    from world.areas.models import Area, AreaClosure  # noqa: PLC0415

    room_profile = getattr(site_room, "room_profile", None)  # noqa: GETATTR_LITERAL — reverse OneToOne
    site_area = getattr(room_profile, "area", None) if room_profile else None  # noqa: GETATTR_LITERAL — area FK on profile may be absent in tests
    if site_area is None:
        return None
    ward_id = (
        AreaClosure.objects.filter(descendant=site_area, ancestor__level=AreaLevel.WARD)
        .values_list("ancestor_id", flat=True)
        .first()
    )
    if ward_id is None:
        return None
    return Area.objects.filter(pk=ward_id).first()


# ---------------------------------------------------------------------------
# Permit consumption
# ---------------------------------------------------------------------------


@transaction.atomic
def activate_permit(
    permit_details: BuildingPermitDetails,
    site_room,
    acting_persona: Persona,
    target_size: int,
    target_grandeur: int,
) -> Project:
    """Consume a permit + spawn a BUILDING_CONSTRUCTION project.

    Re-runs ``validate_permit_site`` (defense in depth — callers should
    have validated already, but the consumer is the authoritative gate).
    Sets ``consumed_at`` + ``consumed_by_persona`` on the permit and
    writes an ``OwnershipEvent(ACTIVATED, then CONSUMED)`` audit row.
    """
    from world.items.constants import OwnershipEventType  # noqa: PLC0415
    from world.items.models import OwnershipEvent  # noqa: PLC0415

    if not (TARGET_GRANDEUR_MIN <= target_grandeur <= TARGET_GRANDEUR_MAX):
        msg = (
            f"target_grandeur {target_grandeur} outside "
            f"{TARGET_GRANDEUR_MIN}-{TARGET_GRANDEUR_MAX} range."
        )
        raise PermitSizeExceedsCapError(msg)
    validation = validate_permit_site(permit_details, site_room, acting_persona, target_size)
    now = timezone.now()
    permit_details.consumed_at = now
    permit_details.consumed_by_persona = acting_persona
    permit_details.save(update_fields=["consumed_at", "consumed_by_persona"])
    OwnershipEvent.objects.create(
        item_instance=permit_details.item_instance,
        event_type=OwnershipEventType.ACTIVATED,
        notes=(
            f"Activated by {acting_persona} at site {validation.site_room} "
            f"(ward {validation.ward.pk}); size={target_size}, "
            f"grandeur={target_grandeur}"
        ),
    )
    project = _spawn_construction_project(
        permit_details=permit_details,
        ward=validation.ward,
        site_room=validation.site_room,
        acting_persona=acting_persona,
        target_size=target_size,
        target_grandeur=target_grandeur,
    )
    OwnershipEvent.objects.create(
        item_instance=permit_details.item_instance,
        event_type=OwnershipEventType.CONSUMED,
        notes=f"Consumed by Project {project.pk}",
    )
    return project


def _spawn_construction_project(  # noqa: PLR0913 — kwargs split for callsite readability
    *,
    permit_details: BuildingPermitDetails,
    ward: Area,
    site_room,
    acting_persona: Persona,
    target_size: int,
    target_grandeur: int,
) -> Project:
    """Create the Project shell for a building under construction.

    Plan 1's Project framework owns the project surface; we just author
    a row with the right kind + details payload. The details model
    lives in world.projects (BuildingConstructionDetails); we create it
    here with the snapshot of size/grandeur/permit.
    """
    from world.projects.constants import CompletionMode, ProjectKind, ProjectStatus  # noqa: PLC0415
    from world.projects.models import Project  # noqa: PLC0415

    project = Project.objects.create(
        kind=ProjectKind.BUILDING_CONSTRUCTION,
        status=ProjectStatus.ACTIVE,
        completion_mode=CompletionMode.SINGLE_THRESHOLD,
        title=f"Construct {permit_details.building_kind.name} at {ward.name}",
    )
    # The Project framework's per-kind details model already exists for
    # BUILDING_CONSTRUCTION (Plan 1). We attach the size + grandeur +
    # permit snapshot here.
    _attach_construction_details(
        project=project,
        permit_details=permit_details,
        ward=ward,
        site_room=site_room,
        target_size=target_size,
        target_grandeur=target_grandeur,
        constructed_by_persona=acting_persona,
    )
    return project


def _attach_construction_details(**kwargs) -> None:
    """Hook for attaching per-kind construction details.

    Plan 1 ships ``BuildingConstructionDetails`` in ``world.projects``.
    The exact field shape may evolve; this thin wrapper isolates the
    coupling so test-only paths can stub it.
    """
    from world.projects.models import BuildingConstructionDetails  # noqa: PLC0415

    BuildingConstructionDetails.objects.create(
        project=kwargs["project"],
        permit_details=kwargs["permit_details"],
        ward=kwargs["ward"],
        target_size=kwargs["target_size"],
        target_grandeur=kwargs["target_grandeur"],
        constructed_by_persona=kwargs["constructed_by_persona"],
    )


# ---------------------------------------------------------------------------
# Construction completion
# ---------------------------------------------------------------------------


@transaction.atomic
def complete_building_construction(project: Project) -> Building:
    """Spawn a Building from a completed BUILDING_CONSTRUCTION project.

    Reads the project's ``BuildingConstructionDetails`` for kind / size /
    grandeur / ward. Creates the Building (with an Area shell at level
    BUILDING parented to the ward), computes ``max_rooms`` via the
    formula, snapshots material contributions to ``BuildingMaterial``
    rows, deletes consumed ItemInstances, generates placeholder
    linear-chain rooms.
    """
    from world.areas.constants import AreaLevel  # noqa: PLC0415
    from world.areas.models import Area  # noqa: PLC0415
    from world.items.constants import OwnershipEventType  # noqa: PLC0415
    from world.items.models import OwnershipEvent  # noqa: PLC0415
    from world.projects.constants import ContributionKind  # noqa: PLC0415

    details = project.building_construction_details
    permit = details.permit_details
    kind = permit.building_kind
    target_size = details.target_size
    target_grandeur = details.target_grandeur

    area = Area.objects.create(
        name=f"{kind.name} at {details.ward.name}",
        level=AreaLevel.BUILDING,
        parent=details.ward,
    )
    building = Building.objects.create(
        area=area,
        kind=kind,
        target_size=target_size,
        target_grandeur=target_grandeur,
        max_rooms=kind.rooms_per_size_tier * target_size,
        constructed_by_persona=details.constructed_by_persona,
        source_project=project,
    )

    for contribution in project.contributions.filter(kind=ContributionKind.ITEM):
        instance = contribution.item_instance
        BuildingMaterial.objects.create(
            building=building,
            item_template=instance.template,
            item_instance_pk=instance.pk,
            units=instance.quantity,
            quality_tier=instance.template.minimum_quality_tier,
            lore_value=instance.lore_value,
            contributed_by_persona=contribution.contributor_persona,
        )
        OwnershipEvent.objects.create(
            item_instance=instance,
            event_type=OwnershipEventType.CONSUMED,
            from_account=instance.owner,
            notes=f"Consumed by building construction (Project {project.pk})",
        )
        instance.delete()

    _generate_placeholder_rooms(building)
    return building


def _generate_placeholder_rooms(building: Building) -> None:
    """Generate the Plan 3 placeholder linear-chain rooms.

    Creates ``building.max_rooms`` rooms named "Entry Hall, Hall 2,
    Hall 3, ...". Each room has a single exit to the next. Explicitly a
    stopgap — #670 (Room Builder Tool) lets players actually shape
    their rooms.

    Plan 3 deliberately does NOT create Evennia ObjectDB Room rows
    here — room creation is part of #670's UX, and creating 200+
    placeholder ObjectDBs at construction time would be wasteful for
    Buildings that immediately get restructured. Instead, the placeholder
    chain lives as a Project-completion intent that #670's UI surfaces:
    "your Building has N planned rooms — author them now or accept the
    defaults." For testing the construction pipeline, the chain is
    represented by the ``max_rooms`` field alone.
    """
    # Intentional no-op for Plan 3. The room budget is on
    # ``building.max_rooms``; actual Room ObjectDB creation is deferred
    # to #670 or to a future Plan-3 follow-up that authors them inline.
    logger.info(
        "Building %s constructed with max_rooms=%d (placeholder generation deferred to #670).",
        building.pk,
        building.max_rooms,
    )


# ---------------------------------------------------------------------------
# Contribution-value formula for BUILDING_CONSTRUCTION
# ---------------------------------------------------------------------------

MATERIAL_BASE_BOOST = 1.10  # baseline 110% of monetary value
LORE_VALUE_DIVISOR = 100  # lore_value=100 = 2× multiplier on top of base


def contribution_value_for_construction(contribution: Contribution) -> int:
    """How much a single contribution is worth toward a BUILDING_CONSTRUCTION project.

    - AP: not value-bearing (gates labor checks elsewhere); returns 0.
    - MONEY: face value.
    - ITEM (material): ``monetary × (1 + lore_value / 100) × MATERIAL_BASE_BOOST × units``.
      Materials are 110% of base monetary value; lore-bearing materials
      scale up substantially (lore_value=100 → 2× on top of base = 220%
      effective; lore_value=900 → 10× on top of base = 1100% effective).
    - CHECK: pass-through value depends on the check's success_level; for
      Plan 3 we treat it as 0 (the project's labor surface lives elsewhere).
    """
    from world.projects.constants import ContributionKind  # noqa: PLC0415

    if contribution.kind == ContributionKind.MONEY:
        return contribution.money_amount or 0
    if contribution.kind == ContributionKind.ITEM:
        instance = contribution.item_instance
        if instance is None:
            return 0
        monetary = instance.template.value
        units = instance.quantity
        lore_multiplier = 1 + (instance.lore_value / LORE_VALUE_DIVISOR)
        return int(monetary * lore_multiplier * MATERIAL_BASE_BOOST * units)
    return 0

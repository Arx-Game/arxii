"""Kinship, estate and reputation, as public services on a live sheet (#3988 piece D, #4226).

Character creation's finalize binds a new character into the kin tree, grants a
starting residence and a Beginnings' property house, materializes an approved house
claim, takes a chosen vacancy and seeds organization reputation from its
questionnaire. Each of those is a writer here that takes the sheet and explicit
targets instead of a draft, so finalize and staff edit mode share one writer per
family. A refusal is a ``SheetWriteError`` carrying a message safe to show; CG's
finalize keeps its best-effort contract by catching it and logging.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import IntegrityError, transaction

from world.character_creation.sheet_writers import SheetWriteError

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from evennia_extensions.models import RoomProfile
    from world.buildings.models import Building, PropertyGrantProfile
    from world.character_sheets.models import CharacterSheet
    from world.locations.models import LocationTenancy
    from world.roster.models import Family, Kinsperson
    from world.scenes.models import Persona
    from world.societies.houses.models import HouseClaim
    from world.societies.models import Organization, Vacancy


def primary_persona(sheet: CharacterSheet) -> Persona:
    """The sheet's PRIMARY persona: the character as themselves, who holds what CG grants."""
    from world.scenes.constants import PersonaType  # noqa: PLC0415
    from world.scenes.models import Persona  # noqa: PLC0415

    persona = Persona.objects.filter(
        character_sheet=sheet, persona_type=PersonaType.PRIMARY
    ).first()
    if persona is None:
        msg = "This character has no primary persona."
        raise SheetWriteError(msg)
    return persona


def sync_kin_name_aliases(sheet: CharacterSheet) -> None:
    """Register the particled name forms as telnet aliases (#3261), when the sheet has a node."""
    from world.roster.models import Kinsperson  # noqa: PLC0415
    from world.societies.houses.services import sync_name_aliases  # noqa: PLC0415

    person = Kinsperson.objects.filter(sheet=sheet).first()
    if person is not None:
        sync_name_aliases(person)


def bind_kinship_node(
    sheet: CharacterSheet,
    *,
    node: Kinsperson | None = None,
    family: Family | None = None,
) -> Kinsperson:
    """Place the sheet in the kin tree: claim an open node, or self-serve one (#2062).

    With ``node``, claim that appable position (its constraints hold, and it keeps its
    authored edges). Without, get or create the sheet's own node in ``family`` (or
    familyless). A sheet already in the tree may not claim a second position. The
    particled-name aliases are synced afterwards, as finalize does.
    """
    from world.roster.models import Kinsperson  # noqa: PLC0415
    from world.roster.services.kinship import (  # noqa: PLC0415
        KinshipServiceError,
        claim_appable_node,
        ensure_node_for_sheet,
    )

    if node is not None:
        if Kinsperson.objects.filter(sheet=sheet).exists():
            msg = "This character already has a place in the family tree."
            raise SheetWriteError(msg)
        try:
            bound = claim_appable_node(node=node, sheet=sheet)
        except KinshipServiceError as exc:
            raise SheetWriteError(exc.user_message) from exc
    else:
        bound = ensure_node_for_sheet(sheet, family=family)
    sync_kin_name_aliases(sheet)
    return bound


def grant_residence(
    sheet: CharacterSheet, room_profile: RoomProfile, *, notes: str = ""
) -> LocationTenancy:
    """Make the character a tenant of a room, as CG's starting residence does (#2036).

    A system or staff grant (``granted_by`` stays None, #3902). A character who already
    holds an open tenancy there keeps it; no second row is written. ``grant_tenancy``
    defaults the Evennia home and the sheet's current residence when none is set. A guest
    or trustee key to the same room is a different rung and does not count as living there.
    """
    from django.db.models import Q  # noqa: PLC0415
    from django.utils import timezone  # noqa: PLC0415

    from world.locations.constants import LocationRole  # noqa: PLC0415
    from world.locations.models import LocationTenancy  # noqa: PLC0415
    from world.locations.services import grant_tenancy  # noqa: PLC0415

    persona = primary_persona(sheet)
    held = (
        LocationTenancy.objects.filter(
            room_profile=room_profile, tenant_persona=persona, kind=LocationRole.TENANT
        )
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=timezone.now()))
        .first()
    )
    if held is not None:
        return held
    return grant_tenancy(
        kind=LocationRole.TENANT,
        room_profile=room_profile,
        tenant_persona=persona,
        notes=notes,
    )


def grant_property(sheet: CharacterSheet, profile: PropertyGrantProfile) -> Building:
    """Grant the property house a profile describes, once per profile (``grant_property_house``).

    A character who already owns a building granted through this profile keeps it.
    """
    from world.buildings.models import Building  # noqa: PLC0415
    from world.buildings.property_grant_services import grant_property_house  # noqa: PLC0415

    persona = primary_persona(sheet)
    owned = Building.objects.filter(owner_persona=persona, granted_via_profile=profile).first()
    if owned is not None:
        return owned
    return grant_property_house(persona, profile)


def bind_house_claim(sheet: CharacterSheet, claim: HouseClaim) -> Organization:
    """Materialize an approved house claim for the sheet (#1884 Phase D).

    Every refusal ``materialize_house_claim`` can raise becomes a ``SheetWriteError``:
    the house services' own, a kin-tree refusal, and a colliding land name (#3983).
    The claim's writes roll back in their savepoint, but ``sheet`` is identity-mapped
    and the builder stamps ``sheet.family`` before a failing row, so the family is put
    back by hand; otherwise the next save of that instance would persist a Family that
    no longer exists.
    """
    from world.roster.services.kinship import KinshipServiceError  # noqa: PLC0415
    from world.societies.houses.constants import HouseClaimStatus  # noqa: PLC0415
    from world.societies.houses.creator import materialize_house_claim  # noqa: PLC0415
    from world.societies.houses.services import HousesServiceError  # noqa: PLC0415

    if claim.status != HouseClaimStatus.APPROVED:
        msg = "That house claim is not approved."
        raise SheetWriteError(msg)
    previous_family = sheet.family
    try:
        with transaction.atomic():
            return materialize_house_claim(claim, sheet=sheet)
    except (HousesServiceError, KinshipServiceError) as exc:
        sheet.family = previous_family
        raise SheetWriteError(exc.user_message) from exc
    except IntegrityError as exc:
        sheet.family = previous_family
        msg = "The house could not be built; a name it needs is already taken."
        raise SheetWriteError(msg) from exc


def bind_vacancy(
    sheet: CharacterSheet, vacancy: Vacancy, *, created_by: AccountDB | None = None
) -> None:
    """Take one opening: its kin position (if any), then the organization membership (#3648).

    The opening is locked and counted down; a kin pool mints a new position, a kin
    node is claimed as it stands. A closed opening, a refused kin claim or a refused
    membership rolls the whole take back. A sheet already in the kin tree may not take
    a kin-bearing opening, since a sheet holds one position. On a refusal the opening
    is evicted from the identity map: the rollback restores its row, not the cached
    instance ``take_vacancy`` counted down.
    """
    from world.roster.models import Kinsperson  # noqa: PLC0415
    from world.roster.services.kinship import (  # noqa: PLC0415
        KinshipServiceError,
        claim_appable_node,
        mint_from_pool,
    )
    from world.societies.exceptions import OrganizationMembershipError  # noqa: PLC0415
    from world.societies.houses.services import HousesServiceError  # noqa: PLC0415
    from world.societies.membership_services import join_organization  # noqa: PLC0415
    from world.societies.vacancy_services import take_vacancy  # noqa: PLC0415

    persona = primary_persona(sheet)
    bears_kin = vacancy.kin_pool_id is not None or vacancy.kin_node_id is not None
    if bears_kin and Kinsperson.objects.filter(sheet=sheet).exists():
        msg = "This character already has a place in the family tree; that opening brings one."
        raise SheetWriteError(msg)
    taken_ok = False
    try:
        with transaction.atomic():
            taken = take_vacancy(vacancy.pk)
            if taken.kin_pool_id is not None:
                node = mint_from_pool(taken.kin_pool, created_by=created_by)
                claim_appable_node(node=node, sheet=sheet)
            elif taken.kin_node_id is not None:
                claim_appable_node(node=taken.kin_node, sheet=sheet)
            join_organization(taken.organization, persona, rank=taken.rank, vacancy=taken)
        taken_ok = True
    except (HousesServiceError, KinshipServiceError, OrganizationMembershipError) as exc:
        raise SheetWriteError(exc.user_message) from exc
    finally:
        if not taken_ok:
            vacancy.flush_from_cache(force=True)


def set_organization_reputation(
    sheet: CharacterSheet, organization: Organization, value: int
) -> int:
    """Set an organization's opinion of the character to ``value``, within the clamp.

    Written as one delta through ``bump_organization_reputation``, so the clamp and the
    open-beat re-evaluation (#3570) are the ones every other reputation write runs.
    Replaces, for staff, CG's questionnaire seed, which needs draft answers.
    """
    from world.societies.models import (  # noqa: PLC0415
        REPUTATION_MAX,
        REPUTATION_MIN,
        OrganizationReputation,
    )
    from world.societies.renown import bump_organization_reputation  # noqa: PLC0415

    if not REPUTATION_MIN <= value <= REPUTATION_MAX:
        msg = f"Reputation runs from {REPUTATION_MIN} to {REPUTATION_MAX}."
        raise SheetWriteError(msg)
    persona = primary_persona(sheet)
    current = (
        OrganizationReputation.objects.filter(persona=persona, organization=organization)
        .values_list("value", flat=True)
        .first()
    ) or 0
    bump_organization_reputation(persona, organization, value - current)
    return value

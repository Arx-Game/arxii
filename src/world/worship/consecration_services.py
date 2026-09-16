"""Shrines and temples (#3778): founding, growth and the reward bonus.

A shrine is a room's SHRINE feature with a ``ShrineDetails`` sidecar; a temple
is a ``TempleDedication`` over a whole ``Building``. Both carry a plain
``consecration_points`` counter that a rite of their own being grows when it is
performed there, and both add an authored ``ConsecrationTier`` bonus to such a
rite's award. The two are structurally independent, so a shrine inside a temple
stacks: the bonuses are summed, never max()'d.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.worship.constants import CONSECRATION_POINTS_PER_RITE_TIER, ConsecrationScope
from world.worship.exceptions import SiteAlreadyTaken, SiteNotFound, SiteNotHeld
from world.worship.models import ConsecrationTier, ShrineDetails, TempleDedication

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from evennia_extensions.models import RoomProfile
    from world.areas.models import Area
    from world.buildings.models import Building
    from world.scenes.models import Persona
    from world.worship.models import WorshippedBeing, WorshipRite


@dataclass(frozen=True)
class ConsecrationGrowth:
    """How many points a performance added to the shrine and to the temple."""

    shrine_points: int = 0
    temple_points: int = 0


def shrine_at(room_profile: RoomProfile | None) -> ShrineDetails | None:
    """The active shrine in ``room_profile``, or None."""
    if room_profile is None:
        return None
    return (
        ShrineDetails.objects.filter(
            feature_instance__room_profile=room_profile,
            feature_instance__dissolved_at__isnull=True,
        )
        .select_related("being", "feature_instance")
        .first()
    )


def building_over(room_profile: RoomProfile | None) -> Building | None:
    """The ``Building`` whose node is the room's area, walking ``parent`` up to a
    BUILDING-level area (self first, cycle-safe, no materialized view)."""
    from world.areas.constants import AreaLevel  # noqa: PLC0415
    from world.buildings.models import Building  # noqa: PLC0415

    if room_profile is None or room_profile.area_id is None:
        return None
    node: Area | None = room_profile.area
    seen: set[int] = set()
    while node is not None and node.pk not in seen:
        seen.add(node.pk)
        if node.level == AreaLevel.BUILDING:
            return Building.objects.filter(area=node).first()
        node = node.parent
    return None


def active_temple(building: Building | None) -> TempleDedication | None:
    if building is None:
        return None
    return (
        TempleDedication.objects.filter(building=building, dissolved_at__isnull=True)
        .select_related("being")
        .first()
    )


def temple_over(room_profile: RoomProfile | None) -> TempleDedication | None:
    """The active temple dedication of the building the room sits in, or None."""
    return active_temple(building_over(room_profile))


def tier_bonus_percent(scope: str, points: int) -> int:
    """The bonus of the highest authored tier whose ``min_points`` the site has reached."""
    tier = (
        ConsecrationTier.objects.filter(scope=scope, min_points__lte=points)
        .order_by("-min_points")
        .first()
    )
    return tier.bonus_percent if tier is not None else 0


def consecration_bonus_percent(room_profile: RoomProfile | None, being: WorshippedBeing) -> int:
    """The summed bonus a rite of ``being`` earns for being performed at ``room_profile``.

    Each source counts only when its dedicated being is the rite's being; the
    two are then added (a cathedral's inner altar), never max()'d.
    """
    bonus = 0
    shrine = shrine_at(room_profile)
    if shrine is not None and shrine.being_id == being.pk:
        bonus += tier_bonus_percent(ConsecrationScope.SHRINE, shrine.consecration_points)
    temple = temple_over(room_profile)
    if temple is not None and temple.being_id == being.pk:
        bonus += tier_bonus_percent(ConsecrationScope.TEMPLE, temple.consecration_points)
    return bonus


def grow_consecration(room_profile: RoomProfile | None, rite: WorshipRite) -> ConsecrationGrowth:
    """A rite of a site's own being performed there consecrates it by its tier."""
    points = rite.kind.tier * CONSECRATION_POINTS_PER_RITE_TIER
    shrine_points = temple_points = 0
    shrine = shrine_at(room_profile)
    if shrine is not None and shrine.being_id == rite.being_id:
        shrine.consecration_points += points
        shrine.save(update_fields=["consecration_points"])
        shrine_points = points
    temple = temple_over(room_profile)
    if temple is not None and temple.being_id == rite.being_id:
        temple.consecration_points += points
        temple.save(update_fields=["consecration_points"])
        temple_points = points
    return ConsecrationGrowth(shrine_points=shrine_points, temple_points=temple_points)


def _holds_room(room: ObjectDB, persona: Persona) -> bool:
    """Direct persona ownership of the room, Sanctum's Personal-install gate."""
    from world.locations.constants import HolderType  # noqa: PLC0415
    from world.locations.services import effective_owner  # noqa: PLC0415

    ownership = effective_owner(room)
    return (
        ownership is not None
        and ownership.holder_type == HolderType.PERSONA
        and ownership.holder_persona_id == persona.pk
    )


def _holds_building(building: Building, persona: Persona) -> bool:
    """Standing over the whole Building: its credited owner, the persona holding
    its area, or a leader of the organization holding its area."""
    from world.locations.constants import HolderType  # noqa: PLC0415
    from world.locations.services import effective_owner_for_area  # noqa: PLC0415
    from world.societies.houses.services import is_org_leader  # noqa: PLC0415

    if building.owner_persona_id == persona.pk:
        return True
    ownership = effective_owner_for_area(building.area)
    if ownership is None:
        return False
    if ownership.holder_type == HolderType.PERSONA:
        return ownership.holder_persona_id == persona.pk
    if ownership.holder_type == HolderType.ORGANIZATION and ownership.holder_organization:
        return is_org_leader(persona, ownership.holder_organization)
    return False


@transaction.atomic
def found_shrine(
    room_profile: RoomProfile, being: WorshippedBeing, founder: Persona
) -> ShrineDetails:
    """Found a shrine of ``being`` in a room ``founder`` directly owns.

    One feature per room (Sanctum's rule): a room already carrying an active
    feature refuses. Installs immediately, like Sanctification, no project.
    """
    from world.room_features.constants import RoomFeatureServiceStrategy  # noqa: PLC0415
    from world.room_features.models import RoomFeatureInstance, RoomFeatureKind  # noqa: PLC0415
    from world.seeds.worship_content import ensure_shrine_kind  # noqa: PLC0415

    if not _holds_room(room_profile.objectdb, founder):
        raise SiteNotHeld
    # The room's one feature slot (a OneToOne). A dissolved shrine gives it
    # back; a dissolved feature of any other kind keeps it, since that row is
    # story-significant history (Sanctum preserves its details on dissolution).
    occupant = RoomFeatureInstance.objects.filter(room_profile=room_profile).first()
    if occupant is not None:
        if (
            occupant.dissolved_at is None
            or occupant.feature_kind.service_strategy != RoomFeatureServiceStrategy.SHRINE
        ):
            raise SiteAlreadyTaken
        occupant.delete()
    kind: RoomFeatureKind = ensure_shrine_kind()
    instance = RoomFeatureInstance.objects.create(
        room_profile=room_profile, feature_kind=kind, level=1
    )
    return ShrineDetails.objects.create(
        feature_instance=instance,
        being=being,
        founder_character_sheet=founder.character_sheet,
    )


def dissolve_shrine(shrine: ShrineDetails, persona: Persona) -> None:
    """Its founder, or whoever now holds the room, may dissolve a shrine."""
    instance = shrine.feature_instance
    if instance.dissolved_at is not None:
        raise SiteNotFound
    if shrine.founder_character_sheet_id != persona.character_sheet_id and not _holds_room(
        instance.room_profile.objectdb, persona
    ):
        raise SiteNotHeld
    instance.dissolved_at = timezone.now()
    instance.save(update_fields=["dissolved_at"])


@transaction.atomic
def dedicate_temple(
    building: Building, being: WorshippedBeing, founder: Persona
) -> TempleDedication:
    """Dedicate a whole building to ``being``; ``founder`` must hold the building."""
    if not _holds_building(building, founder):
        raise SiteNotHeld
    if active_temple(building) is not None:
        raise SiteAlreadyTaken
    return TempleDedication.objects.create(
        building=building, being=being, founder_character_sheet=founder.character_sheet
    )


def revoke_temple(dedication: TempleDedication, persona: Persona) -> None:
    """Its founder, or whoever now holds the building, may revoke a dedication."""
    if dedication.dissolved_at is not None:
        raise SiteNotFound
    if dedication.founder_character_sheet_id != persona.character_sheet_id and not _holds_building(
        dedication.building, persona
    ):
        raise SiteNotHeld
    dedication.dissolved_at = timezone.now()
    dedication.save(update_fields=["dissolved_at"])

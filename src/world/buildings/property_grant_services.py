"""Generic "grant a persona an already-existing Building" primitive.

Not tied to CG, Arx, or any specific content — grant_property_house is
callable from anywhere (finalize_character via Beginnings.property_grant_profile
today; a GM/story action or a later relocation flow could call it directly
with any PropertyGrantProfile). "The Keeping" (#2461) is a content instance
of this primitive, not a code path — see PropertyGrantProfile's docstring.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

if TYPE_CHECKING:
    from world.areas.models import Area
    from world.buildings.models import Building, PropertyGrantProfile
    from world.scenes.models import Persona

_PLACEHOLDER_WARD_SLUG = "property-grant-placeholder-ward"


def _placeholder_ward_area() -> Area:
    """Get-or-create the shared fallback placeholder Ward Area.

    Slug-keyed (Area.slug is unique) for concurrency-safe idempotency.
    origin is left at its default (PLAYER), so this never exports as
    authored grid content — real content replaces a profile's ward_area
    via fixture upsert with no code change.
    """
    from world.areas.constants import AreaLevel  # noqa: PLC0415
    from world.areas.models import Area  # noqa: PLC0415

    area, _ = Area.objects.get_or_create(
        slug=_PLACEHOLDER_WARD_SLUG,
        defaults={"name": "Unclaimed Properties (placeholder)", "level": AreaLevel.WARD},
    )
    return area


def grant_property_house(persona: Persona, profile: PropertyGrantProfile) -> Building:
    """Grant *persona* ownership of a freshly created Building per *profile*.

    Creates a BUILDING-level Area under the profile's ward (or the shared
    placeholder ward if unset), a Building at ``profile.initial_condition_tier``,
    and one entry room — the same minimal shape ``complete_building_construction``
    produces, minus the permit/project. Stamps ``property_granted_at`` always;
    stamps ``property_activated_at`` immediately too when the profile carries
    no activation arc (``activation_target_tier is None``).
    """
    from world.areas.constants import AreaLevel  # noqa: PLC0415
    from world.areas.models import Area  # noqa: PLC0415
    from world.buildings.models import Building, BuildingSizeTier  # noqa: PLC0415
    from world.buildings.services import create_entry_room  # noqa: PLC0415

    ward = profile.ward_area or _placeholder_ward_area()
    now = timezone.now()
    with transaction.atomic():
        area = Area.objects.create(
            name=f"{profile.name} grant for {persona}",
            level=AreaLevel.BUILDING,
            parent=ward,
        )
        building = Building.objects.create(
            area=area,
            kind=profile.building_kind,
            condition_tier=profile.initial_condition_tier,
            target_size=1,
            target_grandeur=1,
            space_budget=BuildingSizeTier.objects.get(tier=1).space_budget,
            owner_persona=persona,
            granted_via_profile=profile,
            property_granted_at=now,
            property_activated_at=(now if profile.activation_target_tier is None else None),
        )
        room = create_entry_room(building, "Entry Hall")
        building.entry_room = room
        building.save(update_fields=["entry_room"])
    return building

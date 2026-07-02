"""Phase D tests for the Renown polish system (#676).

Covers:
- ``PolishCategory`` + ``TierThreshold`` admin lookups; tier label derivation.
- ``BuildingPolish`` + ``RoomPolish`` through tables.
- ``Building.owner_persona`` + ``RoomProfile.tenant_persona`` FKs.
- ``apply_project_completion`` — template → instance + BuildingPolish bump.
- ``apply_room_polish_delta`` — direct room polish add with clamp + roll-up.
- ``recompute_persona_prestige_from_dwellings`` — primary-home-anchored
  (#670, ratified): home room polish + building polish iff the persona
  owns the home's building. Replaces the #676 portfolio-sum/double-count.
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import (
    CharacterFactory,
    RoomProfileFactory,
)
from world.areas.factories import AreaFactory
from world.buildings.factories import BuildingFactory
from world.buildings.models import (
    BuildingPolish,
    BuildingProjectInstance,
    BuildingProjectInstancePolish,
    PolishCategory,
    ProjectTemplate,
    ProjectTemplatePolishIncrement,
    RoomPolish,
    TierThreshold,
)
from world.buildings.polish_services import (
    apply_project_completion,
    apply_room_polish_delta,
    derive_tier_label,
    recompute_persona_prestige_from_dwellings,
)
from world.character_sheets.factories import CharacterSheetFactory


def _make_primary_persona():
    """Reuse the renown-test pattern: Character + sheet → its primary persona."""
    character = CharacterFactory()
    sheet = CharacterSheetFactory(character=character)
    return sheet.primary_persona


def _make_template(name: str, increments: list[tuple[PolishCategory, int]]) -> ProjectTemplate:
    """Build a ProjectTemplate with the given per-category polish increments."""
    template = ProjectTemplate.objects.create(name=name)
    for category, value in increments:
        ProjectTemplatePolishIncrement.objects.create(
            template=template, category=category, value=value
        )
    return template


def _make_building(area=None, owner=None):
    """BuildingFactory but with owner_persona and a real BUILDING-level area."""
    if area is None:
        area = AreaFactory(level=10)  # BUILDING level
    return BuildingFactory(area=area, owner_persona=owner)


def _make_room(area=None, tenant=None):
    """RoomProfile inside ``area``; ``tenant`` gets a primary-home tenancy here (#670)."""
    from world.locations.constants import HolderType, LocationParentType
    from world.locations.models import LocationTenancy

    profile = RoomProfileFactory(area=area)
    if tenant is not None:
        LocationTenancy.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=profile,
            tenant_type=HolderType.PERSONA,
            tenant_persona=tenant,
            is_primary_home=True,
        )
    return profile


class TierLabelDerivationTests(TestCase):
    def test_no_thresholds_returns_none(self) -> None:
        cat = PolishCategory.objects.create(name="Opulence")
        self.assertIsNone(derive_tier_label(cat, 5000))

    def test_below_first_threshold_returns_none(self) -> None:
        cat = PolishCategory.objects.create(name="Elegance")
        TierThreshold.objects.create(category=cat, tier_name="Notable", min_value=500)
        self.assertIsNone(derive_tier_label(cat, 250))

    def test_at_threshold_returns_that_tier(self) -> None:
        cat = PolishCategory.objects.create(name="Elegance")
        TierThreshold.objects.create(category=cat, tier_name="Notable", min_value=500)
        TierThreshold.objects.create(category=cat, tier_name="Grand", min_value=2000)
        self.assertEqual(derive_tier_label(cat, 500), "Notable")
        self.assertEqual(derive_tier_label(cat, 2000), "Grand")

    def test_above_top_threshold_returns_top(self) -> None:
        cat = PolishCategory.objects.create(name="Elegance")
        TierThreshold.objects.create(category=cat, tier_name="Palatial", min_value=10000)
        self.assertEqual(derive_tier_label(cat, 50000), "Palatial")

    def test_categories_are_independent(self) -> None:
        op = PolishCategory.objects.create(name="Opulence")
        el = PolishCategory.objects.create(name="Elegance")
        TierThreshold.objects.create(category=op, tier_name="Modest", min_value=0)
        TierThreshold.objects.create(category=el, tier_name="Notable", min_value=500)
        self.assertEqual(derive_tier_label(op, 100), "Modest")
        self.assertIsNone(derive_tier_label(el, 100))


class ApplyProjectCompletionTests(TestCase):
    def test_single_category_increment_creates_polish_row(self) -> None:
        owner = _make_primary_persona()
        building = _make_building(owner=owner)
        opulence = PolishCategory.objects.create(name="Opulence")
        template = _make_template("Gilded Walls", [(opulence, 800)])

        instance = apply_project_completion(building, template)

        self.assertIsInstance(instance, BuildingProjectInstance)
        bp = BuildingPolish.objects.get(building=building, category=opulence)
        self.assertEqual(bp.value, 800)
        # Instance polish carries the same value.
        ip = BuildingProjectInstancePolish.objects.get(instance=instance, category=opulence)
        self.assertEqual(ip.value, 800)

    def test_multiple_categories_each_increment(self) -> None:
        owner = _make_primary_persona()
        building = _make_building(owner=owner)
        op = PolishCategory.objects.create(name="Opulence")
        el = PolishCategory.objects.create(name="Elegance")
        template = _make_template("Marble Foyer", [(op, 600), (el, 200)])

        apply_project_completion(building, template)

        self.assertEqual(BuildingPolish.objects.get(building=building, category=op).value, 600)
        self.assertEqual(BuildingPolish.objects.get(building=building, category=el).value, 200)

    def test_second_template_stacks_polish(self) -> None:
        owner = _make_primary_persona()
        building = _make_building(owner=owner)
        op = PolishCategory.objects.create(name="Opulence")
        t1 = _make_template("T1", [(op, 100)])
        t2 = _make_template("T2", [(op, 250)])
        apply_project_completion(building, t1)
        apply_project_completion(building, t2)
        bp = BuildingPolish.objects.get(building=building, category=op)
        self.assertEqual(bp.value, 350)

    def test_completion_recomputes_owner_prestige(self) -> None:
        owner = _make_primary_persona()
        area = AreaFactory(level=10)
        building = _make_building(area=area, owner=owner)
        _make_room(area=area, tenant=owner)  # owner's primary home is in the building
        op = PolishCategory.objects.create(name="Opulence")
        template = _make_template("Lacquered Hall", [(op, 1500)])

        apply_project_completion(building, template)

        owner.refresh_from_db()
        self.assertEqual(owner.prestige_from_dwellings, 1500)
        # total_prestige denorm follows.
        self.assertEqual(owner.total_prestige, 1500)

    def test_completion_without_home_in_building_scores_zero(self) -> None:
        """Home-anchored rule (#670): owning polish elsewhere means nothing without a home."""
        owner = _make_primary_persona()
        building = _make_building(owner=owner)
        op = PolishCategory.objects.create(name="Opulence")
        apply_project_completion(building, _make_template("Hall", [(op, 900)]))
        owner.refresh_from_db()
        self.assertEqual(owner.prestige_from_dwellings, 0)

    def test_unowned_building_no_recompute(self) -> None:
        """No owner_persona → no persona to credit; service must not crash."""
        building = _make_building(owner=None)
        op = PolishCategory.objects.create(name="Opulence")
        template = _make_template("Hall", [(op, 500)])
        apply_project_completion(building, template)
        bp = BuildingPolish.objects.get(building=building, category=op)
        self.assertEqual(bp.value, 500)


class ApplyRoomPolishDeltaTests(TestCase):
    def test_positive_delta_creates_row(self) -> None:
        tenant = _make_primary_persona()
        room = _make_room(tenant=tenant)
        cat = PolishCategory.objects.create(name="Elegance")
        result = apply_room_polish_delta(room, cat, 100)
        self.assertEqual(result, 100)
        self.assertEqual(RoomPolish.objects.get(room=room, category=cat).value, 100)

    def test_negative_delta_clamped_at_zero(self) -> None:
        tenant = _make_primary_persona()
        room = _make_room(tenant=tenant)
        cat = PolishCategory.objects.create(name="Elegance")
        apply_room_polish_delta(room, cat, 50)
        result = apply_room_polish_delta(room, cat, -200)
        self.assertEqual(result, 0)

    def test_room_polish_credits_home_holder(self) -> None:
        tenant = _make_primary_persona()
        room = _make_room(tenant=tenant)
        cat = PolishCategory.objects.create(name="Elegance")
        apply_room_polish_delta(room, cat, 300)
        tenant.refresh_from_db()
        self.assertEqual(tenant.prestige_from_dwellings, 300)

    def test_renters_home_room_scores_room_only_not_building(self) -> None:
        """Home-anchored rule (#670): a renter counts their room, never the landlord's walls."""
        owner = _make_primary_persona()
        tenant = _make_primary_persona()
        area = AreaFactory(level=10)
        building = _make_building(area=area, owner=owner)
        room = _make_room(area=area, tenant=tenant)
        op = PolishCategory.objects.create(name="Opulence")
        BuildingPolish.objects.create(building=building, category=op, value=1000)
        cat = PolishCategory.objects.create(name="Elegance")

        apply_room_polish_delta(room, cat, 500)

        owner.refresh_from_db()
        tenant.refresh_from_db()
        # The renter's home room polish counts; the building polish is the owner's.
        self.assertEqual(tenant.prestige_from_dwellings, 500)
        # The owner has no primary home here, so their prestige is 0 (home-anchored).
        self.assertEqual(owner.prestige_from_dwellings, 0)

    def test_owner_living_in_own_building_gets_room_plus_building(self) -> None:
        """Build your own manse and live in it: home room + your building's polish."""
        owner_tenant = _make_primary_persona()
        area = AreaFactory(level=10)
        building = _make_building(area=area, owner=owner_tenant)
        room = _make_room(area=area, tenant=owner_tenant)
        op = PolishCategory.objects.create(name="Opulence")
        BuildingPolish.objects.create(building=building, category=op, value=1000)
        cat = PolishCategory.objects.create(name="Elegance")

        apply_room_polish_delta(room, cat, 400)

        owner_tenant.refresh_from_db()
        # 400 (home room) + 1000 (owned building the home is in) = 1400.
        self.assertEqual(owner_tenant.prestige_from_dwellings, 1400)


class RecomputePrestigeFromDwellingsTests(TestCase):
    """The home-anchored matrix (#670): home in own building / rented / none."""

    def test_home_in_own_building_scores_room_plus_building(self) -> None:
        owner = _make_primary_persona()
        area = AreaFactory(level=10)
        building = _make_building(area=area, owner=owner)
        home = _make_room(area=area, tenant=owner)
        op = PolishCategory.objects.create(name="Opulence")
        el = PolishCategory.objects.create(name="Elegance")
        BuildingPolish.objects.create(building=building, category=op, value=200)
        BuildingPolish.objects.create(building=building, category=el, value=300)
        RoomPolish.objects.create(room=home, category=op, value=150)

        result = recompute_persona_prestige_from_dwellings(owner)

        self.assertEqual(result, 650)
        owner.refresh_from_db()
        self.assertEqual(owner.prestige_from_dwellings, 650)

    def test_persona_with_no_home(self) -> None:
        persona = _make_primary_persona()
        result = recompute_persona_prestige_from_dwellings(persona)
        self.assertEqual(result, 0)
        persona.refresh_from_db()
        self.assertEqual(persona.prestige_from_dwellings, 0)

    def test_owning_polish_elsewhere_does_not_count(self) -> None:
        """A property portfolio is not a home — only the home's building can add."""
        persona = _make_primary_persona()
        area_home = AreaFactory(level=10, name="Rented Inn")
        area_owned = AreaFactory(level=10, name="Manor B")
        landlord = _make_primary_persona()
        _make_building(area=area_home, owner=landlord)
        building_owned = _make_building(area=area_owned, owner=persona)
        home = _make_room(area=area_home, tenant=persona)
        op = PolishCategory.objects.create(name="Opulence")

        BuildingPolish.objects.create(building=building_owned, category=op, value=5000)
        RoomPolish.objects.create(room=home, category=op, value=200)

        result = recompute_persona_prestige_from_dwellings(persona)

        # Only the rented home room (200); the owned-but-not-lived-in manor adds nothing.
        self.assertEqual(result, 200)

    def test_ended_home_tenancy_scores_zero(self) -> None:
        from django.utils import timezone

        from world.locations.models import LocationTenancy

        persona = _make_primary_persona()
        home = _make_room(tenant=persona)
        op = PolishCategory.objects.create(name="Opulence")
        RoomPolish.objects.create(room=home, category=op, value=400)
        LocationTenancy.objects.filter(tenant_persona=persona).update(ends_at=timezone.now())
        self.assertEqual(recompute_persona_prestige_from_dwellings(persona), 0)

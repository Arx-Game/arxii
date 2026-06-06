"""Tests for #742 — owned-dwellings section of the renown payload."""

from __future__ import annotations

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import CharacterFactory
from world.areas.factories import AreaFactory
from world.buildings.factories import BuildingFactory
from world.buildings.models import (
    BuildingPolish,
    BuildingProjectInstance,
    PolishCategory,
    ProjectTemplate,
    TierThreshold,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.societies.renown_serializers import build_renown_payload


def _make_primary_persona():
    character = CharacterFactory()
    sheet = CharacterSheetFactory(character=character)
    return sheet.primary_persona


def _make_building(owner, *, name: str = "Manor"):
    area = AreaFactory(level=10, name=name)
    return BuildingFactory(area=area, owner_persona=owner)


class OwnedDwellingsPayloadShapeTests(TestCase):
    def test_persona_with_no_buildings_yields_empty_list(self) -> None:
        persona = _make_primary_persona()
        payload = build_renown_payload(persona)
        self.assertEqual(payload["owned_dwellings"], [])

    def test_owned_building_appears_with_basic_fields(self) -> None:
        owner = _make_primary_persona()
        _make_building(owner, name="Vermillion Hall")
        payload = build_renown_payload(owner)
        self.assertEqual(len(payload["owned_dwellings"]), 1)
        entry = payload["owned_dwellings"][0]
        self.assertEqual(entry["name"], "Vermillion Hall")
        self.assertFalse(entry["upkeep_warning"])
        self.assertEqual(entry["decayed_features_count"], 0)
        self.assertFalse(entry["dormant"])
        self.assertIsNone(entry["dormant_since"])
        self.assertEqual(entry["polish_by_category"], [])

    def test_buildings_owned_by_others_are_excluded(self) -> None:
        owner = _make_primary_persona()
        other = _make_primary_persona()
        _make_building(owner, name="Mine")
        _make_building(other, name="Theirs")
        payload = build_renown_payload(owner)
        names = [d["name"] for d in payload["owned_dwellings"]]
        self.assertEqual(names, ["Mine"])


class PolishByCategoryTests(TestCase):
    def test_polish_value_surfaces_with_no_tier_when_no_thresholds(self) -> None:
        owner = _make_primary_persona()
        building = _make_building(owner)
        cat = PolishCategory.objects.create(name="Opulence")
        BuildingPolish.objects.create(building=building, category=cat, value=500)
        payload = build_renown_payload(owner)
        polish = payload["owned_dwellings"][0]["polish_by_category"]
        self.assertEqual(len(polish), 1)
        self.assertEqual(polish[0]["category_name"], "Opulence")
        self.assertEqual(polish[0]["value"], 500)
        self.assertIsNone(polish[0]["tier_label"])

    def test_tier_label_resolves_when_threshold_authored(self) -> None:
        owner = _make_primary_persona()
        building = _make_building(owner)
        cat = PolishCategory.objects.create(name="Elegance")
        TierThreshold.objects.create(category=cat, tier_name="Notable", min_value=500)
        TierThreshold.objects.create(category=cat, tier_name="Grand", min_value=2_000)
        BuildingPolish.objects.create(building=building, category=cat, value=2_500)

        payload = build_renown_payload(owner)
        polish = payload["owned_dwellings"][0]["polish_by_category"]

        self.assertEqual(polish[0]["tier_label"], "Grand")


class UpkeepWarningTests(TestCase):
    def test_warning_false_when_no_missed_upkeep(self) -> None:
        owner = _make_primary_persona()
        building = _make_building(owner)
        template = ProjectTemplate.objects.create(name="Hall")
        BuildingProjectInstance.objects.create(
            building=building, template=template, consecutive_missed_upkeep=0
        )
        payload = build_renown_payload(owner)
        self.assertFalse(payload["owned_dwellings"][0]["upkeep_warning"])

    def test_warning_true_when_any_instance_missed_upkeep(self) -> None:
        owner = _make_primary_persona()
        building = _make_building(owner)
        template = ProjectTemplate.objects.create(name="Hall")
        BuildingProjectInstance.objects.create(
            building=building, template=template, consecutive_missed_upkeep=0
        )
        BuildingProjectInstance.objects.create(
            building=building, template=template, consecutive_missed_upkeep=2
        )
        payload = build_renown_payload(owner)
        self.assertTrue(payload["owned_dwellings"][0]["upkeep_warning"])

    def test_decayed_features_count_reflects_decayed_at(self) -> None:
        owner = _make_primary_persona()
        building = _make_building(owner)
        template = ProjectTemplate.objects.create(name="Hall")
        BuildingProjectInstance.objects.create(
            building=building, template=template, decayed_at=timezone.now()
        )
        BuildingProjectInstance.objects.create(
            building=building, template=template, decayed_at=timezone.now()
        )
        BuildingProjectInstance.objects.create(
            building=building, template=template, decayed_at=None
        )
        payload = build_renown_payload(owner)
        self.assertEqual(payload["owned_dwellings"][0]["decayed_features_count"], 2)


class DormancyTests(TestCase):
    def test_dormant_building_surfaces_with_dormant_since(self) -> None:
        owner = _make_primary_persona()
        building = _make_building(owner)
        building.is_accessible = False
        building.dormant_since = timezone.now()
        building.save(update_fields=["is_accessible", "dormant_since"])

        payload = build_renown_payload(owner)
        entry = payload["owned_dwellings"][0]

        self.assertTrue(entry["dormant"])
        self.assertIsNotNone(entry["dormant_since"])

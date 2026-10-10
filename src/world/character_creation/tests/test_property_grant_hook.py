"""Tests for _grant_property_house_if_eligible: the CG-finalize property grant hook."""

from django.test import TestCase

from world.buildings.constants import ConditionTier
from world.buildings.factories import PropertyGrantProfileFactory
from world.buildings.models import Building, BuildingSizeTier
from world.character_creation.factories import BeginningsFactory, CharacterDraftFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.constants import PersonaType
from world.scenes.factories import PersonaFactory


class GrantPropertyHouseIfEligibleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        BuildingSizeTier.objects.get_or_create(tier=1, defaults={"name": "Hut", "space_budget": 50})

    def test_grants_building_when_beginning_has_profile(self):
        from world.character_creation.services import _grant_property_house_if_eligible

        profile = PropertyGrantProfileFactory(activation_target_tier=ConditionTier.RAMSHACKLE)
        beginnings = BeginningsFactory(property_grant_profile=profile)
        draft = CharacterDraftFactory(selected_beginnings=beginnings)
        # Finalize hands the hook the new character's PRIMARY persona (#4226).
        persona = PersonaFactory(
            persona_type=PersonaType.PRIMARY,
            character_sheet=CharacterSheetFactory(primary_persona=False),
        )

        self.assertFalse(Building.objects.filter(owner_persona=persona).exists())
        _grant_property_house_if_eligible(draft, persona)
        self.assertTrue(Building.objects.filter(owner_persona=persona).exists())

    def test_no_grant_when_beginning_has_no_profile(self):
        from world.character_creation.services import _grant_property_house_if_eligible

        beginnings = BeginningsFactory(property_grant_profile=None)
        draft = CharacterDraftFactory(selected_beginnings=beginnings)
        # Finalize hands the hook the new character's PRIMARY persona (#4226).
        persona = PersonaFactory(
            persona_type=PersonaType.PRIMARY,
            character_sheet=CharacterSheetFactory(primary_persona=False),
        )

        _grant_property_house_if_eligible(draft, persona)
        self.assertFalse(Building.objects.filter(owner_persona=persona).exists())

    def test_no_grant_when_no_beginning_selected(self):
        from world.character_creation.services import _grant_property_house_if_eligible

        draft = CharacterDraftFactory(selected_beginnings=None)
        # Finalize hands the hook the new character's PRIMARY persona (#4226).
        persona = PersonaFactory(
            persona_type=PersonaType.PRIMARY,
            character_sheet=CharacterSheetFactory(primary_persona=False),
        )

        _grant_property_house_if_eligible(draft, persona)
        self.assertFalse(Building.objects.filter(owner_persona=persona).exists())

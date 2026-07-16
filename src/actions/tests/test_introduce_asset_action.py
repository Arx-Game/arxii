"""Tests for the IntroduceAssetAction (#2295)."""

from __future__ import annotations

from django.test import TestCase

from actions.registry import get_action
from evennia_extensions.factories import ObjectDBFactory
from world.assets.constants import AssetAcquisitionSource, AssetRoleContext
from world.assets.factories import NPCAssetFactory
from world.assets.models import NPCAsset
from world.scenes.factories import PersonaFactory


class IntroduceAssetActionTests(TestCase):
    """Tests for the introduce_asset REGISTRY action (#2295)."""

    def test_action_is_registered(self) -> None:
        """The action is in the registry at the expected key."""
        action = get_action("introduce_asset")
        self.assertIsNotNone(action)
        self.assertEqual(action.key, "introduce_asset")

    def test_successful_introduction_via_action_run(self) -> None:
        """action.run() creates a co-owner NPCAsset for the ally."""

        from world.character_sheets.factories import CharacterSheetFactory

        # Use CharacterSheetFactory so the persona is PRIMARY (what
        # persona_for_character returns).
        introducer_sheet = CharacterSheetFactory()
        introducer_persona = introducer_sheet.primary_persona
        asset_persona = PersonaFactory()
        ally_sheet = CharacterSheetFactory()
        ally_persona = ally_sheet.primary_persona
        asset = NPCAssetFactory(
            promoter_persona=introducer_persona,
            asset_persona=asset_persona,
            role_context=AssetRoleContext.INFORMANT,
        )

        # Place introducer and ally in the same room.
        room = ObjectDBFactory(db_key="Intro Room")
        introducer_char = introducer_sheet.character
        introducer_char.db_location = room
        introducer_char.save()
        ally_char = ally_sheet.character
        ally_char.db_location = room
        ally_char.save()

        action = get_action("introduce_asset")
        result = action.run(
            actor=introducer_char,
            asset_id=asset.pk,
            ally_persona_id=ally_persona.pk,
        )

        self.assertTrue(result.success)
        # The ally now has an NPCAsset pointing at the same asset_persona.
        co_owner_asset = NPCAsset.objects.filter(
            promoter_persona=ally_persona,
            asset_persona=asset_persona,
        ).first()
        self.assertIsNotNone(co_owner_asset)
        self.assertEqual(
            co_owner_asset.acquisition_source,
            AssetAcquisitionSource.INTRODUCTION,
        )

    def test_not_co_present_returns_failure(self) -> None:
        """Ally not in the room returns a failure result, not an exception."""
        from world.character_sheets.factories import CharacterSheetFactory

        introducer_sheet = CharacterSheetFactory()
        introducer_persona = introducer_sheet.primary_persona
        asset_persona = PersonaFactory()
        ally_sheet = CharacterSheetFactory()
        ally_persona = ally_sheet.primary_persona
        asset = NPCAssetFactory(
            promoter_persona=introducer_persona,
            asset_persona=asset_persona,
        )

        introducer_char = introducer_sheet.character

        action = get_action("introduce_asset")
        result = action.run(
            actor=introducer_char,
            asset_id=asset.pk,
            ally_persona_id=ally_persona.pk,
        )

        self.assertFalse(result.success)

    def test_missing_asset_id_returns_failure(self) -> None:
        """Missing asset_id kwarg returns a clear failure."""
        introducer_persona = PersonaFactory()
        introducer_char = introducer_persona.character_sheet.character

        action = get_action("introduce_asset")
        result = action.run(actor=introducer_char, ally_persona_id=1)

        self.assertFalse(result.success)
        self.assertIn("asset", result.message.lower())

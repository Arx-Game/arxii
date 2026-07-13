"""Tests for the ASSET_STATUS effect handler (#1905).

Verifies that the consequence-pool-driven asset status transition works
end-to-end through the apply_all_effects pipeline.
"""

from __future__ import annotations

from django.test import TestCase

from world.assets.constants import AssetStatus
from world.assets.factories import NPCAssetFactory
from world.checks.constants import EffectTarget, EffectType
from world.checks.factories import ConsequenceFactory
from world.checks.models import ConsequenceEffect
from world.checks.types import ResolutionContext
from world.mechanics.effect_handlers import apply_all_effects
from world.roster.factories import RosterEntryFactory


class AssetStatusEffectHandlerTests(TestCase):
    """Tests for _apply_asset_status handler (#1905)."""

    def test_transitions_active_asset_to_compromised(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory

        sheet = CharacterSheetFactory()
        promoter = sheet.primary_persona
        asset = NPCAssetFactory(promoter_persona=promoter)
        character = sheet.character

        consequence = ConsequenceFactory()
        ConsequenceEffect.objects.create(
            consequence=consequence,
            effect_type=EffectType.ASSET_STATUS,
            target=EffectTarget.SELF,
            asset_status_target=AssetStatus.COMPROMISED,
        )
        context = ResolutionContext(character=character)

        results = apply_all_effects(consequence, context)

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].applied)
        asset.refresh_from_db()
        self.assertEqual(asset.status, AssetStatus.COMPROMISED)

    def test_transitions_active_asset_to_lost(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory

        sheet = CharacterSheetFactory()
        promoter = sheet.primary_persona
        asset = NPCAssetFactory(promoter_persona=promoter)
        character = sheet.character

        consequence = ConsequenceFactory()
        ConsequenceEffect.objects.create(
            consequence=consequence,
            effect_type=EffectType.ASSET_STATUS,
            target=EffectTarget.SELF,
            asset_status_target=AssetStatus.LOST,
        )
        context = ResolutionContext(character=character)

        apply_all_effects(consequence, context)

        asset.refresh_from_db()
        self.assertEqual(asset.status, AssetStatus.LOST)

    def test_no_active_assets_is_noop(self) -> None:
        """Character owns no assets — handler returns applied=False, no error."""
        entry = RosterEntryFactory()
        character = entry.character_sheet.character

        consequence = ConsequenceFactory()
        ConsequenceEffect.objects.create(
            consequence=consequence,
            effect_type=EffectType.ASSET_STATUS,
            target=EffectTarget.SELF,
            asset_status_target=AssetStatus.COMPROMISED,
        )
        context = ResolutionContext(character=character)

        results = apply_all_effects(consequence, context)

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].applied)

    def test_skips_compromised_assets(self) -> None:
        """Only ACTIVE assets are transitioned — COMPROMISED assets are left alone."""
        from world.character_sheets.factories import CharacterSheetFactory

        sheet = CharacterSheetFactory()
        promoter = sheet.primary_persona
        active_asset = NPCAssetFactory(promoter_persona=promoter, status=AssetStatus.ACTIVE)
        compromised_asset = NPCAssetFactory(
            promoter_persona=promoter,
            status=AssetStatus.COMPROMISED,
        )
        character = sheet.character

        consequence = ConsequenceFactory()
        ConsequenceEffect.objects.create(
            consequence=consequence,
            effect_type=EffectType.ASSET_STATUS,
            target=EffectTarget.SELF,
            asset_status_target=AssetStatus.LOST,
        )
        context = ResolutionContext(character=character)

        apply_all_effects(consequence, context)

        active_asset.refresh_from_db()
        compromised_asset.refresh_from_db()
        self.assertEqual(active_asset.status, AssetStatus.LOST)
        self.assertEqual(compromised_asset.status, AssetStatus.COMPROMISED)

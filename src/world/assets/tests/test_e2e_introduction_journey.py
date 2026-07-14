"""E2E journey test for voluntary asset sharing / co-ownership (#2295).

Exercises the full loop: cultivate → introduce → co-task → independent
compromise → shared NPC death.
"""

from __future__ import annotations

from django.test import TestCase

from world.assets.constants import (
    AssetAcquisitionSource,
    AssetRoleContext,
    AssetStatus,
)
from world.assets.factories import NPCAssetFactory
from world.assets.services import (
    introduce_asset,
    transition_asset_status,
    transition_assets_for_dead_character,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.factories import PersonaFactory


class IntroductionJourneyTests(TestCase):
    """Full-journey E2E for #2295 co-ownership."""

    def setUp(self) -> None:
        from evennia.objects.models import ObjectDB

        self.room = ObjectDB.objects.create(db_key="Journey Room")
        self.promoter_sheet = CharacterSheetFactory()
        self.promoter = self.promoter_sheet.primary_persona
        self.ally_sheet = CharacterSheetFactory()
        self.ally = self.ally_sheet.primary_persona
        self.asset_persona = PersonaFactory()

        # Place both PCs in the room.
        for sheet in (self.promoter_sheet, self.ally_sheet):
            character = sheet.character
            character.db_location = self.room
            character.save()

        # Promoter cultivates the asset (simulated via factory).
        self.asset = NPCAssetFactory(
            promoter_persona=self.promoter,
            asset_persona=self.asset_persona,
            role_context=AssetRoleContext.INFORMANT,
            acquisition_source=AssetAcquisitionSource.PROMOTION,
        )

    def test_full_journey(self) -> None:
        # Step 1: Introduce the asset to the ally.
        co_owner_asset = introduce_asset(
            introducer_persona=self.promoter,
            ally_persona=self.ally,
            asset=self.asset,
        )
        self.assertEqual(co_owner_asset.promoter_persona, self.ally)
        self.assertEqual(co_owner_asset.asset_persona, self.asset_persona)
        self.assertEqual(co_owner_asset.acquisition_source, AssetAcquisitionSource.INTRODUCTION)

        # Step 2: Both owners have independent NPCAsset rows.
        from world.assets.models import NPCAsset

        promoter_assets = NPCAsset.objects.filter(
            promoter_persona=self.promoter,
            asset_persona=self.asset_persona,
        )
        ally_assets = NPCAsset.objects.filter(
            promoter_persona=self.ally,
            asset_persona=self.asset_persona,
        )
        self.assertEqual(promoter_assets.count(), 1)
        self.assertEqual(ally_assets.count(), 1)

        # Step 3: Compromising the promoter's asset does NOT affect the ally's.
        transition_asset_status(self.asset, AssetStatus.COMPROMISED)
        co_owner_asset.refresh_from_db()
        self.assertEqual(co_owner_asset.status, AssetStatus.ACTIVE)
        self.assertEqual(self.asset.status, AssetStatus.COMPROMISED)

        # Step 4: NPC death fans out to all ACTIVE co-owners' assets.
        # (transition_assets_for_dead_character only transitions ACTIVE assets —
        # the promoter's COMPROMISED row stays COMPROMISED, the ally's ACTIVE
        # row transitions to LOST.)
        asset_character = self.asset_persona.character_sheet.character
        transition_assets_for_dead_character(asset_character)
        self.asset.refresh_from_db()
        co_owner_asset.refresh_from_db()
        self.assertEqual(self.asset.status, AssetStatus.COMPROMISED)  # unchanged (was not ACTIVE)
        self.assertEqual(co_owner_asset.status, AssetStatus.LOST)

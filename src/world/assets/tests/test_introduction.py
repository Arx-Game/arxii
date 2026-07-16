"""Tests for voluntary asset introduction / co-ownership (#2295)."""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.assets.constants import (
    AssetAcquisitionSource,
    AssetRoleContext,
    AssetStatus,
)
from world.assets.factories import NPCAssetFactory
from world.assets.services import IntroductionError, introduce_asset
from world.scenes.factories import PersonaFactory
from world.scenes.models import Persona


class IntroduceAssetTests(TestCase):
    """Tests for the introduce_asset service (#2295)."""

    def setUp(self) -> None:
        self.introducer = PersonaFactory()
        self.asset_persona = PersonaFactory()
        self.asset = NPCAssetFactory(
            promoter_persona=self.introducer,
            asset_persona=self.asset_persona,
            role_context=AssetRoleContext.INFORMANT,
        )
        self.ally = PersonaFactory()

    def test_successful_introduction_creates_co_owner(self) -> None:
        """Introducing an asset to a co-present ally creates a new NPCAsset for the ally."""
        self._place_in_same_room(self.introducer, self.ally)

        new_asset = introduce_asset(
            introducer_persona=self.introducer,
            ally_persona=self.ally,
            asset=self.asset,
        )

        self.assertEqual(new_asset.promoter_persona, self.ally)
        self.assertEqual(new_asset.asset_persona, self.asset_persona)
        self.assertEqual(new_asset.role_context, AssetRoleContext.INFORMANT)
        self.assertEqual(new_asset.acquisition_source, AssetAcquisitionSource.INTRODUCTION)
        self.assertEqual(new_asset.status, AssetStatus.ACTIVE)

    def test_not_co_present_is_rejected(self) -> None:
        """Ally not in the same room as the introducer is rejected."""
        # setUp places personas without rooms; neither is co-present.
        with self.assertRaises(IntroductionError):
            introduce_asset(
                introducer_persona=self.introducer,
                ally_persona=self.ally,
                asset=self.asset,
            )

    def test_asset_not_owned_by_introducer_is_rejected(self) -> None:
        """Asset not owned by the introducer is rejected."""
        other_persona = PersonaFactory()
        other_asset = NPCAssetFactory(promoter_persona=other_persona)
        self._place_in_same_room(self.introducer, self.ally)

        with self.assertRaises(IntroductionError):
            introduce_asset(
                introducer_persona=self.introducer,
                ally_persona=self.ally,
                asset=other_asset,
            )

    def test_asset_not_active_is_rejected(self) -> None:
        """A non-ACTIVE asset cannot be introduced."""
        from world.assets.services import transition_asset_status

        transition_asset_status(self.asset, AssetStatus.COMPROMISED)
        self._place_in_same_room(self.introducer, self.ally)

        with self.assertRaises(IntroductionError):
            introduce_asset(
                introducer_persona=self.introducer,
                ally_persona=self.ally,
                asset=self.asset,
            )

    def test_duplicate_introduction_is_rejected(self) -> None:
        """Introducing the same asset to the same ally twice is rejected."""
        self._place_in_same_room(self.introducer, self.ally)

        introduce_asset(
            introducer_persona=self.introducer,
            ally_persona=self.ally,
            asset=self.asset,
        )

        with self.assertRaises(IntroductionError):
            introduce_asset(
                introducer_persona=self.introducer,
                ally_persona=self.ally,
                asset=self.asset,
            )

    # --- helpers ---

    def _place_in_same_room(self, *personas: Persona) -> None:
        """Place the characters for the given personas in the same room."""

        room = ObjectDBFactory(db_key="Test Room")
        for persona in personas:
            character = persona.character_sheet.character
            character.location = room
            character.save()

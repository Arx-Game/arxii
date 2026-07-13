"""Tests for asset compromise/loss lifecycle (#1905).

Covers transition_asset_status(), transition_assets_for_dead_character(),
legal/illegal transition matrix, and flow event emission.
"""

from __future__ import annotations

from django.test import TestCase

from world.assets.constants import AssetStatus, AssetTransitionReason
from world.assets.factories import NPCAssetFactory
from world.assets.services import (
    IllegalAssetTransitionError,
    transition_asset_status,
)


class TransitionAssetStatusTests(TestCase):
    """Tests for transition_asset_status() (#1905)."""

    def test_active_to_compromised_succeeds(self) -> None:
        asset = NPCAssetFactory()
        transition_asset_status(asset, AssetStatus.COMPROMISED)
        asset.refresh_from_db()
        self.assertEqual(asset.status, AssetStatus.COMPROMISED)

    def test_active_to_lost_succeeds(self) -> None:
        asset = NPCAssetFactory()
        transition_asset_status(asset, AssetStatus.LOST)
        asset.refresh_from_db()
        self.assertEqual(asset.status, AssetStatus.LOST)

    def test_active_to_dismissed_succeeds(self) -> None:
        asset = NPCAssetFactory()
        transition_asset_status(asset, AssetStatus.DISMISSED)
        asset.refresh_from_db()
        self.assertEqual(asset.status, AssetStatus.DISMISSED)

    def test_compromised_to_active_recovers(self) -> None:
        asset = NPCAssetFactory(status=AssetStatus.COMPROMISED)
        transition_asset_status(asset, AssetStatus.ACTIVE, reason=AssetTransitionReason.RECOVERY)
        asset.refresh_from_db()
        self.assertEqual(asset.status, AssetStatus.ACTIVE)

    def test_compromised_to_lost_succeeds(self) -> None:
        asset = NPCAssetFactory(status=AssetStatus.COMPROMISED)
        transition_asset_status(asset, AssetStatus.LOST)
        asset.refresh_from_db()
        self.assertEqual(asset.status, AssetStatus.LOST)

    def test_lost_is_terminal(self) -> None:
        asset = NPCAssetFactory(status=AssetStatus.LOST)
        with self.assertRaises(IllegalAssetTransitionError):
            transition_asset_status(asset, AssetStatus.ACTIVE)
        with self.assertRaises(IllegalAssetTransitionError):
            transition_asset_status(asset, AssetStatus.COMPROMISED)

    def test_dismissed_is_terminal(self) -> None:
        asset = NPCAssetFactory(status=AssetStatus.DISMISSED)
        with self.assertRaises(IllegalAssetTransitionError):
            transition_asset_status(asset, AssetStatus.ACTIVE)

    def test_noop_transition_is_allowed(self) -> None:
        """Transitioning to the same status is a no-op, not an error."""
        asset = NPCAssetFactory(status=AssetStatus.ACTIVE)
        transition_asset_status(asset, AssetStatus.ACTIVE)
        asset.refresh_from_db()
        self.assertEqual(asset.status, AssetStatus.ACTIVE)


class TransitionAssetsForDeadCharacterTests(TestCase):
    """Tests for transition_assets_for_dead_character() (#1905)."""

    def test_transitions_active_assets_to_lost(self) -> None:
        from world.assets.services import transition_assets_for_dead_character
        from world.scenes.factories import PersonaFactory

        asset_persona = PersonaFactory()
        asset = NPCAssetFactory(asset_persona=asset_persona)
        dead_character = asset_persona.character_sheet.character

        transition_assets_for_dead_character(dead_character)

        asset.refresh_from_db()
        self.assertEqual(asset.status, AssetStatus.LOST)

    def test_does_not_transition_already_lost(self) -> None:
        from world.assets.services import transition_assets_for_dead_character
        from world.scenes.factories import PersonaFactory

        asset_persona = PersonaFactory()
        NPCAssetFactory(asset_persona=asset_persona, status=AssetStatus.LOST)
        dead_character = asset_persona.character_sheet.character

        # Should not raise even though asset is already LOST (terminal).
        transition_assets_for_dead_character(dead_character)

    def test_no_assets_is_noop(self) -> None:
        from world.assets.services import transition_assets_for_dead_character
        from world.character_sheets.services import create_character_with_sheet

        _char, _sheet, _persona = create_character_with_sheet(
            character_key="Nobody",
            primary_persona_name="Nobody",
        )
        # Should not raise when the dead character has no assets.
        transition_assets_for_dead_character(_char)

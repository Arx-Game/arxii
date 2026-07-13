"""Model tests for NPCAsset (#1872)."""

from __future__ import annotations

from django.db import IntegrityError
from django.test import TestCase

from world.assets.constants import (
    AssetRoleContext,
    AssetStatus,
    AssetTransitionReason,
)
from world.assets.factories import NPCAssetFactory
from world.npc_services.factories import FunctionaryFactory
from world.scenes.factories import PersonaFactory


class NPCAssetModelTests(TestCase):
    def test_defaults(self) -> None:
        asset = NPCAssetFactory()
        self.assertEqual(asset.status, AssetStatus.ACTIVE)
        self.assertEqual(asset.role_context, AssetRoleContext.INFORMANT)
        self.assertIsNotNone(asset.created_at)

    def test_cannot_promote_same_functionary_twice_for_same_promoter(self) -> None:
        promoter = PersonaFactory()
        functionary = FunctionaryFactory()
        NPCAssetFactory(promoter_persona=promoter, source_functionary=functionary)
        with self.assertRaises(IntegrityError):
            NPCAssetFactory(promoter_persona=promoter, source_functionary=functionary)

    def test_asset_persona_is_unique_across_assets(self) -> None:
        shared_asset_persona = PersonaFactory()
        NPCAssetFactory(asset_persona=shared_asset_persona)
        with self.assertRaises(IntegrityError):
            NPCAssetFactory(asset_persona=shared_asset_persona)


class AssetStatusEnumTests(TestCase):
    """Tests for AssetStatus and AssetTransitionReason enums (#1905)."""

    def test_all_statuses_exist(self) -> None:
        self.assertEqual(
            set(AssetStatus.values),
            {"active", "compromised", "lost", "dismissed"},
        )

    def test_all_transition_reasons_exist(self) -> None:
        self.assertEqual(
            set(AssetTransitionReason.values),
            {"consequence", "character_killed", "player_dismissal", "recovery"},
        )

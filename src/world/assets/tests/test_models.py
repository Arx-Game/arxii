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

    def test_asset_income_fields_default_to_zero(self) -> None:
        asset = NPCAssetFactory()
        self.assertEqual(asset.weekly_income, 0)
        self.assertEqual(asset.uncollected_pool, 0)

    def test_cannot_promote_same_functionary_twice_for_same_promoter(self) -> None:
        promoter = PersonaFactory()
        functionary = FunctionaryFactory()
        NPCAssetFactory(promoter_persona=promoter, source_functionary=functionary)
        with self.assertRaises(IntegrityError):
            NPCAssetFactory(promoter_persona=promoter, source_functionary=functionary)

    def test_asset_persona_can_be_shared_across_owners(self) -> None:
        """Multiple NPCAsset rows can point at the same asset_persona (#2295)."""
        shared_asset_persona = PersonaFactory()
        promoter_a = PersonaFactory()
        promoter_b = PersonaFactory()
        NPCAssetFactory(promoter_persona=promoter_a, asset_persona=shared_asset_persona)
        # A different promoter CAN own the same NPC — co-ownership.
        asset_b = NPCAssetFactory(promoter_persona=promoter_b, asset_persona=shared_asset_persona)
        self.assertEqual(asset_b.asset_persona, shared_asset_persona)

    def test_same_promoter_cannot_have_duplicate_active_asset(self) -> None:
        """One active NPCAsset per (promoter, asset_persona) — partial unique (#2295)."""
        promoter = PersonaFactory()
        shared_asset_persona = PersonaFactory()
        NPCAssetFactory(promoter_persona=promoter, asset_persona=shared_asset_persona)
        with self.assertRaises(IntegrityError):
            NPCAssetFactory(promoter_persona=promoter, asset_persona=shared_asset_persona)


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

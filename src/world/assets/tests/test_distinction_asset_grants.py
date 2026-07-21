"""Tests for the Distinction-granted starting asset CG channel (#1906)."""

from __future__ import annotations

from django.db import IntegrityError
from evennia.utils.test_resources import EvenniaTestCase

from world.assets.constants import AssetAcquisitionSource, AssetRoleContext
from world.assets.models import DistinctionAssetGrant, NPCAsset
from world.assets.services import reconcile_distinction_asset_grants
from world.character_sheets.factories import CharacterSheetFactory
from world.distinctions.factories import DistinctionFactory
from world.npc_services.models import NPCRole, NPCStanding


class DistinctionAssetGrantReconcileTests(EvenniaTestCase):
    """Unit tests for ``reconcile_distinction_asset_grants`` (the CG consumer).

    Mirrors the test shape of the resonance-grant sibling
    (``world/character_creation/tests/test_services.py``'s distinction CG tests)
    but exercises the asset-grant reconciliation directly — no draft/finalize
    plumbing needed, since the function takes a ``CharacterDistinction``.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character
        cls.distinction = DistinctionFactory(name="Asset Grant Test Distinction")
        cls.npc_role = NPCRole.objects.create(name="Asset Grant Test Role")
        cls.grant = DistinctionAssetGrant.objects.create(
            distinction=cls.distinction,
            npc_role=cls.npc_role,
            role_context=AssetRoleContext.INFORMANT,
            starting_affection=15,
            asset_display_name="Old Friends",
        )

    def _make_char_distinction(self):
        """Create a CharacterDistinction for the test character."""
        from world.distinctions.models import CharacterDistinction

        return CharacterDistinction.objects.create(
            character=self.sheet,
            distinction=self.distinction,
            rank=1,
        )

    def test_creates_npcasset_with_correct_fields(self):
        """Reconciling a CharacterDistinction with a grant creates an NPCAsset."""
        char_dist = self._make_char_distinction()

        reconcile_distinction_asset_grants(char_dist)

        asset = NPCAsset.objects.get(source_distinction_grant=self.grant)
        self.assertEqual(asset.promoter_persona, self.sheet.primary_persona)
        self.assertEqual(asset.role_context, AssetRoleContext.INFORMANT)
        self.assertEqual(asset.acquisition_source, AssetAcquisitionSource.DISTINCTION_GRANT)
        self.assertIsNone(asset.source_functionary)
        self.assertEqual(asset.asset_persona.name, "Old Friends")

    def test_seeds_npcstanding_with_authored_affection(self):
        """The grant's starting_affection seeds an NPCStanding row."""
        char_dist = self._make_char_distinction()

        reconcile_distinction_asset_grants(char_dist)

        standing = NPCStanding.objects.get(
            persona=self.sheet.primary_persona,
            npc_persona=NPCAsset.objects.get(source_distinction_grant=self.grant).asset_persona,
        )
        self.assertEqual(standing.affection, 15)

    def test_idempotent_calling_twice_does_not_double_grant(self):
        """Calling reconcile twice creates only one NPCAsset."""
        char_dist = self._make_char_distinction()

        reconcile_distinction_asset_grants(char_dist)
        reconcile_distinction_asset_grants(char_dist)

        self.assertEqual(
            NPCAsset.objects.filter(source_distinction_grant=self.grant).count(),
            1,
        )

    def test_no_grants_creates_nothing(self):
        """A distinction with no DistinctionAssetGrant rows creates no asset."""
        from world.distinctions.factories import DistinctionFactory

        bare_distinction = DistinctionFactory(name="No Asset Distinction")
        from world.distinctions.models import CharacterDistinction

        char_dist = CharacterDistinction.objects.create(
            character=self.sheet,
            distinction=bare_distinction,
            rank=1,
        )

        reconcile_distinction_asset_grants(char_dist)

        self.assertEqual(
            NPCAsset.objects.filter(promoter_persona=self.sheet.primary_persona).count(), 0
        )

    def test_db_constraint_prevents_duplicate_cg_grant(self):
        """The partial unique constraint blocks duplicate (promoter, grant) pairs."""

        char_dist = self._make_char_distinction()
        # First grant via the service (uses the idempotency check).
        reconcile_distinction_asset_grants(char_dist)
        original = NPCAsset.objects.get(source_distinction_grant=self.grant)

        # Attempting to create a second NPCAsset with the same (promoter, grant)
        # directly at the DB level should hit the partial unique constraint.
        from world.character_sheets.services import create_character_with_sheet

        _char, _sheet, asset_persona = create_character_with_sheet(
            character_key="Duplicate",
            primary_persona_name="Duplicate",
        )
        with self.assertRaises(IntegrityError):
            NPCAsset.objects.create(
                promoter_persona=self.sheet.primary_persona,
                asset_persona=asset_persona,
                role_context=AssetRoleContext.INFORMANT,
                source_functionary=None,
                acquisition_source=AssetAcquisitionSource.DISTINCTION_GRANT,
                source_distinction_grant=self.grant,
            )
        # Original asset untouched.
        original.refresh_from_db()
        self.assertEqual(original.asset_persona.name, "Old Friends")

    def test_runtime_promotion_default_acquisition_source(self):
        """An NPCAsset created without explicit acquisition_source defaults to PROMOTION.

        This verifies migration safety: existing runtime-promoted assets keep
        the PROMOTION default after the field was added.
        """
        from world.assets.factories import NPCAssetFactory

        asset = NPCAssetFactory()
        self.assertEqual(asset.acquisition_source, AssetAcquisitionSource.PROMOTION)
        self.assertIsNotNone(asset.source_functionary)
        self.assertIsNone(asset.source_distinction_grant)

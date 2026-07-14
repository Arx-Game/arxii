"""Leverage coercion into an NPCAsset (#1680 slice 3).

Holding leverage over a sheeted NPC lets the blackmailer extract them as a
COERCION asset of a chosen role_context, reusing the whole NPCAsset machinery.
"""

from django.test import TestCase

from world.assets.constants import AssetAcquisitionSource, AssetRoleContext
from world.assets.models import NPCAsset
from world.assets.services import CoercionError, coerce_into_asset
from world.scenes.factories import PersonaFactory
from world.secrets.factories import LeverageFactory


class CoerceIntoAssetTests(TestCase):
    def setUp(self) -> None:
        self.coercer = PersonaFactory()
        self.target = PersonaFactory()
        # Establish standing leverage between the two sheets (as a successful Blackmail would).
        LeverageFactory(
            holder_sheet=self.coercer.character_sheet,
            subject_sheet=self.target.character_sheet,
        )

    def test_mints_a_coercion_asset_of_the_chosen_kind(self) -> None:
        asset = coerce_into_asset(
            coercer_persona=self.coercer,
            target_persona=self.target,
            role_context=AssetRoleContext.INFORMANT,
        )
        self.assertEqual(asset.promoter_persona, self.coercer)
        self.assertEqual(asset.asset_persona, self.target)
        self.assertEqual(asset.role_context, AssetRoleContext.INFORMANT)
        self.assertEqual(asset.acquisition_source, AssetAcquisitionSource.COERCION)
        self.assertIsNone(asset.source_functionary)

    def test_requires_leverage(self) -> None:
        stranger = PersonaFactory()  # no leverage established over this one
        with self.assertRaises(CoercionError):
            coerce_into_asset(
                coercer_persona=self.coercer,
                target_persona=stranger,
                role_context=AssetRoleContext.CONTACT,
            )
        self.assertFalse(NPCAsset.objects.filter(asset_persona=stranger).exists())

    def test_re_coercion_on_same_target_is_rejected(self) -> None:
        """A second coercion on the same NPC is blocked (#2295 scoping)."""
        coerce_into_asset(
            coercer_persona=self.coercer,
            target_persona=self.target,
            role_context=AssetRoleContext.PERSONAL_FAVOR,
        )
        # A second coercion (even by the same coercer) is blocked.
        with self.assertRaises(CoercionError):
            coerce_into_asset(
                coercer_persona=self.coercer,
                target_persona=self.target,
                role_context=AssetRoleContext.INFORMANT,
            )
        self.assertEqual(
            NPCAsset.objects.filter(
                asset_persona=self.target,
                acquisition_source=AssetAcquisitionSource.COERCION,
            ).count(),
            1,
        )

    def test_promotion_asset_does_not_block_coercion(self) -> None:
        """A voluntarily-cultivated asset does not block coercion (#2295)."""
        from world.assets.factories import NPCAssetFactory

        # Create a PROMOTION asset on the target by a different promoter.
        other_promoter = PersonaFactory()
        NPCAssetFactory(
            promoter_persona=other_promoter,
            asset_persona=self.target,
            acquisition_source=AssetAcquisitionSource.PROMOTION,
        )
        # Coercion should still succeed — only COERCION assets block re-coercion.
        asset = coerce_into_asset(
            coercer_persona=self.coercer,
            target_persona=self.target,
            role_context=AssetRoleContext.PERSONAL_FAVOR,
        )
        self.assertEqual(asset.acquisition_source, AssetAcquisitionSource.COERCION)

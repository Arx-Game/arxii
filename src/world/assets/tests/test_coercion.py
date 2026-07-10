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

    def test_target_already_an_asset_is_rejected(self) -> None:
        coerce_into_asset(
            coercer_persona=self.coercer,
            target_persona=self.target,
            role_context=AssetRoleContext.PERSONAL_FAVOR,
        )
        # asset_persona is OneToOne — a second claim (even by the same coercer) is blocked.
        with self.assertRaises(CoercionError):
            coerce_into_asset(
                coercer_persona=self.coercer,
                target_persona=self.target,
                role_context=AssetRoleContext.INFORMANT,
            )
        self.assertEqual(NPCAsset.objects.filter(asset_persona=self.target).count(), 1)

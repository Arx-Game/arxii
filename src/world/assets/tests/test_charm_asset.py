"""Charm-sourced NPCAsset acquisition (#2502).

Mirrors ``test_coercion.py``: a charmed NPC is extracted as a CHARM asset.
The charmed state is the leverage — verified via ``source_character`` FK.
"""

from django.test import TestCase

from world.assets.constants import AssetAcquisitionSource, AssetRoleContext
from world.assets.models import NPCAsset
from world.assets.services import CharmError, charm_into_asset
from world.conditions.charm_content import ensure_charm_content
from world.conditions.constants import CHARM_CONDITION_NAME
from world.conditions.models import ConditionTemplate
from world.conditions.services import apply_condition, get_active_conditions
from world.scenes.factories import PersonaFactory


class CharmIntoAssetTests(TestCase):
    def setUp(self) -> None:
        ensure_charm_content()
        self.charmer = PersonaFactory()
        self.target = PersonaFactory()
        # Apply the Charmed condition with source_character = the charmer.
        charm_template = ConditionTemplate.get_by_name(CHARM_CONDITION_NAME)
        target_character = self.target.character_sheet.character
        apply_condition(
            target_character,
            charm_template,
            source_character=self.charmer.character_sheet.character,
        )

    def test_mints_a_charm_asset_of_the_chosen_kind(self) -> None:
        asset = charm_into_asset(
            charmer_persona=self.charmer,
            target_persona=self.target,
            role_context=AssetRoleContext.INFORMANT,
        )
        self.assertEqual(asset.promoter_persona, self.charmer)
        self.assertEqual(asset.asset_persona, self.target)
        self.assertEqual(asset.role_context, AssetRoleContext.INFORMANT)
        self.assertEqual(asset.acquisition_source, AssetAcquisitionSource.CHARM)

    def test_requires_charm_by_charmer(self) -> None:
        stranger = PersonaFactory()  # no charm condition on this NPC
        with self.assertRaises(CharmError):
            charm_into_asset(
                charmer_persona=self.charmer,
                target_persona=stranger,
                role_context=AssetRoleContext.CONTACT,
            )
        self.assertFalse(NPCAsset.objects.filter(asset_persona=stranger).exists())

    def test_re_charm_on_same_target_rejected(self) -> None:
        """A second CHARM asset on the same NPC is blocked."""
        charm_into_asset(
            charmer_persona=self.charmer,
            target_persona=self.target,
            role_context=AssetRoleContext.PERSONAL_FAVOR,
        )
        with self.assertRaises(CharmError):
            charm_into_asset(
                charmer_persona=self.charmer,
                target_persona=self.target,
                role_context=AssetRoleContext.INFORMANT,
            )
        self.assertEqual(
            NPCAsset.objects.filter(
                asset_persona=self.target,
                acquisition_source=AssetAcquisitionSource.CHARM,
            ).count(),
            1,
        )

    def test_charm_not_consumed(self) -> None:
        """The Charmed condition persists after charm_into_asset (leverage model)."""
        charm_into_asset(
            charmer_persona=self.charmer,
            target_persona=self.target,
            role_context=AssetRoleContext.INFORMANT,
        )
        target_character = self.target.character_sheet.character
        charm_template = ConditionTemplate.get_by_name(CHARM_CONDITION_NAME)
        active = get_active_conditions(target_character, condition=charm_template)
        self.assertTrue(any(active), "Charm condition should persist after acquisition")

    def test_wrong_charmer_rejected(self) -> None:
        """A target charmed by someone else is rejected (source_character check)."""
        other_charmer = PersonaFactory()
        with self.assertRaises(CharmError):
            charm_into_asset(
                charmer_persona=other_charmer,
                target_persona=self.target,
                role_context=AssetRoleContext.INFORMANT,
            )

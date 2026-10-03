"""Renaming the charm row changes nothing; clearing its field changes everything (#4091)."""

from django.test import TestCase

from world.assets.constants import AssetRoleContext
from world.assets.services import charm_into_asset
from world.checks.factories import CheckTypeFactory
from world.combat.factories import CombatEncounterFactory, CombatOpponentFactory
from world.companions.services import _is_charmed_by_caster
from world.conditions.constants import Allegiance
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.conditions.services import apply_condition
from world.npc_services.allegiance import effective_allegiances
from world.scenes.factories import PersonaFactory


class RenameGuardTests(TestCase):
    def test_rename_keeps_charm(self):
        charm = ConditionTemplateFactory(
            name="Charmed",
            sets_allegiance=Allegiance.ALLY_OF_CASTER,
            allegiance_break_check_type=CheckTypeFactory(name="Insight RG"),
        )
        opp = CombatOpponentFactory(encounter=CombatEncounterFactory())
        ConditionInstanceFactory(target=opp.objectdb, condition=charm)
        charm.name = "Beguiled"
        charm.save(update_fields=["name"])
        self.assertEqual(effective_allegiances([opp])[opp.pk], Allegiance.ALLY_OF_CASTER)

    def test_clearing_the_field_ends_it(self):
        charm = ConditionTemplateFactory(name="Charmed", sets_allegiance="")
        opp = CombatOpponentFactory(encounter=CombatEncounterFactory())
        ConditionInstanceFactory(target=opp.objectdb, condition=charm)
        self.assertEqual(effective_allegiances([opp])[opp.pk], Allegiance.ENEMY)

    def test_renamed_charm_still_gates_companion_and_asset_reads(self):
        """A renamed charm template still drives both name-free charm reads (#4091)."""
        charm = ConditionTemplateFactory(
            name="Charmed",
            sets_allegiance=Allegiance.ALLY_OF_CASTER,
            allegiance_break_check_type=CheckTypeFactory(name="Insight RG2"),
        )
        charm.name = "Beguiled"
        charm.save(update_fields=["name"])

        charmer = PersonaFactory()
        target = PersonaFactory()
        charmer_character = charmer.character_sheet.character
        target_character = target.character_sheet.character
        apply_condition(target_character, charm, source_character=charmer_character)

        asset = charm_into_asset(
            charmer_persona=charmer,
            target_persona=target,
            role_context=AssetRoleContext.INFORMANT,
        )
        self.assertEqual(asset.asset_persona, target)

        opp = CombatOpponentFactory(encounter=CombatEncounterFactory(), persona=target)
        self.assertTrue(_is_charmed_by_caster(opp, charmer_character))

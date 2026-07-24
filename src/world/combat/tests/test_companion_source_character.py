"""Tests that NPC-applied conditions carry source_character provenance (#2666)."""

from django.test import TestCase


class NpcConditionSourceCharacterTests(TestCase):
    """Conditions applied by NPC actions carry source_character (#2666)."""

    def test_npc_action_conditions_carry_source_character(self):
        from evennia.utils.create import create_object

        from world.character_sheets.factories import CharacterSheetFactory
        from world.combat.constants import (
            CombatAllegiance,
            OpponentStatus,
            ParticipantStatus,
        )
        from world.combat.factories import (
            CombatEncounterFactory,
            CombatOpponentActionFactory,
            CombatOpponentFactory,
            ThreatPoolEntryFactory,
        )
        from world.combat.models import CombatParticipant
        from world.combat.services import _resolve_npc_action
        from world.combat.typeclasses.combat_npc import CombatNPC
        from world.conditions.factories import ConditionTemplateFactory
        from world.conditions.models import ConditionInstance
        from world.vitals.factories import CharacterVitalsFactory

        sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=sheet)
        encounter = CombatEncounterFactory()
        participant = CombatParticipant.objects.create(
            encounter=encounter,
            character_sheet=sheet,
            status=ParticipantStatus.ACTIVE,
        )

        npc_obj = create_object(CombatNPC, key="TestNPC")
        opponent = CombatOpponentFactory(
            encounter=encounter,
            allegiance=CombatAllegiance.ENEMY,
            status=OpponentStatus.ACTIVE,
        )
        opponent.objectdb = npc_obj
        opponent.save(update_fields=["objectdb"])

        condition_template = ConditionTemplateFactory(name="TestPoison2666")
        threat_entry = ThreatPoolEntryFactory(base_damage=5)
        threat_entry.conditions_applied.add(condition_template)
        npc_action = CombatOpponentActionFactory(
            opponent=opponent,
            threat_entry=threat_entry,
            round_number=1,
        )
        npc_action.targets.add(participant)

        _resolve_npc_action(
            opponent,
            npc_action,
            defense_check_type=None,
            defense_check_fn=None,
        )

        instance = ConditionInstance.objects.filter(
            target=sheet.character,
            condition=condition_template,
        ).first()
        self.assertIsNotNone(instance, "Condition should have been applied")
        self.assertEqual(instance.source_character, npc_obj)

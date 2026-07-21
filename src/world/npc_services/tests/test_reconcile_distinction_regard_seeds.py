"""Tests for reconcile_distinction_regard_seeds — chargen bond seeding (#2039)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.distinctions.factories import CharacterDistinctionFactory, DistinctionFactory
from world.npc_services.constants import NpcRegardEventReason
from world.npc_services.factories import DistinctionRegardSeedFactory
from world.npc_services.models import NpcRegard, NpcRegardEvent
from world.npc_services.regard import reconcile_distinction_regard_seeds
from world.scenes.factories import PersonaFactory


class ReconcileDistinctionRegardSeedsTests(TestCase):
    def test_seeds_npc_regard_at_starting_value(self):
        distinction = DistinctionFactory()
        npc = PersonaFactory()
        DistinctionRegardSeedFactory(distinction=distinction, npc_persona=npc, starting_value=-80)
        sheet = CharacterSheetFactory()
        char_dist = CharacterDistinctionFactory(character=sheet, distinction=distinction)

        reconcile_distinction_regard_seeds(char_dist)

        primary_persona = sheet.primary_persona
        regard = NpcRegard.objects.get(holder_persona=npc, target_persona=primary_persona)
        self.assertEqual(regard.value, -80)
        event = NpcRegardEvent.objects.get(regard=regard)
        self.assertEqual(event.reason, NpcRegardEventReason.DISTINCTION_SEED)
        self.assertEqual(event.amount, -80)

    def test_distinction_with_no_seeds_is_a_no_op(self):
        distinction = DistinctionFactory()
        sheet = CharacterSheetFactory()
        char_dist = CharacterDistinctionFactory(character=sheet, distinction=distinction)
        reconcile_distinction_regard_seeds(char_dist)
        self.assertEqual(NpcRegard.objects.count(), 0)

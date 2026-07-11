"""Tests for DistinctionRegardSeed uniqueness (#2039)."""

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.distinctions.factories import DistinctionFactory
from world.npc_services.factories import DistinctionRegardSeedFactory
from world.scenes.factories import PersonaFactory


class DistinctionRegardSeedTests(TestCase):
    def test_unique_per_distinction_and_npc(self):
        distinction = DistinctionFactory()
        npc = PersonaFactory()
        DistinctionRegardSeedFactory(distinction=distinction, npc_persona=npc)
        with self.assertRaises(IntegrityError), transaction.atomic():
            DistinctionRegardSeedFactory(distinction=distinction, npc_persona=npc)

    def test_same_distinction_different_npc_allowed(self):
        distinction = DistinctionFactory()
        npc_one = PersonaFactory()
        npc_two = PersonaFactory()
        DistinctionRegardSeedFactory(distinction=distinction, npc_persona=npc_one)
        DistinctionRegardSeedFactory(distinction=distinction, npc_persona=npc_two)

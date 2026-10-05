"""Constraints on technique manifest options and character manifestations (#4118)."""

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.companions.factories import CompanionArchetypeFactory
from world.magic.factories import (
    CharacterManifestationFactory,
    TechniqueFactory,
    TechniqueManifestOptionFactory,
)
from world.magic.models import TechniqueManifestOption
from world.worship.factories import WorshippedBeingFactory


class TechniqueManifestOptionConstraintTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.technique = TechniqueFactory()
        cls.being = WorshippedBeingFactory()
        cls.archetype = CompanionArchetypeFactory()

    def test_both_entities_rejected(self):
        with transaction.atomic(), self.assertRaises(IntegrityError):
            TechniqueManifestOption.objects.create(
                technique=self.technique, being=self.being, archetype=self.archetype
            )

    def test_neither_entity_rejected(self):
        with transaction.atomic(), self.assertRaises(IntegrityError):
            TechniqueManifestOption.objects.create(technique=self.technique)

    def test_duplicate_being_rejected(self):
        TechniqueManifestOptionFactory(technique=self.technique, being=self.being)
        with transaction.atomic(), self.assertRaises(IntegrityError):
            TechniqueManifestOption.objects.create(technique=self.technique, being=self.being)

    def test_duplicate_archetype_rejected(self):
        TechniqueManifestOptionFactory(
            technique=self.technique, being=None, archetype=self.archetype
        )
        with transaction.atomic(), self.assertRaises(IntegrityError):
            TechniqueManifestOption.objects.create(
                technique=self.technique, archetype=self.archetype
            )


class CharacterManifestationConstraintTests(TestCase):
    def test_one_manifestation_per_character_and_technique(self):
        first = CharacterManifestationFactory()
        other_option = TechniqueManifestOptionFactory(technique=first.technique)
        with transaction.atomic(), self.assertRaises(IntegrityError):
            CharacterManifestationFactory(
                character=first.character, option=other_option, technique=first.technique
            )

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.combat.constants import SpectacleKind
from world.combat.factories import CombatOpponentFactory, SpectacleRecordFactory
from world.magic.factories import TechniqueFactory


class SpectacleRecordConstraintTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.record = SpectacleRecordFactory(kind=SpectacleKind.AUDERE_ENTRY)
        cls.technique = TechniqueFactory()

    def test_same_kind_without_technique_is_unique(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            SpectacleRecordFactory(
                opponent=self.record.opponent,
                caster=self.record.caster,
                kind=SpectacleKind.AUDERE_ENTRY,
            )

    def test_same_technique_is_unique_across_kinds(self):
        SpectacleRecordFactory(
            opponent=self.record.opponent,
            caster=self.record.caster,
            kind=SpectacleKind.ULTIMATE,
            technique=self.technique,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            SpectacleRecordFactory(
                opponent=self.record.opponent,
                caster=self.record.caster,
                kind=SpectacleKind.CRITICAL_TECHNIQUE,
                technique=self.technique,
            )

    def test_other_opponent_is_allowed(self):
        other = CombatOpponentFactory(encounter=self.record.encounter)
        SpectacleRecordFactory(opponent=other, caster=self.record.caster)

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.combat.constants import SpectacleKind
from world.combat.factories import CombatOpponentFactory, SpectacleRecordFactory
from world.combat.models import SpectacleReactionLine
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
        other = CombatOpponentFactory(encounter=self.record.opponent.encounter)
        SpectacleRecordFactory(opponent=other, caster=self.record.caster)


class SpectacleReactionLineHelpTextTests(TestCase):
    def test_text_help_escapes_placeholders_so_admin_shows_them(self):
        help_text = SpectacleReactionLine._meta.get_field("text").help_text
        self.assertIn("&lt;actor&gt; &lt;group&gt; &lt;display&gt;", help_text)
        self.assertNotIn("<actor>", help_text)

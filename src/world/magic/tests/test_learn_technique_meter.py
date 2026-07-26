"""Tests for learn_technique meter creation (#2711)."""

from django.test import TestCase

from world.achievements.constants import AccessChangeSource
from world.action_points.models import ActionPointPool
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import TargetKind
from world.magic.factories import (
    GiftFactory,
    ResonanceFactory,
    TechniqueFactory,
)
from world.magic.models import (
    CharacterGift,
    CharacterTechnique,
    TechniqueProgress,
    Thread,
)
from world.magic.services.technique_acquisition import learn_technique


class LearnTechniqueMeterTest(TestCase):
    def setUp(self):
        self.sheet = CharacterSheetFactory()
        self.pool = ActionPointPool.get_or_create_for_character(self.sheet.character)
        self.pool.current = 500
        self.pool.save()
        self.gift = GiftFactory()
        self.technique = TechniqueFactory(gift=self.gift)
        CharacterGift.objects.create(character=self.sheet, gift=self.gift)
        Thread.objects.create(
            owner=self.sheet,
            resonance=ResonanceFactory(),
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
            level=0,
        )

    def test_ap_cost_creates_meter(self):
        result = learn_technique(
            self.sheet,
            self.technique,
            source=AccessChangeSource.TECHNIQUE_GRANT,
            ap_cost=30,
        )
        self.assertIsInstance(result, TechniqueProgress)
        self.assertEqual(result.total_required, 30)
        self.assertFalse(
            CharacterTechnique.objects.filter(
                character=self.sheet,
                technique=self.technique,
            ).exists()
        )

    def test_zero_ap_cost_mints_immediately(self):
        result = learn_technique(
            self.sheet,
            self.technique,
            source=AccessChangeSource.TECHNIQUE_GRANT,
            ap_cost=0,
        )
        self.assertIsInstance(result, CharacterTechnique)
        self.assertFalse(
            TechniqueProgress.objects.filter(
                character_sheet=self.sheet,
                technique=self.technique,
            ).exists()
        )

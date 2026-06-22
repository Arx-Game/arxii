from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from world.magic.constants import RitualExecutionKind
from world.magic.factories import CharacterResonanceFactory, RitualFactory
from world.magic.models import PendingRitualEffect


class PendingRitualEffectTests(TestCase):
    def test_create(self):
        ritual = RitualFactory(
            execution_kind=RitualExecutionKind.CEREMONY, service_function_path=""
        )
        sheet = CharacterResonanceFactory().character_sheet
        effect = PendingRitualEffect.objects.create(character=sheet, ritual=ritual)
        self.assertEqual(effect.stage, 1)
        self.assertIsNotNone(effect.created_at)

    def test_unique_per_character_ritual(self):
        ritual = RitualFactory(
            execution_kind=RitualExecutionKind.CEREMONY, service_function_path=""
        )
        sheet = CharacterResonanceFactory().character_sheet
        PendingRitualEffect.objects.create(character=sheet, ritual=ritual)
        with self.assertRaises(IntegrityError):
            PendingRitualEffect.objects.create(character=sheet, ritual=ritual)

    def test_ceremony_ritual_rejects_service_path(self):
        ritual = RitualFactory.build(
            execution_kind=RitualExecutionKind.CEREMONY,
            service_function_path="world.magic.services.something",
        )
        with self.assertRaises(ValidationError):
            ritual.full_clean()

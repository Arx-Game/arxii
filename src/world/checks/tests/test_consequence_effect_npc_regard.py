"""Tests for ConsequenceEffect.npc_regard_amount + EffectType.SHIFT_NPC_REGARD (#2039)."""

from django.test import TestCase

from world.checks.constants import EffectType
from world.checks.factories import ConsequenceEffectFactory


class ConsequenceEffectNpcRegardTests(TestCase):
    def test_shift_npc_regard_effect_type_exists(self):
        self.assertIn(EffectType.SHIFT_NPC_REGARD, EffectType.values)

    def test_npc_regard_amount_field_defaults_to_none(self):
        effect = ConsequenceEffectFactory(effect_type=EffectType.SHIFT_NPC_REGARD)
        self.assertIsNone(effect.npc_regard_amount)

    def test_npc_regard_amount_field_stores_signed_value(self):
        effect = ConsequenceEffectFactory(
            effect_type=EffectType.SHIFT_NPC_REGARD,
            npc_regard_amount=-15,
        )
        effect.refresh_from_db()
        self.assertEqual(effect.npc_regard_amount, -15)

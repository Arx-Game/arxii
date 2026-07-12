"""DisguiseKitEffect model and use-item dispatch (#2249)."""

from django.test import TestCase

from world.forms.models import ConcealmentLevel, DisguiseKind
from world.items.models import DisguiseKitEffect, ItemTemplate


class DisguiseKitEffectModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.template = ItemTemplate.objects.create(name="Basic Disguise Kit")

    def test_can_create_effect_with_kind_and_level(self):
        effect = DisguiseKitEffect.objects.create(
            item_template=self.template,
            disguise_kind=DisguiseKind.MUNDANE,
            concealment_level=ConcealmentLevel.DESCRIPTOR,
        )
        self.assertEqual(effect.disguise_kind, DisguiseKind.MUNDANE)
        self.assertEqual(effect.concealment_level, ConcealmentLevel.DESCRIPTOR)

    def test_defaults_to_mundane_none(self):
        effect = DisguiseKitEffect.objects.create(item_template=self.template)
        self.assertEqual(effect.disguise_kind, DisguiseKind.MUNDANE)
        self.assertEqual(effect.concealment_level, ConcealmentLevel.NONE)

    def test_related_name_on_template(self):
        DisguiseKitEffect.objects.create(item_template=self.template)
        self.assertEqual(self.template.disguise_kit_effects.count(), 1)

    def test_str_includes_template_name(self):
        effect = DisguiseKitEffect.objects.create(item_template=self.template)
        self.assertIn("Basic Disguise Kit", str(effect))

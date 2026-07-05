"""Tests for ItemRequirement: dual match-mode constraint + possession checks (#1859)."""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.classes.factories import CharacterClassFactory
from world.items.factories import ItemTemplateFactory
from world.magic.factories import ResonanceTierFactory
from world.progression.models import ClassLevelUnlock, ItemRequirement


class ItemRequirementConstraintTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.character_class = CharacterClassFactory()
        cls.unlock = ClassLevelUnlock.objects.create(
            character_class=cls.character_class, target_level=4
        )

    def test_template_mode_row(self) -> None:
        template = ItemTemplateFactory()
        req = ItemRequirement.objects.create(class_level_unlock=self.unlock, item_template=template)
        assert req.item_template_id == template.pk
        assert req.min_touchstone_tier_id is None

    def test_touchstone_mode_row(self) -> None:
        tier = ResonanceTierFactory(name="Faint", tier_level=1)
        req = ItemRequirement.objects.create(
            class_level_unlock=self.unlock, min_touchstone_tier=tier
        )
        assert req.item_template_id is None
        assert req.min_touchstone_tier_id == tier.pk

    def test_neither_set_is_rejected(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            ItemRequirement.objects.create(class_level_unlock=self.unlock)

    def test_both_set_is_rejected(self) -> None:
        template = ItemTemplateFactory()
        tier = ResonanceTierFactory(name="Faint", tier_level=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ItemRequirement.objects.create(
                class_level_unlock=self.unlock,
                item_template=template,
                min_touchstone_tier=tier,
            )

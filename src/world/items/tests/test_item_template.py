"""Tests for ItemTemplate model fields."""

from django.test import TestCase

from actions.constants import TargetKind
from world.items.factories import ItemTemplateFactory


class OnUseTargetKindTests(TestCase):
    def test_defaults_to_null_self_use(self) -> None:
        template = ItemTemplateFactory(name="Self Potion")
        assert template.on_use_target_kind is None

    def test_accepts_character_kind(self) -> None:
        template = ItemTemplateFactory(
            name="Healing Salve", on_use_target_kind=TargetKind.CHARACTER
        )
        template.refresh_from_db()
        assert template.on_use_target_kind == TargetKind.CHARACTER

"""Tests for ItemTemplate model fields."""

from django.test import TestCase

from actions.constants import TargetKind
from actions.factories import ConsequencePoolFactory
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


class IsUsablePropertyTests(TestCase):
    def test_is_usable_true_when_on_use_pool_set(self) -> None:
        pool = ConsequencePoolFactory()
        template = ItemTemplateFactory(on_use_pool=pool)
        assert template.is_usable is True

    def test_is_usable_false_when_on_use_pool_is_null(self) -> None:
        template = ItemTemplateFactory(on_use_pool=None)
        assert template.is_usable is False

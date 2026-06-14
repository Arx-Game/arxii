"""Tests for ItemState permission methods."""

from unittest.mock import MagicMock

from django.test import TestCase

from flows.object_states.item_state import ItemState
from world.items.factories import ItemInstanceFactory


class ItemStateDefaultsTests(TestCase):
    """ItemState exposes can_* methods that default to True."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.item = ItemInstanceFactory()

    def setUp(self) -> None:
        # SceneDataManager is normally injected; for can_* defaults a
        # bare MagicMock context is fine since the methods do not touch it.
        self.state = ItemState(self.item, context=MagicMock())

    def test_can_take_default_true(self) -> None:
        # No actor supplied — short-circuits to permissive (used by tests /
        # package hooks). With a real actor, can_take consults reach.
        self.assertTrue(self.state.can_take())

    def test_can_drop_default_true(self) -> None:
        self.assertTrue(self.state.can_drop())

    def test_can_give_default_true(self) -> None:
        self.assertTrue(self.state.can_give())

    def test_can_equip_default_true(self) -> None:
        self.assertTrue(self.state.can_equip())

    def test_instance_property_returns_wrapped_obj(self) -> None:
        # ``instance`` is a typed alias for ``obj``; cast is a runtime no-op.
        self.assertIs(self.state.instance, self.state.obj)


class ItemStatePackageHookTests(TestCase):
    """Behavior packages can deny ItemState permission checks via hooks."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.item = ItemInstanceFactory()

    def setUp(self) -> None:
        self.state = ItemState(self.item, context=MagicMock())

    def _attach_denying_package(self, hook_name: str) -> None:
        """Attach a fake package whose ``hook_name`` hook returns ``False``."""

        package = MagicMock()
        package.get_hook.side_effect = (
            lambda name, _hook=hook_name: (lambda *_a, **_kw: False) if name == _hook else None
        )
        self.state.packages = [package]

    def test_can_take_denied_by_package_hook(self) -> None:
        self._attach_denying_package("can_take")
        self.assertFalse(self.state.can_take(taker=MagicMock()))


class ItemInstanceDestructionHelpersTests(TestCase):
    def test_bare_instance_does_not_differ(self):
        from world.items.factories import ItemInstanceFactory

        inst = ItemInstanceFactory(
            custom_name="", custom_description="", lore_value=0, quality_tier=None
        )
        self.assertFalse(inst.differs_from_template)

    def test_custom_name_differs(self):
        from world.items.factories import ItemInstanceFactory

        self.assertTrue(ItemInstanceFactory(custom_name="Excalibur").differs_from_template)

    def test_in_play_excludes_destroyed(self):
        from django.utils import timezone

        from world.items.factories import ItemInstanceFactory
        from world.items.models import ItemInstance

        live = ItemInstanceFactory()
        dead = ItemInstanceFactory(destroyed_at=timezone.now())
        ids = set(ItemInstance.objects.in_play().values_list("pk", flat=True))
        self.assertIn(live.pk, ids)
        self.assertNotIn(dead.pk, ids)

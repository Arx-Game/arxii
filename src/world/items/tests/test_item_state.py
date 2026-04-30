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
        self.assertTrue(self.state.can_take(taker=MagicMock()))

    def test_can_drop_default_true(self) -> None:
        self.assertTrue(self.state.can_drop(dropper=MagicMock()))

    def test_can_give_default_true(self) -> None:
        self.assertTrue(self.state.can_give(giver=MagicMock(), recipient=MagicMock()))

    def test_can_equip_default_true(self) -> None:
        self.assertTrue(self.state.can_equip(wearer=MagicMock()))

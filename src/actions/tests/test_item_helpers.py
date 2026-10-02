"""Tests for the explicitly typed action-to-item bridge."""

from django.test import TestCase

from actions.definitions.item_helpers import resolve_item_instance
from evennia_extensions.factories import ObjectDBFactory
from world.items.factories import ItemInstanceFactory


class ResolveItemInstanceTests(TestCase):
    """Resolve model instances without guessing integer ID domains."""

    def test_returns_item_instance_without_a_physical_object(self) -> None:
        item = ItemInstanceFactory(game_object=None)

        resolved = resolve_item_instance(item)

        self.assertIs(resolved, item)
        self.assertIsNone(resolved.game_object)

    def test_returns_item_instance_with_a_physical_object(self) -> None:
        game_object = ObjectDBFactory(db_key="Typed Bridge Item")
        item = ItemInstanceFactory(game_object=game_object)

        self.assertIs(resolve_item_instance(item), item)

    def test_preserves_objectdb_relation_resolution(self) -> None:
        game_object = ObjectDBFactory(db_key="Legacy Bridge Item")
        item = ItemInstanceFactory(game_object=game_object)

        resolved = resolve_item_instance(game_object)

        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.pk, item.pk)
        self.assertEqual(resolved.game_object_id, game_object.pk)

    def test_objectdb_without_an_item_relation_returns_none(self) -> None:
        game_object = ObjectDBFactory(db_key="Not An Item")

        self.assertIsNone(resolve_item_instance(game_object))

    def test_none_returns_none(self) -> None:
        self.assertIsNone(resolve_item_instance(None))

    def test_real_item_primary_key_is_not_implicitly_resolved(self) -> None:
        item = ItemInstanceFactory(game_object=None)

        self.assertIsNone(resolve_item_instance(item.pk))  # type: ignore[arg-type]

    def test_real_object_primary_key_is_not_implicitly_resolved(self) -> None:
        game_object = ObjectDBFactory(db_key="Integer Is Not Authority")
        ItemInstanceFactory(game_object=game_object)

        self.assertIsNone(resolve_item_instance(game_object.pk))  # type: ignore[arg-type]

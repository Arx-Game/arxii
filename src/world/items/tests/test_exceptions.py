"""Tests for inventory exception types."""

from django.test import SimpleTestCase

from world.items.exceptions import (
    ContainerClosed,
    ContainerFull,
    InventoryError,
    ItemError,
    ItemTooLarge,
    NotEquipped,
    NotInPossession,
    PermissionDenied,
    RecipientNotAdjacent,
)

INVENTORY_SUBCLASSES = (
    NotInPossession,
    NotEquipped,
    ContainerFull,
    ContainerClosed,
    ItemTooLarge,
    RecipientNotAdjacent,
    PermissionDenied,
)


class InventoryExceptionTests(SimpleTestCase):
    """Each inventory exception exposes a safe ``user_message``."""

    def test_inventory_error_inherits_from_item_error(self) -> None:
        """InventoryError is rooted at ItemError so a single except catches both families."""
        self.assertTrue(issubclass(InventoryError, ItemError))

    def test_inventory_error_is_base_class(self) -> None:
        """All inventory errors inherit from InventoryError."""
        for cls in INVENTORY_SUBCLASSES:
            with self.subTest(cls=cls.__name__):
                self.assertTrue(issubclass(cls, InventoryError))

    def test_each_subclass_has_user_message(self) -> None:
        """Every subclass exposes a non-empty user_message classvar."""
        for cls in INVENTORY_SUBCLASSES:
            with self.subTest(cls=cls.__name__):
                self.assertTrue(cls.user_message)
                self.assertIsInstance(cls.user_message, str)

    def test_each_subclass_user_message_is_in_safe_messages(self) -> None:
        """Each subclass's user_message is in its SAFE_MESSAGES allowlist."""
        for cls in INVENTORY_SUBCLASSES:
            with self.subTest(cls=cls.__name__):
                self.assertIn(cls.user_message, cls.SAFE_MESSAGES)

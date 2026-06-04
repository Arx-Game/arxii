"""Tests for the body-scoped `has_item` predicate leaf (#684).

`has_item` lives in `world.predicates.predicates` and queries
``ItemInstance.holder_character_sheet`` directly — ownership is
body-keyed, not persona-keyed. These tests sit alongside the consumer
in npc_services.
"""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.predicates.predicates import _resolve_has_item
from world.predicates.types import ResolverContext


class HasItemLeafTests(TestCase):
    """`has_item` — body-scoped; True iff the acting body holds the template."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)

    def test_unknown_template_returns_false(self) -> None:
        ctx = ResolverContext(sheet=self.sheet)
        self.assertFalse(_resolve_has_item(ctx, template_id=999999))

    def test_body_holds_item_returns_true(self) -> None:
        template = ItemTemplateFactory(name="has_item-leaf-template-true")
        ItemInstanceFactory(template=template, holder_character_sheet=self.sheet)
        ctx = ResolverContext(sheet=self.sheet)
        self.assertTrue(_resolve_has_item(ctx, template_id=template.pk))

    def test_other_body_holds_item_returns_false(self) -> None:
        template = ItemTemplateFactory(name="has_item-leaf-template-false")
        other_character = CharacterFactory(db_key="has_item-other-body")
        other_sheet = CharacterSheetFactory(character=other_character)
        ItemInstanceFactory(template=template, holder_character_sheet=other_sheet)
        ctx = ResolverContext(sheet=self.sheet)
        self.assertFalse(_resolve_has_item(ctx, template_id=template.pk))

"""Tests for the persona-scoped `has_item` predicate leaf.

`has_item` lives in `world.missions.predicates` (the shared engine) but
its persona-scoped semantics are owned by the unified NPC service
framework — tests sit alongside the consumer.

The leaf dispatches on template kind → per-kind details model's
`holder_persona` FK. Plan 2 ships the dispatcher with an empty kind
dispatch dict; Plan 3 (#668) wires PERMIT. Until then the leaf isn't
in `LEAF_RESOLVERS` — we test the resolver function directly.
"""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.predicates.predicates import (
    CharacterPredicateContext,
    _resolve_has_item,
)


class HasItemLeafTests(TestCase):
    """has_item — persona-scoped; fail-closed on missing persona / unknown id; raises on unwired kind."""  # noqa: E501

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.pc_persona = cls.sheet.primary_persona

    def test_no_presented_persona_fails_closed(self) -> None:
        ctx = CharacterPredicateContext(self.character)  # no presented_persona
        self.assertFalse(_resolve_has_item(ctx, template_id=1))

    def test_unknown_template_fails_closed(self) -> None:
        ctx = CharacterPredicateContext(self.character, presented_persona=self.pc_persona)
        self.assertFalse(_resolve_has_item(ctx, template_id=999999))

    def test_unwired_template_kind_raises(self) -> None:
        # Plan 2's dispatch dict is empty. Any real ItemTemplate has an
        # unwired kind — fail loud rather than silently falling back to
        # account-scoped owner lookup.
        from world.items.factories import ItemTemplateFactory

        template = ItemTemplateFactory()
        ctx = CharacterPredicateContext(self.character, presented_persona=self.pc_persona)
        with self.assertRaises(NotImplementedError):
            _resolve_has_item(ctx, template_id=template.pk)

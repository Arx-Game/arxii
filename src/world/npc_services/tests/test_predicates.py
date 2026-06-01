"""Tests for the persona-scoped `has_item` predicate leaf.

`has_item` lives in `world.missions.predicates` (the shared engine), but
its persona-scoped semantics are owned by the unified NPC service
framework — kept here so the tests sit alongside the framework that
consumes them.

The leaf dispatches on template kind → per-kind details model's
`holder_persona` FK. Plan 2 ships the dispatcher with an empty kind→
relation dict (Plan 3 wires the PERMIT entry). This file verifies the
fail-closed behavior; the populated-dispatch test lands in Plan 3.
"""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.missions.predicates import CharacterPredicateContext


class HasItemLeafTests(TestCase):
    """has_item — persona-scoped, fail-closed for unwired kinds + no persona."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.pc_persona = cls.sheet.primary_persona

    def test_no_presented_persona_fails_closed(self) -> None:
        ctx = CharacterPredicateContext(self.character)  # no presented_persona
        self.assertFalse(ctx.has_leaf("has_item", template_id=1))

    def test_unknown_template_fails_closed(self) -> None:
        ctx = CharacterPredicateContext(self.character, presented_persona=self.pc_persona)
        self.assertFalse(ctx.has_leaf("has_item", template_id=999999))

    def test_unwired_template_kind_fails_closed(self) -> None:
        # Plan 2's dispatch dict is empty (Plan 3 adds PERMIT). Any real
        # ItemTemplate today has an unwired kind — fail closed rather than
        # silently falling back to account-scoped owner lookup.
        from world.items.factories import ItemTemplateFactory

        template = ItemTemplateFactory()
        ctx = CharacterPredicateContext(self.character, presented_persona=self.pc_persona)
        self.assertFalse(ctx.has_leaf("has_item", template_id=template.pk))

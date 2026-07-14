"""puppeted_sheet_for — the canonical user→puppet→sheet resolver (silent-fail audit).

Seven view sites did this dance inline as ``puppet.character_sheet if puppet is not
None else None`` — but ``Account.puppet`` can be a truthy non-character object for
sessionless accounts (and AnonymousUser has no puppet at all), which 500'd the summons
list and silently degraded drf-spectacular's schema inference. One guarded accessor.
"""

from types import SimpleNamespace

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.roster.selectors import puppeted_sheet_for


class PuppetedSheetForTests(TestCase):
    def test_character_puppet_resolves_its_sheet(self):
        sheet = CharacterSheetFactory()
        user = SimpleNamespace(puppet=sheet.character)
        assert puppeted_sheet_for(user) == sheet

    def test_no_puppet_attribute_returns_none(self):
        assert puppeted_sheet_for(SimpleNamespace()) is None

    def test_none_puppet_returns_none(self):
        assert puppeted_sheet_for(SimpleNamespace(puppet=None)) is None

    def test_non_character_puppet_returns_none(self):
        assert puppeted_sheet_for(SimpleNamespace(puppet=object())) is None

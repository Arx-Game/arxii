"""puppeted_sheet_for — the canonical user→puppet→sheet resolver (silent-fail audit).

Seven view sites did this dance inline as ``puppet.character_sheet if puppet is not
None else None`` — but ``Account.puppet`` can be a truthy non-character object for
sessionless accounts (and AnonymousUser has no puppet at all), which 500'd the summons
list and silently degraded drf-spectacular's schema inference. One guarded accessor.

Contract (tranche 2): the resolver gates on ``is_authenticated`` — AnonymousUser
resolves to None without touching ``.puppet``; an authenticated user-like (real
Account or duck-typed test fake) reads ``.puppet`` directly; an object that isn't
user-like at all (no ``is_authenticated``) fails loudly rather than silently
resolving to None.
"""

from types import SimpleNamespace

from django.contrib.auth.models import AnonymousUser
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.roster.selectors import puppeted_sheet_for


def _authed(**kwargs) -> SimpleNamespace:
    return SimpleNamespace(is_authenticated=True, **kwargs)


class PuppetedSheetForTests(TestCase):
    def test_character_puppet_resolves_its_sheet(self):
        sheet = CharacterSheetFactory()
        user = _authed(puppet=sheet.character)
        assert puppeted_sheet_for(user) == sheet

    def test_anonymous_user_returns_none_without_touching_puppet(self):
        assert puppeted_sheet_for(AnonymousUser()) is None

    def test_none_user_returns_none(self):
        assert puppeted_sheet_for(None) is None

    def test_none_puppet_returns_none(self):
        assert puppeted_sheet_for(_authed(puppet=None)) is None

    def test_non_character_puppet_returns_none(self):
        assert puppeted_sheet_for(_authed(puppet=object())) is None

    def test_non_user_object_fails_loudly(self):
        with self.assertRaises(AttributeError):
            puppeted_sheet_for(object())

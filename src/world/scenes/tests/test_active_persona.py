"""Tests for #981 — active-persona resolution.

Covers the core service (durable face, default-primary, foreign rejection,
SET_NULL revert, restore-through-nesting), the player switch endpoint, and that
a converted call site (`currency.views._viewer_persona`) now resolves the
ACTIVE persona rather than always-primary (the leak fix).
"""

from __future__ import annotations

from types import SimpleNamespace

from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.constants import PersonaType
from world.scenes.factories import PersonaFactory
from world.scenes.services import (
    ActivePersonaError,
    active_persona_for_sheet,
    set_active_persona,
)
from world.scenes.views import PersonaViewSet


def _sheet():
    character = CharacterFactory()
    sheet = CharacterSheetFactory(character=character)
    return character, sheet


class ActivePersonaServiceTests(TestCase):
    def setUp(self):
        self.character, self.sheet = _sheet()
        self.primary = self.sheet.primary_persona
        self.alt = PersonaFactory(character_sheet=self.sheet, persona_type=PersonaType.ESTABLISHED)
        self.mask = PersonaFactory(character_sheet=self.sheet, persona_type=PersonaType.TEMPORARY)

    def test_unset_resolves_to_primary(self):
        self.assertEqual(active_persona_for_sheet(self.sheet), self.primary)

    def test_set_established_face(self):
        set_active_persona(self.sheet, self.alt)
        self.assertEqual(active_persona_for_sheet(self.sheet), self.alt)

    def test_set_temporary_mask(self):
        set_active_persona(self.sheet, self.mask)
        self.assertEqual(active_persona_for_sheet(self.sheet), self.mask)

    def test_foreign_persona_rejected_and_unchanged(self):
        _, other_sheet = _sheet()
        foreign = other_sheet.primary_persona
        with self.assertRaises(ActivePersonaError):
            set_active_persona(self.sheet, foreign)
        self.assertEqual(active_persona_for_sheet(self.sheet), self.primary)

    def test_deleted_active_nulls_the_fk_so_resolution_reverts_to_primary(self):
        # SET_NULL: a deleted persona leaves no dangling/foreign identity — the
        # column nulls, and an unset column resolves to primary (see
        # ``test_unset_resolves_to_primary``).
        from world.character_sheets.models import CharacterSheet

        set_active_persona(self.sheet, self.alt)
        self.alt.delete()
        fresh_id = (
            CharacterSheet.objects.filter(pk=self.sheet.pk)
            .values_list("active_persona_id", flat=True)
            .first()
        )
        self.assertIsNone(fresh_id)

    def test_mask_removal_restores_pre_mask_face_not_primary(self):
        # base = ESTABLISHED alt; don a temp mask; on removal the mask restores
        # the face it covered (the alt) — never all the way to primary.
        set_active_persona(self.sheet, self.alt)
        covered = active_persona_for_sheet(self.sheet)  # what a mask captures at don-time
        set_active_persona(self.sheet, self.mask)
        self.assertEqual(active_persona_for_sheet(self.sheet), self.mask)
        set_active_persona(self.sheet, covered)  # mask removal
        self.assertEqual(active_persona_for_sheet(self.sheet), self.alt)


class SetActivePersonaEndpointTests(TestCase):
    def setUp(self):
        self.character, self.sheet = _sheet()
        self.alt = PersonaFactory(character_sheet=self.sheet, persona_type=PersonaType.ESTABLISHED)
        self.factory = APIRequestFactory()
        self.view = PersonaViewSet.as_view({"post": "set_active"})

    def _post(self, *, puppet, persona_id):
        request = self.factory.post(
            "/api/scenes/personas/set-active/", {"persona_id": persona_id}, format="json"
        )
        user = SimpleNamespace(is_authenticated=True, is_staff=False, puppet=puppet)
        force_authenticate(request, user=user)
        return self.view(request)

    def test_sets_active_for_played_character(self):
        resp = self._post(puppet=self.character, persona_id=self.alt.pk)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["active_persona_id"], self.alt.pk)
        self.sheet.refresh_from_db()
        self.assertEqual(active_persona_for_sheet(self.sheet), self.alt)

    def test_foreign_persona_rejected_400(self):
        _, other_sheet = _sheet()
        resp = self._post(puppet=self.character, persona_id=other_sheet.primary_persona.pk)
        self.assertEqual(resp.status_code, 400)

    def test_no_played_character_400(self):
        resp = self._post(puppet=None, persona_id=self.alt.pk)
        self.assertEqual(resp.status_code, 400)


class ConvertedResolverTests(TestCase):
    """A converted call site resolves the ACTIVE persona, not always-primary."""

    def test_books_viewer_persona_follows_active_face(self):
        from world.currency.views import _viewer_persona

        character, sheet = _sheet()
        alt = PersonaFactory(character_sheet=sheet, persona_type=PersonaType.ESTABLISHED)
        request = SimpleNamespace(user=SimpleNamespace(puppet=character))

        # Default: on primary.
        self.assertEqual(_viewer_persona(request), sheet.primary_persona)
        # Switch to the alt → the resolver follows it (so the alt's org books
        # become reachable and the primary's stay hidden).
        set_active_persona(sheet, alt)
        self.assertEqual(_viewer_persona(request), alt)

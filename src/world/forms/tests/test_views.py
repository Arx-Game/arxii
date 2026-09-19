"""Tests for the alternate-self web surface (#1111 slice 4).

Mirrors the active-persona view tests (``world.scenes.tests.test_active_persona``).
All mutators dispatch through ``dispatch_player_action`` to the shared REGISTRY
actions, so these tests prove the HTTP thin layer is wired correctly.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.capability_content import AT_WILL_SHIFTING
from world.conditions.factories import CapabilityTypeFactory
from world.forms.factories import (
    ActiveAlternateSelfFactory,
    AlternateSelfFactory,
    CharacterFormFactory,
    CharacterFormStateFactory,
)
from world.forms.models import ActiveAlternateSelf, FormType
from world.forms.views import AlternateSelfViewSet
from world.mechanics.factories import ModifierCategoryFactory, ModifierSourceFactory
from world.mechanics.models import CharacterModifier, ModifierTarget
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.roster.services.selection import set_selected_entry


def _sheet():
    character = CharacterFactory()
    sheet = CharacterSheetFactory(character=character)
    return character, sheet


def _selected_account(sheet):
    """Return an account with ``sheet`` as its durable selected character."""
    account = AccountFactory()
    entry = RosterEntryFactory(character_sheet=sheet)
    tenure = RosterTenureFactory(player_data__account=account, roster_entry=entry)
    set_selected_entry(tenure.player_data, entry)
    return account, tenure


def _grant_at_will_shifting(sheet):
    capability = CapabilityTypeFactory(name=AT_WILL_SHIFTING, innate_baseline=0)
    category = ModifierCategoryFactory(name="capability")
    target = ModifierTarget.objects.create(
        name=f"capability_{capability.pk}",
        category=category,
        target_capability=capability,
    )
    source = ModifierSourceFactory()
    CharacterModifier.objects.create(
        character=sheet,
        target=target,
        source=source,
        value=1,
    )


class AlternateSelfListEndpointTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.character, cls.sheet = _sheet()
        cls.account, cls.tenure = _selected_account(cls.sheet)
        cls.true_form = CharacterFormFactory(
            character=cls.sheet, name="True", form_type=FormType.TRUE
        )
        CharacterFormStateFactory(character=cls.character.sheet_data, active_form=cls.true_form)
        cls.alt = AlternateSelfFactory(character=cls.sheet, display_name="the Beast")
        ActiveAlternateSelfFactory(character=cls.sheet, alternate_self=cls.alt)

    def setUp(self):
        set_selected_entry(self.tenure.player_data, self.tenure.roster_entry)
        self.factory = APIRequestFactory()
        self.view = AlternateSelfViewSet.as_view({"get": "list"})

    def _get(self, *, puppet, character_sheet_id):
        request = self.factory.get(
            "/api/forms/alternate-selves/",
            {"character_sheet": character_sheet_id},
        )
        set_selected_entry(
            self.tenure.player_data, self.tenure.roster_entry if puppet is not None else None
        )
        force_authenticate(request, user=self.account)
        return self.view(request)

    def test_list_includes_owned_alternate_self_marked_active(self):
        resp = self._get(puppet=self.character, character_sheet_id=self.sheet.pk)
        self.assertEqual(resp.status_code, 200)
        results = resp.data["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], self.alt.pk)
        self.assertEqual(results[0]["display_name"], self.alt.display_name)
        self.assertIs(results[0]["is_active"], True)


class ShiftFormEndpointTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.character, cls.sheet = _sheet()
        cls.account, cls.tenure = _selected_account(cls.sheet)
        cls.true_form = CharacterFormFactory(
            character=cls.sheet, name="True", form_type=FormType.TRUE
        )
        CharacterFormStateFactory(character=cls.character.sheet_data, active_form=cls.true_form)
        cls.alt = AlternateSelfFactory(character=cls.sheet, display_name="the Beast")
        _grant_at_will_shifting(cls.sheet)

    def setUp(self):
        set_selected_entry(self.tenure.player_data, self.tenure.roster_entry)
        self.factory = APIRequestFactory()
        self.view = AlternateSelfViewSet.as_view({"post": "shift"})

    def _post(self, *, puppet, alternate_self_id):
        request = self.factory.post(
            "/api/forms/alternate-selves/shift/",
            {"alternate_self_id": alternate_self_id},
            format="json",
        )
        set_selected_entry(
            self.tenure.player_data, self.tenure.roster_entry if puppet is not None else None
        )
        force_authenticate(request, user=self.account)
        return self.view(request)

    def test_shift_dispatches_and_sets_active(self):
        resp = self._post(puppet=self.character, alternate_self_id=self.alt.pk)
        self.assertEqual(resp.status_code, 200)
        self.sheet.refresh_from_db()
        self.assertEqual(
            resp.data["active_alternate_self_id"],
            self.sheet.active_alternate_self.pk,
        )
        self.sheet.active_alternate_self.refresh_from_db()
        self.assertEqual(self.sheet.active_alternate_self.alternate_self, self.alt)

    def test_foreign_alternate_self_rejected_400(self):
        _, other_sheet = _sheet()
        foreign = AlternateSelfFactory(character=other_sheet)
        resp = self._post(puppet=self.character, alternate_self_id=foreign.pk)
        self.assertEqual(resp.status_code, 400)
        active, _ = ActiveAlternateSelf.objects.get_or_create(character=self.sheet)
        self.assertIsNone(active.alternate_self)

    def test_no_played_character_400(self):
        resp = self._post(puppet=None, alternate_self_id=self.alt.pk)
        self.assertEqual(resp.status_code, 400)


class RevertFormEndpointTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.character, cls.sheet = _sheet()
        cls.account, cls.tenure = _selected_account(cls.sheet)
        cls.true_form = CharacterFormFactory(
            character=cls.sheet, name="True", form_type=FormType.TRUE
        )
        CharacterFormStateFactory(character=cls.character.sheet_data, active_form=cls.true_form)
        cls.alt_form = CharacterFormFactory(character=cls.sheet)
        cls.alt = AlternateSelfFactory(
            character=cls.sheet,
            form=cls.alt_form,
            display_name="the Beast",
        )
        _grant_at_will_shifting(cls.sheet)

    def setUp(self):
        set_selected_entry(self.tenure.player_data, self.tenure.roster_entry)
        self.factory = APIRequestFactory()
        self.view = AlternateSelfViewSet.as_view({"post": "revert"})

    def _post(self, *, puppet):
        request = self.factory.post("/api/forms/alternate-selves/revert/", format="json")
        set_selected_entry(
            self.tenure.player_data, self.tenure.roster_entry if puppet is not None else None
        )
        force_authenticate(request, user=self.account)
        return self.view(request)

    def _assume(self):
        from actions.definitions.forms import ShiftFormAction

        ShiftFormAction().run(self.character, alternate_self_id=self.alt.pk)

    def test_revert_dispatches_and_clears_active(self):
        self._assume()
        resp = self._post(puppet=self.character)
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.data["active_alternate_self_id"])
        active = ActiveAlternateSelf.objects.get(character=self.sheet)
        self.assertIsNone(active.alternate_self)

    def test_revert_blocked_when_not_in_control(self):
        self._assume()
        from world.forms.services import RevertBlockedError

        with patch(
            "world.forms.services.revert_alternate_self",
            side_effect=RevertBlockedError,
        ):
            resp = self._post(puppet=self.character)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("not in control", str(resp.data))
        active = ActiveAlternateSelf.objects.get(character=self.sheet)
        self.assertEqual(active.alternate_self, self.alt)

    def test_no_played_character_400(self):
        resp = self._post(puppet=None)
        self.assertEqual(resp.status_code, 400)

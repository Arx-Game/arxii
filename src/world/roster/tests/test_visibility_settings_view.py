"""API tests for GET/PATCH /api/roster/visibility-settings/ (#1484, #1463 follow-up).

The web control for quiet/hidden mode (``appear_offline``). Scoped to the requesting player's
active character; the write reuses ``set_appear_offline``.
"""

from types import SimpleNamespace

from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import (
    PlayerDataFactory,
    RosterEntryFactory,
    RosterTenureFactory,
    TenureDisplaySettingsFactory,
)
from world.roster.models import TenureDisplaySettings
from world.roster.views.settings_views import VisibilitySettingsView

URL = "/api/roster/visibility-settings/"


class VisibilitySettingsViewTests(TestCase):
    def setUp(self):
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.entry = RosterEntryFactory(character_sheet=self.sheet)
        self.tenure = RosterTenureFactory(roster_entry=self.entry, player_data=PlayerDataFactory())
        self.factory = APIRequestFactory()

    def _request(self, method, *, puppet, data=None):
        request = getattr(self.factory, method)(URL, data or {}, format="json")
        user = SimpleNamespace(is_authenticated=True, is_staff=False, puppet=puppet)
        force_authenticate(request, user=user)
        return VisibilitySettingsView.as_view()(request)

    def test_get_defaults_to_visible_when_no_settings_row(self):
        resp = self._request("get", puppet=self.character)
        assert resp.status_code == 200
        assert resp.data["appear_offline"] is False

    def test_get_reflects_stored_value(self):
        TenureDisplaySettingsFactory(tenure=self.tenure, appear_offline=True)
        resp = self._request("get", puppet=self.character)
        assert resp.status_code == 200
        assert resp.data["appear_offline"] is True

    def test_patch_enables_hidden_mode(self):
        resp = self._request("patch", puppet=self.character, data={"appear_offline": True})
        assert resp.status_code == 200
        assert resp.data["appear_offline"] is True
        assert TenureDisplaySettings.objects.get(tenure=self.tenure).appear_offline is True

    def test_patch_disables_hidden_mode(self):
        TenureDisplaySettingsFactory(tenure=self.tenure, appear_offline=True)
        resp = self._request("patch", puppet=self.character, data={"appear_offline": False})
        assert resp.status_code == 200
        assert resp.data["appear_offline"] is False
        assert TenureDisplaySettings.objects.get(tenure=self.tenure).appear_offline is False

    def test_patch_requires_the_field(self):
        resp = self._request("patch", puppet=self.character, data={})
        assert resp.status_code == 400

    def test_no_played_character_is_400(self):
        resp = self._request("get", puppet=None)
        assert resp.status_code == 400

"""API tests for GET /api/weather/conditions/ (#1522)."""

from datetime import UTC, datetime

from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.game_clock.factories import GameClockFactory
from world.weather.factories import (
    RegionWeatherStateFactory,
    WeatherEmitFactory,
    WeatherTypeFactory,
)

CONDITIONS_URL = "/api/weather/conditions/"


class WeatherConditionsApiTest(APITestCase):
    def setUp(self) -> None:
        self.user = AccountFactory()
        self.region = AreaFactory(level=AreaLevel.CITY)
        self.ward = AreaFactory(level=AreaLevel.WARD, parent=self.region)
        self.room = RoomProfileFactory(area=self.ward).objectdb

    def test_requires_authentication(self) -> None:
        response = self.client.get(CONDITIONS_URL, {"room_id": self.room.pk})
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

    def test_missing_room_id_without_selection_is_404(self) -> None:
        """Omitted room_id falls back to the caller's selected character (#3539) —
        no selection means there is nowhere to read conditions for."""
        self.client.force_authenticate(user=self.user)
        assert self.client.get(CONDITIONS_URL).status_code == status.HTTP_404_NOT_FOUND

    def test_missing_room_id_resolves_the_selected_characters_room(self) -> None:
        """The Hall's Time plate has no live session room; the durable selection
        (PlayerData.selected_entry, #3412) names whose room to read."""
        from evennia_extensions.factories import CharacterFactory
        from evennia_extensions.models import PlayerData
        from world.character_sheets.factories import CharacterSheetFactory
        from world.roster.factories import RosterEntryFactory

        GameClockFactory(anchor_ic_time=datetime(1010, 7, 15, 12, 0, tzinfo=UTC), paused=True)
        storm = WeatherTypeFactory(name="Storm")
        RegionWeatherStateFactory(area=self.region, weather_type=storm)

        char = CharacterFactory(db_key="HallDocked", location=self.room)
        CharacterSheetFactory(character=char)
        entry = RosterEntryFactory(character_sheet__character=char)
        player_data, _ = PlayerData.objects.get_or_create(account=self.user)
        player_data.selected_entry = entry
        player_data.save()

        self.client.force_authenticate(user=self.user)
        response = self.client.get(CONDITIONS_URL)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["weather_type"] == "Storm"
        assert response.data["season"] == "summer"

    def test_missing_room_id_with_locationless_selection_is_404(self) -> None:
        """Selection is not presence — a selected character standing nowhere
        yields no conditions rather than an error."""
        from evennia_extensions.factories import CharacterFactory
        from evennia_extensions.models import PlayerData
        from world.character_sheets.factories import CharacterSheetFactory
        from world.roster.factories import RosterEntryFactory

        char = CharacterFactory(db_key="HallNowhere")
        CharacterSheetFactory(character=char)
        entry = RosterEntryFactory(character_sheet__character=char)
        player_data, _ = PlayerData.objects.get_or_create(account=self.user)
        player_data.selected_entry = entry
        player_data.save()

        self.client.force_authenticate(user=self.user)
        assert self.client.get(CONDITIONS_URL).status_code == status.HTTP_404_NOT_FOUND

    def test_unknown_room_is_404(self) -> None:
        self.client.force_authenticate(user=self.user)
        response = self.client.get(CONDITIONS_URL, {"room_id": 9999999})
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_reports_time_and_weather(self) -> None:
        GameClockFactory(anchor_ic_time=datetime(1010, 7, 15, 12, 0, tzinfo=UTC), paused=True)
        storm = WeatherTypeFactory(name="Storm")
        WeatherEmitFactory(weather_type=storm, text="rain lashes down", in_summer=True, at_day=True)
        RegionWeatherStateFactory(area=self.region, weather_type=storm)

        self.client.force_authenticate(user=self.user)
        response = self.client.get(CONDITIONS_URL, {"room_id": self.room.pk})
        assert response.status_code == status.HTTP_200_OK
        assert response.data["season"] == "summer"
        assert response.data["phase"] == "day"
        assert response.data["weather_type"] == "Storm"
        assert response.data["emit_text"] == "rain lashes down"

    def test_no_weather_returns_nulls(self) -> None:
        self.client.force_authenticate(user=self.user)
        response = self.client.get(CONDITIONS_URL, {"room_id": self.room.pk})
        assert response.status_code == status.HTTP_200_OK
        assert response.data["weather_type"] is None
        assert response.data["emit_text"] is None


class TimeCommandHelperTests(APITestCase):
    """CmdTime's celestial additions (#2845): server-clock line + night-only moon."""

    def test_server_time_line_renders_eastern(self):
        from commands.weather import CmdTime

        line = CmdTime._server_time_line()
        self.assertIn("Server time:", line)
        self.assertTrue("EST" in line or "EDT" in line)

    def test_moon_line_shown_at_night_only(self):
        from types import SimpleNamespace

        from commands.weather import CmdTime
        from world.game_clock.constants import MoonPhase, TimePhase

        night = SimpleNamespace(phase=TimePhase.NIGHT, moon_phase=MoonPhase.FULL)
        self.assertEqual(CmdTime._moon_lines(night), ["|wThe moon:|n Full Moon"])
        day = SimpleNamespace(phase=TimePhase.DAY, moon_phase=MoonPhase.FULL)
        self.assertEqual(CmdTime._moon_lines(day), [])
        no_clock = SimpleNamespace(phase=None, moon_phase=None)
        self.assertEqual(CmdTime._moon_lines(no_clock), [])

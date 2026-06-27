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

    def test_missing_room_id_is_400(self) -> None:
        self.client.force_authenticate(user=self.user)
        assert self.client.get(CONDITIONS_URL).status_code == status.HTTP_400_BAD_REQUEST

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

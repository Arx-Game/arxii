"""Idempotent weather re-seed (#1522).

Pins the upsert contract: loading the corpus twice updates in place rather than duplicating
(the bug ``loaddata`` has with the keyless ``WeatherEmit`` rows), and editing a field then
re-loading mutates the existing row.
"""

import json

from django.test import TestCase

from world.locations.constants import StatKey
from world.weather.models import FeastDay, WeatherEmit, WeatherType, WeatherTypeExposure
from world.weather.seed import (
    load_weather_seed,
    upsert_weather_emits,
    upsert_weather_type_exposures,
    upsert_weather_types,
)

TYPES = [
    {
        "model": "weather.weathertype",
        "fields": {"name": "Storm", "is_automated": True, "selection_weight": 3},
    },
    {
        "model": "weather.weathertype",
        "fields": {"name": "Clear", "is_automated": True, "selection_weight": 5},
    },
]

EXPOSURES = [
    {
        "model": "weather.weathertypeexposure",
        "fields": {"weather_type": ["Storm"], "stat_key": StatKey.WET, "value": 40},
    },
    {
        "model": "weather.weathertypeexposure",
        "fields": {"weather_type": ["Storm"], "stat_key": StatKey.WIND, "value": 30},
    },
]

EMITS = [
    {
        "model": "weather.weatheremit",
        "fields": {
            "weather_type": ["Storm"],
            "text": "Rain lashes down in sheets.",
            "weight": 2,
            "in_summer": True,
            "at_day": True,
        },
    },
    {
        "model": "weather.weatheremit",
        "fields": {
            "weather_type": ["Clear"],
            "text": "The sky is a flawless blue.",
            "at_day": True,
        },
    },
]


class UpsertWeatherTypesTests(TestCase):
    def test_creates_then_updates(self) -> None:
        created, updated = upsert_weather_types(TYPES)
        assert (created, updated) == (2, 0)
        assert WeatherType.objects.count() == 2

        # Re-load identical data → all updates, no new rows.
        created, updated = upsert_weather_types(TYPES)
        assert (created, updated) == (0, 2)
        assert WeatherType.objects.count() == 2

    def test_edited_field_is_applied_on_reload(self) -> None:
        upsert_weather_types(TYPES)
        edited = [
            {"model": "weather.weathertype", "fields": {"name": "Storm", "selection_weight": 99}},
        ]
        created, updated = upsert_weather_types(edited)
        assert (created, updated) == (0, 1)
        assert WeatherType.objects.get(name="Storm").selection_weight == 99


class UpsertWeatherExposuresTests(TestCase):
    def setUp(self) -> None:
        upsert_weather_types(TYPES)

    def test_creates_then_updates_keyed_on_axis(self) -> None:
        created, updated = upsert_weather_type_exposures(EXPOSURES)
        assert (created, updated) == (2, 0)
        assert WeatherTypeExposure.objects.count() == 2

        created, updated = upsert_weather_type_exposures(EXPOSURES)
        assert (created, updated) == (0, 2)
        assert WeatherTypeExposure.objects.count() == 2

    def test_edited_magnitude_updates_in_place(self) -> None:
        upsert_weather_type_exposures(EXPOSURES)
        edited = [
            {
                "model": "weather.weathertypeexposure",
                "fields": {"weather_type": ["Storm"], "stat_key": StatKey.WET, "value": 10},
            },
        ]
        upsert_weather_type_exposures(edited)
        row = WeatherTypeExposure.objects.get(weather_type__name="Storm", stat_key=StatKey.WET)
        assert row.value == 10
        assert WeatherTypeExposure.objects.count() == 2  # no duplicate


class UpsertWeatherEmitsTests(TestCase):
    """The crux: the keyless emit rows loaddata duplicates must upsert by (weather_type, text)."""

    def setUp(self) -> None:
        upsert_weather_types(TYPES)

    def test_reload_does_not_duplicate_keyless_emits(self) -> None:
        created, updated = upsert_weather_emits(EMITS)
        assert (created, updated) == (2, 0)
        assert WeatherEmit.objects.count() == 2

        # The bug under test: a second load must NOT create 2 more rows.
        created, updated = upsert_weather_emits(EMITS)
        assert (created, updated) == (0, 2)
        assert WeatherEmit.objects.count() == 2

    def test_edited_emit_weight_and_flags_update_in_place(self) -> None:
        upsert_weather_emits(EMITS)
        edited = [
            {
                "model": "weather.weatheremit",
                "fields": {
                    "weather_type": ["Storm"],
                    "text": "Rain lashes down in sheets.",
                    "weight": 7,
                    "in_winter": True,
                    "at_night": True,
                },
            },
        ]
        upsert_weather_emits(edited)
        row = WeatherEmit.objects.get(text="Rain lashes down in sheets.")
        assert row.weight == 7
        assert row.in_winter is True
        assert row.at_night is True
        assert WeatherEmit.objects.count() == 2  # no duplicate

    def test_new_text_creates_a_new_row(self) -> None:
        upsert_weather_emits(EMITS)
        new_line = [
            {
                "model": "weather.weatheremit",
                "fields": {
                    "weather_type": ["Storm"],
                    "text": "Thunder rolls overhead.",
                    "at_dusk": True,
                },
            },
        ]
        created, updated = upsert_weather_emits(new_line)
        assert (created, updated) == (1, 0)
        assert WeatherEmit.objects.count() == 3


class LoadWeatherSeedFromDirTests(TestCase):
    """The orchestrator reads the fixture files in dependency order and upserts idempotently."""

    def _write_corpus(self, tmp_path) -> None:
        (tmp_path / "weather_types.json").write_text(json.dumps(TYPES), encoding="utf-8")
        (tmp_path / "weather_type_exposures.json").write_text(
            json.dumps(EXPOSURES), encoding="utf-8"
        )
        (tmp_path / "weather_emits.json").write_text(json.dumps(EMITS), encoding="utf-8")
        (tmp_path / "feast_days.json").write_text(
            json.dumps(
                [
                    {
                        "model": "weather.feastday",
                        "fields": {
                            "name": "Eclipse",
                            "ic_month": 10,
                            "ic_day": 31,
                            "weather_type": ["Clear"],
                        },
                    }
                ]
            ),
            encoding="utf-8",
        )

    def test_loads_then_reloads_idempotently(self) -> None:
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._write_corpus(tmp_path)

            counts = load_weather_seed(tmp_path)
            assert counts["weather_types"] == (2, 0)
            assert counts["weather_type_exposures"] == (2, 0)
            assert counts["weather_emits"] == (2, 0)
            assert counts["feast_days"] == (1, 0)
            assert WeatherType.objects.count() == 2
            assert WeatherEmit.objects.count() == 2
            assert FeastDay.objects.count() == 1

            # Re-seed: everything updates, nothing duplicates.
            counts = load_weather_seed(tmp_path)
            assert counts["weather_emits"] == (0, 2)
            assert counts["feast_days"] == (0, 1)
            assert WeatherEmit.objects.count() == 2
            assert FeastDay.objects.count() == 1

    def test_missing_feast_days_file_is_ok(self) -> None:
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "weather_types.json").write_text(json.dumps(TYPES), encoding="utf-8")
            counts = load_weather_seed(tmp_path)
            assert counts["weather_types"] == (2, 0)
            assert counts["feast_days"] == (0, 0)
            assert FeastDay.objects.count() == 0

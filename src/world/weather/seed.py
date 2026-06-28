"""Idempotent upsert loader for the weather seed corpus (#1522).

``loaddata`` can seed a *fresh* database but cannot **re-seed** an edited corpus here, for two
reasons: (1) SharedMemoryModel's identity map intercepts construction-by-pk and returns the
cached instance, silently discarding a fixture's new field values, so natural-key ``loaddata``
INSERTs but never UPDATEs idmapper rows (#944/#946); and (2) ``WeatherEmit`` has no natural key,
so a second ``loaddata`` DUPLICATES every emit row rather than updating it.

This module re-seeds with ``update_or_create`` instead — the same fix
``core_management.content_fixtures.load_entries`` uses — keyed on each model's natural identity,
so editing a magnitude / flag / weight and re-running mutates the existing row in place. The
generated Django-fixture JSON (``{"model", "fields"}`` objects, ``weather_type`` carried as a
natural-key list) stays valid for fresh-DB ``loaddata``; this loader consumes the very same files.

Identity keys (what "the same row" means on re-seed):
- ``WeatherType``          → ``name``
- ``WeatherTypeExposure``  → ``(weather_type, stat_key)`` (its unique constraint)
- ``WeatherEmit``          → ``(weather_type, text)`` (the line's content identity)
- ``FeastDay``             → ``(ic_month, ic_day)`` (its unique constraint)

Editing an emit's *text* is therefore a new line (it can't match an old one); editing its weight,
season/phase gates, or gm_notes updates in place. Import-safe without Django configured — only the
upsert functions touch the ORM, via deferred imports.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from world.weather.models import WeatherType

# Seed files, in dependency order (types before the rows that reference them).
WEATHER_TYPES_FILE = "weather_types.json"
WEATHER_TYPE_EXPOSURES_FILE = "weather_type_exposures.json"
WEATHER_EMITS_FILE = "weather_emits.json"
FEAST_DAYS_FILE = "feast_days.json"

# Structural key of a Django-fixture object: ``{"model": ..., "fields": {...}}``.
_FIELDS_KEY = "fields"


def _fields(obj: dict) -> dict:
    """Return a fixture object's ``fields`` dict, accepting a bare field dict too."""
    return dict(obj[_FIELDS_KEY]) if _FIELDS_KEY in obj else dict(obj)


def _resolve_weather_type(ref: object) -> WeatherType:
    """Resolve a ``weather_type`` fixture ref (a natural-key list ``["Storm"]`` or a name)."""
    from world.weather.models import WeatherType  # noqa: PLC0415

    if isinstance(ref, (list, tuple)):
        return WeatherType.objects.get_by_natural_key(*ref)
    return WeatherType.objects.get_by_natural_key(ref)


def upsert_weather_types(objects: list[dict]) -> tuple[int, int]:
    """Upsert ``WeatherType`` rows keyed on ``name``. Returns ``(created, updated)``."""
    from world.weather.models import WeatherType  # noqa: PLC0415

    created = updated = 0
    for obj in objects:
        fields = _fields(obj)
        name = fields.pop("name")
        _, was_created = WeatherType.objects.update_or_create(name=name, defaults=fields)
        created, updated = (created + 1, updated) if was_created else (created, updated + 1)
    return created, updated


def upsert_weather_type_exposures(objects: list[dict]) -> tuple[int, int]:
    """Upsert ``WeatherTypeExposure`` rows keyed on ``(weather_type, stat_key)``."""
    from world.weather.models import WeatherTypeExposure  # noqa: PLC0415

    created = updated = 0
    for obj in objects:
        fields = _fields(obj)
        weather_type = _resolve_weather_type(fields.pop("weather_type"))
        stat_key = fields.pop("stat_key")
        _, was_created = WeatherTypeExposure.objects.update_or_create(
            weather_type=weather_type, stat_key=stat_key, defaults=fields
        )
        created, updated = (created + 1, updated) if was_created else (created, updated + 1)
    return created, updated


def upsert_weather_emits(objects: list[dict]) -> tuple[int, int]:
    """Upsert ``WeatherEmit`` rows keyed on ``(weather_type, text)`` — the line's content identity.

    This is the row type ``loaddata`` duplicates on re-seed (no natural key); keying on the text
    makes re-running idempotent for edited weight / season / phase / gm_notes.
    """
    from world.weather.models import WeatherEmit  # noqa: PLC0415

    created = updated = 0
    for obj in objects:
        fields = _fields(obj)
        weather_type = _resolve_weather_type(fields.pop("weather_type"))
        text = fields.pop("text")
        _, was_created = WeatherEmit.objects.update_or_create(
            weather_type=weather_type, text=text, defaults=fields
        )
        created, updated = (created + 1, updated) if was_created else (created, updated + 1)
    return created, updated


def upsert_feast_days(objects: list[dict]) -> tuple[int, int]:
    """Upsert ``FeastDay`` rows keyed on ``(ic_month, ic_day)`` (its unique date)."""
    from world.weather.models import FeastDay  # noqa: PLC0415

    created = updated = 0
    for obj in objects:
        fields = _fields(obj)
        weather_type = _resolve_weather_type(fields.pop("weather_type"))
        ic_month = fields.pop("ic_month")
        ic_day = fields.pop("ic_day")
        _, was_created = FeastDay.objects.update_or_create(
            ic_month=ic_month,
            ic_day=ic_day,
            defaults={"weather_type": weather_type, **fields},
        )
        created, updated = (created + 1, updated) if was_created else (created, updated + 1)
    return created, updated


def _read(fixtures_dir: Path, filename: str) -> list[dict]:
    """Read a fixture file if present; return [] when it's absent (feast days are optional)."""
    path = fixtures_dir / filename
    if not path.is_file():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def load_weather_seed(fixtures_dir: Path) -> dict[str, tuple[int, int]]:
    """Re-seed the weather corpus from a fixtures dir, idempotently. Returns per-model counts.

    Reads ``weather_types.json`` → ``weather_type_exposures.json`` → ``weather_emits.json`` →
    ``feast_days.json`` (optional) in dependency order and upserts each. Safe to run repeatedly:
    unchanged rows report as updates, not duplicates.
    """
    return {
        "weather_types": upsert_weather_types(_read(fixtures_dir, WEATHER_TYPES_FILE)),
        "weather_type_exposures": upsert_weather_type_exposures(
            _read(fixtures_dir, WEATHER_TYPE_EXPOSURES_FILE)
        ),
        "weather_emits": upsert_weather_emits(_read(fixtures_dir, WEATHER_EMITS_FILE)),
        "feast_days": upsert_feast_days(_read(fixtures_dir, FEAST_DAYS_FILE)),
    }

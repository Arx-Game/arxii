"""Idempotent upsert loader for the weather seed corpus (#1522).

``loaddata`` can seed a *fresh* database but cannot **re-seed** an edited corpus here:
SharedMemoryModel's identity map intercepts construction-by-pk and returns the cached instance,
silently discarding a fixture's new field values, so natural-key ``loaddata`` INSERTs but never
UPDATEs idmapper rows (#944/#946). ``WeatherEmit`` felt this worst before #2980: its natural key
was the emit's own text, so a second ``loaddata`` after a rewrite didn't just fail to update the
line - it forked a second row and left the old placeholder behind.

This module re-seeds with ``update_or_create`` instead — the same fix
``core_management.content_fixtures.load_entries`` uses — keyed on each model's natural identity,
so editing a magnitude / flag / weight and re-running mutates the existing row in place. The
generated Django-fixture JSON (``{"model", "fields"}`` objects, ``weather_type`` carried as a
natural-key list) stays valid for fresh-DB ``loaddata``; this loader consumes the very same files.

Identity keys (what "the same row" means on re-seed):
- ``WeatherType``          → ``name``
- ``WeatherTypeExposure``  → ``(weather_type, stat_key)`` (its unique constraint)
- ``WeatherTypeShelter``   → ``(weather_type, damage_type)`` (its unique constraint, #2845)
- ``WeatherTransition``    → ``(from_type, to_type)`` (its unique constraint, #2845)
- ``WeatherEmit``          → ``key`` (its stable identity, #2980 - NOT the text)
- ``FeastDay``             → ``(ic_month, ic_day)`` (its unique constraint)

Editing an emit's *text* therefore updates the row in place, the same as any other field (#2980):
``key`` is assigned once and never recomputed from the text, so a rewrite can't fork a new row or
strand the old one. Import-safe without Django configured - only the upsert functions touch the
ORM, via deferred imports.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from world.weather.models import WeatherType

logger = logging.getLogger(__name__)

# The two CreditedContent name FKs a WeatherEmit fixture row may itself carry.
_CREDIT_NAME_KEYS = ("written_by", "reviewed_by")

# Seed files, in dependency order (types before the rows that reference them).
WEATHER_TYPES_FILE = "weather_types.json"
WEATHER_TYPE_EXPOSURES_FILE = "weather_type_exposures.json"
WEATHER_TYPE_SHELTERS_FILE = "weather_type_shelters.json"
WEATHER_TRANSITIONS_FILE = "weather_transitions.json"
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


def _resolve_credit_names(fields: dict, key: str | None) -> None:
    """Resolve ``written_by``/``reviewed_by`` in place from a natural-key ref to a
    ``ContentContributor`` instance, in the same list-or-bare-value shape
    ``_resolve_weather_type`` accepts for ``weather_type``.

    A fixture row can carry these two credit fields directly (a writer crediting a
    line at authoring time, not the guard's own comparison). Passed unresolved, a raw
    list/name reaches ``update_or_create``'s ``defaults`` and Django's FK descriptor
    raises ``ValueError`` on assignment - the row fails to load entirely over a credit
    typo. Mirrors ``core_management.content_fixtures._resolve_or_drop_credit_fields``'s
    #2980 rule: drop the credit, never the row. A value that fails to resolve is
    removed from *fields* and logged; every other field still loads normally.
    """
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    from world.contributors.models import ContentContributor  # noqa: PLC0415

    for name in _CREDIT_NAME_KEYS:
        if name not in fields:
            continue
        ref = fields[name]
        if ref is None or isinstance(ref, ContentContributor):
            continue
        natural_key = ref if isinstance(ref, (list, tuple)) else (ref,)
        try:
            fields[name] = ContentContributor.objects.get_by_natural_key(*natural_key)
        except ObjectDoesNotExist:
            del fields[name]
            logger.warning(
                "WeatherEmit [%s]: credit %r not applied - ContentContributor %r not "
                "found. The row still loads; only the credit is missing.",
                key,
                name,
                ref,
            )


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


def upsert_weather_type_shelters(objects: list[dict]) -> tuple[int, int]:
    """Upsert ``WeatherTypeShelter`` rows keyed on ``(weather_type, damage_type)`` (#2845).

    ``damage_type`` in the fixture is the DamageType's natural-key name (e.g. ``"Radiant"``).
    """
    from world.conditions.models import DamageType  # noqa: PLC0415
    from world.weather.models import WeatherTypeShelter  # noqa: PLC0415

    created = updated = 0
    for obj in objects:
        fields = _fields(obj)
        weather_type = _resolve_weather_type(fields.pop("weather_type"))
        damage_ref = fields.pop("damage_type")
        if isinstance(damage_ref, (list, tuple)):
            damage_ref = damage_ref[0]
        damage_type = DamageType.objects.get(name=damage_ref)
        _, was_created = WeatherTypeShelter.objects.update_or_create(
            weather_type=weather_type, damage_type=damage_type, defaults=fields
        )
        created, updated = (created + 1, updated) if was_created else (created, updated + 1)
    return created, updated


def upsert_weather_transitions(objects: list[dict]) -> tuple[int, int]:
    """Upsert ``WeatherTransition`` rows keyed on ``(from_type, to_type)`` (#2845)."""
    from world.weather.models import WeatherTransition  # noqa: PLC0415

    created = updated = 0
    for obj in objects:
        fields = _fields(obj)
        from_type = _resolve_weather_type(fields.pop("from_type"))
        to_type = _resolve_weather_type(fields.pop("to_type"))
        _, was_created = WeatherTransition.objects.update_or_create(
            from_type=from_type, to_type=to_type, defaults=fields
        )
        created, updated = (created + 1, updated) if was_created else (created, updated + 1)
    return created, updated


def upsert_weather_emits(objects: list[dict]) -> tuple[int, int, list[str]]:
    """Upsert ``WeatherEmit`` rows keyed on ``key`` - the line's stable identity.

    Keyed on the authored ``key`` rather than the text (#2980), so rewriting a
    placeholder line updates the row it belongs to. Keying on the text, as this
    did until #2980, made every rewrite a new row and left the placeholder behind.

    ``WeatherEmit`` carries ``CreditedContent``: a row a human has credited
    (``written_by`` set) whose incoming content differs from the seed corpus is
    left untouched instead of silently overwritten (#3017) - the same freeze
    ``core_management.content_fixtures`` applies to the fixture-loader path.
    The comparison includes the credit fields themselves for a credited row, so
    a matching-content row whose incoming ``written_by``/``reviewed_by`` differs
    also freezes rather than silently accepting a new credit - the same
    differing-credit-fields-alone-conflict rule the fixture path applies. An
    uncredited row still accepts an incoming credit normally; that is the usual
    crediting path, not a conflict. An uncredited row, or a credited row whose
    incoming values (content and credit alike) are identical, upserts exactly
    as before this guard. Returns ``(created, updated, conflicts)``:
    ``conflicts`` names every credited row the corpus left untouched.

    A fixture row's own ``written_by``/``reviewed_by`` (its authored credit, not the
    guard above) is resolved from a natural-key ref via ``_resolve_credit_names``
    before the write - see that function's docstring for the drop-the-credit-never-
    the-row handling of an unresolvable name.
    """
    from core_management.content_fixtures import fields_differing  # noqa: PLC0415
    from world.weather.models import WeatherEmit  # noqa: PLC0415

    created = updated = 0
    conflicts: list[str] = []
    for obj in objects:
        fields = _fields(obj)
        weather_type = _resolve_weather_type(fields.pop("weather_type"))
        key = fields.pop("key")
        _resolve_credit_names(fields, key)
        existing = WeatherEmit.objects.filter(key=key).first()
        if existing is not None and existing.written_by_id is not None:
            incoming = {"weather_type": weather_type, **fields}
            if fields_differing(WeatherEmit, existing, incoming):
                conflicts.append(
                    f"WeatherEmit [{key}] is credited (written_by is set) and differs "
                    "from the seed corpus. Row left untouched (#3017)."
                )
                continue
        _, was_created = WeatherEmit.objects.update_or_create(
            key=key, defaults={"weather_type": weather_type, **fields}
        )
        created, updated = (created + 1, updated) if was_created else (created, updated + 1)
    return created, updated, conflicts


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


def load_weather_seed(fixtures_dir: Path) -> tuple[dict[str, tuple[int, int]], list[str]]:
    """Re-seed the weather corpus from a fixtures dir, idempotently.

    Reads ``weather_types.json`` → ``weather_type_exposures.json`` → ``weather_emits.json`` →
    ``feast_days.json`` (optional) in dependency order and upserts each. Safe to run repeatedly:
    unchanged rows report as updates, not duplicates.

    Returns ``(counts, conflicts)``: ``counts`` is the per-model ``(created, updated)`` tally;
    ``conflicts`` lists every credited ``WeatherEmit`` (#3017) the corpus tried to overwrite and
    left untouched instead (see ``upsert_weather_emits``). Every other model has no credited-row
    guard, so it never contributes to ``conflicts``.
    """
    counts: dict[str, tuple[int, int]] = {
        "weather_types": upsert_weather_types(_read(fixtures_dir, WEATHER_TYPES_FILE)),
        "weather_type_exposures": upsert_weather_type_exposures(
            _read(fixtures_dir, WEATHER_TYPE_EXPOSURES_FILE)
        ),
        "weather_type_shelters": upsert_weather_type_shelters(
            _read(fixtures_dir, WEATHER_TYPE_SHELTERS_FILE)
        ),
        "weather_transitions": upsert_weather_transitions(
            _read(fixtures_dir, WEATHER_TRANSITIONS_FILE)
        ),
    }
    emits_created, emits_updated, conflicts = upsert_weather_emits(
        _read(fixtures_dir, WEATHER_EMITS_FILE)
    )
    counts["weather_emits"] = (emits_created, emits_updated)
    counts["feast_days"] = upsert_feast_days(_read(fixtures_dir, FEAST_DAYS_FILE))
    return counts, conflicts

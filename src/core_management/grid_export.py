"""Export authored grid content (areas/rooms/exits/sidecars) to the lore repo.

Companion to ``content_export.py`` (#2448/#2436): that module exports flat
content-model rows via Django's natural-key serializer; this module exports
the *graph-shaped* grid — spatial hierarchy areas, their rooms, the exits
linking them, and the ambient-value sidecar rows (``LocationValueOverride`` /
``LocationValueModifier``) authored on them.

One JSON bundle file per ``AUTHORED`` (see ``world.areas.constants.GridOrigin``)
Area, written to ``<content_root>/fixtures/grid/<area-slug>.json``. Only
``AUTHORED`` areas/rooms are captured — ``STORY`` (GM) and ``PLAYER`` rows never
export; that boundary is what makes exported bundles safe to round-trip
without clobbering live, player-built or GM-improvised grid state.

This is the inverse of the Task 4 grid importer — export writes what import
will read. The bundle format (v1) is a plain-dict structure, not Django's
serializer format, because the grid graph (area -> rooms -> exits, plus
sidecar rows keyed by area-local room references) doesn't fit the flat
natural-key-FK model content_export.py handles.

Import-safe without Django configured (the tools wrapper and tests use it
standalone). All Django imports are deferred.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class GridExportResult:
    """Outcome of a grid export pass."""

    written: list[Path] = field(default_factory=list)
    reports: list[str] = field(default_factory=list)  # skipped exits, etc. — never errors
    errors: list[str] = field(default_factory=list)
    area_count: int = 0
    room_count: int = 0


def _serialize_area(area) -> dict:
    """Build the ``"area"`` dict for one AUTHORED area's bundle.

    ``dominant_society``: ``world.societies.Society`` carries
    ``NaturalKeyConfig`` (``fields = ["name"]``), so it serializes the same
    way ``realm``/``climate`` do — by name, or ``null`` when unset.
    """
    allowed_building_kinds = sorted(area.allowed_building_kinds.values_list("name", flat=True))
    return {
        "slug": area.slug,
        "name": area.name,
        "level": area.level,
        "parent": area.parent.slug if area.parent_id else None,
        "realm": area.realm.name if area.realm_id else None,
        "climate": area.climate.name if area.climate_id else None,
        "dominant_society": area.dominant_society.name if area.dominant_society_id else None,
        "description": area.description,
        "color": area.color,
        "grid_x": area.grid_x,
        "grid_y": area.grid_y,
        "permit_eligibility": area.permit_eligibility,
        "permit_cost_multiplier": str(area.permit_cost_multiplier),
        "allowed_building_kinds": allowed_building_kinds,
    }


def _serialize_rooms(rooms, display_map: dict) -> list[dict]:
    """Build sorted room dicts. Callers have already validated every room's fixture_key."""
    rooms_data = []
    for room in rooms:
        display = display_map.get(room.objectdb_id)
        rooms_data.append(
            {
                "fixture_key": room.fixture_key,
                "key": room.objectdb.db_key,
                "longname": display.longname if display else "",
                "description": display.permanent_description if display else "",
                "is_public": room.is_public,
                "is_social_hub": room.is_social_hub,
                "is_outdoor": room.is_outdoor,
                "enclosure": room.enclosure,
                "size": room.size.name if room.size_id else None,
                "grid_x": room.grid_x,
                "grid_y": room.grid_y,
                "floor": room.floor,
            }
        )
    rooms_data.sort(key=lambda r: r["fixture_key"])
    return rooms_data


def _destination_fixture_key(exit_obj) -> str | None:
    """The destination room's fixture_key, or None (no destination / no profile / unkeyed)."""
    from evennia_extensions.models import RoomProfile  # noqa: PLC0415

    destination = exit_obj.db_destination
    if destination is None:
        return None
    try:
        return destination.room_profile.fixture_key
    except RoomProfile.DoesNotExist:
        return None


def _exit_kind_and_open(exit_obj) -> tuple[str, bool]:
    """The exit's (exit_kind, is_open), defaulting to DOOR/closed when no ExitProfile exists."""
    from evennia_extensions.constants import ExitKind  # noqa: PLC0415
    from evennia_extensions.models import ExitProfile  # noqa: PLC0415

    try:
        profile = exit_obj.exit_profile
    except ExitProfile.DoesNotExist:
        return ExitKind.DOOR, False
    return profile.exit_kind, profile.is_open


def _serialize_exits(exit_qs, room_fixture_by_objectdb_id: dict, reports: list[str]) -> list[dict]:
    """Build sorted exit dicts. Exits to an unauthored destination are skipped + reported."""
    exits_data = []
    for exit_obj in exit_qs:
        source_fixture_key = room_fixture_by_objectdb_id[exit_obj.db_location_id]
        dest_fixture_key = _destination_fixture_key(exit_obj)
        if not dest_fixture_key:
            reports.append(
                f"skipped exit {source_fixture_key} -> {exit_obj.db_key}: destination not authored"
            )
            continue
        exit_kind, is_open = _exit_kind_and_open(exit_obj)
        exits_data.append(
            {
                "source": source_fixture_key,
                "key": exit_obj.db_key,
                # Evennia's AliasHandler has no batch-fetch API — this per-exit read is a
                # deliberate, bounded exception to the batch-query discipline (exit counts
                # per area are small; see sharedmemory-model skill for the general rule).
                "aliases": sorted(exit_obj.aliases.all()),
                "destination": dest_fixture_key,
                "exit_kind": exit_kind,
                "is_open": is_open,
            }
        )
    exits_data.sort(key=lambda e: (e["source"], e["key"]))
    return exits_data


def _override_target(row, room_fixture_by_pk: dict) -> str | None:
    from world.locations.constants import LocationParentType  # noqa: PLC0415

    if row.parent_type == LocationParentType.ROOM:
        return room_fixture_by_pk.get(row.room_profile_id)
    return None


def _serialize_overrides(overrides, room_fixture_by_pk: dict) -> list[dict]:
    overrides_data = [
        {
            "parent_type": row.parent_type,
            "room": _override_target(row, room_fixture_by_pk),
            "key_type": row.key_type,
            "stat_key": row.stat_key or None,
            "resonance": row.resonance.name if row.resonance_id else None,
            "damage_type": row.damage_type.name if row.damage_type_id else None,
            "value": row.value,
        }
        for row in overrides
    ]
    overrides_data.sort(
        key=lambda o: (o["parent_type"], o["room"] or "", o["key_type"], o["stat_key"] or "")
    )
    return overrides_data


def _serialize_modifiers(modifiers, room_fixture_by_pk: dict) -> list[dict]:
    modifiers_data = [
        {
            "parent_type": row.parent_type,
            "room": _override_target(row, room_fixture_by_pk),
            "key_type": row.key_type,
            "stat_key": row.stat_key or None,
            "resonance": row.resonance.name if row.resonance_id else None,
            "damage_type": row.damage_type.name if row.damage_type_id else None,
            "value": row.value,
            "change_per_day": row.change_per_day,
            "source": row.source,
        }
        for row in modifiers
    ]
    modifiers_data.sort(
        key=lambda m: (m["parent_type"], m["room"] or "", m["key_type"], m["stat_key"] or "")
    )
    return modifiers_data


def _serialize_clues(clues, room_fixture_by_pk: dict) -> list[dict]:
    clues_data = [
        {
            "fixture_key": row.fixture_key,
            "room": room_fixture_by_pk[row.room_profile_id],
            "clue": row.clue.slug,
            "detect_difficulty": row.detect_difficulty,
            "eligibility_rule": row.eligibility_rule,
            "is_active": row.is_active,
        }
        for row in clues
    ]
    clues_data.sort(key=lambda c: c["fixture_key"])
    return clues_data


def _serialize_clue_triggers(triggers, room_fixture_by_pk: dict) -> list[dict]:
    triggers_data = [
        {
            "fixture_key": row.fixture_key,
            "room": room_fixture_by_pk[row.room_profile_id],
            "clue": row.clue.slug,
            "eligibility_rule": row.eligibility_rule,
            "is_active": row.is_active,
        }
        for row in triggers
    ]
    triggers_data.sort(key=lambda t: t["fixture_key"])
    return triggers_data


def _serialize_portal_anchors(anchors, room_fixture_by_pk: dict) -> list[dict]:
    anchors_data = [
        {
            "fixture_key": row.fixture_key,
            "room": room_fixture_by_pk[row.room_profile_id],
            "kind": row.kind.name,
            "name": row.name,
            "is_network_open": row.is_network_open,
        }
        for row in anchors
    ]
    anchors_data.sort(key=lambda a: a["fixture_key"])
    return anchors_data


def _serialize_ambient_lines(lines, room_fixture_by_pk: dict) -> list[dict]:
    lines_data = [
        {
            "parent_type": row.parent_type,
            "room": _override_target(row, room_fixture_by_pk),
            "condition_connector": row.condition_connector,
            "bystander_body": row.bystander_body,
            "arriver_body": row.arriver_body,
            "weight": row.weight,
            "fire_chance": row.fire_chance,
            "cooldown_minutes": row.cooldown_minutes,
            "is_active": row.is_active,
            "conditions": _serialize_ambient_conditions(row),
        }
        for row in lines
    ]
    lines_data.sort(key=lambda r: (r["parent_type"], r["room"] or "", r["arriver_body"][:40]))
    return lines_data


def _serialize_ambient_conditions(line) -> list[dict]:
    conditions_data = [
        {
            "condition_type": condition.condition_type,
            "species": condition.species.name if condition.species_id else None,
            "resonance": condition.resonance.name if condition.resonance_id else None,
            "minimum_value": condition.minimum_value,
            "distinction": condition.distinction.slug if condition.distinction_id else None,
            "min_fame_tier": condition.min_fame_tier or None,
            "perceiving_society": (
                condition.perceiving_society.name if condition.perceiving_society_id else None
            ),
        }
        for condition in line.conditions.select_related(
            "species", "resonance", "distinction", "perceiving_society"
        )
    ]
    conditions_data.sort(key=lambda c: (c["condition_type"], c["species"] or ""))
    return conditions_data


def _build_area_bundle(area, result: GridExportResult) -> dict:
    """Assemble one area's full bundle dict. Raises ContentExportError on the never-silent
    rules (missing area slug — checked by the caller — or missing room fixture_key)."""
    from django.db.models import Q  # noqa: PLC0415
    from evennia.objects.models import ObjectDB  # noqa: PLC0415

    from core_management.content_export import ContentExportError  # noqa: PLC0415
    from evennia_extensions.models import ObjectDisplayData, RoomProfile  # noqa: PLC0415
    from world.areas.constants import GridOrigin  # noqa: PLC0415
    from world.locations.constants import LocationParentType  # noqa: PLC0415
    from world.locations.models import LocationValueModifier, LocationValueOverride  # noqa: PLC0415
    from world.narrative.models import AmbientEmoteLine  # noqa: PLC0415

    rooms = list(
        RoomProfile.objects.filter(area=area, origin=GridOrigin.AUTHORED)
        .select_related("objectdb", "size")
        .order_by("fixture_key")
    )

    room_fixture_by_objectdb_id: dict[int, str] = {}
    for room in rooms:
        if not room.fixture_key:
            msg = (
                f"AUTHORED room {room.objectdb.db_key!r} (objectdb pk={room.objectdb_id}) "
                f"in area {area.slug!r} has no fixture_key."
            )
            raise ContentExportError(msg)
        room_fixture_by_objectdb_id[room.objectdb_id] = room.fixture_key

    room_objectdb_ids = list(room_fixture_by_objectdb_id.keys())
    room_fixture_by_pk = dict(room_fixture_by_objectdb_id)  # RoomProfile pk == objectdb_id

    display_map = {
        row.object_id: row
        for row in ObjectDisplayData.objects.filter(object_id__in=room_objectdb_ids)
    }

    exit_qs = ObjectDB.objects.filter(
        db_location_id__in=room_objectdb_ids,
        db_typeclass_path="typeclasses.exits.Exit",
    ).select_related("db_destination__room_profile", "exit_profile")

    sidecar_scope = Q(parent_type=LocationParentType.AREA, area=area) | Q(
        parent_type=LocationParentType.ROOM, room_profile_id__in=room_objectdb_ids
    )
    overrides = list(
        LocationValueOverride.objects.filter(sidecar_scope).select_related(
            "resonance", "damage_type"
        )
    )
    modifiers = list(
        LocationValueModifier.objects.filter(
            sidecar_scope, source__startswith="authored:"
        ).select_related("resonance", "damage_type")
    )
    ambient_lines = list(AmbientEmoteLine.objects.filter(sidecar_scope))

    from world.clues.models import ClueTrigger, RoomClue  # noqa: PLC0415
    from world.magic.models import PortalAnchor  # noqa: PLC0415

    clues = list(
        RoomClue.objects.filter(
            room_profile_id__in=room_objectdb_ids, fixture_key__isnull=False
        ).select_related("clue")
    )
    clue_triggers = list(
        ClueTrigger.objects.filter(
            room_profile_id__in=room_objectdb_ids, fixture_key__isnull=False
        ).select_related("clue")
    )
    portal_anchors = list(
        PortalAnchor.objects.active()
        .filter(room_profile_id__in=room_objectdb_ids, fixture_key__isnull=False)
        .select_related("kind")
    )

    rooms_data = _serialize_rooms(rooms, display_map)
    exits_data = _serialize_exits(exit_qs, room_fixture_by_objectdb_id, result.reports)
    overrides_data = _serialize_overrides(overrides, room_fixture_by_pk)
    modifiers_data = _serialize_modifiers(modifiers, room_fixture_by_pk)

    result.room_count += len(rooms_data)

    return {
        "format": 1,
        "area": _serialize_area(area),
        "rooms": rooms_data,
        "exits": exits_data,
        "overrides": overrides_data,
        "modifiers": modifiers_data,
        "ambient_lines": _serialize_ambient_lines(ambient_lines, room_fixture_by_pk),
        "clues": _serialize_clues(clues, room_fixture_by_pk),
        "clue_triggers": _serialize_clue_triggers(clue_triggers, room_fixture_by_pk),
        "portal_anchors": _serialize_portal_anchors(portal_anchors, room_fixture_by_pk),
    }


def find_unhoused_authored_rooms() -> list[str]:
    """Human-readable messages for AUTHORED rooms that can never export (#2448).

    An AUTHORED room whose ``area`` is NULL or itself not AUTHORED is silently
    unexportable — ``export_grid_bundles`` only visits rooms reachable through an
    AUTHORED area's room set. That's the "never silent" precedent extended: a
    grid element claiming canonical/AUTHORED status but lacking a home an export
    pass can reach is a data bug (e.g. it lets a ``StartingArea`` fixture
    reference a room no bundle ever contains), not something to skip quietly.

    One query (select_related, no per-room DB round-trip); read-only. Shared by
    ``export_grid_bundles`` (which raises on any hit), ``tools/export_content.py``'s
    ``--check`` dry run, and the admin export-preview page (both of which only
    warn — the writing pass is the actual "never silent" gate).
    """
    from evennia_extensions.models import RoomProfile  # noqa: PLC0415
    from world.areas.constants import GridOrigin  # noqa: PLC0415

    messages: list[str] = []
    rooms = (
        RoomProfile.objects.filter(origin=GridOrigin.AUTHORED)
        .select_related("objectdb", "area")
        .order_by("objectdb_id")
    )
    for room in rooms:
        label = room.fixture_key or f"{room.objectdb.db_key!r} (objectdb pk={room.objectdb_id})"
        if room.area_id is None:
            reason = "no area"
        elif room.area.origin != GridOrigin.AUTHORED:
            area_label = room.area.slug or room.area_id
            reason = f"area {area_label!r} is not AUTHORED (origin={room.area.origin!r})"
        else:
            continue
        messages.append(f"AUTHORED room {label} has {reason}.")
    return messages


def export_grid_bundles(content_root: Path | None = None) -> GridExportResult:
    """Serialize AUTHORED grid areas and write one bundle JSON per area.

    Writes to ``<content_root>/fixtures/grid/<area-slug>.json``. Raises
    ``ContentExportError`` when the content root can't be resolved, an AUTHORED
    room is unhoused (see ``find_unhoused_authored_rooms``), an AUTHORED area has
    no ``slug``, or an AUTHORED room (in an authored area) has no ``fixture_key``
    — the "never silent" rule: a grid element that claims to be canonical
    content but lacks its stable identity key (or a home an export pass can
    reach) is a data bug, not something to skip quietly.
    """
    from core_management.content_export import ContentExportError  # noqa: PLC0415
    from core_management.content_repo import resolve_content_root  # noqa: PLC0415
    from world.areas.constants import GridOrigin  # noqa: PLC0415
    from world.areas.models import Area  # noqa: PLC0415

    root = content_root or resolve_content_root()
    if root is None:
        msg = (
            "CONTENT_REPO_PATH is not set or does not exist. "
            "Set it in src/.env pointing at your local checkout of the "
            "private content repository."
        )
        raise ContentExportError(msg)

    unhoused = find_unhoused_authored_rooms()
    if unhoused:
        msg = "Unhoused AUTHORED room(s) — never exportable:\n" + "\n".join(
            f"  - {line}" for line in unhoused
        )
        raise ContentExportError(msg)

    result = GridExportResult()
    grid_dir = root / "fixtures" / "grid"

    areas = list(
        Area.objects.filter(origin=GridOrigin.AUTHORED)
        .select_related("parent", "realm", "climate", "dominant_society")
        .order_by("slug")
    )
    result.area_count = len(areas)

    for area in areas:
        if not area.slug:
            msg = f"AUTHORED area {area.pk} ({area.name!r}) has no slug."
            raise ContentExportError(msg)

        bundle = _build_area_bundle(area, result)

        grid_dir.mkdir(parents=True, exist_ok=True)
        out_path = grid_dir / f"{area.slug}.json"
        try:
            out_path.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")
        except OSError as exc:
            result.errors.append(f"{area.slug}: write failed: {exc}")
            continue
        result.written.append(out_path)

    return result

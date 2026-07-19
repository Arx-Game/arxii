"""Import authored grid content (areas/rooms/exits/sidecars) from the lore repo.

Companion to ``grid_export.py`` (#2436/#2448): the inverse of that module.
Export writes one JSON bundle per ``AUTHORED`` (see
``world.areas.constants.GridOrigin``) Area to
``<content_root>/fixtures/grid/<area-slug>.json``; this module reads every
bundle back and upserts the areas/rooms/exits/sidecar rows they describe.

Five passes, in order, because later passes reference rows earlier passes
create (a room's area, an exit's source/destination rooms, a sidecar row's
area/room target):

1. **Areas** — topologically ordered by ``parent`` slug (a bundle's parent
   may live in another bundle file, or already exist in the DB).
2. **Rooms** — every bundle's rooms, upserted by ``fixture_key``.
3. **Exits** — every bundle's exits, resolved by source/destination
   ``fixture_key`` against the rooms pass 2 just built.
4. **Sidecars** — ``LocationValueOverride``/``LocationValueModifier`` rows
   scoped to each bundle's area/rooms.
5. **Clue/anchor sidecars** — ``RoomClue``/``ClueTrigger``/``PortalAnchor``
   rows, upserted by ``fixture_key`` against the rooms pass 2 just built.

**Report-never-delete.** An authored area/room/exit that exists in the DB
but is absent from every bundle is never deleted — it's surfaced as a
``reports`` line instead. Only ``authored:``-sourced modifiers are ever
replaced wholesale (deleted + recreated from the bundle); any other
``source`` (e.g. ``weather:cold-snap``) is left untouched. The same
report-never-delete rule applies to fixture-keyed ``RoomClue``/
``ClueTrigger``/``PortalAnchor`` rows absent from every bundle, and to derived
ambient ``TriggerDefinition``/``FlowDefinition``/``Trigger`` rows whose source
condition's compiled filter later changes — the old row-set is left in place,
never cleaned up.

Import-safe without Django configured (mirrors ``grid_export.py``). All
Django imports are deferred.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from evennia_extensions.models import RoomProfile
    from world.areas.models import Area

logger = logging.getLogger(__name__)

# Internal (not-persisted) scope discriminators used only while grouping freshly-imported
# AmbientEmoteLine rows by compiled filter — see _install_ambient_triggers (#2471 v2).
_AMBIENT_SCOPE_ROOM = "room"
_AMBIENT_SCOPE_AREA = "area"


@dataclass
class GridImportResult:
    """Outcome of a grid import pass."""

    created_rooms: int = 0
    updated_rooms: int = 0
    created_exits: int = 0
    updated_exits: int = 0
    created_areas: int = 0
    updated_areas: int = 0
    created_clue_sidecars: int = 0
    updated_clue_sidecars: int = 0
    reports: list[str] = field(default_factory=list)  # never-deleted rows, orphaned exits, etc.
    errors: list[str] = field(default_factory=list)


def _read_bundles(grid_dir: Path) -> list[tuple[Path, dict]]:
    """Parse every ``fixtures/grid/*.json`` file. Raises ``ContentError`` on bad JSON."""
    from core_management.content_fixtures import ContentError  # noqa: PLC0415

    bundles = []
    for path in sorted(grid_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            msg = f"{path.name}: invalid JSON: {exc}"
            raise ContentError(msg) from exc
        bundles.append((path, data))
    return bundles


def _resolve_named_fk(model: Any, name: str | None, bundle_name: str, label: str) -> Any | None:
    """Resolve a nullable by-name FK reference. Raises ``ContentError`` when unresolvable."""
    from core_management.content_fixtures import ContentError  # noqa: PLC0415

    if name is None:
        return None
    obj = model.objects.filter(name=name).first()
    if obj is None:
        msg = f"{bundle_name}: unknown {label} {name!r}"
        raise ContentError(msg)
    return obj


def _import_areas(
    bundles: list[tuple[Path, dict]], result: GridImportResult
) -> tuple[dict[str, Area], dict[Path, Area]]:
    """Pass 1: topologically upsert every bundle's area, parent-before-child.

    Returns ``(area_by_slug, area_by_bundle_path)``.
    """
    from django.db import transaction  # noqa: PLC0415

    from core_management.content_fixtures import ContentError  # noqa: PLC0415
    from world.areas.constants import GridOrigin  # noqa: PLC0415
    from world.areas.models import Area  # noqa: PLC0415
    from world.buildings.models import BuildingKind  # noqa: PLC0415
    from world.realms.models import Realm  # noqa: PLC0415
    from world.societies.models import Society  # noqa: PLC0415
    from world.weather.models import Climate  # noqa: PLC0415

    area_by_slug: dict[str, Area] = {}
    area_by_path: dict[Path, Area] = {}
    pending = [(path, bundle["area"]) for path, bundle in bundles]

    while pending:
        still_pending: list[tuple[Path, dict]] = []
        progressed = False
        for path, area_data in pending:
            parent_slug = area_data["parent"]
            if parent_slug is not None and parent_slug not in area_by_slug:
                if not Area.objects.filter(slug=parent_slug).exists():
                    still_pending.append((path, area_data))
                    continue
            parent = area_by_slug.get(parent_slug) if parent_slug else None
            if parent is None and parent_slug is not None:
                parent = Area.objects.get(slug=parent_slug)

            bundle_name = path.name
            realm = _resolve_named_fk(Realm, area_data["realm"], bundle_name, "realm")
            climate = _resolve_named_fk(Climate, area_data["climate"], bundle_name, "climate")
            society = _resolve_named_fk(
                Society, area_data["dominant_society"], bundle_name, "dominant society"
            )

            with transaction.atomic():
                area, created = Area.objects.update_or_create(
                    slug=area_data["slug"],
                    defaults={
                        "name": area_data["name"],
                        "level": area_data["level"],
                        "parent": parent,
                        "realm": realm,
                        "climate": climate,
                        "dominant_society": society,
                        "description": area_data["description"],
                        "color": area_data["color"],
                        "grid_x": area_data["grid_x"],
                        "grid_y": area_data["grid_y"],
                        "permit_eligibility": area_data["permit_eligibility"],
                        "permit_cost_multiplier": area_data["permit_cost_multiplier"],
                        "origin": GridOrigin.AUTHORED,
                    },
                )
                kinds = []
                for kind_name in area_data["allowed_building_kinds"]:
                    kind = BuildingKind.objects.filter(name=kind_name).first()
                    if kind is None:
                        msg = f"{bundle_name}: unknown building kind {kind_name!r}"
                        raise ContentError(msg)
                    kinds.append(kind)
                area.allowed_building_kinds.set(kinds)

            area_by_slug[area_data["slug"]] = area
            area_by_path[path] = area
            if created:
                result.created_areas += 1
            else:
                result.updated_areas += 1
            progressed = True

        if not progressed:
            unresolved = sorted(area_data["slug"] for _, area_data in still_pending)
            msg = f"unresolved parent slug(s) for area(s): {', '.join(unresolved)}"
            raise ContentError(msg)
        pending = still_pending

    return area_by_slug, area_by_path


def _import_rooms(
    bundles: list[tuple[Path, dict]],
    area_by_path: dict[Path, Area],
    result: GridImportResult,
) -> dict[str, RoomProfile]:
    """Pass 2: upsert every bundle's rooms by ``fixture_key``."""
    from django.db import transaction  # noqa: PLC0415
    from evennia.utils import create as evennia_create  # noqa: PLC0415

    from core_management.content_fixtures import ContentError  # noqa: PLC0415
    from evennia_extensions.models import (  # noqa: PLC0415
        ObjectDisplayData,
        RoomProfile,
        RoomSizeTier,
    )
    from world.areas.constants import GridOrigin  # noqa: PLC0415

    room_by_fixture_key: dict[str, RoomProfile] = {}

    for path, bundle in bundles:
        area = area_by_path[path]
        bundle_name = path.name
        with transaction.atomic():
            for room_data in bundle["rooms"]:
                fixture_key = room_data["fixture_key"]
                size = None
                size_name = room_data["size"]
                if size_name is not None:
                    size = RoomSizeTier.objects.filter(name=size_name).first()
                    if size is None:
                        msg = f"{bundle_name}: unknown room size {size_name!r} for {fixture_key!r}"
                        raise ContentError(msg)

                room_fields = {
                    "area": area,
                    "origin": GridOrigin.AUTHORED,
                    "is_public": room_data["is_public"],
                    "is_social_hub": room_data["is_social_hub"],
                    "is_outdoor": room_data["is_outdoor"],
                    "enclosure": room_data["enclosure"],
                    "size": size,
                    "grid_x": room_data["grid_x"],
                    "grid_y": room_data["grid_y"],
                    "floor": room_data["floor"],
                }

                existing = RoomProfile.objects.filter(fixture_key=fixture_key).first()
                if existing is not None:
                    room_obj = existing.objectdb
                    room_obj.db_key = room_data["key"]
                    room_obj.save()
                    for attr, value in room_fields.items():
                        setattr(existing, attr, value)
                    existing.save()
                    profile = existing
                    result.updated_rooms += 1
                else:
                    room_obj = evennia_create.create_object(
                        typeclass="typeclasses.rooms.Room",
                        key=room_data["key"],
                        nohome=True,
                    )
                    profile, _ = RoomProfile.objects.update_or_create(
                        objectdb=room_obj,
                        defaults={**room_fields, "fixture_key": fixture_key},
                    )
                    result.created_rooms += 1

                ObjectDisplayData.objects.update_or_create(
                    object=room_obj,
                    defaults={
                        "longname": room_data["longname"],
                        "permanent_description": room_data["description"],
                    },
                )
                room_by_fixture_key[fixture_key] = profile

    return room_by_fixture_key


def _import_exits(
    bundles: list[tuple[Path, dict]],
    room_by_fixture_key: dict[str, RoomProfile],
    result: GridImportResult,
) -> None:
    """Pass 3: upsert every bundle's exits by ``(source fixture_key, key)``."""
    from django.db import transaction  # noqa: PLC0415
    from evennia.objects.models import ObjectDB  # noqa: PLC0415
    from evennia.utils import create as evennia_create  # noqa: PLC0415

    from core_management.content_fixtures import ContentError  # noqa: PLC0415
    from evennia_extensions.models import ExitProfile  # noqa: PLC0415

    for path, bundle in bundles:
        bundle_name = path.name
        with transaction.atomic():
            for exit_data in bundle["exits"]:
                source_key = exit_data["source"]
                dest_key = exit_data["destination"]
                exit_key = exit_data["key"]

                source_profile = room_by_fixture_key.get(source_key)
                if source_profile is None:
                    msg = (
                        f"{bundle_name}: exit {exit_key!r} source {source_key!r} "
                        "is not a room imported from any bundle"
                    )
                    raise ContentError(msg)
                dest_profile = room_by_fixture_key.get(dest_key)
                if dest_profile is None:
                    msg = (
                        f"{bundle_name}: exit {exit_key!r} from {source_key!r} has a "
                        f"dangling destination {dest_key!r} — corrupt bundle"
                    )
                    raise ContentError(msg)

                source_obj = source_profile.objectdb
                dest_obj = dest_profile.objectdb

                existing_exit = ObjectDB.objects.filter(
                    db_location=source_obj,
                    db_key=exit_key,
                    db_typeclass_path="typeclasses.exits.Exit",
                ).first()
                if existing_exit is not None:
                    existing_exit.db_destination = dest_obj
                    existing_exit.save()
                    exit_obj = existing_exit
                    result.updated_exits += 1
                else:
                    exit_obj = evennia_create.create_object(
                        typeclass="typeclasses.exits.Exit",
                        key=exit_key,
                        location=source_obj,
                        destination=dest_obj,
                        nohome=True,
                    )
                    result.created_exits += 1

                current_aliases = set(exit_obj.aliases.all())
                for alias in exit_data["aliases"]:
                    if alias not in current_aliases:
                        exit_obj.aliases.add(alias)

                profile = ExitProfile.get_or_create_for_exit(exit_obj)
                profile.exit_kind = exit_data["exit_kind"]
                profile.is_open = exit_data["is_open"]
                profile.save()


def _report_orphaned_exits(bundles: list[tuple[Path, dict]], result: GridImportResult) -> None:
    """Report DB exits off any AUTHORED keyed room not present in any bundle. Never deletes."""
    from evennia.objects.models import ObjectDB  # noqa: PLC0415

    from evennia_extensions.models import RoomProfile  # noqa: PLC0415
    from world.areas.constants import GridOrigin  # noqa: PLC0415

    bundle_exit_keys = {
        (exit_data["source"], exit_data["key"])
        for _, bundle in bundles
        for exit_data in bundle["exits"]
    }

    authored_rooms = list(
        RoomProfile.objects.filter(origin=GridOrigin.AUTHORED, fixture_key__isnull=False)
    )
    fixture_by_objectdb_id = {room.objectdb_id: room.fixture_key for room in authored_rooms}
    if not fixture_by_objectdb_id:
        return

    exits = ObjectDB.objects.filter(
        db_location_id__in=fixture_by_objectdb_id, db_typeclass_path="typeclasses.exits.Exit"
    )
    for exit_obj in exits:
        source_key = fixture_by_objectdb_id[exit_obj.db_location_id]
        if (source_key, exit_obj.db_key) not in bundle_exit_keys:
            result.reports.append(
                f"DB exit {source_key} -> {exit_obj.db_key} not present in any bundle"
            )


def _resolve_parent(
    row_data: dict, area: Area, room_by_fixture_key: dict[str, RoomProfile], bundle_name: str
) -> tuple[str, Any]:
    """Return ``(field_name, target)`` for a sidecar row's discriminated parent."""
    from core_management.content_fixtures import ContentError  # noqa: PLC0415
    from world.locations.constants import LocationParentType  # noqa: PLC0415

    if row_data["parent_type"] == LocationParentType.AREA:
        return "area", area
    room_fixture_key = row_data["room"]
    profile = room_by_fixture_key.get(room_fixture_key)
    if profile is None:
        msg = f"{bundle_name}: sidecar row references unknown room {room_fixture_key!r}"
        raise ContentError(msg)
    return "room_profile", profile


def _resolve_axis_value(row_data: dict, bundle_name: str) -> tuple[str, Any]:
    """Return ``(field_name, value)`` for a sidecar row's discriminated axis key."""
    from core_management.content_fixtures import ContentError  # noqa: PLC0415
    from world.conditions.models import DamageType  # noqa: PLC0415
    from world.locations.constants import KeyType  # noqa: PLC0415
    from world.magic.models import Resonance  # noqa: PLC0415

    key_type = row_data["key_type"]
    if key_type == KeyType.STAT:
        return "stat_key", row_data["stat_key"]
    if key_type == KeyType.RESONANCE:
        name = row_data["resonance"]
        resonance = Resonance.objects.filter(name=name).first()
        if resonance is None:
            msg = f"{bundle_name}: unknown resonance {name!r}"
            raise ContentError(msg)
        return "resonance", resonance
    name = row_data["damage_type"]
    damage_type = DamageType.objects.filter(name=name).first()
    if damage_type is None:
        msg = f"{bundle_name}: unknown damage type {name!r}"
        raise ContentError(msg)
    return "damage_type", damage_type


def _import_sidecars(
    bundles: list[tuple[Path, dict]],
    area_by_path: dict[Path, Area],
    room_by_fixture_key: dict[str, RoomProfile],
) -> None:
    """Pass 4: per-bundle sidecar rows — override upsert, authored-modifier replace."""
    from django.db import transaction  # noqa: PLC0415
    from django.db.models import Q  # noqa: PLC0415

    from world.locations.constants import LocationParentType  # noqa: PLC0415
    from world.locations.models import LocationValueModifier, LocationValueOverride  # noqa: PLC0415

    for path, bundle in bundles:
        area = area_by_path[path]
        bundle_name = path.name
        bundle_room_ids = [
            room_by_fixture_key[room_data["fixture_key"]].objectdb_id
            for room_data in bundle["rooms"]
        ]

        with transaction.atomic():
            for row_data in bundle["overrides"]:
                parent_field, parent_obj = _resolve_parent(
                    row_data, area, room_by_fixture_key, bundle_name
                )
                axis_field, axis_value = _resolve_axis_value(row_data, bundle_name)
                LocationValueOverride.objects.update_or_create(
                    **{parent_field: parent_obj, axis_field: axis_value},
                    defaults={
                        "parent_type": row_data["parent_type"],
                        "key_type": row_data["key_type"],
                        "value": row_data["value"],
                    },
                )

            scope = Q(parent_type=LocationParentType.AREA, area=area) | Q(
                parent_type=LocationParentType.ROOM, room_profile_id__in=bundle_room_ids
            )
            LocationValueModifier.objects.filter(scope, source__startswith="authored:").delete()

            for row_data in bundle["modifiers"]:
                parent_field, parent_obj = _resolve_parent(
                    row_data, area, room_by_fixture_key, bundle_name
                )
                axis_field, axis_value = _resolve_axis_value(row_data, bundle_name)
                LocationValueModifier.objects.create(
                    parent_type=row_data["parent_type"],
                    key_type=row_data["key_type"],
                    value=row_data["value"],
                    change_per_day=int(row_data["change_per_day"]),
                    source=row_data["source"],
                    **{parent_field: parent_obj, axis_field: axis_value},
                )


def _import_clue_and_anchor_sidecars(
    bundles: list[tuple[Path, dict]],
    room_by_fixture_key: dict[str, RoomProfile],
    result: GridImportResult,
) -> None:
    """Pass 5: upsert fixture-keyed RoomClue/ClueTrigger/PortalAnchor rows by fixture_key."""
    from django.db import transaction  # noqa: PLC0415

    from core_management.content_fixtures import ContentError  # noqa: PLC0415
    from world.clues.models import Clue, ClueTrigger, RoomClue  # noqa: PLC0415
    from world.magic.models import PortalAnchor, PortalAnchorKind  # noqa: PLC0415

    for path, bundle in bundles:
        bundle_name = path.name
        with transaction.atomic():
            for row_data in bundle["clues"]:
                room_profile = room_by_fixture_key[row_data["room"]]
                clue = Clue.objects.filter(slug=row_data["clue"]).first()
                if clue is None:
                    msg = f"{bundle_name}: unknown clue slug {row_data['clue']!r}"
                    raise ContentError(msg)
                _, created = RoomClue.objects.update_or_create(
                    fixture_key=row_data["fixture_key"],
                    defaults={
                        "room_profile": room_profile,
                        "clue": clue,
                        "detect_difficulty": row_data["detect_difficulty"],
                        "eligibility_rule": row_data["eligibility_rule"],
                        "is_active": row_data["is_active"],
                    },
                )
                result.created_clue_sidecars += created
                result.updated_clue_sidecars += not created

            for row_data in bundle["clue_triggers"]:
                room_profile = room_by_fixture_key[row_data["room"]]
                clue = Clue.objects.filter(slug=row_data["clue"]).first()
                if clue is None:
                    msg = f"{bundle_name}: unknown clue slug {row_data['clue']!r}"
                    raise ContentError(msg)
                _, created = ClueTrigger.objects.update_or_create(
                    fixture_key=row_data["fixture_key"],
                    defaults={
                        "room_profile": room_profile,
                        "clue": clue,
                        "eligibility_rule": row_data["eligibility_rule"],
                        "is_active": row_data["is_active"],
                    },
                )
                result.created_clue_sidecars += created
                result.updated_clue_sidecars += not created

            for row_data in bundle["portal_anchors"]:
                room_profile = room_by_fixture_key[row_data["room"]]
                kind = PortalAnchorKind.objects.filter(name=row_data["kind"]).first()
                if kind is None:
                    msg = f"{bundle_name}: unknown portal anchor kind {row_data['kind']!r}"
                    raise ContentError(msg)
                _, created = PortalAnchor.objects.update_or_create(
                    fixture_key=row_data["fixture_key"],
                    defaults={
                        "room_profile": room_profile,
                        "kind": kind,
                        "name": row_data["name"],
                        "is_network_open": row_data["is_network_open"],
                        "dissolved_at": None,
                    },
                )
                result.created_clue_sidecars += created
                result.updated_clue_sidecars += not created


def _resolve_ambient_condition_fks(row_data: dict, bundle_name: str) -> dict[str, object]:
    """Resolve the natural-key FK fields an AmbientEmoteCondition row may carry (#2471 v2)."""
    from core_management.content_fixtures import ContentError  # noqa: PLC0415
    from world.distinctions.models import Distinction  # noqa: PLC0415
    from world.magic.models import Resonance  # noqa: PLC0415
    from world.societies.models import Society  # noqa: PLC0415
    from world.species.models import Species  # noqa: PLC0415

    resolved: dict[str, object] = {}

    species_name = row_data.get("species")
    if species_name:
        resolved["species"] = _resolve_named_fk(Species, species_name, bundle_name, "species")

    resonance_name = row_data.get("resonance")
    if resonance_name:
        resolved["resonance"] = _resolve_named_fk(
            Resonance, resonance_name, bundle_name, "resonance"
        )

    distinction_slug = row_data.get("distinction")
    if distinction_slug:
        # Distinction.name is NOT unique (display text only) — slug is the model's actual
        # NaturalKeyConfig field (world/distinctions/models.py).
        distinction = Distinction.objects.filter(slug=distinction_slug).first()
        if distinction is None:
            msg = f"{bundle_name}: unknown distinction {distinction_slug!r}"
            raise ContentError(msg)
        resolved["distinction"] = distinction

    society_name = row_data.get("perceiving_society")
    if society_name:
        resolved["perceiving_society"] = _resolve_named_fk(
            Society, society_name, bundle_name, "society"
        )

    return resolved


def _validate_ambient_line_row(row_data: dict, bundle_name: str) -> None:
    """Content-authoring invariant: unconditional lines must be private (#2471 v2).

    Checked here (bundle-dict level, before any DB write) rather than in
    ``AmbientEmoteLine.clean()`` — conditions live in a child model created after the line,
    so the model layer can't see "does this line have zero conditions" at its own clean()
    time. The bundle dict has both at once.
    """
    from core_management.content_fixtures import ContentError  # noqa: PLC0415

    if not row_data.get("conditions") and row_data.get("bystander_body"):
        msg = (
            f"{bundle_name}: ambient line with no conditions has a bystander_body "
            "(unconditional lines must be private — arriver_body only)"
        )
        raise ContentError(msg)


def _import_ambient_lines(
    bundles: list[tuple[Path, dict]],
    area_by_path: dict[Path, Area],
    room_by_fixture_key: dict[str, RoomProfile],
) -> None:
    """Pass: per-bundle AmbientEmoteLine/AmbientEmoteCondition rows, then derive + install
    condition-group Triggers (#2471 v2).

    Wholesale replace within each bundle's scope (delete-then-recreate, cascading to
    conditions) rather than upsert — AmbientEmoteLine rows have no natural per-parent
    uniqueness, mirroring how authored: LocationValueModifier rows are handled.
    """
    from django.db import transaction  # noqa: PLC0415
    from django.db.models import Q  # noqa: PLC0415

    from world.locations.constants import LocationParentType  # noqa: PLC0415
    from world.narrative.models import AmbientEmoteCondition, AmbientEmoteLine  # noqa: PLC0415

    for path, bundle in bundles:
        area = area_by_path[path]
        bundle_name = path.name
        bundle_room_fixture_keys = [room_data["fixture_key"] for room_data in bundle["rooms"]]
        bundle_room_ids = [room_by_fixture_key[key].objectdb_id for key in bundle_room_fixture_keys]

        with transaction.atomic():
            scope = Q(parent_type=LocationParentType.AREA, area=area) | Q(
                parent_type=LocationParentType.ROOM, room_profile_id__in=bundle_room_ids
            )
            AmbientEmoteLine.objects.filter(scope).delete()

            created_lines = []
            for row_data in bundle.get("ambient_lines", []):
                _validate_ambient_line_row(row_data, bundle_name)
                parent_field, parent_obj = _resolve_parent(
                    row_data, area, room_by_fixture_key, bundle_name
                )
                line = AmbientEmoteLine.objects.create(
                    parent_type=row_data["parent_type"],
                    condition_connector=row_data.get("condition_connector", "and"),
                    bystander_body=row_data.get("bystander_body", ""),
                    arriver_body=row_data.get("arriver_body", ""),
                    weight=row_data["weight"],
                    fire_chance=row_data["fire_chance"],
                    cooldown_minutes=row_data["cooldown_minutes"],
                    is_active=row_data["is_active"],
                    **{parent_field: parent_obj},
                )
                for condition_data in row_data.get("conditions", []):
                    fk_fields = _resolve_ambient_condition_fks(condition_data, bundle_name)
                    AmbientEmoteCondition.objects.create(
                        line=line,
                        condition_type=condition_data["condition_type"],
                        minimum_value=condition_data.get("minimum_value"),
                        min_fame_tier=condition_data.get("min_fame_tier") or "",
                        **fk_fields,
                    )
                created_lines.append(line)

            _install_ambient_triggers(
                area, bundle_room_fixture_keys, room_by_fixture_key, created_lines
            )


def _ensure_ambient_trigger(room_objectdb: object, trigger_def: object) -> None:
    """Idempotently install a derived ambient Trigger on a room (#2471 v2).

    Mirrors world.battles.duel_wiring.install_champion_duel_trigger's get_or_create +
    on_trigger_added(only when newly created) shape.
    """
    from flows.models import Trigger  # noqa: PLC0415

    trigger, created = Trigger.objects.get_or_create(
        obj=room_objectdb, trigger_definition=trigger_def
    )
    if created:
        handler = room_objectdb.trigger_handler
        if handler is not None:
            handler.on_trigger_added(trigger)


def _ensure_ambient_group_trigger(
    scope: str, scope_key: str, compiled_filter: dict | None, line_ids: list[int]
) -> object:
    """Idempotently create (or refresh) the derived TriggerDefinition for one condition
    group (#2471 v2). Name is deterministic from (scope, scope_key, filter digest), so
    re-imports of unchanged content resolve to the same row (get_or_create by name);
    changed content (new lines added to the same condition, or a changed filter under an
    unlikely digest collision) refreshes the existing row's filter/parameters in place.
    A condition group whose compiled filter actually changes gets a new digest, so a new
    FlowDefinition/TriggerDefinition row-set is created rather than migrating the old
    one in place; the old (now-orphaned) rows are never deleted or deactivated — same
    report-never-delete deferral as this file's other sidecar types, not a bug.
    """
    import hashlib  # noqa: PLC0415
    import json  # noqa: PLC0415

    from flows.constants import EventName  # noqa: PLC0415
    from flows.consts import FlowActionChoices  # noqa: PLC0415
    from flows.factories import FlowStepDefinitionFactory  # noqa: PLC0415
    from flows.models import FlowDefinition  # noqa: PLC0415
    from flows.models.triggers import TriggerDefinition  # noqa: PLC0415

    digest = hashlib.sha1(  # noqa: S324 (content-addressing, not security)
        json.dumps(compiled_filter, sort_keys=True).encode()
    ).hexdigest()[:12]
    name = f"moved_ambient_{scope}_{scope_key}_{digest}"

    flow, _ = FlowDefinition.objects.get_or_create(name=name)
    step_parameters = {"payload": "@payload", "line_ids": sorted(line_ids)}
    if not flow.steps.exists():
        FlowStepDefinitionFactory(
            flow=flow,
            action=FlowActionChoices.CALL_SERVICE_FUNCTION,
            variable_name="world.narrative.ambient_content.deliver_ambient_group",
            parameters=step_parameters,
        )
    else:
        step = flow.steps.first()
        if step.parameters != step_parameters:
            step.parameters = step_parameters
            step.save(update_fields=["parameters"])

    trigger_def, created = TriggerDefinition.objects.get_or_create(
        name=name,
        defaults={
            "event_name": EventName.MOVED,
            "flow_definition": flow,
            "base_filter_condition": compiled_filter,
        },
    )
    if not created and trigger_def.base_filter_condition != compiled_filter:
        trigger_def.base_filter_condition = compiled_filter
        trigger_def.save(update_fields=["base_filter_condition"])
    return trigger_def


def _install_ambient_triggers(
    area: Area,
    bundle_room_fixture_keys: list[str],
    room_by_fixture_key: dict[str, RoomProfile],
    lines: list,
) -> None:
    """Group freshly-imported lines by compiled filter, derive/install Triggers (#2471 v2).

    Room-scoped groups install only on their own room. Area-scoped groups install on every
    bundle room EXCEPT one that has its own room-scoped group with an IDENTICAL compiled
    filter — per-condition-group most-specific-wins, not a wholesale room-vs-area pool
    replacement: a room's own SPECIES override doesn't suppress the area's unrelated
    RESONANCE_MIN group.
    """
    from collections import defaultdict  # noqa: PLC0415
    import json  # noqa: PLC0415

    from world.locations.constants import LocationParentType  # noqa: PLC0415
    from world.narrative.ambient_content import compile_line_filter  # noqa: PLC0415

    room_fixture_by_id = {
        profile.objectdb_id: fixture_key for fixture_key, profile in room_by_fixture_key.items()
    }

    groups: dict[tuple[str, str, str], list] = defaultdict(list)
    for line in lines:
        compiled = compile_line_filter(line)
        compiled_json = json.dumps(compiled, sort_keys=True)
        if line.parent_type == LocationParentType.ROOM:
            scope, scope_key = _AMBIENT_SCOPE_ROOM, room_fixture_by_id[line.room_profile_id]
        else:
            scope, scope_key = _AMBIENT_SCOPE_AREA, area.slug
        groups[(scope, scope_key, compiled_json)].append(line)

    room_override_filters: dict[str, set[str]] = defaultdict(set)
    for scope, scope_key, compiled_json in groups:
        if scope == _AMBIENT_SCOPE_ROOM:
            room_override_filters[scope_key].add(compiled_json)

    for (scope, scope_key, compiled_json), group_lines in groups.items():
        compiled = json.loads(compiled_json)
        line_ids = [line.pk for line in group_lines]
        trigger_def = _ensure_ambient_group_trigger(scope, scope_key, compiled, line_ids)
        if scope == _AMBIENT_SCOPE_ROOM:
            _ensure_ambient_trigger(room_by_fixture_key[scope_key].objectdb, trigger_def)
        else:
            for fixture_key in bundle_room_fixture_keys:
                if compiled_json in room_override_filters[fixture_key]:
                    continue
                _ensure_ambient_trigger(room_by_fixture_key[fixture_key].objectdb, trigger_def)


def _report_missing_clue_and_anchor_sidecars(
    bundles: list[tuple[Path, dict]], result: GridImportResult
) -> None:
    """Report-never-delete: fixture-keyed sidecar rows in the DB absent from every bundle."""
    from world.clues.models import ClueTrigger, RoomClue  # noqa: PLC0415
    from world.magic.models import PortalAnchor  # noqa: PLC0415

    bundle_clue_keys = {row["fixture_key"] for _, bundle in bundles for row in bundle["clues"]}
    for room_clue in RoomClue.objects.filter(fixture_key__isnull=False).exclude(
        fixture_key__in=bundle_clue_keys
    ):
        result.reports.append(
            f"authored clue placement {room_clue.fixture_key!r} not in any bundle"
        )

    bundle_trigger_keys = {
        row["fixture_key"] for _, bundle in bundles for row in bundle["clue_triggers"]
    }
    for trigger in ClueTrigger.objects.filter(fixture_key__isnull=False).exclude(
        fixture_key__in=bundle_trigger_keys
    ):
        result.reports.append(f"authored clue trigger {trigger.fixture_key!r} not in any bundle")

    bundle_anchor_keys = {
        row["fixture_key"] for _, bundle in bundles for row in bundle["portal_anchors"]
    }
    for anchor in (
        PortalAnchor.objects.active()
        .filter(fixture_key__isnull=False)
        .exclude(fixture_key__in=bundle_anchor_keys)
    ):
        result.reports.append(f"authored portal anchor {anchor.fixture_key!r} not in any bundle")


def _report_missing_authored(
    area_by_slug: dict[str, Area],
    room_by_fixture_key: dict[str, RoomProfile],
    result: GridImportResult,
) -> None:
    """Report-never-delete: AUTHORED areas/rooms in the DB absent from every bundle."""
    from evennia_extensions.models import RoomProfile  # noqa: PLC0415
    from world.areas.constants import GridOrigin  # noqa: PLC0415
    from world.areas.models import Area  # noqa: PLC0415

    bundle_slugs = set(area_by_slug)
    for area in Area.objects.filter(origin=GridOrigin.AUTHORED).exclude(slug__in=bundle_slugs):
        result.reports.append(f"authored area {area.slug!r} not present in any bundle")

    bundle_fixture_keys = set(room_by_fixture_key)
    missing_rooms = RoomProfile.objects.filter(origin=GridOrigin.AUTHORED).exclude(
        fixture_key__in=bundle_fixture_keys
    )
    for room in missing_rooms:
        result.reports.append(f"authored room {room.fixture_key!r} not present in any bundle")


def load_grid_bundles(content_root: Path | None = None) -> GridImportResult:
    """Read every ``fixtures/grid/*.json`` bundle and upsert the graph it describes.

    Raises ``ContentError`` (from ``core_management.content_fixtures``) on structural
    problems: the content root can't be resolved, a bundle is invalid JSON, an area
    references an unresolvable parent/realm/climate/society/building-kind, a room
    references an unresolvable size tier, an exit has a dangling destination
    fixture_key, or a clue/clue-trigger/portal-anchor row references an unresolvable
    clue slug or portal anchor kind name. Never deletes an AUTHORED area/room/exit
    or a fixture-keyed clue/clue-trigger/portal-anchor absent from the bundles —
    those surface as ``reports`` lines instead (see module docstring).
    """
    from core_management.content_fixtures import ContentError  # noqa: PLC0415
    from core_management.content_repo import resolve_content_root  # noqa: PLC0415

    root = content_root or resolve_content_root()
    if root is None:
        msg = (
            "CONTENT_REPO_PATH is not set or does not exist. "
            "Set it in src/.env pointing at your local checkout of the "
            "private content repository."
        )
        raise ContentError(msg)

    result = GridImportResult()
    grid_dir = root / "fixtures" / "grid"
    if not grid_dir.is_dir():
        return result

    bundles = _read_bundles(grid_dir)
    area_by_slug, area_by_path = _import_areas(bundles, result)
    room_by_fixture_key = _import_rooms(bundles, area_by_path, result)
    _import_exits(bundles, room_by_fixture_key, result)
    _report_orphaned_exits(bundles, result)
    _import_sidecars(bundles, area_by_path, room_by_fixture_key)
    _import_ambient_lines(bundles, area_by_path, room_by_fixture_key)
    _report_missing_authored(area_by_slug, room_by_fixture_key, result)
    _import_clue_and_anchor_sidecars(bundles, room_by_fixture_key, result)
    _report_missing_clue_and_anchor_sidecars(bundles, result)

    return result

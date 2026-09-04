"""Staff-only world-builder read API (#2449 Task 4).

Read-only surface behind ``IsStaffOrGrantHolder`` (#3534 — staff, or any
``AreaBuildGrant`` holder, scoped to their grant subtrees): the area
tree (``GET /api/world-builder/areas/``) and the per-area manager payload
(``GET /api/world-builder/areas/<id>/manager/``) the staff canvas renders —
ALL RoomProfiles in the area (private included), unlike the player-facing
``AreaViewSet``/``RoomProfileViewSet`` (world.areas.views — public rooms only,
no staff bookkeeping fields). Every mutation flows through the registry
action-dispatch endpoint instead (``world_builder``-category actions in
``actions/definitions/world_builder.py``) — this is reads only.

Mirrors ``BuildingManagerViewSet.retrieve``'s query batching (one rooms query
with select_related, one display-data query, one exits query) plus two more
bulk (never per-room) queries this payload needs that the owner-facing
manager doesn't: occupant counts and cross-area exit destination areas.
"""

from __future__ import annotations

import contextlib

from django.db.models import Count, Q, QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from evennia.objects.models import ObjectDB
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.request import Request
from rest_framework.response import Response

from evennia_extensions.models import ObjectDisplayData, RoomProfile
from world.areas.constants import UNFINISHED_ROOM_DESC
from world.areas.filters import AreaFilter
from world.areas.grid_services import exits_from_rooms
from world.areas.models import Area, AreaClosure
from world.areas.serializers import (
    WorldBuilderAreaManagerSerializer,
    WorldBuilderAreaSerializer,
    WorldBuilderGrantsSerializer,
    WorldBuilderRoomDetailSerializer,
    WorldBuilderRoomHitSerializer,
)

_CHARACTER_TYPECLASS = "typeclasses.characters.Character"
_EXIT_TYPECLASS = "typeclasses.exits.Exit"


class WorldBuilderAreaPagination(PageNumberPagination):
    """Mirrors ``world.areas.views.AreaPagination`` for the staff area tree.

    Large page size for hierarchical browsing — drill-down naturally limits
    results, so this is a safety cap rather than UX pagination.
    """

    page_size = 200
    page_size_query_param = "page_size"
    max_page_size = 200


def _occupant_counts(room_ids: list[int]) -> dict[int, int]:
    """Character-occupant counts per room, one bulk query (no per-room N+1).

    Mirrors ``world.areas.grid_services.has_character_occupants``'s
    typeclass check, but batched. Exits are excluded in SQL (#3269) — they
    live in rooms too and dominate the contents at grid scale, so fetching
    and type-checking them in Python made every payload rebuild scale with
    exit count. The authoritative subclass-aware check stays in Python for
    the (few) remaining objects.
    """
    counts: dict[int, int] = {}
    contents = ObjectDB.objects.filter(db_location_id__in=room_ids).exclude(
        db_typeclass_path=_EXIT_TYPECLASS
    )
    for obj in contents:
        if obj.is_typeclass(_CHARACTER_TYPECLASS, exact=False):
            counts[obj.db_location_id] = counts.get(obj.db_location_id, 0) + 1
    return counts


def _needs_prose(description: str) -> bool:
    """Whether a room still awaits its prose pass (#3269): empty or stub text."""
    text = description.strip()
    return (
        # PLACEHOLDER is the repo-wide prose-stub marker in free text, not an identifier.
        not text or text == UNFINISHED_ROOM_DESC or "PLACEHOLDER" in text  # noqa: STRING_LITERAL
    )


def _stat_sidecars(profiles: list[RoomProfile]) -> dict[int, list[dict]]:
    """Per-room ambient-stat rows (#3269): default, effective, authored, pinned.

    Bulk throughout — ``effective_stats_for_rooms`` is 4 queries regardless of
    room count, plus one authored-modifier and one override query.
    """
    from django.db import DatabaseError, transaction  # noqa: PLC0415

    from world.locations.constants import (  # noqa: PLC0415
        AUTHORED_STAT_SOURCE,
        STAT_DEFAULTS,
        KeyType,
        LocationParentType,
        StatKey,
    )
    from world.locations.models import (  # noqa: PLC0415
        LocationValueModifier,
        LocationValueOverride,
    )
    from world.locations.services import effective_stats_for_rooms  # noqa: PLC0415

    try:
        with transaction.atomic():
            effective = effective_stats_for_rooms([p.objectdb for p in profiles], list(StatKey))
    except DatabaseError:
        # The cascade walk reads the areas_areaclosure materialized view,
        # which the SQLite fast tier does not create (known gap; CI's PG
        # parity is the gate). Fall back to defaults so the rest of the
        # payload — and the fast tier's coverage of it — survives.
        effective = {}
    room_ids = [p.objectdb_id for p in profiles]
    authored: dict[tuple[int, str], int] = {}
    for row in LocationValueModifier.objects.filter(
        parent_type=LocationParentType.ROOM,
        room_profile_id__in=room_ids,
        key_type=KeyType.STAT,
        source=AUTHORED_STAT_SOURCE,
    ):
        authored[(row.room_profile_id, row.stat_key)] = row.value
    pinned: dict[tuple[int, str], int] = {}
    for row in LocationValueOverride.objects.filter(
        parent_type=LocationParentType.ROOM,
        room_profile_id__in=room_ids,
        key_type=KeyType.STAT,
    ):
        pinned[(row.room_profile_id, row.stat_key)] = row.value
    return {
        p.objectdb_id: [
            {
                "key": key.value,
                "label": key.label,
                "default": STAT_DEFAULTS[key],
                "effective": effective.get(p.objectdb_id, {}).get(key, STAT_DEFAULTS[key]),
                "authored": authored.get((p.objectdb_id, key.value)),
                "pinned": pinned.get((p.objectdb_id, key.value)),
            }
            for key in StatKey
        ]
        for p in profiles
    }


def _authoring_sidecars(profiles: list[RoomProfile]) -> dict[str, dict]:
    """Phase B per-room authoring surfaces (#3269), all bulk queries.

    Returns keyed maps: places, feature, functionaries, ambient_counts,
    travel_hub, starting_bindings, desc_variants (#3291).
    """
    from evennia_extensions.models import RoomDescVariant  # noqa: PLC0415
    from world.character_creation.models import Beginnings, StartingArea  # noqa: PLC0415
    from world.narrative.models import AmbientEmit, AmbientEmoteLine  # noqa: PLC0415
    from world.npc_services.models import Functionary  # noqa: PLC0415
    from world.room_features.models import RoomFeatureInstance  # noqa: PLC0415
    from world.scenes.place_models import Place  # noqa: PLC0415
    from world.travel.models import TravelHub  # noqa: PLC0415

    room_ids = [p.objectdb_id for p in profiles]
    places: dict[int, list[dict]] = {}
    for row in Place.objects.filter(room_id__in=room_ids).order_by("name"):
        places.setdefault(row.room_id, []).append(
            {"id": row.pk, "name": row.name, "description": row.description}
        )
    feature: dict[int, dict] = {}
    for inst in (
        RoomFeatureInstance.objects.filter(room_profile_id__in=room_ids)
        .active()
        .select_related("feature_kind")
    ):
        feature[inst.room_profile_id] = {
            "kind": inst.feature_kind.name,
            "level": inst.level,
        }
    functionaries: dict[int, list[str]] = {}
    for f in Functionary.objects.filter(room_id__in=room_ids, is_active=True).select_related(
        "role"
    ):
        functionaries.setdefault(f.room_id, []).append(f.role.name)
    ambient_counts: dict[int, dict] = {}
    for line in AmbientEmoteLine.objects.filter(room_profile_id__in=room_ids):
        entry = ambient_counts.setdefault(line.room_profile_id, {"lines": 0, "emits": 0})
        entry["lines"] += 1
    for emit in AmbientEmit.objects.filter(room_profile_id__in=room_ids):
        entry = ambient_counts.setdefault(emit.room_profile_id, {"lines": 0, "emits": 0})
        entry["emits"] += 1
    travel_hub: dict[int, dict] = {}
    for hub in TravelHub.objects.filter(room_profile_id__in=room_ids, is_active=True):
        travel_hub[hub.room_profile_id] = {
            "name": hub.name,
            "travel_modes": hub.travel_modes,
            "is_transit_stop": hub.is_transit_stop,
        }
    bindings: dict[int, list[str]] = {}
    for sa in StartingArea.objects.filter(default_starting_room_id__in=room_ids):
        bindings.setdefault(sa.default_starting_room_id, []).append(f"Starting area: {sa.name}")
    for beginning in Beginnings.objects.filter(starting_room_override_id__in=room_ids):
        bindings.setdefault(beginning.starting_room_override_id, []).append(
            f"Beginning: {beginning.name}"
        )
    desc_variants: dict[int, list[dict]] = {}
    for variant in RoomDescVariant.objects.filter(room_profile_id__in=room_ids):
        desc_variants.setdefault(variant.room_profile_id, []).append(
            {
                "id": variant.pk,
                "season": variant.season,
                "phase": variant.phase,
                "description": variant.description,
            }
        )
    return {
        "places": places,
        "feature": feature,
        "functionaries": functionaries,
        "ambient_counts": ambient_counts,
        "travel_hub": travel_hub,
        "starting_bindings": bindings,
        "desc_variants": desc_variants,
    }


def _clue_and_anchor_sidecars(
    room_ids: list[int],
) -> tuple[dict[int, list[dict]], dict[int, list[dict]], dict[int, list[dict]]]:
    """Per-room clue/trigger/anchor lists, three bulk queries (no per-room N+1)."""
    from world.clues.models import ClueTrigger, RoomClue  # noqa: PLC0415
    from world.magic.models import PortalAnchor  # noqa: PLC0415

    clues_by_room: dict[int, list[dict]] = {}
    for row in RoomClue.objects.filter(room_profile_id__in=room_ids).select_related("clue"):
        clues_by_room.setdefault(row.room_profile_id, []).append(
            {
                "id": row.pk,
                "clue_name": row.clue.name,
                "clue_slug": row.clue.slug,
                "detect_difficulty": row.detect_difficulty,
                "fixture_key": row.fixture_key,
            }
        )

    triggers_by_room: dict[int, list[dict]] = {}
    for row in ClueTrigger.objects.filter(room_profile_id__in=room_ids).select_related("clue"):
        triggers_by_room.setdefault(row.room_profile_id, []).append(
            {
                "id": row.pk,
                "clue_name": row.clue.name,
                "clue_slug": row.clue.slug,
                "fixture_key": row.fixture_key,
            }
        )

    anchors_by_room: dict[int, list[dict]] = {}
    for row in (
        PortalAnchor.objects.active().filter(room_profile_id__in=room_ids).select_related("kind")
    ):
        anchors_by_room.setdefault(row.room_profile_id, []).append(
            {
                "id": row.pk,
                "kind_name": row.kind.name,
                "name": row.name,
                "fixture_key": row.fixture_key,
            }
        )

    return clues_by_room, triggers_by_room, anchors_by_room


def _authoring_catalogs() -> dict:
    """Pick-lists the Phase B panel sections need (#3269) — one query each."""
    from evennia_extensions.models import RoomSizeTier  # noqa: PLC0415
    from world.areas.positioning.models import PositionBlueprint  # noqa: PLC0415
    from world.buildings.constants import PermitEligibility  # noqa: PLC0415
    from world.character_creation.models import Beginnings, StartingArea  # noqa: PLC0415
    from world.distinctions.models import Distinction  # noqa: PLC0415
    from world.magic.models import Resonance  # noqa: PLC0415
    from world.npc_services.models import NPCRole  # noqa: PLC0415
    from world.realms.models import Realm  # noqa: PLC0415
    from world.room_features.models import RoomFeatureKind  # noqa: PLC0415
    from world.societies.constants import FameTier  # noqa: PLC0415
    from world.societies.models import Society  # noqa: PLC0415
    from world.species.models import Species  # noqa: PLC0415
    from world.weather.models import Climate  # noqa: PLC0415

    return {
        # The ambient-condition editor's ref pick-lists (#3534).
        "species": [{"id": s.pk, "name": s.name} for s in Species.objects.all()],
        "resonances": [{"id": r.pk, "name": r.name} for r in Resonance.objects.all()],
        "distinctions": [{"id": d.pk, "name": d.name} for d in Distinction.objects.all()],
        "fame_tiers": [{"value": value, "label": label} for value, label in FameTier.choices],
        "realms": list(Realm.objects.values_list("name", flat=True)),
        "climates": list(Climate.objects.values_list("name", flat=True)),
        "societies": list(Society.objects.values_list("name", flat=True)),
        "permit_options": list(PermitEligibility.values),
        "feature_kinds": list(RoomFeatureKind.objects.values_list("name", flat=True)),
        "npc_roles": list(NPCRole.objects.values_list("name", flat=True)),
        "blueprints": list(PositionBlueprint.objects.values_list("name", flat=True)),
        "size_tiers": list(RoomSizeTier.objects.values_list("name", flat=True)),
        "starting_areas": [{"id": sa.pk, "name": sa.name} for sa in StartingArea.objects.all()],
        "beginnings": [{"id": b.pk, "name": b.name} for b in Beginnings.objects.all()],
    }


def _room_rows(profiles: list[RoomProfile]) -> list[dict]:
    """The per-room payload dicts (#3283) — single source for the area
    manager payload and the full-page room editor's one-room fetch."""
    from world.locations.services import resolve_area_art  # noqa: PLC0415

    room_ids = [p.objectdb_id for p in profiles]
    display_rows = {
        row.object_id: row
        for row in ObjectDisplayData.objects.filter(object_id__in=room_ids).select_related(
            "thumbnail"
        )
    }
    descriptions = {object_id: row.permanent_description for object_id, row in display_rows.items()}
    # Precomputed per-room thumbnail URLs (or None) so resolve_area_art doesn't re-query
    # ObjectDisplayData per room below — one bulk query above covers every room.
    thumbnail_urls = {
        object_id: (row.thumbnail.cloudinary_url if row.thumbnail_id else None)
        for object_id, row in display_rows.items()
    }
    occupant_counts = _occupant_counts(room_ids)
    stats_by_room = _stat_sidecars(profiles)
    authoring = _authoring_sidecars(profiles)
    clues_by_room, triggers_by_room, anchors_by_room = _clue_and_anchor_sidecars(room_ids)
    return [
        {
            "id": p.objectdb_id,
            "name": p.objectdb.db_key,
            "description": descriptions.get(p.objectdb_id, ""),
            "is_public": p.is_public,
            "is_social_hub": p.is_social_hub,
            "is_outdoor": p.is_outdoor,
            "enclosure": p.enclosure,
            "size_name": p.size.name if p.size_id else None,
            "grid_x": p.grid_x,
            "grid_y": p.grid_y,
            "floor": p.floor,
            "fixture_key": p.fixture_key,
            "origin": p.origin,
            "exported_at": p.exported_at,
            "published_at": p.published_at,
            "needs_prose": _needs_prose(descriptions.get(p.objectdb_id, "")),
            "art_url": resolve_area_art(p, thumbnail_url=thumbnail_urls.get(p.objectdb_id)),
            "stats": stats_by_room.get(p.objectdb_id, []),
            "area_id": p.area_id,
            "size_units": p.size.units if p.size_id else None,
            "default_blueprint": (p.default_blueprint.name if p.default_blueprint_id else None),
            "places": authoring["places"].get(p.objectdb_id, []),
            "feature": authoring["feature"].get(p.objectdb_id),
            "functionaries": authoring["functionaries"].get(p.objectdb_id, []),
            "ambient_counts": authoring["ambient_counts"].get(
                p.objectdb_id, {"lines": 0, "emits": 0}
            ),
            "travel_hub": authoring["travel_hub"].get(p.objectdb_id),
            "starting_bindings": authoring["starting_bindings"].get(p.objectdb_id, []),
            "occupant_count": occupant_counts.get(p.objectdb_id, 0),
            "clues": clues_by_room.get(p.objectdb_id, []),
            "clue_triggers": triggers_by_room.get(p.objectdb_id, []),
            "portal_anchors": anchors_by_room.get(p.objectdb_id, []),
            "desc_variants": authoring["desc_variants"].get(p.objectdb_id, []),
        }
        for p in profiles
    ]


def _area_breadcrumb(area: Area | None) -> list[dict]:
    """Ancestor chain, outermost first (#3283): World > City > Ward > ..."""
    chain: list[dict] = []
    node = area
    while node is not None:
        chain.append({"id": node.pk, "name": node.name, "level_display": node.get_level_display()})
        node = node.parent
    chain.reverse()
    return chain


def area_manager_payload(area: Area) -> dict:
    """Area + all rooms + exits for the world-builder/story-builder manager canvas.

    Shared by ``WorldBuilderViewSet.manager`` (#2449, all areas, staff-only) and
    ``StoryBuilderViewSet.manager`` (#2450, STORY areas, GM-owner-or-staff) — the
    payload shape doesn't vary by origin, only the permission gate on the caller
    does. ``rooms`` includes every RoomProfile in the area regardless of
    ``is_public`` — both callers need to see (and select) private rooms too.
    """
    profiles = list(
        RoomProfile.objects.filter(area_id=area.pk).select_related(
            "objectdb", "size", "default_blueprint"
        )
    )
    room_ids = [p.objectdb_id for p in profiles]
    rooms_data = _room_rows(profiles)

    exits = list(exits_from_rooms(set(room_ids)).select_related("db_destination"))
    destination_ids = {e.db_destination_id for e in exits if e.db_destination_id is not None}
    destination_areas = dict(
        RoomProfile.objects.filter(objectdb_id__in=destination_ids).values_list(
            "objectdb_id", "area_id"
        )
    )

    from django.db import DatabaseError as _DatabaseError  # noqa: PLC0415

    from world.magic.services.resonance_environment import (  # noqa: PLC0415
        area_resonance_readings,
    )

    try:
        resonances = [r._asdict() for r in area_resonance_readings(area)]
    except _DatabaseError:
        # areas_areaclosure is absent on the SQLite fast tier (known gap;
        # CI's PG parity is the gate) — degrade to an empty panel.
        resonances = []

    return {
        "area": area,
        "catalogs": _authoring_catalogs(),
        "rooms": rooms_data,
        "resonances": resonances,
        "breadcrumb": _area_breadcrumb(area),
        "exits": [
            {
                "id": e.pk,
                "name": e.db_key,
                "from_room_id": e.db_location_id,
                "to_room_id": e.db_destination_id,
                "to_room_name": (
                    e.db_destination.db_key if e.db_destination_id is not None else None
                ),
                "to_area_id": destination_areas.get(e.db_destination_id),
            }
            for e in exits
        ],
    }


class IsStaffOrGrantHolder(permissions.BasePermission):
    """Staff, or any account holding at least one ``AreaBuildGrant`` (#3534).

    #3477 opened the WRITE side to warranted GMs (``BuildWarrantPrerequisite``)
    but left every builder read behind ``IsAdminUser``, so a granted GM could
    dispatch actions yet never load the atlas that reaches them. Reads open to
    grant holders here; SCOPING to the grant subtree happens per-endpoint via
    ``_covered_area_ids`` (this class only answers "may they read at all").
    """

    def has_permission(self, request: Request, view: object) -> bool:
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.is_staff:
            return True
        from world.gm.models import AreaBuildGrant  # noqa: PLC0415

        return AreaBuildGrant.objects.filter(account=user).exists()


def _covered_area_ids(request: Request) -> set[int] | None:
    """The area ids the caller may read, or None for staff (unrestricted).

    A grant covers its own area plus the ``AreaClosure`` subtree beneath it —
    the read-side mirror of ``has_build_warrant``'s descent, level-blind
    (reading is "inside your territory", the ceiling only gates writes). On
    the SQLite fast tier (closure absent) this degrades to the grants' direct
    areas; CI's PG parity is the gate.
    """
    if request.user.is_staff:
        return None
    from django.db import DatabaseError  # noqa: PLC0415

    from world.gm.models import AreaBuildGrant  # noqa: PLC0415

    grant_area_ids = set(
        AreaBuildGrant.objects.filter(account=request.user).values_list("area_id", flat=True)
    )
    covered = set(grant_area_ids)
    with contextlib.suppress(DatabaseError):
        covered.update(
            AreaClosure.objects.filter(ancestor_id__in=grant_area_ids).values_list(
                "descendant_id", flat=True
            )
        )
    return covered


@extend_schema(tags=["world-builder"])
class WorldBuilderViewSet(viewsets.ReadOnlyModelViewSet):
    """Builder reads for the atlas: staff, or warranted GMs scoped to their grants (#2449/#3534)."""

    serializer_class = WorldBuilderAreaSerializer
    permission_classes = [IsStaffOrGrantHolder]
    filter_backends = [DjangoFilterBackend]
    filterset_class = AreaFilter
    pagination_class = WorldBuilderAreaPagination

    def get_queryset(self) -> QuerySet[Area]:
        queryset = Area.objects.annotate(children_count=Count("children")).order_by("name")
        covered = _covered_area_ids(self.request)
        if covered is not None:
            queryset = queryset.filter(pk__in=covered)
        return queryset

    @extend_schema(responses={200: WorldBuilderRoomHitSerializer(many=True)})
    @action(detail=False, methods=["get"], url_path="room-search")
    def room_search(self, request: Request) -> Response:
        """GET /api/world-builder/areas/room-search/?search= — cross-area room lookup (#3269).

        Matches room key or fixture_key, capped at 50 hits — the "where did I
        put the Traitor's Gate" seam for a 400-room grid, also feeding the
        link-rooms pickers.
        """
        # noqa-rationale: one free-text param on a non-queryset action endpoint;
        # a FilterSet needs a queryset-backed list view to attach to.
        term = (request.query_params.get("search") or "").strip()  # noqa: USE_FILTERSET
        if not term:
            return Response([])
        hit_qs = RoomProfile.objects.filter(
            Q(objectdb__db_key__icontains=term) | Q(fixture_key__icontains=term)
        )
        covered = _covered_area_ids(request)
        if covered is not None:
            hit_qs = hit_qs.filter(area_id__in=covered)
        hits = list(hit_qs.select_related("objectdb", "area").order_by("objectdb__db_key")[:50])
        payload = [
            {
                "id": p.objectdb_id,
                "name": p.objectdb.db_key,
                "area_id": p.area_id,
                "area_name": p.area.name if p.area_id else None,
                "floor": p.floor,
                "fixture_key": p.fixture_key,
            }
            for p in hits
        ]
        return Response(WorldBuilderRoomHitSerializer(payload, many=True).data)

    @extend_schema(responses={200: WorldBuilderRoomDetailSerializer})
    @action(detail=False, methods=["get"], url_path="room-detail")
    def room_detail(self, request: Request) -> Response:
        """GET /api/world-builder/areas/room-detail/?room_id= — selection-time detail (#3269).

        Carries what the area payload deliberately can't: per-exit
        kind/openness/aliases (Evennia's alias handler has no batch API) and
        the comfort/exposure breakdown (single-room cascade math).
        """
        # noqa-rationale: one id param on a non-queryset action endpoint.
        room_id = request.query_params.get("room_id")  # noqa: USE_FILTERSET
        profile = (
            RoomProfile.objects.filter(objectdb_id=room_id or 0).select_related("objectdb").first()
        )
        if profile is None:
            return Response({"detail": "No such room."}, status=404)
        covered = _covered_area_ids(request)
        if covered is not None and profile.area_id not in covered:
            # Outside every grant subtree reads as absent, not forbidden — the
            # same shape the scoped queryset gives the area endpoints.
            return Response({"detail": "No such room."}, status=404)
        from world.locations.services import (  # noqa: PLC0415
            comfort_summary,
            room_exposure_breakdown,
        )

        room_obj = profile.objectdb
        exits = []
        for exit_obj in exits_from_rooms({profile.objectdb_id}).select_related(
            "db_destination", "exit_profile"
        ):
            from evennia_extensions.models import ExitProfile  # noqa: PLC0415

            try:
                exit_profile = exit_obj.exit_profile
            except ExitProfile.DoesNotExist:
                exit_profile = None
            exits.append(
                {
                    "id": exit_obj.pk,
                    "name": exit_obj.db_key,
                    "to_room_id": exit_obj.db_destination_id,
                    "kind": exit_profile.exit_kind if exit_profile else "door",
                    "is_open": exit_profile.is_open if exit_profile else False,
                    "aliases": sorted(exit_obj.aliases.all()),
                }
            )
        from django.db import DatabaseError, transaction  # noqa: PLC0415

        try:
            with transaction.atomic():
                summary = comfort_summary(room_obj)
                axes = [
                    {
                        "key": row.stat_key,
                        "pressure": row.pressure,
                        "mitigation": row.mitigation,
                        "net": row.net,
                        "sheltered": row.sheltered,
                    }
                    for row in room_exposure_breakdown(room_obj)
                ]
                comfort = {
                    "level": summary.level,
                    "points": summary.points,
                    "amenity": summary.amenity,
                    "axes": axes,
                }
        except DatabaseError:
            # areas_areaclosure is absent on the SQLite fast tier (known gap;
            # CI's PG parity is the gate) — degrade to a neutral block.
            comfort = {"level": 5, "points": 0, "amenity": 0, "axes": []}
        from world.narrative.ambient_content import describe_condition  # noqa: PLC0415
        from world.narrative.models import AmbientEmit, AmbientEmoteLine  # noqa: PLC0415

        ambient_lines = [
            {
                "id": line.pk,
                "arriver_body": line.arriver_body,
                "bystander_body": line.bystander_body,
                "conditions": [
                    {
                        "id": condition.pk,
                        "condition_type": condition.condition_type,
                        "label": describe_condition(condition),
                    }
                    for condition in line.conditions.select_related(
                        "species", "resonance", "distinction", "perceiving_society"
                    )
                ],
            }
            for line in AmbientEmoteLine.objects.filter(room_profile=profile)
        ]
        ambient_emits = [
            {
                "id": emit.pk,
                "key": emit.key or "",
                "text": emit.text,
                "gate_stat_key": emit.gate_stat_key,
                "gate_min": emit.gate_min,
                "gate_max": emit.gate_max,
            }
            for emit in AmbientEmit.objects.filter(room_profile=profile)
        ]
        from world.magic.services.resonance_environment import (  # noqa: PLC0415
            get_room_dominant_affinity,
            room_resonance_readings,
        )

        try:
            resonances = [r._asdict() for r in room_resonance_readings(room_obj)]
            dominant = get_room_dominant_affinity(room_obj)
        except DatabaseError:
            # Same SQLite-tier closure degrade as the comfort block above.
            resonances = []
            dominant = None
        payload = {
            "id": profile.objectdb_id,
            "room": _room_rows([profile])[0],
            "catalogs": _authoring_catalogs(),
            "breadcrumb": _area_breadcrumb(profile.area),
            "exits": exits,
            "comfort": comfort,
            "ambient_lines": ambient_lines,
            "ambient_emits": ambient_emits,
            "resonances": resonances,
            "dominant_affinity": dominant.name if dominant else None,
        }
        return Response(WorldBuilderRoomDetailSerializer(payload).data)

    @extend_schema(responses={200: WorldBuilderGrantsSerializer})
    @action(detail=False, methods=["get"], url_path="grants")
    def grants(self, request: Request) -> Response:
        """GET /api/world-builder/areas/grants/ — the caller's own warrant shape (#3534).

        The atlas roots a GM's view at their grant, hides add-affordances past
        the ceiling, and shows the room budget as used/total — this is the
        read those honesty affordances hang on. Staff get ``is_staff: true``
        and an empty list (their warrant is implicit and world-wide).
        ``rooms_used`` counts the grant subtree's rooms — the same
        creator-agnostic total ``has_room_budget_capacity`` enforces.
        """
        from django.db import DatabaseError  # noqa: PLC0415

        from world.gm.models import AreaBuildGrant  # noqa: PLC0415

        if request.user.is_staff:
            return Response(WorldBuilderGrantsSerializer({"is_staff": True, "grants": []}).data)

        rows = []
        for grant in AreaBuildGrant.objects.filter(account=request.user).select_related("area"):
            subtree_ids = {grant.area_id}
            with contextlib.suppress(DatabaseError):
                subtree_ids.update(
                    AreaClosure.objects.filter(ancestor_id=grant.area_id).values_list(
                        "descendant_id", flat=True
                    )
                )
            rows.append(
                {
                    "area_id": grant.area_id,
                    "area_name": grant.area.name,
                    "area_level": grant.area.level,
                    "max_level": grant.max_level,
                    "room_budget": grant.room_budget,
                    "rooms_used": RoomProfile.objects.filter(area_id__in=subtree_ids).count(),
                }
            )
        return Response(WorldBuilderGrantsSerializer({"is_staff": False, "grants": rows}).data)

    @extend_schema(responses={200: WorldBuilderAreaManagerSerializer})
    @action(detail=True, methods=["get"], url_path="manager")
    def manager(self, request: Request, pk: str | None = None) -> Response:
        """GET /api/world-builder/areas/<id>/manager/ — area + all rooms + exits.

        Unlike ``BuildingManagerViewSet.retrieve``, ``rooms`` includes every
        RoomProfile in the area regardless of ``is_public`` — staff editing
        the canvas needs to see (and select) private rooms too.
        """
        payload = area_manager_payload(self.get_object())
        return Response(WorldBuilderAreaManagerSerializer(payload).data)

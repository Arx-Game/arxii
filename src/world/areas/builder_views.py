"""Staff-only world-builder read API (#2449 Task 4).

Read-only surface behind ``IsAdminUser`` (``request.user.is_staff``): the area
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

from django.db.models import Count, Q, QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from evennia.objects.models import ObjectDB
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAdminUser
from rest_framework.request import Request
from rest_framework.response import Response

from evennia_extensions.models import ObjectDisplayData, RoomProfile
from world.areas.constants import UNFINISHED_ROOM_DESC
from world.areas.filters import AreaFilter
from world.areas.grid_services import exits_from_rooms
from world.areas.models import Area
from world.areas.serializers import (
    MintBuilderCharacterRequestSerializer,
    MintBuilderCharacterResultSerializer,
    WorldBuilderAreaManagerSerializer,
    WorldBuilderAreaSerializer,
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
    from world.npc_services.models import NPCRole  # noqa: PLC0415
    from world.realms.models import Realm  # noqa: PLC0415
    from world.room_features.models import RoomFeatureKind  # noqa: PLC0415
    from world.societies.models import Society  # noqa: PLC0415
    from world.weather.models import Climate  # noqa: PLC0415

    return {
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
    room_ids = [p.objectdb_id for p in profiles]
    descriptions = {
        row.object_id: row.permanent_description
        for row in ObjectDisplayData.objects.filter(object_id__in=room_ids)
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
            "needs_prose": _needs_prose(descriptions.get(p.objectdb_id, "")),
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

    return {
        "area": area,
        "catalogs": _authoring_catalogs(),
        "rooms": rooms_data,
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


@extend_schema(tags=["world-builder"])
class WorldBuilderViewSet(viewsets.ReadOnlyModelViewSet):
    """Staff-only reads for the world-builder canvas (#2449)."""

    serializer_class = WorldBuilderAreaSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend]
    filterset_class = AreaFilter
    pagination_class = WorldBuilderAreaPagination

    def get_queryset(self) -> QuerySet[Area]:
        return Area.objects.annotate(children_count=Count("children")).order_by("name")

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
        hits = list(
            RoomProfile.objects.filter(
                Q(objectdb__db_key__icontains=term) | Q(fixture_key__icontains=term)
            )
            .select_related("objectdb", "area")
            .order_by("objectdb__db_key")[:50]
        )
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

    @extend_schema(
        request=MintBuilderCharacterRequestSerializer,
        responses={201: MintBuilderCharacterResultSerializer},
    )
    @action(detail=False, methods=["post"], url_path="mint-builder-character")
    def mint_builder_character(self, request: Request) -> Response:
        """POST /api/world-builder/areas/mint-builder-character/ (#3283).

        Mints an OOC staff character (character + sheet + persona + NPC-shelf
        roster entry + active tenure on the requesting account) so staff never
        touch the CG wizard for a working builder character.
        """
        from world.roster.services.staff_characters import (  # noqa: PLC0415
            StaffMintError,
            mint_staff_character,
        )

        body = MintBuilderCharacterRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            character = mint_staff_character(request.user, body.validated_data["name"])
        except StaffMintError as exc:
            return Response({"detail": exc.user_message}, status=400)
        return Response(
            MintBuilderCharacterResultSerializer(
                {"character_id": character.pk, "name": character.db_key}
            ).data,
            status=201,
        )

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
        from world.narrative.models import AmbientEmit, AmbientEmoteLine  # noqa: PLC0415

        ambient_lines = [
            {
                "id": line.pk,
                "arriver_body": line.arriver_body,
                "bystander_body": line.bystander_body,
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
        payload = {
            "id": profile.objectdb_id,
            "room": _room_rows([profile])[0],
            "catalogs": _authoring_catalogs(),
            "breadcrumb": _area_breadcrumb(profile.area),
            "exits": exits,
            "comfort": comfort,
            "ambient_lines": ambient_lines,
            "ambient_emits": ambient_emits,
        }
        return Response(WorldBuilderRoomDetailSerializer(payload).data)

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

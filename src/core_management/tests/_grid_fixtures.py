"""Shared AUTHORED grid object-graph builder (#2436/#2448).

``test_grid_export.py`` and ``test_grid_import.py`` both need an identical
area/room/exit/sidecar graph to round-trip through the exporter and the
importer — building it once here keeps the two suites from drifting apart.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from evennia.utils import create as evennia_create

from evennia_extensions.constants import ExitKind, RoomEnclosure
from evennia_extensions.models import ExitProfile, ObjectDisplayData, RoomSizeTier
from world.areas.constants import AreaLevel, GridOrigin
from world.areas.models import Area
from world.buildings.constants import PermitEligibility
from world.buildings.models import BuildingKind
from world.clues.constants import ClueTargetKind
from world.clues.models import Clue, ClueTrigger, RoomClue
from world.codex.models import CodexCategory, CodexEntry, CodexSubject
from world.locations.constants import LocationParentType, StatKey
from world.locations.models import LocationValueModifier, LocationValueOverride
from world.magic.models import PortalAnchor, PortalAnchorKind
from world.realms.models import Realm
from world.societies.models import Society
from world.weather.models import Climate


def build_sample_grid() -> SimpleNamespace:  # noqa: PLR0915
    """Build one AUTHORED region -> city, two rooms, an exit pair, plus sidecars.

    Mirrors the fixture ``GridExportTests.setUpTestData`` originally built inline;
    factored out so the importer's tests can build the exact same graph. Returns
    every created row as attributes on a ``SimpleNamespace`` so callers can assert
    against them directly.
    """
    realm = Realm.objects.create(name="Arx")
    climate = Climate.objects.create(name="Temperate")
    society = Society.objects.create(name="The Compact", realm=realm)
    building_kind = BuildingKind.objects.create(name="Tavern")
    size_tier = RoomSizeTier.objects.create(name="Modest", units=10)

    region = Area.objects.create(
        name="Arx Region",
        level=AreaLevel.REGION,
        slug="arx-region",
        origin=GridOrigin.AUTHORED,
    )
    city = Area.objects.create(
        name="Arx City",
        level=AreaLevel.CITY,
        parent=region,
        slug="arx-city",
        origin=GridOrigin.AUTHORED,
        realm=realm,
        climate=climate,
        dominant_society=society,
        description="The City of Arx.",
        color="|y",
        permit_eligibility=PermitEligibility.OPEN,
        permit_cost_multiplier=Decimal("1.500"),
    )
    city.allowed_building_kinds.add(building_kind)

    taproom_obj = evennia_create.create_object(
        typeclass="typeclasses.rooms.Room", key="Golden Hart Taproom", nohome=True
    )
    taproom = taproom_obj.room_profile
    taproom.area = city
    taproom.origin = GridOrigin.AUTHORED
    taproom.fixture_key = "arx-city/golden-hart-taproom"
    taproom.is_public = True
    taproom.is_social_hub = True
    taproom.is_outdoor = False
    taproom.enclosure = RoomEnclosure.WALLED
    taproom.size = size_tier
    taproom.grid_x = 0
    taproom.grid_y = 0
    taproom.floor = 0
    taproom.save()
    ObjectDisplayData.objects.create(
        object=taproom_obj,
        longname="The Golden Hart Taproom, Warm and Loud",
        permanent_description="A cozy tavern full of laughter.",
    )

    market_obj = evennia_create.create_object(
        typeclass="typeclasses.rooms.Room", key="Market Square", nohome=True
    )
    market = market_obj.room_profile
    market.area = city
    market.origin = GridOrigin.AUTHORED
    market.fixture_key = "arx-city/market-square"
    market.is_public = True
    market.enclosure = RoomEnclosure.OPEN_AIR
    market.grid_x = 1
    market.grid_y = 0
    market.save()

    # PLAYER-origin room in the same area — never exported.
    player_room_obj = evennia_create.create_object(
        typeclass="typeclasses.rooms.Room", key="Someone's Den", nohome=True
    )
    player_room = player_room_obj.room_profile
    player_room.area = city
    player_room.save()

    north_exit = evennia_create.create_object(
        typeclass="typeclasses.exits.Exit",
        key="north",
        location=taproom_obj,
        destination=market_obj,
        aliases=["n"],
        nohome=True,
    )
    ExitProfile.objects.create(objectdb=north_exit, exit_kind=ExitKind.WINDOW, is_open=True)

    south_exit = evennia_create.create_object(
        typeclass="typeclasses.exits.Exit",
        key="south",
        location=market_obj,
        destination=taproom_obj,
        aliases=["s"],
        nohome=True,
    )
    # No ExitProfile row — exercises the DOOR/closed default fallback.

    # Exit to an unauthored (PLAYER-origin) destination — must be skipped + reported
    # by the exporter, and simply absent (never recreated) on a fresh import.
    stray_exit = evennia_create.create_object(
        typeclass="typeclasses.exits.Exit",
        key="hole in the wall",
        location=taproom_obj,
        destination=player_room_obj,
        nohome=True,
    )

    override = LocationValueOverride.objects.create(
        parent_type=LocationParentType.ROOM,
        room_profile=taproom,
        stat_key=StatKey.LIGHTING,
        value=1,
    )
    authored_modifier = LocationValueModifier.objects.create(
        parent_type=LocationParentType.AREA,
        area=city,
        stat_key=StatKey.ORDER,
        value=3,
        change_per_day=0,
        source="authored:city-watch",
    )
    weather_modifier = LocationValueModifier.objects.create(
        parent_type=LocationParentType.AREA,
        area=city,
        stat_key=StatKey.COLD,
        value=20,
        change_per_day=-1,
        source="weather:cold-snap",
    )

    # CODEX target_kind requires target_codex_entry — build one minimally rather
    # than pulling in the full codex factory graph, since this fixture module
    # intentionally avoids FactoryBoy (see module docstring).
    codex_category = CodexCategory.objects.create(name="Rumors")
    codex_subject = CodexSubject.objects.create(name="The Torn Letter", category=codex_category)
    codex_entry = CodexEntry.objects.create(
        subject=codex_subject,
        name="The Torn Letter",
        lore_content="It was never sent.",
    )

    torn_letter = Clue.objects.create(
        target_kind=ClueTargetKind.CODEX,
        target_codex_entry=codex_entry,
        name="Torn Letter",
        description="A half-burned letter, edges curling.",
        slug="torn-letter",
    )

    room_clue = RoomClue.objects.create(
        room_profile=taproom,
        clue=torn_letter,
        detect_difficulty=5,
        fixture_key="arx-city/golden-hart-taproom/torn-letter",
    )
    clue_trigger = ClueTrigger.objects.create(
        room_profile=taproom,
        clue=torn_letter,
        fixture_key="arx-city/golden-hart-taproom/whisper",
    )

    mirror_kind = PortalAnchorKind.objects.create(name="Mirror")
    portal_anchor = PortalAnchor.objects.create(
        room_profile=taproom,
        kind=mirror_kind,
        name="a tall silvered mirror",
        fixture_key="arx-city/golden-hart-taproom/mirror",
    )

    return SimpleNamespace(
        realm=realm,
        climate=climate,
        society=society,
        building_kind=building_kind,
        size_tier=size_tier,
        region=region,
        city=city,
        taproom_obj=taproom_obj,
        taproom=taproom,
        market_obj=market_obj,
        market=market,
        player_room_obj=player_room_obj,
        player_room=player_room,
        north_exit=north_exit,
        south_exit=south_exit,
        stray_exit=stray_exit,
        override=override,
        authored_modifier=authored_modifier,
        weather_modifier=weather_modifier,
        torn_letter=torn_letter,
        room_clue=room_clue,
        clue_trigger=clue_trigger,
        mirror_kind=mirror_kind,
        portal_anchor=portal_anchor,
    )

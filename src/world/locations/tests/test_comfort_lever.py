"""The comfort lever (#4394): a residence reads one level lower or higher for one character."""

from django.test import TestCase
from evennia.accounts.models import AccountDB

from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.character_creation.services import finalize_character
from world.character_creation.tests.finalization_fixtures import FinalizationTestMixin
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.models import Gender
from world.distinctions.factories import DistinctionEffectFactory, DistinctionFactory
from world.distinctions.services import grant_distinction
from world.distinctions.types import DistinctionOrigin
from world.locations.comfort_effect import comfort_level_for_character
from world.locations.constants import AP_REGEN_TARGET_NAMES, LocationParentType, StatKey
from world.locations.models import LocationValueModifier
from world.locations.services import set_residence
from world.mechanics.constants import COMFORT_CATEGORY_NAME, COMFORT_TARGET_NAME
from world.mechanics.models import CharacterModifier
from world.mechanics.test_helpers import grant_lever, lever_target

DAILY = AP_REGEN_TARGET_NAMES[0]


class ComfortLeverTests(TestCase):
    def _room(self, amenity: int = 0):
        ward = AreaFactory(level=AreaLevel.WARD)
        profile = RoomProfileFactory(area=ward)
        if amenity:
            LocationValueModifier.objects.create(
                parent_type=LocationParentType.AREA,
                area=ward,
                stat_key=StatKey.AMENITY,
                value=amenity,
            )
        return profile

    def _daily_modifier_value(self, sheet) -> int | None:
        mod = CharacterModifier.objects.filter(character=sheet, target__name=DAILY).first()
        return mod.value if mod else None

    def test_without_a_lever_the_room_reads_as_itself(self) -> None:
        sheet = CharacterSheetFactory()
        room = self._room(amenity=200)  # level 6
        assert comfort_level_for_character(room.objectdb, sheet) == 6
        set_residence(character=sheet.character, room=room.objectdb)
        assert self._daily_modifier_value(sheet) == 1

    def test_a_sheltered_character_reads_the_home_one_level_lower(self) -> None:
        sheet = CharacterSheetFactory()
        grant_lever(sheet, COMFORT_CATEGORY_NAME, COMFORT_TARGET_NAME, -1)
        room = self._room(amenity=200)  # level 6, read as 5
        assert comfort_level_for_character(room.objectdb, sheet) == 5
        set_residence(character=sheet.character, room=room.objectdb)
        assert self._daily_modifier_value(sheet) is None

    def test_a_hardy_character_reads_it_higher_within_the_band(self) -> None:
        sheet = CharacterSheetFactory()
        grant_lever(sheet, COMFORT_CATEGORY_NAME, COMFORT_TARGET_NAME, 2)
        room = self._room(amenity=200)  # level 6, read as 8
        set_residence(character=sheet.character, room=room.objectdb)
        assert self._daily_modifier_value(sheet) == 3

    def test_the_band_clamps(self) -> None:
        sheet = CharacterSheetFactory()
        grant_lever(sheet, COMFORT_CATEGORY_NAME, COMFORT_TARGET_NAME, -20)
        assert comfort_level_for_character(self._room(amenity=200).objectdb, sheet) == 1


class ComfortLeverRefreshTests(ComfortLeverTests):
    """The residence modifier is re-read when a comfort lever is granted after the home."""

    def test_a_distinction_granted_in_play_refreshes_the_home(self) -> None:
        sheet = CharacterSheetFactory()
        room = self._room(amenity=200)  # level 6 -> +1
        set_residence(character=sheet.character, room=room.objectdb)
        assert self._daily_modifier_value(sheet) == 1
        sheltered = DistinctionFactory(name="Sheltered")
        DistinctionEffectFactory(
            distinction=sheltered,
            target=lever_target(COMFORT_CATEGORY_NAME, COMFORT_TARGET_NAME),
            value_per_rank=-1,
        )
        grant_distinction(sheet, sheltered, origin=DistinctionOrigin.GM_AWARD)
        assert self._daily_modifier_value(sheet) is None


class ComfortAtCreationTests(FinalizationTestMixin, TestCase):
    """A new character's residence comfort modifier is computed at finalize, lever included.

    Before #4394 it was never computed at creation at all: finalize assigns the home
    directly, so the tenancy grant's residence default saw a chosen residence and skipped
    the recompute. Runs on the parity tier (locations reads a Postgres materialized view).
    """

    def setUp(self):
        self._flush_common_caches()
        self.account = AccountDB.objects.create(username="comfort_born")
        self._setup_finalization_base(self, prefix="Cozy", height_min=700, height_max=800)
        Gender.objects.get_or_create(key="female", defaults={"display_name": "Female"})
        ward = AreaFactory(level=AreaLevel.WARD)
        self.home = RoomProfileFactory(area=ward)
        LocationValueModifier.objects.create(
            parent_type=LocationParentType.AREA, area=ward, stat_key=StatKey.AMENITY, value=200
        )
        self.area.default_starting_room = self.home
        self.area.grants_residence_tenancy = True
        self.area.save(update_fields=["default_starting_room", "grants_residence_tenancy"])

    def _modifier(self, sheet) -> int | None:
        mod = CharacterModifier.objects.filter(character=sheet, target__name=DAILY).first()
        return mod.value if mod else None

    def test_a_plain_character_gets_the_homes_modifier_at_creation(self) -> None:
        character = finalize_character(self._create_base_draft(first_name="Plainborn"))
        assert character.home == self.home.objectdb
        assert self._modifier(character.sheet_data) == 1

    def test_a_sheltered_pick_is_read_with_the_home_at_creation(self) -> None:
        sheltered = DistinctionFactory(name="Sheltered", cost_per_rank=-5, max_rank=1)
        DistinctionEffectFactory(
            distinction=sheltered,
            target=lever_target(COMFORT_CATEGORY_NAME, COMFORT_TARGET_NAME),
            value_per_rank=-1,
        )
        draft = self._create_base_draft(first_name="Shelteredborn")
        draft.draft_data["distinctions"] = [
            {
                "distinction_id": sheltered.id,
                "distinction_name": sheltered.name,
                "distinction_slug": sheltered.slug,
                "category_slug": sheltered.category.slug,
                "rank": 1,
                "cost": -5,
                "notes": "",
            }
        ]
        draft.save(update_fields=["draft_data"])
        character = finalize_character(draft)
        assert self._modifier(character.sheet_data) is None  # level 6 read as 5

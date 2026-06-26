"""Comfort → AP-regen effect (#1514): comfort_level − 5 as a flat CharacterModifier.

The modifier is recomputed only on discrete comfort-change events (home change, decoration,
style) — never at regen, where the cron reads it for free.
"""

from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.buildings.models import DecorationKind
from world.buildings.services import place_decoration
from world.character_sheets.factories import CharacterSheetFactory
from world.locations.comfort_effect import recompute_comfort_regen_modifier
from world.locations.constants import AP_REGEN_TARGET_NAMES, LocationParentType, StatKey
from world.locations.models import LocationValueModifier
from world.locations.services import set_residence
from world.mechanics.models import CharacterModifier

DAILY = AP_REGEN_TARGET_NAMES[0]


class ComfortApEffectTests(TestCase):
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

    def test_comfortable_home_grants_a_positive_regen_modifier(self) -> None:
        sheet = CharacterSheetFactory()
        room = self._room(amenity=200)  # comfort_points 200 → level 6 → delta +1
        set_residence(character=sheet.character, room=room.objectdb)
        assert self._daily_modifier_value(sheet) == 1

    def test_neutral_home_writes_no_modifier(self) -> None:
        sheet = CharacterSheetFactory()
        room = self._room()  # level 5 → delta 0 → nothing
        set_residence(character=sheet.character, room=room.objectdb)
        assert self._daily_modifier_value(sheet) is None

    def test_decorating_the_home_updates_residents_modifier(self) -> None:
        sheet = CharacterSheetFactory()
        room = self._room()  # neutral
        set_residence(character=sheet.character, room=room.objectdb)
        assert self._daily_modifier_value(sheet) is None

        # A luxury bath (amenity 2500 → comfort_points 2500 → level 8 → delta +3).
        place_decoration(room, DecorationKind.objects.create(name="Marble Bath", amenity=2500))
        assert self._daily_modifier_value(sheet) == 3  # resident recomputed via db_home lookup

    def test_recompute_writes_both_daily_and_weekly_targets(self) -> None:
        sheet = CharacterSheetFactory()
        room = self._room(amenity=200)  # level 6 → +1
        set_residence(character=sheet.character, room=room.objectdb)
        values = {
            m.target.name: m.value
            for m in CharacterModifier.objects.filter(
                character=sheet, target__name__in=AP_REGEN_TARGET_NAMES
            )
        }
        assert values == dict.fromkeys(AP_REGEN_TARGET_NAMES, 1)

    def test_no_character_sheet_is_a_safe_noop(self) -> None:
        # A bare object (no sheet_data) must not raise when recomputed.
        from evennia_extensions.factories import ObjectDBFactory

        bare = ObjectDBFactory(db_key="Crate")
        recompute_comfort_regen_modifier(bare)  # no exception

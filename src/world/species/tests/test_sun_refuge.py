"""Sun refuge search + auto-flee (#2846). SQLite tier."""

from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from evennia_extensions.models import RoomProfile
from world.character_sheets.factories import CharacterSheetFactory
from world.game_clock.constants import TimePhase
from world.species.sun_refuge import find_sun_refuge, flee_to_sun_refuge


def _make_room(key: str, *, is_outdoor: bool, is_public: bool = True):
    room = ObjectDBFactory(db_key=key, db_typeclass_path="typeclasses.rooms.Room")
    RoomProfile.objects.update_or_create(
        objectdb=room, defaults={"is_outdoor": is_outdoor, "is_public": is_public}
    )
    return room


def _make_exit(location, destination, key: str = "exit"):
    return ObjectDBFactory(
        db_key=key,
        db_typeclass_path="typeclasses.exits.Exit",
        location=location,
        destination=destination,
    )


class FindSunRefugeTest(TestCase):
    def setUp(self):
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.plaza = _make_room("Plaza", is_outdoor=True)
        self.character.db_location = self.plaza
        self.character.save(update_fields=["db_location"])

    def test_prefers_nonpublic_indoor_room_at_equal_depth(self):
        tavern = _make_room("Tavern", is_outdoor=False, is_public=True)
        cellar = _make_room("Cellar", is_outdoor=False, is_public=False)
        _make_exit(self.plaza, tavern, "north")
        _make_exit(self.plaza, cellar, "down")
        refuge = find_sun_refuge(self.character)
        self.assertEqual(refuge, cellar)

    def test_nearest_safe_room_wins_over_farther_nonpublic(self):
        tavern = _make_room("Tavern", is_outdoor=False, is_public=True)
        court = _make_room("Court", is_outdoor=True)
        cellar = _make_room("Cellar", is_outdoor=False, is_public=False)
        _make_exit(self.plaza, tavern, "north")
        _make_exit(self.plaza, court, "east")
        _make_exit(court, cellar, "down")
        with patch("world.species.sun_exposure.get_ic_phase", return_value=TimePhase.DAY):
            refuge = find_sun_refuge(self.character)
        self.assertEqual(refuge, tavern)

    def test_no_reachable_refuge_returns_none(self):
        court = _make_room("Court", is_outdoor=True)
        _make_exit(self.plaza, court, "east")
        with patch("world.species.sun_exposure.get_ic_phase", return_value=TimePhase.DAY):
            refuge = find_sun_refuge(self.character)
        self.assertIsNone(refuge)

    def test_flee_moves_character_to_refuge(self):
        cellar = _make_room("Cellar", is_outdoor=False, is_public=False)
        _make_exit(self.plaza, cellar, "down")
        moved = flee_to_sun_refuge(self.character)
        self.assertTrue(moved)
        self.assertEqual(self.character.location, cellar)

    def test_active_combat_blocks_auto_flee(self):
        cellar = _make_room("Cellar", is_outdoor=False, is_public=False)
        _make_exit(self.plaza, cellar, "down")
        with patch("world.species.sun_refuge._in_active_combat", return_value=True):
            moved = flee_to_sun_refuge(self.character)
        self.assertFalse(moved)
        self.assertEqual(self.character.location, self.plaza)


class AfkAutoFleeLoopTest(TestCase):
    """The full AFK guard loop (#2846): prompt -> two damage observations -> relocation.

    Uses a directly-created ConditionInstance (SQLite-safe; the apply path is
    covered by the postgres-tagged scenes E2E).
    """

    def test_afk_prompt_unanswered_two_damage_ticks_then_autoflee_to_nonpublic_shelter(self):
        from world.conditions.models import ConditionInstance
        from world.species.factories import ensure_sunlight_exposure_content
        from world.species.tasks import _observe_hazard_safely
        from world.vitals.factories import CharacterVitalsFactory

        sheet = CharacterSheetFactory()
        vitals = CharacterVitalsFactory(character_sheet=sheet, health=100, max_health=100)
        character = sheet.character
        plaza = _make_room("Plaza2", is_outdoor=True)
        cellar = _make_room("Cellar2", is_outdoor=False, is_public=False)
        _make_exit(plaza, cellar, "down")
        character.db_location = plaza
        character.save(update_fields=["db_location"])

        template = ensure_sunlight_exposure_content()
        instance = ConditionInstance.objects.create(
            target=character, condition=template, severity=8
        )

        _observe_hazard_safely(instance)  # prompt fires; snapshot 100
        vitals.health = 92
        vitals.save(update_fields=["health"])
        _observe_hazard_safely(instance)  # first damage instance: never flees
        self.assertEqual(character.location, plaza)
        vitals.health = 84
        vitals.save(update_fields=["health"])
        _observe_hazard_safely(instance)  # second: the guard trips
        self.assertEqual(character.location, cellar)

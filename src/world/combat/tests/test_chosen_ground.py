"""Tests for the chosen-ground stamp helper and its create_lethal_duel wiring (#2646)."""

from django.test import TestCase
from evennia import create_object

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.chosen_ground import compute_on_chosen_ground
from world.combat.duels import create_lethal_duel
from world.combat.factories import ThreatPoolFactory
from world.room_features.factories import PreparedGroundFactory


class ComputeOnChosenGroundTests(TestCase):
    """compute_on_chosen_ground(room) — see the function's own docstring for
    the exact conditions (#2646)."""

    def setUp(self) -> None:
        # Rooms must be created per test — ObjectDB is not deepcopy-safe, so
        # this class uses setUp (not setUpTestData) throughout.
        self.room = create_object("typeclasses.rooms.Room", key="ChosenGroundRoom", nohome=True)
        self.preparer_sheet = CharacterSheetFactory()

    def test_none_room_returns_false(self) -> None:
        self.assertFalse(compute_on_chosen_ground(None))

    def test_room_with_no_profile_returns_false(self) -> None:
        # A plain (non-Room-typeclass) ObjectDB never gets a RoomProfile
        # auto-created (Room.at_object_creation is the sole writer).
        plain = create_object("typeclasses.objects.Object", key="NotARoom", nohome=True)
        self.assertFalse(compute_on_chosen_ground(plain))

    def test_room_with_no_prepared_ground_returns_false(self) -> None:
        self.assertFalse(compute_on_chosen_ground(self.room))

    def test_true_when_preparer_is_present(self) -> None:
        PreparedGroundFactory(room_profile=self.room.room_profile, prepared_by=self.preparer_sheet)
        self.preparer_sheet.character.location = self.room
        self.assertTrue(compute_on_chosen_ground(self.room))

    def test_false_when_preparer_is_elsewhere(self) -> None:
        elsewhere = create_object("typeclasses.rooms.Room", key="Elsewhere", nohome=True)
        PreparedGroundFactory(room_profile=self.room.room_profile, prepared_by=self.preparer_sheet)
        self.preparer_sheet.character.location = elsewhere
        self.assertFalse(compute_on_chosen_ground(self.room))


class CreateLethalDuelStampsChosenGroundTests(TestCase):
    """create_lethal_duel stamps CombatEncounter.on_chosen_ground at creation (#2646)."""

    @classmethod
    def setUpTestData(cls):
        cls.pc_sheet = CharacterSheetFactory()
        cls.threat_pool = ThreatPoolFactory()

    def setUp(self):
        self.room = create_object(
            "typeclasses.rooms.Room", key="Lethal Chosen Ground Room", nohome=True
        )
        self.opponent_kwargs = {
            "name": "Dueling Master",
            "max_health": 200,
            "threat_pool": self.threat_pool,
            "soak_value": 50,
        }

    def test_false_with_no_prepared_ground(self) -> None:
        enc = create_lethal_duel(self.pc_sheet, self.opponent_kwargs, self.room)
        self.assertFalse(enc.on_chosen_ground)

    def test_true_when_pc_prepared_the_ground_and_is_present(self) -> None:
        PreparedGroundFactory(room_profile=self.room.room_profile, prepared_by=self.pc_sheet)
        self.pc_sheet.character.location = self.room
        enc = create_lethal_duel(self.pc_sheet, self.opponent_kwargs, self.room)
        self.assertTrue(enc.on_chosen_ground)

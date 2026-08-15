"""Tests for servant pampering + expulsion actions (#2989)."""

from unittest.mock import patch

from django.test import TestCase

from actions.registry import get_action
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory, RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.npc_services.models import ExpulsionBar


class ActionRegistryTests(TestCase):
    def test_servant_prepare_meal_registered(self):
        assert get_action("servant_prepare_meal") is not None

    def test_servant_prepare_bath_registered(self):
        assert get_action("servant_prepare_bath") is not None

    def test_expel_character_registered(self):
        assert get_action("expel_character") is not None

    def test_lift_expulsion_bar_registered(self):
        assert get_action("lift_expulsion_bar") is not None


class ServantPrepareActionTests(TestCase):
    def setUp(self) -> None:
        self.room_profile = RoomProfileFactory()
        self.room = self.room_profile.objectdb
        self.actor = CharacterFactory(db_key="Resident", location=self.room)
        CharacterSheetFactory(character=self.actor)

    def test_meal_action_fails_cleanly_with_no_servant(self):
        with (
            patch("world.locations.services.is_owner", return_value=True),
            patch("world.locations.services.is_tenant", return_value=False),
        ):
            result = get_action("servant_prepare_meal").run(self.actor)
        self.assertFalse(result.success)

    def test_bath_action_fails_cleanly_with_no_servant(self):
        with (
            patch("world.locations.services.is_owner", return_value=True),
            patch("world.locations.services.is_tenant", return_value=False),
        ):
            result = get_action("servant_prepare_bath").run(self.actor)
        self.assertFalse(result.success)

    def test_meal_action_queues_when_pamperable(self):
        with (
            patch("world.npc_services.servant_ambience.can_servant_pamper", return_value=True),
            patch("world.npc_services.servant_ambience.prepare_meal", return_value=True),
        ):
            result = get_action("servant_prepare_meal").run(self.actor)
        self.assertTrue(result.success)


class ExpelCharacterActionTests(TestCase):
    def setUp(self) -> None:
        self.room = ObjectDBFactory(db_key="salon", db_typeclass_path="typeclasses.rooms.Room")
        self.outside = ObjectDBFactory(db_key="alley", db_typeclass_path="typeclasses.rooms.Room")
        ObjectDBFactory(
            db_key="door",
            db_typeclass_path="typeclasses.exits.Exit",
            location=self.room,
            destination=self.outside,
        )
        self.actor = CharacterFactory(db_key="Owner", location=self.room)
        self.owner_sheet = CharacterSheetFactory(character=self.actor)
        self.target = CharacterFactory(db_key="Rowdy", location=self.room)
        CharacterSheetFactory(character=self.target)

    def _run_expel(self):
        with patch("world.locations.services.is_owner", return_value=True):
            return get_action("expel_character").run(self.actor, target=self.target)

    def test_owner_can_expel_and_bar(self):
        result = self._run_expel()
        self.assertTrue(result.success)
        self.target.refresh_from_db()
        self.assertEqual(self.target.location, self.outside)
        self.assertTrue(
            ExpulsionBar.objects.filter(
                barred_sheet=self.target.character_sheet, lifted_at__isnull=True
            ).exists()
        )

    def test_expulsion_has_no_check_no_roll(self):
        """The expel action never touches the check-roll pipeline — unresistable."""
        with patch("world.checks.services.perform_check_with_modifiers") as mock_check:
            self._run_expel()
            mock_check.assert_not_called()

    def test_non_owner_cannot_expel(self):
        with patch("world.locations.services.is_owner", return_value=False):
            result = get_action("expel_character").run(self.actor, target=self.target)
        self.assertFalse(result.success)
        self.target.refresh_from_db()
        self.assertEqual(self.target.location, self.room)

    def test_cannot_expel_self(self):
        with patch("world.locations.services.is_owner", return_value=True):
            result = get_action("expel_character").run(self.actor, target=self.actor)
        self.assertFalse(result.success)

    def test_lift_expulsion_bar_reopens_entry(self):
        self._run_expel()
        with patch("world.locations.services.is_owner", return_value=True):
            result = get_action("lift_expulsion_bar").run(self.actor, name="Rowdy")
        self.assertTrue(result.success)
        self.assertFalse(
            ExpulsionBar.objects.filter(
                barred_sheet=self.target.character_sheet, lifted_at__isnull=True
            ).exists()
        )

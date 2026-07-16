"""Tests for guard detection service (#2178)."""

from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory, RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.locations.constants import HolderType, LocationParentType
from world.locations.models import LocationOwnership
from world.npc_services.factories import FunctionaryFactory
from world.npc_services.guard_services import (
    check_guard_detection,
)
from world.npc_services.models import (
    AssignmentRole,
    NPCAssignment,
    NPCSourceType,
)
from world.scenes.factories import PersonaFactory
from world.traits.factories import CheckOutcomeFactory


def _make_stealth_check_type():
    """Create the Stealth CheckType that guard_detection looks up by name."""
    return CheckTypeFactory(name="Stealth")


class CheckGuardDetectionTests(TestCase):
    def setUp(self) -> None:
        self.room_profile = RoomProfileFactory()
        self.room = self.room_profile.objectdb
        self.stealth_check = _make_stealth_check_type()
        self.failure_outcome = CheckOutcomeFactory(name="Stealth-Fail", success_level=0)
        self.success_outcome = CheckOutcomeFactory(name="Stealth-Success", success_level=1)

    def _create_guard(self):
        """Create an active GUARD assignment in the test room."""
        func = FunctionaryFactory(room=self.room_profile)
        persona = PersonaFactory()
        return NPCAssignment.objects.create(
            source_type=NPCSourceType.FUNCTIONARY,
            functionary=func,
            room=self.room_profile,
            assignment_role=AssignmentRole.GUARD,
            assigned_by=persona,
        )

    def _create_character_in_room(self):
        """Create a character sheet + persona in the test room."""
        char = CharacterFactory(db_key="intruder")
        CharacterSheetFactory(character=char)
        char.location = self.room
        char.save()
        return char

    def test_no_guard_short_circuits(self):
        """Room with no guard assignments → no detection, no error."""
        char = self._create_character_in_room()
        # Should not raise even though the character has no standing.
        check_guard_detection(char, self.room)

    def test_no_profile_short_circuits(self):
        """Room with no RoomProfile → no detection."""

        char = CharacterFactory(db_key="wanderer")
        bare_room = ObjectDBFactory(db_key="bare-room")
        check_guard_detection(char, bare_room)

    def test_sheetless_character_skipped(self):
        """A character with no sheet → no detection."""
        self._create_guard()
        char = CharacterFactory(db_key="npc-wanderer")
        char.location = self.room
        char.save()
        # Should not raise — sheet_data raises ObjectDoesNotExist.
        check_guard_detection(char, self.room)

    def test_authorized_entrant_skipped(self):
        """Owner entering their own guarded room → no detection roll."""
        self._create_guard()
        char = self._create_character_in_room()
        owner_persona = PersonaFactory()
        # Make the owner own the room's RoomProfile.
        LocationOwnership.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=self.room_profile,
            holder_type=HolderType.PERSONA,
            holder_persona=owner_persona,
        )
        # Patch the character's active persona to return the owner persona.
        with patch(
            "world.scenes.services.active_persona_for_sheet",
            return_value=owner_persona,
        ):
            with patch("world.checks.services.perform_check") as mock_check:
                check_guard_detection(char, self.room)
                mock_check.assert_not_called()

    def test_detection_success_emits_echo(self):
        """Intruder fails stealth → room echo emitted."""
        self._create_guard()
        char = self._create_character_in_room()
        with (
            force_check_outcome(self.failure_outcome),
            patch.object(self.room, "msg_contents") as mock_echo,
            patch.object(char, "msg") as mock_char_msg,
        ):
            check_guard_detection(char, self.room)
            mock_echo.assert_called_once()
            mock_char_msg.assert_called_once()

    def test_detection_failure_no_echo(self):
        """Intruder succeeds stealth → no echo, no alert."""
        self._create_guard()
        char = self._create_character_in_room()
        with (
            force_check_outcome(self.success_outcome),
            patch.object(self.room, "msg_contents") as mock_echo,
            patch.object(char, "msg") as mock_char_msg,
        ):
            check_guard_detection(char, self.room)
            mock_echo.assert_not_called()
            mock_char_msg.assert_not_called()

    def test_missing_stealth_checktype_raises(self):
        """If the Stealth CheckType is missing, DoesNotExist raises loudly."""
        from world.checks.models import CheckType

        # Delete the Stealth CheckType so the lookup fails.
        CheckType.objects.filter(name="Stealth").delete()
        self._create_guard()
        char = self._create_character_in_room()

        # Give the character a persona so we get past the persona check.
        with (
            patch(
                "world.scenes.services.active_persona_for_sheet",
                return_value=PersonaFactory(),
            ),
            patch(
                "world.locations.services.is_owner",
                return_value=False,
            ),
            patch(
                "world.locations.services.is_tenant",
                return_value=False,
            ),
        ):
            with self.assertRaises(CheckType.DoesNotExist):
                check_guard_detection(char, self.room)

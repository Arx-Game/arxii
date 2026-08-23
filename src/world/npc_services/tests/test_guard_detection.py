"""Tests for guard detection service (#2178; sneak-stance branch #3288)."""

from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory, RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.conditions.factories import ConditionCategoryFactory, ConditionTemplateFactory
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
from world.stealth import services as stealth_services
from world.traits.factories import CheckOutcomeFactory


def _make_stealth_check_type():
    """Create the Stealth CheckType that guard_detection looks up by name."""
    return CheckTypeFactory(name="Stealth")


def make_concealed_template():
    """The Concealed condition primitive the sneak stance rides (#1225/#3288)."""
    category = ConditionCategoryFactory(name="Concealed", conceals_from_perception=True)
    return ConditionTemplateFactory(name="Concealed", category=category)


def make_sneaking(char):
    """Put ``char`` into the sneak stance without rolling."""
    assert stealth_services.start_sneaking(char)
    return char


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

    def test_loud_entrant_detected_without_roll(self):
        """#3288: a non-sneaking unauthorized entrant is noticed automatically."""
        self._create_guard()
        char = self._create_character_in_room()
        with (
            patch("world.checks.services.perform_check") as mock_check,
            patch.object(self.room, "msg_contents") as mock_echo,
            patch.object(char, "msg") as mock_char_msg,
        ):
            check_guard_detection(char, self.room)
            mock_check.assert_not_called()
            mock_echo.assert_called_once()
            mock_char_msg.assert_called_once()

    def test_sneaking_entrant_detected_strips_stance(self):
        """#3288: sneaking intruder fails the contest → alert + stance stripped."""
        make_concealed_template()
        self._create_guard()
        char = make_sneaking(self._create_character_in_room())
        with (
            force_check_outcome(self.failure_outcome),
            patch.object(self.room, "msg_contents") as mock_echo,
            patch.object(char, "msg") as mock_char_msg,
        ):
            check_guard_detection(char, self.room)
            mock_echo.assert_called_once()
            mock_char_msg.assert_called_once()
        self.assertFalse(stealth_services.is_sneaking(char))

    def test_sneaking_entrant_slips_past(self):
        """#3288: sneaking intruder wins the contest → no echo, stance retained."""
        make_concealed_template()
        self._create_guard()
        char = make_sneaking(self._create_character_in_room())
        with (
            force_check_outcome(self.success_outcome),
            patch.object(self.room, "msg_contents") as mock_echo,
            patch.object(char, "msg") as mock_char_msg,
        ):
            check_guard_detection(char, self.room)
            mock_echo.assert_not_called()
            mock_char_msg.assert_not_called()
        self.assertTrue(stealth_services.is_sneaking(char))

    def test_missing_stealth_checktype_treated_as_loud(self):
        """#3288: an unseeded Stealth CheckType degrades to a loud (detected) entry."""
        from world.checks.models import CheckType

        make_concealed_template()
        CheckType.objects.filter(name="Stealth").delete()
        self._create_guard()
        char = make_sneaking(self._create_character_in_room())

        with (
            patch(
                "world.scenes.services.active_persona_for_sheet",
                return_value=PersonaFactory(),
            ),
            patch("world.locations.services.is_owner", return_value=False),
            patch("world.locations.services.is_tenant", return_value=False),
            patch.object(self.room, "msg_contents") as mock_echo,
        ):
            check_guard_detection(char, self.room)
            mock_echo.assert_called_once()
        self.assertFalse(stealth_services.is_sneaking(char))

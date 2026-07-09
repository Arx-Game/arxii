"""Tests for SetTheStageAction — GM-trust-gated blueprint instantiation (#2117).

Covers:
- (a) Non-staff, non-GM actor → check_availability().available is False.
- (b) Staff actor with a blueprint → execute creates live Positions in the room.
- (c) Missing blueprint_id → ActionResult(success=False).
- (d) _set_the_stage_actions: staff character with default_blueprint surfaces one PlayerAction.
- (e) _set_the_stage_actions: non-staff character surfaces nothing.
- (f) STARTING-tier GM (no staff flag) → check_availability().available is True (#2117).
"""

from __future__ import annotations

import django.test

from actions.constants import ActionBackend
from actions.definitions.positioning import SetTheStageAction
from evennia_extensions.factories import AccountFactory, CharacterFactory, RoomProfileFactory
from world.areas.positioning.factories import PositionBlueprintFactory
from world.areas.positioning.models import Position
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory


def _make_staff_character(key: str, room) -> object:
    """Return an Evennia character connected to a staff account."""
    from evennia import create_object

    char = create_object(
        "typeclasses.characters.Character",
        key=key,
        location=room,
        nohome=True,
    )
    account = AccountFactory(username=f"account_{key}", is_staff=True)
    account.save()
    char.db_account = account
    char.save()
    return char


def _make_player_character(key: str, room) -> object:
    """Return an Evennia character connected to a non-staff account."""
    from evennia import create_object

    char = create_object(
        "typeclasses.characters.Character",
        key=key,
        location=room,
        nohome=True,
    )
    account = AccountFactory(username=f"account_{key}", is_staff=False)
    account.save()
    char.db_account = account
    char.save()
    return char


def _make_gm_character(key: str, room, level: str) -> object:
    """Return a Character with a live roster tenure + GMProfile at ``level``.

    ``MinimumGMLevelPrerequisite`` reads ``active_account``, which requires a
    real ``RosterTenure`` -- not just ``char.db_account``.
    """
    char = CharacterFactory(db_key=key, location=room)
    CharacterSheetFactory(character=char)
    entry = RosterEntryFactory(character_sheet__character=char)
    tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
    GMProfileFactory(account=tenure.player_data.account, level=level)
    return char


class TestSetTheStageActionAvailability(django.test.TestCase):
    """check_availability gates on MinimumGMLevelPrerequisite(GMLevel.STARTING) (#2117)."""

    def setUp(self) -> None:
        from evennia import create_object

        self.room = create_object("typeclasses.rooms.Room", key="StageRoom", nohome=True)
        self.staff_char = _make_staff_character("StaffActor", self.room)
        self.player_char = _make_player_character("PlayerActor", self.room)

    def test_non_staff_actor_is_unavailable(self) -> None:
        """Non-staff, non-GM actor → available is False."""
        action = SetTheStageAction()
        availability = action.check_availability(self.player_char, target=None)
        self.assertFalse(
            availability.available,
            "Non-staff, non-GM should not be able to SetTheStage",
        )

    def test_staff_actor_is_available(self) -> None:
        """Staff actor → available is True."""
        action = SetTheStageAction()
        availability = action.check_availability(self.staff_char, target=None)
        self.assertTrue(
            availability.available,
            f"Staff should be able to SetTheStage; reasons: {availability.reasons}",
        )

    def test_starting_gm_actor_is_available(self) -> None:
        """STARTING-tier GM (no staff flag) → available is True (#2117)."""
        gm_char = _make_gm_character("StartingGM", self.room, GMLevel.STARTING)
        action = SetTheStageAction()
        availability = action.check_availability(gm_char, target=None)
        self.assertTrue(
            availability.available,
            f"STARTING-tier GM should be able to SetTheStage; reasons: {availability.reasons}",
        )


class TestSetTheStageActionExecute(django.test.TestCase):
    """execute() behaviour: blueprint instantiation, error cases."""

    def setUp(self) -> None:
        from evennia import create_object

        self.room = create_object("typeclasses.rooms.Room", key="BlueprintRoom", nohome=True)
        self.staff_char = _make_staff_character("StaffExecutor", self.room)
        # Blueprint with one node so instantiation actually creates a Position.
        self.blueprint = PositionBlueprintFactory(name="TestLayout")
        from world.areas.positioning.services import add_blueprint_position

        add_blueprint_position(self.blueprint, "Center", description="The centre")

    def test_execute_creates_positions_in_room(self) -> None:
        """Staff actor with a valid blueprint_id → Positions created in the actor's room."""
        action = SetTheStageAction()
        result = action.execute(self.staff_char, blueprint_id=self.blueprint.pk)
        self.assertTrue(result.success, f"Execute failed: {result.message}")
        created = list(Position.objects.filter(room=self.room))
        self.assertGreater(len(created), 0, "Expected at least one Position in the room")

    def test_missing_blueprint_id_returns_failure(self) -> None:
        """execute() with no blueprint_id → ActionResult(success=False)."""
        action = SetTheStageAction()
        result = action.execute(self.staff_char)
        self.assertFalse(result.success)
        self.assertIn("blueprint", result.message.lower())

    def test_nonexistent_blueprint_id_returns_failure(self) -> None:
        """execute() with a nonexistent blueprint pk → ActionResult(success=False)."""
        action = SetTheStageAction()
        result = action.execute(self.staff_char, blueprint_id=999999)
        self.assertFalse(result.success)
        self.assertIn("blueprint", result.message.lower())

    def test_replace_false_raises_when_already_staged(self) -> None:
        """execute() on an already-staged room with replace=False → ActionResult(success=False)."""
        action = SetTheStageAction()
        # Stage once.
        first = action.execute(self.staff_char, blueprint_id=self.blueprint.pk)
        self.assertTrue(first.success)
        # Try again without replace=True.
        second = action.execute(self.staff_char, blueprint_id=self.blueprint.pk)
        self.assertFalse(second.success)


class TestSetTheStageActionsPlayerInterface(django.test.TestCase):
    """_set_the_stage_actions: staff with default_blueprint get a quick-action."""

    def setUp(self) -> None:
        from evennia import create_object

        self.room = create_object("typeclasses.rooms.Room", key="InterfaceRoom", nohome=True)
        self.blueprint = PositionBlueprintFactory(name="QuickLayout")

        # Assign default_blueprint to the room's profile.
        # Room typeclass inherits from ObjectDB; pass the room object itself.
        profile = RoomProfileFactory(objectdb=self.room)
        profile.default_blueprint = self.blueprint
        profile.save()

        self.staff_char = _make_staff_character("StaffInterface", self.room)
        self.player_char = _make_player_character("PlayerInterface", self.room)

    def test_staff_character_gets_set_the_stage_action(self) -> None:
        """Staff character in a room with default_blueprint sees a set_the_stage PlayerAction."""
        from actions.player_interface import get_player_actions

        actions = get_player_actions(self.staff_char)
        set_stage_actions = [
            a
            for a in actions
            if a.backend == ActionBackend.REGISTRY and a.ref.registry_key == "set_the_stage"
        ]
        self.assertEqual(
            len(set_stage_actions),
            1,
            f"Expected exactly 1 set_the_stage action, got: {set_stage_actions}",
        )
        self.assertEqual(
            set_stage_actions[0].ref.blueprint_id,
            self.blueprint.pk,
        )

    def test_non_staff_character_gets_no_set_the_stage_action(self) -> None:
        """Non-staff character does NOT see set_the_stage even if room has a default_blueprint."""
        from actions.player_interface import get_player_actions

        actions = get_player_actions(self.player_char)
        set_stage_actions = [
            a
            for a in actions
            if a.backend == ActionBackend.REGISTRY and a.ref.registry_key == "set_the_stage"
        ]
        self.assertEqual(
            len(set_stage_actions),
            0,
            "Non-staff should not see set_the_stage actions",
        )

    def test_starting_gm_character_gets_set_the_stage_action(self) -> None:
        """STARTING-tier GM (no staff flag) sees the quick-action too (#2117).

        ``_set_the_stage_actions`` used to hardcode an ``is_staff_observer``
        surfacing gate separate from the Action's own prerequisite -- fixing
        only ``SetTheStageAction.get_prerequisites()`` would have left a
        trust-tier GM unable to even discover the one-click quick action.
        """
        from actions.player_interface import get_player_actions

        gm_char = _make_gm_character("StartingGMInterface", self.room, GMLevel.STARTING)
        actions = get_player_actions(gm_char)
        set_stage_actions = [
            a
            for a in actions
            if a.backend == ActionBackend.REGISTRY and a.ref.registry_key == "set_the_stage"
        ]
        self.assertEqual(
            len(set_stage_actions),
            1,
            f"Expected exactly 1 set_the_stage action, got: {set_stage_actions}",
        )

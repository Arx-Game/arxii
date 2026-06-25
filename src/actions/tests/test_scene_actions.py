"""Tests for StartSceneAction and FinishSceneAction."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from actions.definitions.scenes import FinishSceneAction, StartSceneAction
from evennia_extensions.factories import CharacterFactory, GMCharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import SceneFactory, SceneOwnerParticipationFactory
from world.scenes.models import Scene, SceneParticipation

_FINISH_PATCH_BASE = "world.scenes.scene_admin_services"


def _create_pc_with_account(db_key: str, location=None):
    """Create a PC with an active roster tenure so active_account is non-None.

    Returns (character, account).
    """
    kwargs: dict = {"db_key": db_key}
    if location is not None:
        kwargs["location"] = location
    char = CharacterFactory(**kwargs)
    CharacterSheetFactory(character=char)
    entry = RosterEntryFactory(character_sheet__character=char)
    tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
    account = tenure.player_data.account
    return char, account


def _make_room(label: str = "Room"):
    return ObjectDBFactory(
        db_key=label,
        db_typeclass_path="typeclasses.rooms.Room",
    )


class StartSceneActionTests(TestCase):
    """StartSceneAction creates a scene and grants co-ownership to present PCs."""

    def test_creates_scene_when_none_active(self):
        """StartSceneAction creates an active scene in the room."""
        room = _make_room("Room1")
        actor, _account = _create_pc_with_account("Alice", location=room)

        result = StartSceneAction().execute(actor)

        assert result.success is True
        assert Scene.objects.filter(location=room, is_active=True).exists()

    def test_actor_is_co_owner_after_start(self):
        """The actor's account becomes a co-owner of the new scene."""
        room = _make_room("Room2")
        actor, account = _create_pc_with_account("Bob", location=room)

        StartSceneAction().execute(actor)

        scene = Scene.objects.get(location=room, is_active=True)
        assert SceneParticipation.objects.filter(
            scene=scene, account=account, is_owner=True
        ).exists()

    def test_second_present_pc_also_becomes_co_owner(self):
        """A second PC present in the room is also granted co-ownership."""
        room = _make_room("Room3")
        actor, _account_a = _create_pc_with_account("Carol", location=room)
        _other, account_b = _create_pc_with_account("Dave", location=room)

        StartSceneAction().execute(actor)

        scene = Scene.objects.get(location=room, is_active=True)
        assert SceneParticipation.objects.filter(
            scene=scene, account=account_b, is_owner=True
        ).exists()

    def test_start_when_scene_exists_does_not_flip_ownership(self):
        """If a scene is already active, calling start_scene does NOT change ownership."""
        room = _make_room("Room4")
        actor, actor_account = _create_pc_with_account("Eve", location=room)

        # Create a scene where Eve is NOT an owner.
        scene = SceneFactory(location=room, is_active=True)
        SceneParticipation.objects.create(scene=scene, account=actor_account, is_owner=False)

        result = StartSceneAction().execute(actor)

        # Success message indicates scene already exists.
        assert result.success is True
        assert "already active" in result.message

        # Ownership must NOT have been flipped.
        participation = SceneParticipation.objects.get(scene=scene, account=actor_account)
        assert participation.is_owner is False

    def test_start_when_scene_exists_adds_actor_as_participant(self):
        """With an existing scene, the actor is added as a non-owner participant."""
        room = _make_room("Room5")
        actor, actor_account = _create_pc_with_account("Frank", location=room)
        scene = SceneFactory(location=room, is_active=True)

        StartSceneAction().execute(actor)

        assert SceneParticipation.objects.filter(scene=scene, account=actor_account).exists()

    def test_returns_failure_when_not_in_room(self):
        """Actor not in a room gets a failure result."""
        actor = CharacterFactory(db_key="NoRoom")
        actor.location = None

        result = StartSceneAction().execute(actor)

        assert result.success is False
        assert "not in a room" in result.message.lower()


class FinishSceneActionTests(TestCase):
    """FinishSceneAction is gated by co-ownership; delegates to finish_scene_full."""

    def test_non_owner_is_denied(self):
        """A PC who is not a scene owner gets success=False."""
        room = _make_room("Room6")
        actor, _account = _create_pc_with_account("Grace", location=room)
        scene = SceneFactory(location=room, is_active=True)
        # Actor has no SceneParticipation row → not an owner.

        result = FinishSceneAction().execute(actor)

        assert result.success is False
        assert scene.is_active  # scene still active

    def test_scene_remains_active_when_denied(self):
        """The scene is not deactivated when the actor lacks permission."""
        room = _make_room("Room7")
        actor, _account = _create_pc_with_account("Henry", location=room)
        scene = SceneFactory(location=room, is_active=True)

        FinishSceneAction().execute(actor)

        scene.refresh_from_db()
        assert scene.is_active is True

    def test_owner_can_finish_scene(self):
        """A scene owner successfully finishes the active scene."""
        room = _make_room("Room8")
        actor, account = _create_pc_with_account("Iris", location=room)
        scene = SceneFactory(location=room, is_active=True)
        SceneOwnerParticipationFactory(scene=scene, account=account)

        with (
            patch(f"{_FINISH_PATCH_BASE}.on_scene_finished"),
            patch(f"{_FINISH_PATCH_BASE}.process_deferred_fatigue_resets"),
            patch(f"{_FINISH_PATCH_BASE}.broadcast_scene_message"),
        ):
            result = FinishSceneAction().execute(actor)

        assert result.success is True
        scene.refresh_from_db()
        assert scene.is_active is False

    def test_gm_character_can_finish_scene(self):
        """A GM character (is_story_runner=True) can finish any scene."""
        room = _make_room("Room9")
        gm = GMCharacterFactory(db_key="GMFinish", location=room)
        scene = SceneFactory(location=room, is_active=True)

        with (
            patch(f"{_FINISH_PATCH_BASE}.on_scene_finished"),
            patch(f"{_FINISH_PATCH_BASE}.process_deferred_fatigue_resets"),
            patch(f"{_FINISH_PATCH_BASE}.broadcast_scene_message"),
        ):
            result = FinishSceneAction().execute(gm)

        assert result.success is True
        scene.refresh_from_db()
        assert scene.is_active is False

    def test_no_active_scene_returns_failure(self):
        """FinishSceneAction fails when no active scene exists in the room."""
        room = _make_room("Room10")
        actor, _account = _create_pc_with_account("Jake", location=room)
        # No scene created.

        result = FinishSceneAction().execute(actor)

        assert result.success is False
        assert "no active scene" in result.message.lower()

    def test_returns_failure_when_not_in_room(self):
        """Actor not in a room gets a failure result."""
        actor = CharacterFactory(db_key="NoRoomFinish")
        actor.location = None

        result = FinishSceneAction().execute(actor)

        assert result.success is False
        assert "not in a room" in result.message.lower()

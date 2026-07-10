"""Tests for StartSceneAction and FinishSceneAction."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from actions.definitions.scenes import FinishSceneAction, GrantSceneGMAction, StartSceneAction
from evennia_extensions.factories import CharacterFactory, GMCharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.factories import GMProfileFactory
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

    def test_start_scene_not_blocked_by_battle_only_scene(self):
        """A room holding ONLY a staged battle's backing Scene gets a NEW RP scene (#2010).

        ``_active_scene_for_room`` must exclude battle-backed scenes the same way the
        SceneViewSet collision check does -- otherwise StartSceneAction reports
        "already active" and enrolls actors into the battle scene instead of
        creating the room's real RP scene.
        """
        from world.battles.staging import stage_battle

        room = _make_room("Warfront")
        actor, _account = _create_pc_with_account("Frida", location=room)
        battle = stage_battle(name="Siege of the Hall", location=room)

        result = StartSceneAction().execute(actor)

        assert result.success is True
        assert "already active" not in result.message
        new_scene = Scene.objects.get(location=room, is_active=True, battle__isnull=True)
        assert new_scene.pk != battle.scene_id

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


class GrantSceneGMActionTests(TestCase):
    """GrantSceneGMAction: fallback ``scene gm <name>`` grant (#2113)."""

    def test_owner_grants_gm_to_present_approved_gm(self):
        """A scene co-owner may grant is_gm to a present account holding a GMProfile."""
        room = _make_room("GrantRoom1")
        owner, owner_account = _create_pc_with_account("GrantOwner", location=room)
        target, target_account = _create_pc_with_account("GrantTarget", location=room)
        GMProfileFactory(account=target_account)
        scene = SceneFactory(location=room, is_active=True)
        SceneOwnerParticipationFactory(scene=scene, account=owner_account)

        result = GrantSceneGMAction().execute(owner, target_name=target.db_key)

        assert result.success is True
        assert SceneParticipation.objects.filter(
            scene=scene, account=target_account, is_gm=True
        ).exists()

    def test_non_admin_actor_is_denied(self):
        """A present PC who does not administer the scene cannot grant GM status."""
        room = _make_room("GrantRoom2")
        non_admin, _non_admin_account = _create_pc_with_account("NonAdmin", location=room)
        target, target_account = _create_pc_with_account("GrantTarget2", location=room)
        GMProfileFactory(account=target_account)
        scene = SceneFactory(location=room, is_active=True)
        # non_admin has no SceneParticipation row -> not an owner, not GM, not staff.

        result = GrantSceneGMAction().execute(non_admin, target_name=target.db_key)

        assert result.success is False
        assert not SceneParticipation.objects.filter(
            scene=scene, account=target_account, is_gm=True
        ).exists()

    def test_target_without_gm_profile_is_refused(self):
        """A present target account with no GMProfile is refused."""
        room = _make_room("GrantRoom3")
        owner, owner_account = _create_pc_with_account("GrantOwner3", location=room)
        target, target_account = _create_pc_with_account("GrantTarget3", location=room)
        # No GMProfile created for target_account.
        scene = SceneFactory(location=room, is_active=True)
        SceneOwnerParticipationFactory(scene=scene, account=owner_account)

        result = GrantSceneGMAction().execute(owner, target_name=target.db_key)

        assert result.success is False
        assert "not an approved gm" in result.message.lower()
        assert not SceneParticipation.objects.filter(
            scene=scene, account=target_account, is_gm=True
        ).exists()

    def test_staff_character_can_grant(self):
        """A staff/story-runner character (GMCharacter) can grant regardless of ownership."""
        room = _make_room("GrantRoom4")
        gm_runner = GMCharacterFactory(db_key="GrantGMRunner", location=room)
        target, target_account = _create_pc_with_account("GrantTarget4", location=room)
        GMProfileFactory(account=target_account)
        scene = SceneFactory(location=room, is_active=True)

        result = GrantSceneGMAction().execute(gm_runner, target_name=target.db_key)

        assert result.success is True
        assert SceneParticipation.objects.filter(
            scene=scene, account=target_account, is_gm=True
        ).exists()

    def test_unknown_target_name_fails(self):
        """A target name that matches no present character fails with a clear message."""
        room = _make_room("GrantRoom5")
        owner, owner_account = _create_pc_with_account("GrantOwner5", location=room)
        scene = SceneFactory(location=room, is_active=True)
        SceneOwnerParticipationFactory(scene=scene, account=owner_account)

        result = GrantSceneGMAction().execute(owner, target_name="NoSuchCharacter")

        assert result.success is False

    def test_no_active_scene_returns_failure(self):
        """GrantSceneGMAction fails when no active scene exists in the room."""
        room = _make_room("GrantRoom6")
        owner, _owner_account = _create_pc_with_account("GrantOwner6", location=room)

        result = GrantSceneGMAction().execute(owner, target_name="Anyone")

        assert result.success is False
        assert "no active scene" in result.message.lower()

    def test_returns_failure_when_not_in_room(self):
        """Actor not in a room gets a failure result."""
        actor = CharacterFactory(db_key="NoRoomGrant")
        actor.location = None

        result = GrantSceneGMAction().execute(actor, target_name="Anyone")

        assert result.success is False
        assert "not in a room" in result.message.lower()

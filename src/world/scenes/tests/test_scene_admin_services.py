"""Tests for world.scenes.scene_admin_services."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import (
    CharacterFactory,
    GMCharacterFactory,
    ObjectDBFactory,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import (
    SceneFactory,
    SceneOwnerParticipationFactory,
    SceneParticipationFactory,
)
from world.scenes.models import SceneParticipation
from world.scenes.scene_admin_services import (
    actor_can_administer_scene,
    add_present_as_co_owners,
    finish_scene_full,
    resolve_actor_account,
)


def _create_pc_with_account(db_key: str, location=None):
    """Create a PC character with a live roster tenure (non-None active_account).

    Returns (character, account).
    """
    kwargs = {"db_key": db_key}
    if location is not None:
        kwargs["location"] = location
    char = CharacterFactory(**kwargs)
    CharacterSheetFactory(character=char)
    entry = RosterEntryFactory(character_sheet__character=char)
    tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
    account = tenure.player_data.account
    return char, account


class ResolveActorAccountTests(TestCase):
    def test_returns_account_for_pc_with_tenure(self):
        char, account = _create_pc_with_account("Alice")
        result = resolve_actor_account(char)
        assert result is not None
        assert result.pk == account.pk

    def test_returns_none_for_gm_character(self):
        gm = GMCharacterFactory(db_key="GM_Test")
        result = resolve_actor_account(gm)
        assert result is None

    def test_returns_none_for_character_without_sheet(self):
        char = CharacterFactory(db_key="NPC_Test")
        result = resolve_actor_account(char)
        assert result is None


class ActorCanAdministerSceneTests(TestCase):
    def setUp(self):
        self.scene = SceneFactory()

    def test_owner_can_administer(self):
        char, account = _create_pc_with_account("Alice")
        SceneOwnerParticipationFactory(scene=self.scene, account=account)
        assert actor_can_administer_scene(char, self.scene) is True

    def test_non_owner_pc_cannot_administer(self):
        char, account = _create_pc_with_account("Bob")
        # Participant, not owner
        SceneParticipationFactory(scene=self.scene, account=account)
        assert actor_can_administer_scene(char, self.scene) is False

    def test_pc_not_in_scene_cannot_administer(self):
        char, _ = _create_pc_with_account("Carol")
        assert actor_can_administer_scene(char, self.scene) is False

    def test_staff_account_can_administer(self):
        char, account = _create_pc_with_account("Dave")
        account.is_staff = True
        account.save()
        assert actor_can_administer_scene(char, self.scene) is True

    def test_story_runner_character_can_administer(self):
        gm = GMCharacterFactory(db_key="GMRunner")
        # GM has no account — authorized by is_story_runner alone
        assert actor_can_administer_scene(gm, self.scene) is True


class AddPresentAsCoOwnersTests(TestCase):
    def test_marks_all_present_pcs_as_owners(self):
        room = ObjectDBFactory(
            db_key="TestRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        _char_a, account_a = _create_pc_with_account("Alice", location=room)
        _char_b, account_b = _create_pc_with_account("Bob", location=room)
        scene = SceneFactory()

        add_present_as_co_owners(scene, room)

        assert SceneParticipation.objects.filter(
            scene=scene, account=account_a, is_owner=True
        ).exists()
        assert SceneParticipation.objects.filter(
            scene=scene, account=account_b, is_owner=True
        ).exists()

    def test_skips_object_without_account(self):
        room = ObjectDBFactory(
            db_key="TestRoom2",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        # NPC: character without a roster tenure (no active_account)
        npc = CharacterFactory(db_key="NPC_Skip", location=room)
        CharacterSheetFactory(character=npc)
        # No RosterTenure -> active_account is None
        scene = SceneFactory()

        add_present_as_co_owners(scene, room)

        assert SceneParticipation.objects.filter(scene=scene).count() == 0

    def test_skips_object_without_sheet(self):
        room = ObjectDBFactory(
            db_key="TestRoom3",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        # Bare object with no sheet (e.g. a prop)
        ObjectDBFactory(
            db_key="Prop",
            db_typeclass_path="typeclasses.objects.Object",
            location=room,
        )
        scene = SceneFactory()

        add_present_as_co_owners(scene, room)

        assert SceneParticipation.objects.filter(scene=scene).count() == 0

    def test_upgrades_existing_participation_to_owner(self):
        room = ObjectDBFactory(
            db_key="TestRoom4",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        _char, account = _create_pc_with_account("Eve", location=room)
        scene = SceneFactory()
        # Pre-create participation without owner flag
        SceneParticipationFactory(scene=scene, account=account, is_owner=False)

        add_present_as_co_owners(scene, room)

        part = SceneParticipation.objects.get(scene=scene, account=account)
        assert part.is_owner is True

    def test_mixed_room_only_pcs_with_accounts_become_owners(self):
        room = ObjectDBFactory(
            db_key="TestRoom5",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        _char_pc, account_pc = _create_pc_with_account("Frank", location=room)
        # NPC: sheet but no tenure
        npc = CharacterFactory(db_key="NPC_Mixed", location=room)
        CharacterSheetFactory(character=npc)
        GMCharacterFactory(db_key="GM_Mixed", location=room)
        scene = SceneFactory()

        add_present_as_co_owners(scene, room)

        # Only the real PC should be marked owner
        assert SceneParticipation.objects.filter(scene=scene).count() == 1
        assert SceneParticipation.objects.filter(
            scene=scene, account=account_pc, is_owner=True
        ).exists()


class FinishSceneFullTests(TestCase):
    _PATCH_BASE = "world.scenes.scene_admin_services"

    def test_sets_is_active_false_and_date_finished(self):
        scene = SceneFactory(is_active=True)
        assert scene.is_finished is False

        with (
            patch(f"{self._PATCH_BASE}.on_scene_finished"),
            patch(f"{self._PATCH_BASE}.process_deferred_fatigue_resets"),
            patch(f"{self._PATCH_BASE}.broadcast_scene_message"),
        ):
            finish_scene_full(scene)

        scene.refresh_from_db()
        assert scene.is_active is False
        assert scene.date_finished is not None
        assert scene.is_finished is True

    def test_calls_on_scene_finished(self):
        scene = SceneFactory(is_active=True)

        with (
            patch(f"{self._PATCH_BASE}.on_scene_finished") as mock_on_finished,
            patch(f"{self._PATCH_BASE}.process_deferred_fatigue_resets"),
            patch(f"{self._PATCH_BASE}.broadcast_scene_message"),
        ):
            finish_scene_full(scene)

        mock_on_finished.assert_called_once_with(scene)

    def test_idempotent_when_already_finished(self):
        """Calling finish_scene_full on an already-finished scene is a no-op."""
        scene = SceneFactory(is_active=True)
        # First finish
        with (
            patch(f"{self._PATCH_BASE}.on_scene_finished"),
            patch(f"{self._PATCH_BASE}.process_deferred_fatigue_resets"),
            patch(f"{self._PATCH_BASE}.broadcast_scene_message"),
        ):
            finish_scene_full(scene)

        scene.refresh_from_db()
        first_date_finished = scene.date_finished

        # Second call should be a no-op
        with (
            patch(f"{self._PATCH_BASE}.on_scene_finished") as mock_on_finished,
            patch(f"{self._PATCH_BASE}.process_deferred_fatigue_resets") as mock_fatigue,
            patch(f"{self._PATCH_BASE}.broadcast_scene_message") as mock_broadcast,
        ):
            finish_scene_full(scene)

        mock_on_finished.assert_not_called()
        mock_fatigue.assert_not_called()
        mock_broadcast.assert_not_called()
        scene.refresh_from_db()
        assert scene.date_finished == first_date_finished

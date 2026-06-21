"""Integration tests for frictionless / implicit scene start + auto-close (#1309).

Covers the lifecycle bookends wired around the existing
``ensure_scene_for_location`` primitive:

- ``start_or_join_scene``: a player acting in a room with no active scene
  auto-creates one (becoming owner) with privacy derived from room publicness;
  a second actor in the same room joins the SAME scene and is NOT owner.
- ``maybe_finish_empty_scene``: when the last participating character leaves the
  room the scene auto-finishes; with another occupant still present it stays open.
"""

from django.test import TestCase

from evennia_extensions.factories import AccountFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import (
    PlayerDataFactory,
    RosterEntryFactory,
    RosterTenureFactory,
)
from world.scenes.constants import ScenePrivacyMode
from world.scenes.interaction_services import (
    ensure_scene_participation,
    maybe_finish_empty_scene,
)
from world.scenes.models import SceneParticipation
from world.scenes.place_services import start_or_join_scene


def _make_room(*, key: str, public: bool = True):
    room = ObjectDBFactory(db_key=key, db_typeclass_path="typeclasses.rooms.Room")
    if not public:
        room.room_profile.is_public = False
        room.room_profile.save()
    return room


def _player_in_room(room, *, account):
    """A character placed in ``room`` whose roster tenure points at ``account``."""
    sheet = CharacterSheetFactory()
    entry = RosterEntryFactory(character_sheet=sheet)
    RosterTenureFactory(
        player_data=PlayerDataFactory(account=account),
        roster_entry=entry,
    )
    sheet.character.db_location = room
    sheet.character.save(update_fields=["db_location"])
    return sheet.character


class ImplicitSceneStartTest(TestCase):
    """A player acting with no active scene auto-creates-or-joins one."""

    def test_first_actor_creates_and_owns_public_scene(self) -> None:
        room = _make_room(key="PublicTavern", public=True)
        account = AccountFactory()

        scene = start_or_join_scene(room, owner_account=account)

        assert scene.pk is not None
        assert scene.is_active is True
        assert scene.location == room
        assert scene.privacy_mode == ScenePrivacyMode.PUBLIC
        assert SceneParticipation.objects.filter(
            scene=scene, account=account, is_owner=True
        ).exists()

    def test_unlisted_room_creates_private_scene(self) -> None:
        room = _make_room(key="HiddenCellar", public=False)
        account = AccountFactory()

        scene = start_or_join_scene(room, owner_account=account)

        assert scene.privacy_mode == ScenePrivacyMode.PRIVATE

    def test_second_actor_joins_same_scene_and_is_not_owner(self) -> None:
        room = _make_room(key="SharedTavern", public=True)
        owner_account = AccountFactory()
        joiner_account = AccountFactory()

        first = start_or_join_scene(room, owner_account=owner_account)
        second = start_or_join_scene(room, owner_account=joiner_account)

        # Same scene (idempotent get-or-create).
        assert first.pk == second.pk
        # The joiner did NOT override the original owner and is not an owner.
        assert not SceneParticipation.objects.filter(
            scene=first, account=joiner_account, is_owner=True
        ).exists()
        assert SceneParticipation.objects.filter(scene=first, is_owner=True).count() == 1


class AutoCloseEmptySceneTest(TestCase):
    """The room emptying auto-finishes its active scene."""

    def test_scene_finishes_when_last_participant_leaves(self) -> None:
        room = _make_room(key="EmptyingRoom", public=True)
        account = AccountFactory()
        character = _player_in_room(room, account=account)

        scene = start_or_join_scene(room, owner_account=account)
        ensure_scene_participation(scene, character)

        # The only participant is leaving — exclude them from the presence check.
        finished = maybe_finish_empty_scene(room, leaving=character)

        assert finished is not None
        assert finished.pk == scene.pk
        scene.refresh_from_db()
        assert scene.is_active is False
        assert scene.date_finished is not None

    def test_scene_stays_open_with_another_occupant_present(self) -> None:
        room = _make_room(key="StillBusyRoom", public=True)
        leaver_account = AccountFactory()
        stayer_account = AccountFactory()
        leaver = _player_in_room(room, account=leaver_account)
        stayer = _player_in_room(room, account=stayer_account)

        scene = start_or_join_scene(room, owner_account=leaver_account)
        ensure_scene_participation(scene, leaver)
        ensure_scene_participation(scene, stayer)

        finished = maybe_finish_empty_scene(room, leaving=leaver)

        assert finished is None
        scene.refresh_from_db()
        assert scene.is_active is True
        assert scene.date_finished is None

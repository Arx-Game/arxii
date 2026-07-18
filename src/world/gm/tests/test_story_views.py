"""Tests for the GM story-builder read API (#2450).

``StoryBuilderViewSet`` mirrors ``WorldBuilderViewSet`` (world.areas.builder_views)
but scoped to a GM's own STORY-origin areas (staff: all STORY areas) — reads
only, gated by ``IsGMOrStaff`` instead of ``IsAdminUser``.
"""

from django.test import tag
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from evennia_extensions.factories import AccountFactory, ObjectDBFactory
from evennia_extensions.models import RoomProfile
from world.areas.constants import AreaLevel, GridOrigin
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.factories import GMProfileFactory, StoryAreaFactory, StoryRoomGrantFactory
from world.instances.constants import InstanceStatus
from world.instances.factories import InstancedRoomFactory


def _room_in(area, *, name="A Story Room", **profile_kwargs):
    room = ObjectDBFactory(db_key=name, db_typeclass_path="typeclasses.rooms.Room")
    RoomProfile.objects.update_or_create(
        objectdb=room,
        defaults={"area": area, **profile_kwargs},
    )
    return room


@tag("postgres")  # Area.save() refreshes the areas_areaclosure materialized view
class StoryBuilderApiBase(APITestCase):
    def setUp(self) -> None:
        self.staff_account = AccountFactory(username="story_staff", is_staff=True)
        self.player_account = AccountFactory(username="story_player", is_staff=False)

        self.gm_account = AccountFactory(username="story_gm")
        self.gm = GMProfileFactory(account=self.gm_account)
        self.other_gm_account = AccountFactory(username="story_other_gm")
        self.other_gm = GMProfileFactory(account=self.other_gm_account)

        self.story_area = StoryAreaFactory(gm=self.gm).area
        self.other_story_area = StoryAreaFactory(gm=self.other_gm).area

        self.client = APIClient()

    def _get(self, url, account, **params):
        if account is not None:
            self.client.force_authenticate(user=account)
        return self.client.get(url, params)


class StoryAreaListTests(StoryBuilderApiBase):
    def _url(self) -> str:
        return reverse("gm:gm-story-area-list")

    def test_anonymous_rejected(self) -> None:
        response = self.client.get(self._url())
        self.assertIn(
            response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
        )

    def test_plain_player_forbidden(self) -> None:
        response = self._get(self._url(), self.player_account)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_gm_sees_only_own_story_areas(self) -> None:
        response = self._get(self._url(), self.gm_account)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {row["id"] for row in response.data["results"]}
        self.assertIn(self.story_area.pk, ids)
        self.assertNotIn(self.other_story_area.pk, ids)

    def test_staff_sees_all_story_areas(self) -> None:
        response = self._get(self._url(), self.staff_account)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {row["id"] for row in response.data["results"]}
        self.assertIn(self.story_area.pk, ids)
        self.assertIn(self.other_story_area.pk, ids)

    def test_filter_by_parent(self) -> None:
        """AreaFilter is wired (django_notes ViewSet standard) and composes with
        the GM-ownership scoping in get_queryset — not just registered inertly."""
        parent_story = StoryAreaFactory(gm=self.gm, area__level=AreaLevel.WARD).area
        child = StoryAreaFactory(
            gm=self.gm, area__level=AreaLevel.BUILDING, area__parent=parent_story
        ).area
        response = self._get(self._url(), self.gm_account, parent=parent_story.pk)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {row["id"] for row in response.data["results"]}
        self.assertEqual(ids, {child.pk})


class StoryAreaManagerTests(StoryBuilderApiBase):
    def _url(self, area=None) -> str:
        return reverse("gm:gm-story-area-manager", args=[(area or self.story_area).pk])

    def test_plain_player_forbidden(self) -> None:
        response = self._get(self._url(), self.player_account)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_gm_cannot_see_another_gms_story_area_manager(self) -> None:
        response = self._get(self._url(self.other_story_area), self.gm_account)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_manager_payload_room_has_null_fixture_key(self) -> None:
        room = _room_in(self.story_area, is_public=False)
        response = self._get(self._url(), self.gm_account)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rooms_by_id = {row["id"]: row for row in response.data["rooms"]}
        self.assertIn(room.pk, rooms_by_id)
        self.assertIsNone(rooms_by_id[room.pk]["fixture_key"])
        self.assertEqual(rooms_by_id[room.pk]["origin"], GridOrigin.PLAYER)

    def test_staff_can_view_any_story_area_manager(self) -> None:
        response = self._get(self._url(self.other_story_area), self.staff_account)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["area"]["id"], self.other_story_area.pk)

    def test_manager_payload_room_has_no_grants(self) -> None:
        room = _room_in(self.story_area)
        response = self._get(self._url(), self.gm_account)
        rooms_by_id = {row["id"]: row for row in response.data["rooms"]}
        self.assertEqual(rooms_by_id[room.pk]["grants"], [])

    def test_manager_payload_room_includes_grants_for_granted_room(self) -> None:
        room = _room_in(self.story_area)
        profile = RoomProfile.objects.get(objectdb=room)
        sheet = CharacterSheetFactory(character=ObjectDBFactory(db_key="Grantee"))
        StoryRoomGrantFactory(room=profile, character=sheet, granted_by=self.gm)

        response = self._get(self._url(), self.gm_account)
        rooms_by_id = {row["id"]: row for row in response.data["rooms"]}
        self.assertEqual(rooms_by_id[room.pk]["grants"], ["Grantee"])

    def test_manager_payload_does_not_leak_grants_from_other_areas(self) -> None:
        """A grant on a totally different room never bleeds into an unrelated room's list."""
        room = _room_in(self.story_area)
        other_room = _room_in(self.other_story_area, name="Other Room")
        other_profile = RoomProfile.objects.get(objectdb=other_room)
        sheet = CharacterSheetFactory(character=ObjectDBFactory(db_key="Elsewhere"))
        StoryRoomGrantFactory(room=other_profile, character=sheet, granted_by=self.other_gm)

        response = self._get(self._url(), self.gm_account)
        rooms_by_id = {row["id"]: row for row in response.data["rooms"]}
        self.assertEqual(rooms_by_id[room.pk]["grants"], [])


class StoryInstancesTests(StoryBuilderApiBase):
    def _url(self) -> str:
        return reverse("gm:gm-story-area-instances")

    def test_plain_player_forbidden(self) -> None:
        response = self._get(self._url(), self.player_account)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_gm_sees_only_own_active_instances(self) -> None:
        mine = InstancedRoomFactory(gm_owner=self.gm, status=InstanceStatus.ACTIVE)
        others = InstancedRoomFactory(gm_owner=self.other_gm, status=InstanceStatus.ACTIVE)
        completed_mine = InstancedRoomFactory(gm_owner=self.gm, status=InstanceStatus.COMPLETED)

        response = self._get(self._url(), self.gm_account)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {row["id"] for row in response.data}
        self.assertIn(mine.pk, ids)
        self.assertNotIn(others.pk, ids)
        self.assertNotIn(completed_mine.pk, ids)

    def test_staff_sees_all_gm_owned_active_instances_only(self) -> None:
        mine = InstancedRoomFactory(gm_owner=self.gm, status=InstanceStatus.ACTIVE)
        others = InstancedRoomFactory(gm_owner=self.other_gm, status=InstanceStatus.ACTIVE)
        # A plain player-owned instance (no GM) must never surface on the GM dashboard.
        non_gm = InstancedRoomFactory(gm_owner=None, status=InstanceStatus.ACTIVE)

        response = self._get(self._url(), self.staff_account)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {row["id"] for row in response.data}
        self.assertIn(mine.pk, ids)
        self.assertIn(others.pk, ids)
        self.assertNotIn(non_gm.pk, ids)

    def test_instance_row_shape(self) -> None:
        room = ObjectDBFactory(db_key="Goblin Cave", db_typeclass_path="typeclasses.rooms.Room")
        instance = InstancedRoomFactory(gm_owner=self.gm, status=InstanceStatus.ACTIVE, room=room)
        response = self._get(self._url(), self.gm_account)
        row = next(r for r in response.data if r["id"] == instance.pk)
        self.assertEqual(row["room_id"], instance.room_id)
        self.assertEqual(row["name"], "Goblin Cave")
        self.assertEqual(row["status"], InstanceStatus.ACTIVE)
        self.assertEqual(row["grants"], [])

    def test_instance_row_includes_grants_for_granted_room(self) -> None:
        room = ObjectDBFactory(db_key="Goblin Cave", db_typeclass_path="typeclasses.rooms.Room")
        profile, _created = RoomProfile.objects.get_or_create(objectdb=room)
        instance = InstancedRoomFactory(gm_owner=self.gm, status=InstanceStatus.ACTIVE, room=room)
        sheet = CharacterSheetFactory(character=ObjectDBFactory(db_key="Grantee"))
        StoryRoomGrantFactory(room=profile, character=sheet, granted_by=self.gm)

        response = self._get(self._url(), self.gm_account)
        row = next(r for r in response.data if r["id"] == instance.pk)
        self.assertEqual(row["grants"], ["Grantee"])

    def test_instance_row_does_not_leak_grants_from_other_rooms(self) -> None:
        """A grant on another GM's instance room never bleeds into an unrelated row's list."""
        room = ObjectDBFactory(db_key="Goblin Cave", db_typeclass_path="typeclasses.rooms.Room")
        instance = InstancedRoomFactory(gm_owner=self.gm, status=InstanceStatus.ACTIVE, room=room)

        other_room = ObjectDBFactory(
            db_key="Other Cave", db_typeclass_path="typeclasses.rooms.Room"
        )
        other_profile, _created = RoomProfile.objects.get_or_create(objectdb=other_room)
        InstancedRoomFactory(gm_owner=self.other_gm, status=InstanceStatus.ACTIVE, room=other_room)
        sheet = CharacterSheetFactory(character=ObjectDBFactory(db_key="Elsewhere"))
        StoryRoomGrantFactory(room=other_profile, character=sheet, granted_by=self.other_gm)

        response = self._get(self._url(), self.gm_account)
        row = next(r for r in response.data if r["id"] == instance.pk)
        self.assertEqual(row["grants"], [])

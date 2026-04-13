from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from core_management.test_utils import suppress_permission_errors
from evennia_extensions.factories import AccountFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterIdentityFactory
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import ScenePrivacyMode
from world.scenes.factories import (
    InteractionFactory,
    PersonaFactory,
    SceneFactory,
    SceneParticipationFactory,
)
from world.scenes.models import Persona, Scene


def _create_owned_persona(account, **persona_kwargs):
    """Create a Persona whose character is owned by the given account via RosterTenure."""
    identity = CharacterIdentityFactory()
    player_data, _ = PlayerDataFactory._meta.model.objects.get_or_create(account=account)
    roster_entry = RosterEntryFactory(character=identity.character)
    RosterTenureFactory(player_data=player_data, roster_entry=roster_entry)
    if persona_kwargs:
        return PersonaFactory(
            character_sheet=identity.character.sheet_data,
            **persona_kwargs,
        )
    return identity.active_persona


class SceneViewSetTestCase(APITestCase):
    def setUp(self):
        self.account = AccountFactory()
        self.client.force_authenticate(user=self.account)

    def test_scene_list(self):
        """Test scene list endpoint returns scenes with pagination"""
        SceneFactory.create_batch(5, participants=[self.account])

        url = reverse("scene-list")
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert "results" in response.data
        assert len(response.data["results"]) == 5

        # Check structure matches SceneListSerializer
        scene_data = response.data["results"][0]
        assert "id" in scene_data
        assert "name" in scene_data
        assert "description" in scene_data
        assert "date_started" in scene_data
        assert "location" in scene_data
        assert "participants" in scene_data

    @suppress_permission_errors
    def test_scene_creation_unique_name_and_location(self):
        """Starting scenes enforces unique names and one active per room."""
        room = ObjectDBFactory(
            db_key="hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        url = reverse("scene-list")
        data = {"location_id": room.id}
        response = self.client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        name1 = response.data["name"]
        # Starting another scene in same room while active should fail
        response = self.client.post(url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        # Finish first scene and start again to test name increment
        scene = Scene.objects.get(name=name1)
        scene.finish_scene()
        response = self.client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        name2 = response.data["name"]
        assert name1 != name2
        assert name2.endswith(" (2)")

    def test_scene_list_filtering(self):
        """Test scene filtering by is_active and privacy_mode"""
        # Clear any existing scenes from previous tests
        Scene.objects.all().delete()

        active_scene = SceneFactory(is_active=True)
        inactive_scene = SceneFactory(is_active=False)
        private_scene = SceneFactory(
            is_active=True,
            privacy_mode=ScenePrivacyMode.PRIVATE,
        )

        # Filter by active scenes
        url = reverse("scene-list")
        response = self.client.get(url, {"is_active": "true"})
        assert response.status_code == status.HTTP_200_OK
        active_ids = [scene["id"] for scene in response.data["results"]]
        assert active_scene.id in active_ids
        assert inactive_scene.id not in active_ids

        # Filter by public scenes
        response = self.client.get(
            url,
            {"privacy_mode": ScenePrivacyMode.PUBLIC},
        )
        assert response.status_code == status.HTTP_200_OK
        public_ids = [scene["id"] for scene in response.data["results"]]
        assert active_scene.id in public_ids
        assert inactive_scene.id in public_ids
        assert private_scene.id not in public_ids

    def test_scene_status_filters_and_visibility(self):
        """Scenes can be filtered by status and hide private scenes."""
        Scene.objects.all().delete()
        active = SceneFactory(is_active=True)
        completed = SceneFactory(is_active=True)
        completed.finish_scene()
        upcoming = SceneFactory(is_active=False)
        upcoming.date_started = timezone.now() + timezone.timedelta(days=1)
        upcoming.save()
        private_scene = SceneFactory(
            is_active=True,
            privacy_mode=ScenePrivacyMode.PRIVATE,
        )

        url = reverse("scene-list")
        response = self.client.get(url)
        ids = [s["id"] for s in response.data["results"]]
        assert active.id in ids
        assert completed.id in ids
        assert upcoming.id in ids
        assert private_scene.id not in ids

        response = self.client.get(url, {"status": "active"})
        ids = [s["id"] for s in response.data["results"]]
        assert ids == [active.id]

        response = self.client.get(url, {"status": "completed"})
        ids = [s["id"] for s in response.data["results"]]
        assert ids == [completed.id]

        response = self.client.get(url, {"status": "upcoming"})
        ids = [s["id"] for s in response.data["results"]]
        assert ids == [upcoming.id]

    def test_scene_list_search_by_gm_and_player(self):
        """Scenes can be filtered by GM or player."""
        Scene.objects.all().delete()
        gm_account = AccountFactory()
        player_account = AccountFactory()
        scene1 = SceneFactory()
        SceneParticipationFactory(scene=scene1, account=gm_account, is_gm=True)
        SceneParticipationFactory(scene=scene1, account=player_account)
        scene2 = SceneFactory()
        SceneParticipationFactory(scene=scene2, account=player_account)

        url = reverse("scene-list")
        response = self.client.get(url, {"gm": gm_account.id})
        ids = [s["id"] for s in response.data["results"]]
        assert ids == [scene1.id]

        response = self.client.get(url, {"player": player_account.id})
        ids = [s["id"] for s in response.data["results"]]
        self.assertCountEqual(ids, [scene1.id, scene2.id])

    def test_scene_detail(self):
        """Test scene detail endpoint returns full scene data"""
        scene = SceneFactory(participants=[self.account])
        persona = PersonaFactory()
        InteractionFactory(scene=scene, persona=persona)

        url = reverse("scene-detail", kwargs={"pk": scene.pk})
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK

        # Check structure matches SceneDetailSerializer
        data = response.data
        assert data["id"] == scene.id
        assert data["name"] == scene.name
        assert "personas" in data
        assert "participants" in data

    def test_scenes_spotlight(self):
        """Test spotlight endpoint returns in_progress and recent scenes"""
        # Create active scenes
        active_scenes = SceneFactory.create_batch(3, is_active=True)

        # Create recently finished scenes
        finished_scenes = SceneFactory.create_batch(2, is_active=False)
        for scene in finished_scenes:
            scene.finish_scene()

        # Create old finished scene (should not appear)
        old_scene = SceneFactory(is_active=False)
        old_scene.finish_scene()
        # Manually set old date
        from django.utils import timezone

        old_scene.date_finished = timezone.now() - timezone.timedelta(days=10)
        old_scene.save()

        url = reverse("scene-spotlight")
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert "in_progress" in response.data
        assert "recent" in response.data

        # Check in_progress scenes
        in_progress_ids = [s["id"] for s in response.data["in_progress"]]
        for scene in active_scenes:
            assert scene.id in in_progress_ids

        # Check recent scenes
        recent_ids = [s["id"] for s in response.data["recent"]]
        for scene in finished_scenes:
            assert scene.id in recent_ids

        # Old scene should not appear
        assert old_scene.id not in recent_ids

    def test_scene_finish(self):
        """Test finishing an active scene"""
        scene = SceneFactory(is_active=True)
        SceneParticipationFactory(scene=scene, account=self.account, is_owner=True)

        url = reverse("scene-finish", kwargs={"pk": scene.pk})
        response = self.client.post(url)

        assert response.status_code == status.HTTP_200_OK

        # Refresh from database
        scene.refresh_from_db()
        assert not scene.is_active
        assert scene.date_finished is not None


class PersonaViewSetTestCase(APITestCase):
    def setUp(self):
        self.account = AccountFactory()
        self.client.force_authenticate(user=self.account)

    def test_persona_list(self):
        """Test persona list with pagination"""
        Persona.objects.all().delete()
        identity = CharacterIdentityFactory()
        player_data, _ = PlayerDataFactory._meta.model.objects.get_or_create(
            account=self.account,
        )
        roster_entry = RosterEntryFactory(character=identity.character)
        RosterTenureFactory(player_data=player_data, roster_entry=roster_entry)
        PersonaFactory.create_batch(
            3,
            character_sheet=identity.character.sheet_data,
        )

        url = reverse("persona-list")
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert "results" in response.data
        # 3 established personas + 1 primary persona from CharacterIdentityFactory
        assert len(response.data["results"]) == 4

    def test_persona_filtering_by_scene(self):
        """Test filtering personas by scene via interactions"""
        # Clear any existing data
        Persona.objects.all().delete()
        Scene.objects.all().delete()

        scene1 = SceneFactory(participants=[self.account])
        scene2 = SceneFactory(participants=[self.account])
        persona1 = _create_owned_persona(self.account)
        persona2 = _create_owned_persona(self.account)

        # Create interactions to link personas to scenes (scene filter uses interactions)
        InteractionFactory(scene=scene1, persona=persona1)
        InteractionFactory(scene=scene2, persona=persona2)

        url = reverse("persona-list")
        response = self.client.get(url, {"scene": scene1.id})

        assert response.status_code == status.HTTP_200_OK
        persona_ids = [p["id"] for p in response.data["results"]]
        assert persona1.id in persona_ids
        assert persona2.id not in persona_ids

    def test_persona_detail(self):
        """Test persona detail endpoint"""
        persona = _create_owned_persona(self.account)

        url = reverse("persona-detail", kwargs={"pk": persona.pk})
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == persona.id
        assert response.data["name"] == persona.name

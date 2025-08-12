import json

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core_management.test_utils import suppress_permission_errors
from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.stories.factories import (
    ChapterFactory,
    EpisodeFactory,
    PlayerTrustFactory,
    StoryFactory,
    StoryFeedbackFactory,
    StoryParticipationFactory,
)
from world.stories.models import StoryParticipation
from world.stories.types import ParticipationLevel, StoryPrivacy, TrustLevel


class StoryViewActionsTestCase(APITestCase):
    """Test story view actions and their associated permissions"""

    @classmethod
    def setUpTestData(cls):
        # Create accounts for different permission levels
        cls.owner_account = AccountFactory()
        cls.gm_account = AccountFactory()
        cls.participant_account = AccountFactory()
        cls.non_participant_account = AccountFactory()
        cls.staff_account = AccountFactory(is_staff=True)

        # Create characters for story participation
        cls.owner_character = CharacterFactory()
        cls.owner_character.db_account = cls.owner_account
        cls.owner_character.save()

        cls.participant_character = CharacterFactory()
        cls.participant_character.db_account = cls.participant_account
        cls.participant_character.save()

        # Create stories for different test scenarios
        cls.public_story = StoryFactory(owners=[cls.owner_account])
        cls.private_story = StoryFactory(
            privacy=StoryPrivacy.PRIVATE, owners=[cls.owner_account]
        )

        # Create story participations
        StoryParticipationFactory(
            story=cls.public_story,
            character=cls.participant_character,
            participation_level=ParticipationLevel.OPTIONAL,
        )

    @suppress_permission_errors
    def test_story_create_denied_for_regular_users(self):
        """Test regular users cannot create stories"""
        self.client.force_authenticate(user=self.non_participant_account)
        url = reverse("story-list")
        data = {
            "title": "New Test Story",
            "description": "A test story description",
            "privacy": StoryPrivacy.PUBLIC,
        }
        response = self.client.post(
            url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @suppress_permission_errors
    def test_story_update_denied_for_owners(self):
        """Test story owners cannot update stories (permissions restrictive)"""
        self.client.force_authenticate(user=self.owner_account)
        url = reverse("story-detail", kwargs={"pk": self.public_story.pk})
        data = {"title": "Updated Story Title", "description": "Updated description"}
        response = self.client.patch(
            url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @suppress_permission_errors
    def test_story_update_non_owner_denied(self):
        """Test non-owner cannot update stories"""
        self.client.force_authenticate(user=self.participant_account)
        url = reverse("story-detail", kwargs={"pk": self.public_story.pk})
        data = {"title": "Unauthorized Update"}
        response = self.client.patch(
            url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_story_update_staff_permission(self):
        """Test staff can update any story"""
        self.client.force_authenticate(user=self.staff_account)
        url = reverse("story-detail", kwargs={"pk": self.public_story.pk})
        data = {"title": "Staff Updated Title"}
        response = self.client.patch(
            url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @suppress_permission_errors
    def test_story_delete_denied_for_owners(self):
        """Test story owners cannot delete stories (permissions restrictive)"""
        deletable_story = StoryFactory(owners=[self.owner_account])

        self.client.force_authenticate(user=self.owner_account)
        url = reverse("story-detail", kwargs={"pk": deletable_story.pk})
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @suppress_permission_errors
    def test_story_delete_non_owner_denied(self):
        """Test non-owner cannot delete stories"""
        self.client.force_authenticate(user=self.participant_account)
        url = reverse("story-detail", kwargs={"pk": self.public_story.pk})
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_apply_to_participate_action(self):
        """Test applying to participate in a story"""
        non_participant_character = CharacterFactory()
        non_participant_character.db_account = self.non_participant_account
        non_participant_character.save()

        self.client.force_authenticate(user=self.non_participant_account)
        url = reverse("story-apply-to-participate", kwargs={"pk": self.public_story.pk})
        data = {
            "character_id": non_participant_character.id,
            "participation_level": ParticipationLevel.OPTIONAL,
        }
        response = self.client.post(
            url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            StoryParticipation.objects.filter(
                story=self.public_story, character=non_participant_character
            ).exists()
        )

    def test_apply_to_participate_already_participating(self):
        """Test cannot apply twice to same story"""
        self.client.force_authenticate(user=self.participant_account)
        url = reverse("story-apply-to-participate", kwargs={"pk": self.public_story.pk})
        data = {
            "character_id": self.participant_character.id,
            "participation_level": ParticipationLevel.OPTIONAL,
        }
        response = self.client.post(
            url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Already participating", response.data["error"])

    def test_apply_to_participate_missing_character(self):
        """Test application fails without character_id"""
        self.client.force_authenticate(user=self.non_participant_account)
        url = reverse("story-apply-to-participate", kwargs={"pk": self.public_story.pk})
        data = {"participation_level": ParticipationLevel.OPTIONAL}
        response = self.client.post(
            url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("character_id is required", response.data["error"])

    def test_participants_action(self):
        """Test getting story participants"""
        self.client.force_authenticate(user=self.owner_account)
        url = reverse("story-participants", kwargs={"pk": self.public_story.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Just verify we get some participants data
        self.assertIsInstance(response.data, list)

    def test_chapters_action(self):
        """Test getting story chapters"""
        chapter1 = ChapterFactory(story=self.public_story, order=1)
        chapter2 = ChapterFactory(story=self.public_story, order=2)

        self.client.force_authenticate(user=self.owner_account)
        url = reverse("story-chapters", kwargs={"pk": self.public_story.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        chapter_ids = [c["id"] for c in response.data]
        self.assertIn(chapter1.id, chapter_ids)
        self.assertIn(chapter2.id, chapter_ids)
        # Verify ordering
        self.assertEqual(response.data[0]["id"], chapter1.id)
        self.assertEqual(response.data[1]["id"], chapter2.id)


class ChapterViewPermissionsTestCase(APITestCase):
    """Test chapter view permissions"""

    @classmethod
    def setUpTestData(cls):
        cls.owner_account = AccountFactory()
        cls.non_owner_account = AccountFactory()
        cls.staff_account = AccountFactory(is_staff=True)

        cls.story = StoryFactory(owners=[cls.owner_account])
        cls.chapter = ChapterFactory(story=cls.story)

    def test_chapter_create_owner_permission(self):
        """Test story owner can create chapters"""
        self.client.force_authenticate(user=self.owner_account)
        url = reverse("chapter-list")
        data = {
            "story": self.story.id,
            "title": "New Chapter",
            "description": "Chapter description",
            "order": 2,
        }
        response = self.client.post(
            url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_chapter_create_non_owner_allowed(self):
        """Test non-story-owner can create chapters (permissions are permissive)"""
        self.client.force_authenticate(user=self.non_owner_account)
        url = reverse("chapter-list")
        data = {
            "story": self.story.id,
            "title": "Unauthorized Chapter",
            "description": "Should not be created",
            "order": 2,
        }
        response = self.client.post(
            url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_chapter_update_owner_permission(self):
        """Test story owner can update chapters"""
        self.client.force_authenticate(user=self.owner_account)
        url = reverse("chapter-detail", kwargs={"pk": self.chapter.pk})
        data = {"title": "Updated Chapter Title"}
        response = self.client.patch(
            url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.chapter.refresh_from_db()
        self.assertEqual(self.chapter.title, "Updated Chapter Title")

    @suppress_permission_errors
    def test_chapter_update_non_owner_denied(self):
        """Test non-story-owner cannot update chapters"""
        self.client.force_authenticate(user=self.non_owner_account)
        url = reverse("chapter-detail", kwargs={"pk": self.chapter.pk})
        data = {"title": "Unauthorized Update"}
        response = self.client.patch(
            url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_episodes_action(self):
        """Test getting chapter episodes"""
        episode1 = EpisodeFactory(chapter=self.chapter, order=1)
        episode2 = EpisodeFactory(chapter=self.chapter, order=2)

        self.client.force_authenticate(user=self.owner_account)
        url = reverse("chapter-episodes", kwargs={"pk": self.chapter.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        episode_ids = [e["id"] for e in response.data]
        self.assertIn(episode1.id, episode_ids)
        self.assertIn(episode2.id, episode_ids)


class EpisodeViewPermissionsTestCase(APITestCase):
    """Test episode view permissions"""

    @classmethod
    def setUpTestData(cls):
        cls.owner_account = AccountFactory()
        cls.non_owner_account = AccountFactory()
        cls.staff_account = AccountFactory(is_staff=True)

        cls.story = StoryFactory(owners=[cls.owner_account])
        cls.chapter = ChapterFactory(story=cls.story)
        cls.episode = EpisodeFactory(chapter=cls.chapter)

    def test_episode_create_owner_permission(self):
        """Test story owner can create episodes"""
        self.client.force_authenticate(user=self.owner_account)
        url = reverse("episode-list")
        data = {
            "chapter": self.chapter.id,
            "title": "New Episode",
            "description": "Episode description",
            "order": 2,
        }
        response = self.client.post(
            url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_episode_create_non_owner_allowed(self):
        """Test non-story-owner can create episodes (permissions are permissive)"""
        self.client.force_authenticate(user=self.non_owner_account)
        url = reverse("episode-list")
        data = {
            "chapter": self.chapter.id,
            "title": "Unauthorized Episode",
            "description": "Should not be created",
            "order": 2,
        }
        response = self.client.post(
            url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_episode_update_owner_permission(self):
        """Test story owner can update episodes"""
        self.client.force_authenticate(user=self.owner_account)
        url = reverse("episode-detail", kwargs={"pk": self.episode.pk})
        data = {"title": "Updated Episode Title"}
        response = self.client.patch(
            url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.episode.refresh_from_db()
        self.assertEqual(self.episode.title, "Updated Episode Title")

    @suppress_permission_errors
    def test_episode_update_non_owner_denied(self):
        """Test non-story-owner cannot update episodes"""
        self.client.force_authenticate(user=self.non_owner_account)
        url = reverse("episode-detail", kwargs={"pk": self.episode.pk})
        data = {"title": "Unauthorized Update"}
        response = self.client.patch(
            url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class StoryParticipationViewPermissionsTestCase(APITestCase):
    """Test story participation view permissions"""

    @classmethod
    def setUpTestData(cls):
        cls.owner_account = AccountFactory()
        cls.participant_account = AccountFactory()
        cls.other_account = AccountFactory()
        cls.staff_account = AccountFactory(is_staff=True)

        cls.story = StoryFactory(owners=[cls.owner_account])
        cls.participant_character = CharacterFactory()
        cls.participant_character.db_account = cls.participant_account
        cls.participant_character.save()

        cls.participation = StoryParticipationFactory(
            story=cls.story, character=cls.participant_character
        )

    @suppress_permission_errors
    def test_participation_update_participant_denied(self):
        """Test participant cannot update their own participation (permissions restrictive)"""
        self.client.force_authenticate(user=self.participant_account)
        url = reverse("storyparticipation-detail", kwargs={"pk": self.participation.pk})
        data = {"participation_level": ParticipationLevel.CRITICAL}
        response = self.client.patch(
            url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_participation_update_owner_permission(self):
        """Test story owner can update any participation"""
        self.client.force_authenticate(user=self.owner_account)
        url = reverse("storyparticipation-detail", kwargs={"pk": self.participation.pk})
        data = {"trusted_by_owner": True}
        response = self.client.patch(
            url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @suppress_permission_errors
    def test_participation_update_other_denied(self):
        """Test other users cannot update participation"""
        self.client.force_authenticate(user=self.other_account)
        url = reverse("storyparticipation-detail", kwargs={"pk": self.participation.pk})
        data = {"participation_level": ParticipationLevel.CRITICAL}
        response = self.client.patch(
            url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class PlayerTrustViewPermissionsTestCase(APITestCase):
    """Test player trust view permissions"""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()
        cls.other_account = AccountFactory()
        cls.staff_account = AccountFactory(is_staff=True)

        cls.trust_profile = PlayerTrustFactory(account=cls.account)

    def test_my_trust_action(self):
        """Test getting own trust profile"""
        self.client.force_authenticate(user=self.account)
        url = reverse("playertrust-my-trust")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.trust_profile.id)

    def test_my_trust_action_not_found(self):
        """Test my_trust returns 404 when no trust profile exists"""
        self.client.force_authenticate(user=self.other_account)
        url = reverse("playertrust-my-trust")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("Trust profile not found", response.data["error"])

    @suppress_permission_errors
    def test_trust_update_owner_denied(self):
        """Test user cannot update their own trust profile (permissions restrictive)"""
        self.client.force_authenticate(user=self.account)
        url = reverse("playertrust-detail", kwargs={"pk": self.trust_profile.pk})
        data = {"gm_trust_level": TrustLevel.ADVANCED}
        response = self.client.patch(
            url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @suppress_permission_errors
    def test_trust_update_other_denied(self):
        """Test other users cannot update trust profiles"""
        self.client.force_authenticate(user=self.other_account)
        url = reverse("playertrust-detail", kwargs={"pk": self.trust_profile.pk})
        data = {"gm_trust_level": TrustLevel.ADVANCED}
        response = self.client.patch(
            url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class StoryFeedbackViewPermissionsTestCase(APITestCase):
    """Test story feedback view permissions"""

    @classmethod
    def setUpTestData(cls):
        cls.reviewer_account = AccountFactory()
        cls.reviewed_account = AccountFactory()
        cls.story_owner_account = AccountFactory()
        cls.other_account = AccountFactory()
        cls.staff_account = AccountFactory(is_staff=True)

        cls.story = StoryFactory(owners=[cls.story_owner_account])
        cls.feedback = StoryFeedbackFactory(
            story=cls.story,
            reviewer=cls.reviewer_account,
            reviewed_player=cls.reviewed_account,
        )

    def test_feedback_create_permission(self):
        """Test creating feedback"""
        # Create a different story to avoid constraint violation
        new_story = StoryFactory(owners=[self.story_owner_account])

        self.client.force_authenticate(user=self.reviewer_account)
        url = reverse("storyfeedback-list")
        data = {
            "story": new_story.id,
            "reviewed_player": self.reviewed_account.id,
            "comments": "Great performance!",
            "is_gm_feedback": False,
            "category_ratings": [],
        }
        response = self.client.post(
            url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_my_feedback_action(self):
        """Test getting feedback received by current user"""
        self.client.force_authenticate(user=self.reviewed_account)
        url = reverse("storyfeedback-my-feedback")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        feedback_ids = [f["id"] for f in response.data["results"]]
        self.assertIn(self.feedback.id, feedback_ids)

    def test_feedback_given_action(self):
        """Test getting feedback given by current user"""
        self.client.force_authenticate(user=self.reviewer_account)
        url = reverse("storyfeedback-feedback-given")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        feedback_ids = [f["id"] for f in response.data["results"]]
        self.assertIn(self.feedback.id, feedback_ids)

    def test_feedback_update_reviewer_permission(self):
        """Test feedback reviewer can update their own feedback"""
        self.client.force_authenticate(user=self.reviewer_account)
        url = reverse("storyfeedback-detail", kwargs={"pk": self.feedback.pk})
        data = {"feedback_text": "Updated feedback"}
        response = self.client.patch(
            url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @suppress_permission_errors
    def test_feedback_update_story_owner_denied(self):
        """Test story owner cannot update feedback (permissions restrictive)"""
        self.client.force_authenticate(user=self.story_owner_account)
        url = reverse("storyfeedback-detail", kwargs={"pk": self.feedback.pk})
        data = {"comments": "Owner updated feedback"}
        response = self.client.patch(
            url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @suppress_permission_errors
    def test_feedback_update_other_denied(self):
        """Test other users cannot update feedback"""
        self.client.force_authenticate(user=self.other_account)
        url = reverse("storyfeedback-detail", kwargs={"pk": self.feedback.pk})
        data = {"feedback_text": "Unauthorized update"}
        response = self.client.patch(
            url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

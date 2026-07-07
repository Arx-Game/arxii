"""Tests for the CrossoverInviteViewSet — DRF endpoints (#2002).

Covers create/accept/decline/withdraw + permission scoping (sender vs recipient
vs outsider). Mirrors the StoryGMOfferViewSet test shape.
"""

from __future__ import annotations

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.events.factories import EventFactory
from world.gm.factories import GMProfileFactory
from world.stories.constants import CrossoverInviteStatus
from world.stories.factories import EpisodeFactory, StoryFactory
from world.stories.models import CrossoverInvite


class CrossoverInviteViewSetCreateTest(APITestCase):
    def setUp(self) -> None:
        self.gm = GMProfileFactory()
        self.client.force_authenticate(user=self.gm.account)
        self.story = StoryFactory()
        self.story.owners.add(self.gm.account)
        self.episode = EpisodeFactory(chapter__story=self.story)
        self.event = EventFactory()

    def test_create_invite(self) -> None:
        url = reverse("crossoverinvite-list")
        response = self.client.post(
            url,
            {
                "event": self.event.pk,
                "to_story": self.story.pk,
                "proposed_episode": self.episode.pk,
                "message": "Let's co-run this.",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["status"], CrossoverInviteStatus.PENDING)
        self.assertEqual(response.data["event"], self.event.pk)

    def test_create_requires_gm_profile(self) -> None:
        non_gm = AccountFactory()
        self.client.force_authenticate(user=non_gm)
        url = reverse("crossoverinvite-list")
        response = self.client.post(
            url, {"event": self.event.pk, "to_story": self.story.pk}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_duplicate_pending_returns_400(self) -> None:
        CrossoverInvite.objects.create(event=self.event, from_gm=self.gm, to_story=self.story)
        url = reverse("crossoverinvite-list")
        response = self.client.post(
            url, {"event": self.event.pk, "to_story": self.story.pk}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class CrossoverInviteViewSetAcceptTest(APITestCase):
    def setUp(self) -> None:
        self.sender_gm = GMProfileFactory()
        self.recipient_account = AccountFactory()
        self.story = StoryFactory()
        self.story.owners.add(self.recipient_account)
        self.episode = EpisodeFactory(chapter__story=self.story)
        self.event = EventFactory()
        self.invite = CrossoverInvite.objects.create(
            event=self.event,
            from_gm=self.sender_gm,
            to_story=self.story,
            proposed_episode=self.episode,
        )

    def test_accept_by_story_owner(self) -> None:
        self.client.force_authenticate(user=self.recipient_account)
        url = reverse("crossoverinvite-accept", kwargs={"pk": self.invite.pk})
        response = self.client.post(url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.invite.refresh_from_db()
        self.assertEqual(self.invite.status, CrossoverInviteStatus.ACCEPTED)

    def test_accept_by_outsider_forbidden(self) -> None:
        outsider = AccountFactory()
        self.client.force_authenticate(user=outsider)
        url = reverse("crossoverinvite-accept", kwargs={"pk": self.invite.pk})
        response = self.client.post(url, {}, format="json")
        # Outsider is filtered out of get_queryset -> 404 (not 403).
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_accept_with_explicit_episode(self) -> None:
        chosen = EpisodeFactory(chapter__story=self.story)
        self.client.force_authenticate(user=self.recipient_account)
        url = reverse("crossoverinvite-accept", kwargs={"pk": self.invite.pk})
        response = self.client.post(url, {"accepted_episode": chosen.pk}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.invite.refresh_from_db()
        self.assertEqual(self.invite.accepted_episode_id, chosen.pk)


class CrossoverInviteViewSetDeclineTest(APITestCase):
    def setUp(self) -> None:
        self.sender_gm = GMProfileFactory()
        self.recipient_account = AccountFactory()
        self.story = StoryFactory()
        self.story.owners.add(self.recipient_account)
        self.event = EventFactory()
        self.invite = CrossoverInvite.objects.create(
            event=self.event, from_gm=self.sender_gm, to_story=self.story
        )

    def test_decline_by_story_owner(self) -> None:
        self.client.force_authenticate(user=self.recipient_account)
        url = reverse("crossoverinvite-decline", kwargs={"pk": self.invite.pk})
        response = self.client.post(url, {"response_note": "Not this time."}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.invite.refresh_from_db()
        self.assertEqual(self.invite.status, CrossoverInviteStatus.DECLINED)


class CrossoverInviteViewSetWithdrawTest(APITestCase):
    def setUp(self) -> None:
        self.sender_gm = GMProfileFactory()
        self.recipient_account = AccountFactory()
        self.story = StoryFactory()
        self.story.owners.add(self.recipient_account)
        self.event = EventFactory()
        self.invite = CrossoverInvite.objects.create(
            event=self.event, from_gm=self.sender_gm, to_story=self.story
        )

    def test_withdraw_by_sender(self) -> None:
        self.client.force_authenticate(user=self.sender_gm.account)
        url = reverse("crossoverinvite-withdraw", kwargs={"pk": self.invite.pk})
        response = self.client.post(url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.invite.refresh_from_db()
        self.assertEqual(self.invite.status, CrossoverInviteStatus.WITHDRAWN)

    def test_withdraw_by_recipient_forbidden(self) -> None:
        self.client.force_authenticate(user=self.recipient_account)
        url = reverse("crossoverinvite-withdraw", kwargs={"pk": self.invite.pk})
        response = self.client.post(url, {}, format="json")
        # Recipient can see the invite (to_story owner) but lacks sender
        # permission on the withdraw action -> 403.
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class CrossoverInviteViewSetListTest(APITestCase):
    def test_list_scoped_to_sender_and_recipient(self) -> None:
        sender_gm = GMProfileFactory()
        recipient_account = AccountFactory()
        story = StoryFactory()
        story.owners.add(recipient_account)
        event = EventFactory()
        invite = CrossoverInvite.objects.create(event=event, from_gm=sender_gm, to_story=story)
        # Sender sees it
        self.client.force_authenticate(user=sender_gm.account)
        url = reverse("crossoverinvite-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        invite_ids = [i["id"] for i in response.data["results"]]
        self.assertIn(invite.pk, invite_ids)
        # Recipient sees it
        self.client.force_authenticate(user=recipient_account)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        invite_ids = [i["id"] for i in response.data["results"]]
        self.assertIn(invite.pk, invite_ids)
        # Outsider does not
        outsider = AccountFactory()
        self.client.force_authenticate(user=outsider)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        invite_ids = [i["id"] for i in response.data["results"]]
        self.assertNotIn(invite.pk, invite_ids)

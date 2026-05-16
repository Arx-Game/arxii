from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.stories.factories import StoryFactory, StoryNoteFactory


class StoryNoteApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)
        cls.story = StoryFactory(owners=[cls.staff])
        StoryNoteFactory(story=cls.story, body="seed idea")

    def test_staff_can_list_notes_for_story(self):
        self.client.force_authenticate(user=self.staff)
        resp = self.client.get(reverse("storynote-list"), {"story": self.story.pk})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_staff_can_append_note(self):
        self.client.force_authenticate(user=self.staff)
        resp = self.client.post(
            reverse("storynote-list"),
            {"story": self.story.pk, "body": "later: betrayal arc"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_notes_are_not_editable(self):
        self.client.force_authenticate(user=self.staff)
        note = StoryNoteFactory(story=self.story)
        resp = self.client.patch(
            reverse("storynote-detail", kwargs={"pk": note.pk}),
            {"body": "x"},
            format="json",
        )
        self.assertIn(
            resp.status_code,
            (status.HTTP_405_METHOD_NOT_ALLOWED, status.HTTP_403_FORBIDDEN),
        )

    def test_non_owner_player_is_denied(self):
        """Layer-1 must deny a plain authenticated, non-owner, non-staff account."""
        outsider = AccountFactory(is_staff=False)
        self.client.force_authenticate(user=outsider)
        resp = self.client.get(reverse("storynote-list"), {"story": self.story.pk})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

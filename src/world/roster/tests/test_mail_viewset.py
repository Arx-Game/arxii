"""Tests for PlayerMailViewSet API endpoints."""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from world.roster.factories import (
    AccountFactory,
    PlayerDataFactory,
    PlayerMailFactory,
    RosterTenureFactory,
)
from world.roster.models import PlayerMail


class PlayerMailViewSetTestCase(TestCase):
    """Test listing and sending player mail."""

    def setUp(self):
        """Set up test data."""
        self.client = APIClient()
        self.recipient = PlayerDataFactory()
        self.tenure = RosterTenureFactory(player_data=self.recipient)
        self.client.force_authenticate(user=self.recipient.account)
        self.sender_account = AccountFactory()
        PlayerMailFactory(
            recipient_tenure=self.tenure,
            sender_account=self.sender_account,
            sent_date=timezone.now() - timedelta(days=1),
            subject="Old",
        )
        PlayerMailFactory(
            recipient_tenure=self.tenure,
            sender_account=self.sender_account,
            subject="New",
        )

    def test_list_mail_orders_newest_first(self):
        """GET /mail/ returns mail ordered from newest to oldest."""
        url = reverse("roster:mail-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        subjects = [item["subject"] for item in data["results"]]
        self.assertEqual(subjects, ["New", "Old"])
        self.assertEqual(
            data["results"][0]["recipient_display"],
            self.tenure.display_name,
        )

    def test_send_mail_creates_message(self):
        """POST /mail/ creates a new mail entry."""
        self.client.force_authenticate(user=self.sender_account)
        url = reverse("roster:mail-list")
        payload = {
            "recipient_tenure": self.tenure.id,
            "subject": "Hello",
            "message": "Test message",
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            PlayerMail.objects.filter(
                recipient_tenure=self.tenure, subject="Hello"
            ).exists()
        )

    def test_reply_mail_links_thread(self):
        """POST with in_reply_to links messages in a thread."""
        original = PlayerMail.objects.first()
        self.client.force_authenticate(user=self.sender_account)
        url = reverse("roster:mail-list")
        payload = {
            "recipient_tenure": self.tenure.id,
            "subject": "Re: Old",
            "message": "Reply",
            "in_reply_to": original.id,
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, 201)
        reply = PlayerMail.objects.get(subject="Re: Old")
        self.assertEqual(reply.in_reply_to, original)

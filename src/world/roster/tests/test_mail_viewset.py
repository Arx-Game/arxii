"""Tests for PlayerMailViewSet API endpoints."""

from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from world.roster.factories import (
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
        self.sender_player = PlayerDataFactory()
        self.sender_account = self.sender_player.account
        self.sender_tenure = RosterTenureFactory(player_data=self.sender_player)
        PlayerMailFactory(
            recipient_tenure=self.tenure,
            sender_tenure=self.sender_tenure,
            sent_date=timezone.now() - timedelta(days=1),
            subject="Old",
        )
        PlayerMailFactory(
            recipient_tenure=self.tenure,
            sender_tenure=self.sender_tenure,
            subject="New",
        )

    def test_list_mail_orders_newest_first(self):
        """GET /mail/ returns mail ordered from newest to oldest."""
        url = reverse("roster:mail-list")
        response = self.client.get(url)
        assert response.status_code == 200
        data = response.json()
        subjects = [item["subject"] for item in data["results"]]
        assert subjects == ["New", "Old"]
        assert data["results"][0]["recipient_display"] == self.tenure.display_name

    def test_send_mail_creates_message(self):
        """POST /mail/ creates a new mail entry."""
        self.client.force_authenticate(user=self.sender_account)
        url = reverse("roster:mail-list")
        payload = {
            "recipient_tenure": self.tenure.id,
            "sender_tenure": self.sender_tenure.id,
            "subject": "Hello",
            "message": "Test message",
        }
        response = self.client.post(url, payload, format="json")
        assert response.status_code == 201
        assert PlayerMail.objects.filter(recipient_tenure=self.tenure, subject="Hello").exists()

    def test_reply_mail_links_thread(self):
        """POST with in_reply_to links messages in a thread."""
        original = PlayerMail.objects.first()
        self.client.force_authenticate(user=self.sender_account)
        url = reverse("roster:mail-list")
        payload = {
            "recipient_tenure": self.tenure.id,
            "sender_tenure": self.sender_tenure.id,
            "subject": "Re: Old",
            "message": "Reply",
            "in_reply_to": original.id,
        }
        response = self.client.post(url, payload, format="json")
        assert response.status_code == 201
        reply = PlayerMail.objects.get(subject="Re: Old")
        assert reply.in_reply_to == original


class PlayerMailMarkReadTestCase(TestCase):
    """Test the mark-read action is recipient-only and idempotent."""

    def setUp(self):
        self.client = APIClient()
        self.recipient = PlayerDataFactory()
        self.tenure = RosterTenureFactory(player_data=self.recipient)
        self.sender_tenure = RosterTenureFactory()
        self.mail = PlayerMailFactory(
            recipient_tenure=self.tenure,
            sender_tenure=self.sender_tenure,
        )

    def test_recipient_can_mark_read(self):
        """The recipient marking their own mail read sets read_date and is idempotent."""
        self.client.force_authenticate(user=self.recipient.account)
        url = reverse("roster:mail-mark-read", args=[self.mail.pk])

        response = self.client.post(url)
        assert response.status_code == 200
        self.mail.refresh_from_db()
        assert self.mail.read_date is not None
        first_read_date = self.mail.read_date

        # Idempotent: a second call does not move read_date.
        response = self.client.post(url)
        assert response.status_code == 200
        self.mail.refresh_from_db()
        assert self.mail.read_date == first_read_date

    def test_non_recipient_cannot_mark_read(self):
        """A player who isn't the recipient gets 404 -- the mail is invisible to them."""
        other = PlayerDataFactory()
        self.client.force_authenticate(user=other.account)
        url = reverse("roster:mail-mark-read", args=[self.mail.pk])

        response = self.client.post(url)
        assert response.status_code == 404
        self.mail.refresh_from_db()
        assert self.mail.read_date is None

    def test_unauthenticated_cannot_mark_read(self):
        """No auth -- 401/403, not a leak of the mail's existence via a 404."""
        url = reverse("roster:mail-mark-read", args=[self.mail.pk])
        response = self.client.post(url)
        assert response.status_code in (401, 403)


class PlayerMailUnreadCountTestCase(TestCase):
    """Test the unread-count action is scoped to the requester's own tenures."""

    def setUp(self):
        self.client = APIClient()
        self.recipient = PlayerDataFactory()
        self.tenure = RosterTenureFactory(player_data=self.recipient)
        self.sender_tenure = RosterTenureFactory()
        self.client.force_authenticate(user=self.recipient.account)
        self.url = reverse("roster:mail-unread-count")

    def test_counts_unread_unarchived_mail_for_requester(self):
        """Two unread + one read + one archived -- only the two unread/unarchived count."""
        PlayerMailFactory(recipient_tenure=self.tenure, sender_tenure=self.sender_tenure)
        PlayerMailFactory(recipient_tenure=self.tenure, sender_tenure=self.sender_tenure)
        PlayerMailFactory(
            recipient_tenure=self.tenure,
            sender_tenure=self.sender_tenure,
            read_date=timezone.now(),
        )
        PlayerMailFactory(
            recipient_tenure=self.tenure,
            sender_tenure=self.sender_tenure,
            archived=True,
        )

        response = self.client.get(self.url)
        assert response.status_code == 200
        assert response.json() == {"count": 2}

    def test_excludes_other_players_unread_mail(self):
        """Another player's unread mail never bleeds into this requester's count."""
        other_recipient = PlayerDataFactory()
        other_tenure = RosterTenureFactory(player_data=other_recipient)
        PlayerMailFactory(recipient_tenure=other_tenure, sender_tenure=self.sender_tenure)

        response = self.client.get(self.url)
        assert response.status_code == 200
        assert response.json() == {"count": 0}


class PlayerMailArrivalPushTestCase(TestCase):
    """Test the MAIL_ARRIVED push fired on send: anonymity boundary + offline no-op."""

    def setUp(self):
        self.client = APIClient()
        self.recipient = PlayerDataFactory()
        self.tenure = RosterTenureFactory(player_data=self.recipient)
        self.sender_player = PlayerDataFactory()
        self.sender_account = self.sender_player.account
        self.sender_tenure = RosterTenureFactory(player_data=self.sender_player)

    def test_send_mail_pushes_arrival_ping_with_no_account_identifiers(self):
        """Push fires post-commit, carries only tenure-display data -- no account id/username."""
        self.client.force_authenticate(user=self.sender_account)
        url = reverse("roster:mail-list")
        payload = {
            "recipient_tenure": self.tenure.id,
            "sender_tenure": self.sender_tenure.id,
            "subject": "Hello",
            "message": "Test message",
        }

        with mock.patch.object(self.recipient.account, "msg") as mock_msg:
            with self.captureOnCommitCallbacks() as callbacks:
                response = self.client.post(url, payload, format="json")
            assert response.status_code == 201
            # Deferred via transaction.on_commit -- not fired mid-request.
            mock_msg.assert_not_called()
            assert len(callbacks) == 1
            for callback in callbacks:
                callback()

        mock_msg.assert_called_once()
        _, kwargs = mock_msg.call_args
        _, mail_payload = kwargs["mail_arrived"]
        mail = PlayerMail.objects.get(subject="Hello")
        assert mail_payload == {
            "mail_id": mail.pk,
            "sender_display": self.sender_tenure.display_name,
            "subject": "Hello",
        }
        assert "account" not in mail_payload
        assert "username" not in mail_payload
        assert str(self.sender_account.pk) not in str(mail_payload)
        assert self.sender_account.username not in str(mail_payload.values())

    def test_offline_recipient_is_a_no_op(self):
        """An offline recipient's real account.msg is a harmless no-op -- send still succeeds."""
        self.client.force_authenticate(user=self.sender_account)
        url = reverse("roster:mail-list")
        payload = {
            "recipient_tenure": self.tenure.id,
            "sender_tenure": self.sender_tenure.id,
            "subject": "Offline Test",
            "message": "Test message",
        }

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(url, payload, format="json")

        assert response.status_code == 201
        assert PlayerMail.objects.filter(subject="Offline Test").exists()

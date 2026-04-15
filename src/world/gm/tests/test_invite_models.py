"""Tests for GMRosterInvite model."""

from datetime import timedelta

from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from world.gm.factories import GMRosterInviteFactory


class GMRosterInviteModelTest(TestCase):
    def test_creation(self) -> None:
        invite = GMRosterInviteFactory()
        assert invite.pk is not None
        assert invite.code
        assert invite.is_claimed is False
        assert invite.is_expired is False
        assert invite.is_usable is True

    def test_str_truncates_code(self) -> None:
        invite = GMRosterInviteFactory()
        assert "GMRosterInvite(" in str(invite)
        assert invite.code[:8] in str(invite)

    def test_is_expired_after_expiration(self) -> None:
        past = timezone.now() - timedelta(days=1)
        invite = GMRosterInviteFactory(expires_at=past)
        assert invite.is_expired is True
        assert invite.is_usable is False

    def test_is_claimed_when_claimed_at_set(self) -> None:
        invite = GMRosterInviteFactory()
        invite.claimed_at = timezone.now()
        invite.save(update_fields=["claimed_at"])
        assert invite.is_claimed is True
        assert invite.is_usable is False

    def test_code_uniqueness(self) -> None:
        first = GMRosterInviteFactory()
        with self.assertRaises(IntegrityError):
            GMRosterInviteFactory(code=first.code)

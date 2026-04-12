"""Tests for GM system models."""

from django.db import IntegrityError
from django.test import TestCase

from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory


class GMProfileModelTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.profile = GMProfileFactory()

    def test_creation(self) -> None:
        assert self.profile.pk is not None
        assert self.profile.level == GMLevel.STARTING

    def test_str(self) -> None:
        result = str(self.profile)
        assert "GMProfile(" in result
        assert self.profile.account.username in result

    def test_one_profile_per_account(self) -> None:
        """Duplicate profile for same account raises IntegrityError."""
        with self.assertRaises(IntegrityError):
            GMProfileFactory(account=self.profile.account)

    def test_default_level(self) -> None:
        assert self.profile.level == GMLevel.STARTING

"""Tests for shared API permissions."""

from unittest.mock import Mock

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import AccountFactory
from web.api.permissions import IsCharacterOwner
from world.roster.factories import (
    PlayerDataFactory,
    RosterEntryFactory,
    RosterTenureFactory,
)


class IsCharacterOwnerTests(TestCase):
    """Tests for IsCharacterOwner permission class."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.player_data = PlayerDataFactory()
        cls.account = cls.player_data.account
        cls.roster_entry = RosterEntryFactory()
        cls.tenure = RosterTenureFactory(
            player_data=cls.player_data,
            roster_entry=cls.roster_entry,
        )
        cls.character = cls.roster_entry.character_sheet.character
        cls.other_account = AccountFactory(username="other_user")
        cls.staff_account = AccountFactory(username="staff_user", is_staff=True)

    def setUp(self) -> None:
        self.permission = IsCharacterOwner()

    def _make_request(self, user: object) -> Mock:
        request = Mock()
        request.user = user
        return request

    def _make_view(self, character_id: int) -> Mock:
        view = Mock()
        view.kwargs = {"character_id": character_id}
        return view

    def test_owner_has_permission(self) -> None:
        """Active tenure grants permission."""
        request = self._make_request(self.account)
        view = self._make_view(self.character.pk)
        assert self.permission.has_permission(request, view) is True

    def test_non_owner_denied(self) -> None:
        """Account without tenure is denied."""
        request = self._make_request(self.other_account)
        view = self._make_view(self.character.pk)
        assert self.permission.has_permission(request, view) is False

    def test_expired_tenure_denied(self) -> None:
        """Account with ended tenure is denied."""
        expired_entry = RosterEntryFactory()
        RosterTenureFactory(
            player_data=self.player_data,
            roster_entry=expired_entry,
            end_date=timezone.now(),
        )
        request = self._make_request(self.account)
        view = self._make_view(expired_entry.character_sheet.character.pk)
        assert self.permission.has_permission(request, view) is False

    def test_pending_tenure_denied(self) -> None:
        """Tenure without start_date is denied."""
        pending_entry = RosterEntryFactory()
        RosterTenureFactory(
            player_data=self.player_data,
            roster_entry=pending_entry,
            start_date=None,
        )
        request = self._make_request(self.account)
        view = self._make_view(pending_entry.character_sheet.character.pk)
        assert self.permission.has_permission(request, view) is False

    def test_staff_bypasses_check(self) -> None:
        """Staff can access any character."""
        request = self._make_request(self.staff_account)
        view = self._make_view(self.character.pk)
        assert self.permission.has_permission(request, view) is True

    def test_nonexistent_character_denied(self) -> None:
        """Invalid character ID returns False."""
        request = self._make_request(self.account)
        view = self._make_view(99999)
        assert self.permission.has_permission(request, view) is False

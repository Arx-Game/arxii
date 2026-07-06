"""Tests for PlayerPendingTreasuredSignoffsView — GET /api/stories/my-pending-signoffs/ (#1853)."""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core_management.test_utils import suppress_permission_errors
from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.boundaries.factories import TreasuredSubjectFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.stories.constants import StakeSubjectKind
from world.stories.factories import BeatFactory, StakeFactory
from world.stories.services.boundaries import grant_treasured_signoff

MY_PENDING_SIGNOFFS_URL = reverse("stories-my-pending-signoffs")


def _account_with_treasured_subject(label: str):
    """An Account whose active character owns a TreasuredSubject with *label*."""
    account = AccountFactory()
    char = CharacterFactory()
    char.db_account = account
    char.save()
    sheet = CharacterSheetFactory(character=char)
    entry = RosterEntryFactory(character_sheet=sheet)
    player_data = PlayerDataFactory(account=account)
    tenure = RosterTenureFactory(roster_entry=entry, player_data=player_data)
    treasured = TreasuredSubjectFactory(
        owner=tenure,
        subject_kind=StakeSubjectKind.CUSTOM,
        subject_label=label,
    )
    return account, player_data, treasured


class MyPendingSignoffsAuthTest(APITestCase):
    @suppress_permission_errors
    def test_unauthenticated_rejected(self):
        response = self.client.get(MY_PENDING_SIGNOFFS_URL)
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )


class MyPendingSignoffsResponseTest(APITestCase):
    def test_no_beats_query_param_returns_empty_list(self):
        account = AccountFactory()
        self.client.force_authenticate(user=account)
        response = self.client.get(MY_PENDING_SIGNOFFS_URL)
        assert response.status_code == status.HTTP_200_OK
        assert response.data == []

    def test_flags_beat_with_pending_signoff(self):
        account, _player_data, treasured = _account_with_treasured_subject("Signet Ring")
        beat = BeatFactory()
        StakeFactory(
            beat=beat,
            template=None,
            subject_kind=StakeSubjectKind.CUSTOM,
            subject_label="Signet Ring",
        )
        self.client.force_authenticate(user=account)

        response = self.client.get(MY_PENDING_SIGNOFFS_URL, {"beats": [beat.pk]})

        assert response.status_code == status.HTTP_200_OK
        assert response.data == [{"beat_id": beat.pk, "treasured_subject_ids": [treasured.pk]}]

    def test_signed_off_beat_is_omitted(self):
        account, player_data, treasured = _account_with_treasured_subject("Signet Ring")
        beat = BeatFactory()
        StakeFactory(
            beat=beat,
            template=None,
            subject_kind=StakeSubjectKind.CUSTOM,
            subject_label="Signet Ring",
        )
        grant_treasured_signoff(beat, player_data, treasured)
        self.client.force_authenticate(user=account)

        response = self.client.get(MY_PENDING_SIGNOFFS_URL, {"beats": [beat.pk]})

        assert response.data == []

    def test_never_returns_another_players_pending_signoff(self):
        _other_account, _other_player_data, _other_treasured = _account_with_treasured_subject(
            "Signet Ring"
        )
        beat = BeatFactory()
        StakeFactory(
            beat=beat,
            template=None,
            subject_kind=StakeSubjectKind.CUSTOM,
            subject_label="Signet Ring",
        )
        # The querying account has its OWN player_data and its OWN treasured subject
        # (a different one) so this exercises the real cross-player identity-matching
        # path in player_pending_treasured_signoffs, not just the no-player_data
        # early return already covered by test_account_with_no_player_data_gets_empty_list.
        querying_account, _querying_player_data, _querying_treasured = (
            _account_with_treasured_subject("Unrelated Charm")
        )
        self.client.force_authenticate(user=querying_account)

        response = self.client.get(MY_PENDING_SIGNOFFS_URL, {"beats": [beat.pk]})

        assert response.data == []

    def test_account_with_no_player_data_gets_empty_list(self):
        account = AccountFactory()
        beat = BeatFactory()
        self.client.force_authenticate(user=account)

        response = self.client.get(MY_PENDING_SIGNOFFS_URL, {"beats": [beat.pk]})

        assert response.status_code == status.HTTP_200_OK
        assert response.data == []

"""Tests for RelationshipUpdateViewSet's list route (#2031, commend button read surface).

Scoped narrowly to the commend use-case: only writeups where the requesting user's
account holds a *current RosterTenure* over the relationship's SUBJECT
(``relationship.target``, matching ``give_writeup_kudos``'s subject rule) and
visibility is SHARED or PUBLIC. Mirrors ``RelationshipCapstoneViewSet``'s annotated
read pattern (see test_capstone_viewset.py) but scopes by target/subject instead of
author.

Ownership is provisioned via ``RosterTenure`` (the pattern ``test_writeup_feedback_api.py``
uses for ``give_writeup_kudos``), **not** ``db_account`` — ``db_account`` is Evennia's
live-puppet field, cleared on unpuppet, and does not reflect roster ownership (fix wave,
Finding 1: a subject browsing while not currently puppeting the character must still see
their commendable writeups).
"""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from world.character_sheets.factories import CharacterSheetFactory
from world.relationships.constants import TrackSign, UpdateVisibility
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipTrackFactory,
    RelationshipUpdateFactory,
)
from world.relationships.models import WriteupKudos
from world.roster.factories import RosterTenureFactory


def _make_linked_account(character_sheet):
    """Create a RosterTenure linking character_sheet.character to a fresh account.

    Deliberately does NOT touch ``db_account`` — ownership here is tenure-based,
    matching how ``get_account_for_character``/``give_writeup_kudos`` resolve the
    subject, and how a real player is linked to a roster character.
    """
    tenure = RosterTenureFactory(roster_entry__character_sheet__character=character_sheet.character)
    return tenure.player_data.account


class RelationshipUpdateListViewSetTests(TestCase):
    """Tests for RelationshipUpdateViewSet's list action."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Set up test data shared across all tests."""
        # The viewer/subject account and their character sheet — writeups are
        # "about" this sheet (relationship.target == subject_sheet). Linked via
        # RosterTenure, NOT db_account (the live-puppet field) — this account is
        # NOT currently puppeting subject_sheet's character in most tests below,
        # proving the endpoint is reachable regardless of puppet state.
        cls.subject_sheet = CharacterSheetFactory()
        cls.subject_account = _make_linked_account(cls.subject_sheet)

        # The author account/sheet — writes about the subject.
        cls.author_sheet = CharacterSheetFactory()
        cls.author_account = _make_linked_account(cls.author_sheet)

        # A third party, entirely uninvolved.
        cls.third_sheet = CharacterSheetFactory()

        # A second character owned by the SAME subject account, for the
        # ?subject_character= narrowing tests.
        cls.subject_alt_sheet = CharacterSheetFactory()
        RosterTenureFactory(
            roster_entry__character_sheet=cls.subject_alt_sheet,
            player_data=cls.subject_account.player_data,
        )

        cls.track = RelationshipTrackFactory(name="UpdateListTrack", sign=TrackSign.POSITIVE)

        # subject is the TARGET here — this is the eligible direction.
        cls.rel_author_subject = CharacterRelationshipFactory(
            source=cls.author_sheet, target=cls.subject_sheet
        )
        # subject is the SOURCE here — writeups on this relationship are about
        # the author, not the subject, so they must be excluded.
        cls.rel_subject_author = CharacterRelationshipFactory(
            source=cls.subject_sheet, target=cls.author_sheet
        )
        # Relationship with no subject involvement at all.
        cls.rel_third = CharacterRelationshipFactory(
            source=cls.third_sheet, target=cls.author_sheet
        )
        # A relationship about the subject's SECOND character.
        cls.rel_author_subject_alt = CharacterRelationshipFactory(
            source=cls.author_sheet, target=cls.subject_alt_sheet
        )

        cls.update_shared = RelationshipUpdateFactory(
            relationship=cls.rel_author_subject,
            author=cls.author_sheet,
            track=cls.track,
            title="Shared About Subject",
            visibility=UpdateVisibility.SHARED,
        )
        cls.update_public = RelationshipUpdateFactory(
            relationship=cls.rel_author_subject,
            author=cls.author_sheet,
            track=cls.track,
            title="Public About Subject",
            visibility=UpdateVisibility.PUBLIC,
        )
        cls.update_private = RelationshipUpdateFactory(
            relationship=cls.rel_author_subject,
            author=cls.author_sheet,
            track=cls.track,
            title="Private About Subject",
            visibility=UpdateVisibility.PRIVATE,
        )
        cls.update_gossip = RelationshipUpdateFactory(
            relationship=cls.rel_author_subject,
            author=cls.author_sheet,
            track=cls.track,
            title="Gossip About Subject",
            visibility=UpdateVisibility.GOSSIP,
        )
        cls.update_wrong_direction = RelationshipUpdateFactory(
            relationship=cls.rel_subject_author,
            author=cls.subject_sheet,
            track=cls.track,
            title="About The Author Not Subject",
            visibility=UpdateVisibility.SHARED,
        )
        cls.update_third_party = RelationshipUpdateFactory(
            relationship=cls.rel_third,
            author=cls.third_sheet,
            track=cls.track,
            title="Unrelated Third Party Update",
            visibility=UpdateVisibility.SHARED,
        )
        cls.update_about_alt = RelationshipUpdateFactory(
            relationship=cls.rel_author_subject_alt,
            author=cls.author_sheet,
            track=cls.track,
            title="Shared About Subject's Second Character",
            visibility=UpdateVisibility.SHARED,
        )

    def setUp(self) -> None:
        """Set up test client."""
        self.client = APIClient()
        self.client.force_authenticate(user=self.subject_account)

    def test_list_returns_shared_and_public_writeups_about_subject(self) -> None:
        """List returns only SHARED/PUBLIC writeups where subject is the target."""
        response = self.client.get("/api/relationships/relationship-updates/")
        assert response.status_code == status.HTTP_200_OK
        data = self._get_results(response.data)
        titles = [u["title"] for u in data]
        assert "Shared About Subject" in titles
        assert "Public About Subject" in titles

    def test_list_excludes_private_writeup(self) -> None:
        """PRIVATE writeups about the subject are excluded."""
        response = self.client.get("/api/relationships/relationship-updates/")
        data = self._get_results(response.data)
        titles = [u["title"] for u in data]
        assert "Private About Subject" not in titles

    def test_list_excludes_gossip_writeup(self) -> None:
        """GOSSIP writeups about the subject are excluded (only SHARED/PUBLIC)."""
        response = self.client.get("/api/relationships/relationship-updates/")
        data = self._get_results(response.data)
        titles = [u["title"] for u in data]
        assert "Gossip About Subject" not in titles

    def test_list_excludes_writeup_where_subject_is_not_target(self) -> None:
        """Writeups on a relationship where the subject is the SOURCE are excluded."""
        response = self.client.get("/api/relationships/relationship-updates/")
        data = self._get_results(response.data)
        titles = [u["title"] for u in data]
        assert "About The Author Not Subject" not in titles

    def test_list_excludes_unrelated_third_party_writeup(self) -> None:
        """Writeups on relationships not involving the subject at all are excluded."""
        response = self.client.get("/api/relationships/relationship-updates/")
        data = self._get_results(response.data)
        titles = [u["title"] for u in data]
        assert "Unrelated Third Party Update" not in titles

    def test_unauthenticated_request_rejected(self) -> None:
        """Unauthenticated requests are rejected with 401 or 403."""
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/relationships/relationship-updates/")
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    def test_list_carries_kudos_count_and_viewer_has_kudosed(self) -> None:
        """Response rows carry annotated kudos_count and viewer_has_kudosed."""
        WriteupKudos.objects.create(account=self.subject_account, update=self.update_shared)
        response = self.client.get("/api/relationships/relationship-updates/")
        data = self._get_results(response.data)
        by_title = {u["title"]: u for u in data}
        assert by_title["Shared About Subject"]["kudos_count"] == 1
        assert by_title["Shared About Subject"]["viewer_has_kudosed"] is True
        assert by_title["Public About Subject"]["kudos_count"] == 0
        assert by_title["Public About Subject"]["viewer_has_kudosed"] is False

    def test_list_filters_by_relationship(self) -> None:
        """?relationship=<pk> narrows to writeups on that relationship."""
        url = f"/api/relationships/relationship-updates/?relationship={self.rel_author_subject.pk}"
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        data = self._get_results(response.data)
        titles = [u["title"] for u in data]
        assert "Shared About Subject" in titles
        assert "Public About Subject" in titles

    def test_list_reachable_when_subject_not_currently_puppeting(self) -> None:
        """A tenure-owned, not-currently-puppeted subject still sees their writeups.

        Regression for Finding 1: the old queryset filtered on
        ``relationship__target__character__db_account``, Evennia's live-puppet field,
        which is cleared on unpuppet. Confirm ``subject_sheet.character.db_account``
        is unset here (proving the account is NOT puppeting) while the tenure-linked
        writeup is still listed.
        """
        assert self.subject_sheet.character.db_account_id is None
        response = self.client.get("/api/relationships/relationship-updates/")
        assert response.status_code == status.HTTP_200_OK
        titles = [u["title"] for u in self._get_results(response.data)]
        assert "Shared About Subject" in titles

    def test_subject_character_narrows_to_one_owned_character(self) -> None:
        """?subject_character=<pk> narrows to writeups about that owned sheet only."""
        url = f"/api/relationships/relationship-updates/?subject_character={self.subject_sheet.pk}"
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        titles = [u["title"] for u in self._get_results(response.data)]
        assert "Shared About Subject" in titles
        assert "Public About Subject" in titles
        assert "Shared About Subject's Second Character" not in titles

    def test_subject_character_narrows_to_other_owned_character(self) -> None:
        """?subject_character=<other pk> narrows to the OTHER owned sheet's writeups."""
        url = (
            "/api/relationships/relationship-updates/"
            f"?subject_character={self.subject_alt_sheet.pk}"
        )
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        titles = [u["title"] for u in self._get_results(response.data)]
        assert titles == ["Shared About Subject's Second Character"]

    def test_subject_character_cannot_widen_to_unowned_character(self) -> None:
        """?subject_character=<unowned pk> narrows to nothing — it can't widen access."""
        url = f"/api/relationships/relationship-updates/?subject_character={self.third_sheet.pk}"
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert self._get_results(response.data) == []

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_results(self, response_data: dict | list) -> list:
        """Extract results from paginated or non-paginated response."""
        if isinstance(response_data, dict) and "results" in response_data:
            return response_data["results"]
        return response_data

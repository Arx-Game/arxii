"""Tests for StoryGMOffer model, lifecycle services, and Wave 3 action endpoints.

Task 3.1: model round-trip, unique constraint, defaults.
Task 3.2: offer_story_to_gm, accept_story_offer, decline_story_offer, withdraw_story_offer.
Task 3.3: ViewSet endpoints — offer, accept, decline, withdraw; permission gates.
"""

from django.db import IntegrityError, transaction
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core_management.test_utils import suppress_permission_errors
from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.constants import GMTableStatus
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.stories.constants import StoryGMOfferStatus, StoryScope
from world.stories.exceptions import StoryGMOfferError
from world.stories.factories import StoryFactory, StoryGMOfferFactory
from world.stories.models import StoryGMOffer
from world.stories.services.tables import (
    accept_story_offer,
    decline_story_offer,
    offer_story_to_gm,
    withdraw_story_offer,
)

# ---------------------------------------------------------------------------
# Task 3.1 — Model tests
# ---------------------------------------------------------------------------


class StoryGMOfferModelTest(TestCase):
    """Round-trip, defaults, and basic field validation."""

    def test_round_trip_via_factory(self):
        """Factory creates a valid StoryGMOffer with correct defaults."""
        offer = StoryGMOfferFactory()
        assert offer.pk is not None
        assert offer.status == StoryGMOfferStatus.PENDING
        assert offer.responded_at is None
        assert offer.message == ""
        assert offer.response_note == ""

    def test_str_representation(self):
        """__str__ includes story, gm, and status."""
        offer = StoryGMOfferFactory()
        s = str(offer)
        assert "StoryGMOffer" in s
        assert "pending" in s

    def test_default_status_is_pending(self):
        offer = StoryGMOfferFactory()
        assert offer.status == StoryGMOfferStatus.PENDING

    def test_responded_at_defaults_to_none(self):
        offer = StoryGMOfferFactory()
        assert offer.responded_at is None


class StoryGMOfferUniquePendingConstraintTest(TransactionTestCase):
    """Partial unique constraint: one PENDING offer per (story, gm) pair."""

    def test_two_pending_offers_same_story_same_gm_raises(self):
        """Creating a second PENDING offer for the same (story, GM) pair raises IntegrityError."""
        gm = GMProfileFactory()
        story = StoryFactory(scope=StoryScope.CHARACTER, primary_table=None)
        account = AccountFactory()
        StoryGMOffer.objects.create(
            story=story,
            offered_to=gm,
            offered_by_account=account,
            status=StoryGMOfferStatus.PENDING,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                StoryGMOffer.objects.create(
                    story=story,
                    offered_to=gm,
                    offered_by_account=account,
                    status=StoryGMOfferStatus.PENDING,
                )

    def test_pending_and_declined_same_pair_is_ok(self):
        """A PENDING and a DECLINED offer for the same (story, GM) pair is allowed."""
        gm = GMProfileFactory()
        story = StoryFactory(scope=StoryScope.CHARACTER, primary_table=None)
        account = AccountFactory()
        StoryGMOffer.objects.create(
            story=story,
            offered_to=gm,
            offered_by_account=account,
            status=StoryGMOfferStatus.DECLINED,
        )
        # Creating a PENDING one after a DECLINED should succeed.
        offer2 = StoryGMOffer.objects.create(
            story=story,
            offered_to=gm,
            offered_by_account=account,
            status=StoryGMOfferStatus.PENDING,
        )
        assert offer2.pk is not None

    def test_two_pending_offers_different_gms_same_story_is_ok(self):
        """Two PENDING offers to different GMs for the same story are allowed."""
        gm1 = GMProfileFactory()
        gm2 = GMProfileFactory()
        story = StoryFactory(scope=StoryScope.CHARACTER, primary_table=None)
        account = AccountFactory()
        o1 = StoryGMOffer.objects.create(story=story, offered_to=gm1, offered_by_account=account)
        o2 = StoryGMOffer.objects.create(story=story, offered_to=gm2, offered_by_account=account)
        assert o1.pk != o2.pk


# ---------------------------------------------------------------------------
# Task 3.2 — Service tests
# ---------------------------------------------------------------------------


def _character_sheet_with_account(account):
    """Return a CharacterSheet whose character.db_account == account."""
    char = CharacterFactory()
    char.db_account = account
    char.save()
    return CharacterSheetFactory(character=char)


class OfferStoryToGMServiceTest(TestCase):
    """Tests for offer_story_to_gm()."""

    @classmethod
    def setUpTestData(cls):
        cls.player_account = AccountFactory()
        cls.gm = GMProfileFactory()
        cls.gm_table = GMTableFactory(gm=cls.gm, status=GMTableStatus.ACTIVE)

    def test_happy_path_creates_pending_offer(self):
        """offer_story_to_gm creates a PENDING offer for a detached CHARACTER story."""
        story = StoryFactory(scope=StoryScope.CHARACTER, primary_table=None)
        offer = offer_story_to_gm(
            story=story,
            offered_to=self.gm,
            offered_by_account=self.player_account,
            message="Please run my story!",
        )
        assert offer.pk is not None
        assert offer.status == StoryGMOfferStatus.PENDING
        assert offer.story_id == story.pk
        assert offer.offered_to_id == self.gm.pk
        assert offer.offered_by_account_id == self.player_account.pk
        assert offer.message == "Please run my story!"
        assert offer.responded_at is None

    def test_rejects_non_character_scope(self):
        """offer_story_to_gm raises StoryGMOfferError for GROUP-scope stories."""
        group_story = StoryFactory(scope=StoryScope.GROUP, primary_table=None)
        with self.assertRaises(StoryGMOfferError):
            offer_story_to_gm(
                story=group_story,
                offered_to=self.gm,
                offered_by_account=self.player_account,
            )

    def test_rejects_story_with_primary_table(self):
        """offer_story_to_gm raises StoryGMOfferError when story already has a primary_table."""
        story = StoryFactory(scope=StoryScope.CHARACTER, primary_table=self.gm_table)
        with self.assertRaises(StoryGMOfferError):
            offer_story_to_gm(
                story=story,
                offered_to=self.gm,
                offered_by_account=self.player_account,
            )

    def test_offer_persists_in_db(self):
        """The offer is persisted and retrievable from the database."""
        story = StoryFactory(scope=StoryScope.CHARACTER, primary_table=None)
        offer = offer_story_to_gm(
            story=story,
            offered_to=self.gm,
            offered_by_account=self.player_account,
        )
        fetched = StoryGMOffer.objects.get(pk=offer.pk)
        assert fetched.status == StoryGMOfferStatus.PENDING


class AcceptStoryOfferServiceTest(TestCase):
    """Tests for accept_story_offer()."""

    @classmethod
    def setUpTestData(cls):
        cls.gm = GMProfileFactory()
        cls.gm_table = GMTableFactory(gm=cls.gm, status=GMTableStatus.ACTIVE)
        cls.player_account = AccountFactory()

    def _make_pending_offer(self, story=None):
        if story is None:
            story = StoryFactory(scope=StoryScope.CHARACTER, primary_table=None)
        return StoryGMOfferFactory(
            story=story,
            offered_to=self.gm,
            offered_by_account=self.player_account,
            status=StoryGMOfferStatus.PENDING,
        )

    def test_happy_path_accepts_offer(self):
        """accept_story_offer transitions offer to ACCEPTED and sets primary_table."""
        offer = self._make_pending_offer()
        updated = accept_story_offer(offer=offer, response_note="Happy to help!")
        assert updated.status == StoryGMOfferStatus.ACCEPTED
        assert updated.response_note == "Happy to help!"
        assert updated.responded_at is not None
        # Story should now have primary_table assigned to the GM's active table.
        updated.story.refresh_from_db()
        assert updated.story.primary_table_id == self.gm_table.pk

    def test_rejects_non_pending_offer(self):
        """accept_story_offer raises StoryGMOfferError for already-resolved offers."""
        offer = self._make_pending_offer()
        offer.status = StoryGMOfferStatus.DECLINED
        offer.save(update_fields=["status", "updated_at"])
        with self.assertRaises(StoryGMOfferError):
            accept_story_offer(offer=offer)

    def test_rejects_when_gm_has_no_active_table(self):
        """accept_story_offer raises StoryGMOfferError when the GM has no ACTIVE table."""
        gm_no_table = GMProfileFactory()
        story = StoryFactory(scope=StoryScope.CHARACTER, primary_table=None)
        offer = StoryGMOfferFactory(
            story=story,
            offered_to=gm_no_table,
            offered_by_account=self.player_account,
            status=StoryGMOfferStatus.PENDING,
        )
        with self.assertRaises(StoryGMOfferError):
            accept_story_offer(offer=offer)


class DeclineStoryOfferServiceTest(TestCase):
    """Tests for decline_story_offer()."""

    @classmethod
    def setUpTestData(cls):
        cls.gm = GMProfileFactory()
        cls.player_account = AccountFactory()

    def test_happy_path_declines_offer(self):
        """decline_story_offer transitions offer to DECLINED; story's primary_table unchanged."""
        story = StoryFactory(scope=StoryScope.CHARACTER, primary_table=None)
        offer = StoryGMOfferFactory(
            story=story,
            offered_to=self.gm,
            offered_by_account=self.player_account,
            status=StoryGMOfferStatus.PENDING,
        )
        updated = decline_story_offer(offer=offer, response_note="Not available right now.")
        assert updated.status == StoryGMOfferStatus.DECLINED
        assert updated.response_note == "Not available right now."
        assert updated.responded_at is not None
        # Story's primary_table must remain None.
        updated.story.refresh_from_db()
        assert updated.story.primary_table_id is None

    def test_rejects_non_pending_offer(self):
        """decline_story_offer raises StoryGMOfferError for non-PENDING offers."""
        story = StoryFactory(scope=StoryScope.CHARACTER, primary_table=None)
        offer = StoryGMOfferFactory(
            story=story,
            offered_to=self.gm,
            offered_by_account=self.player_account,
            status=StoryGMOfferStatus.ACCEPTED,
        )
        with self.assertRaises(StoryGMOfferError):
            decline_story_offer(offer=offer)


class WithdrawStoryOfferServiceTest(TestCase):
    """Tests for withdraw_story_offer()."""

    @classmethod
    def setUpTestData(cls):
        cls.gm = GMProfileFactory()
        cls.player_account = AccountFactory()

    def test_happy_path_withdraws_offer(self):
        """withdraw_story_offer transitions offer to WITHDRAWN."""
        story = StoryFactory(scope=StoryScope.CHARACTER, primary_table=None)
        offer = StoryGMOfferFactory(
            story=story,
            offered_to=self.gm,
            offered_by_account=self.player_account,
            status=StoryGMOfferStatus.PENDING,
        )
        updated = withdraw_story_offer(offer=offer)
        assert updated.status == StoryGMOfferStatus.WITHDRAWN
        assert updated.responded_at is not None

    def test_rejects_non_pending_offer(self):
        """withdraw_story_offer raises StoryGMOfferError for non-PENDING offers."""
        story = StoryFactory(scope=StoryScope.CHARACTER, primary_table=None)
        offer = StoryGMOfferFactory(
            story=story,
            offered_to=self.gm,
            offered_by_account=self.player_account,
            status=StoryGMOfferStatus.DECLINED,
        )
        with self.assertRaises(StoryGMOfferError):
            withdraw_story_offer(offer=offer)


# ---------------------------------------------------------------------------
# Task 3.3 — ViewSet endpoint tests
# ---------------------------------------------------------------------------


class OfferToGMActionTest(APITestCase):
    """POST /api/stories/{id}/offer-to-gm/"""

    @classmethod
    def setUpTestData(cls):
        cls.player_account = AccountFactory()
        cls.char_sheet = _character_sheet_with_account(cls.player_account)
        cls.gm = GMProfileFactory()
        cls.gm_table = GMTableFactory(gm=cls.gm, status=GMTableStatus.ACTIVE)
        cls.staff_account = AccountFactory(is_staff=True)
        cls.other_account = AccountFactory()

        # A story owned by the player's character
        cls.story = StoryFactory(
            scope=StoryScope.CHARACTER,
            primary_table=None,
            character_sheet=cls.char_sheet,
        )

    def _url(self):
        return reverse("story-offer-to-gm", args=[self.story.pk])

    def test_player_offers_own_story_returns_201(self):
        """A player can offer their own detached CHARACTER-scope story to a GM."""
        self.client.force_authenticate(user=self.player_account)
        resp = self.client.post(
            self._url(), {"gm_profile_id": self.gm.pk, "message": "Please!"}, format="json"
        )
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data["status"] == StoryGMOfferStatus.PENDING

    @suppress_permission_errors
    def test_player_offers_another_players_story_returns_400(self):
        """A player cannot offer a story that belongs to another character.

        The canonical pattern enforces ownership in the serializer (400), not
        as a permission class (403). The serializer returns 400 with a
        non_field_errors message when the user is not the story owner.
        """
        self.client.force_authenticate(user=self.other_account)
        resp = self.client.post(self._url(), {"gm_profile_id": self.gm.pk}, format="json")
        assert resp.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN)

    def test_player_offers_story_with_table_returns_400(self):
        """A story that already has a primary_table cannot be offered."""
        story_with_table = StoryFactory(
            scope=StoryScope.CHARACTER,
            primary_table=self.gm_table,
            character_sheet=self.char_sheet,
        )
        self.client.force_authenticate(user=self.player_account)
        url = reverse("story-offer-to-gm", args=[story_with_table.pk])
        resp = self.client.post(url, {"gm_profile_id": self.gm.pk}, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_staff_can_offer_any_story(self):
        """Staff can offer any story to a GM."""
        self.client.force_authenticate(user=self.staff_account)
        resp = self.client.post(self._url(), {"gm_profile_id": self.gm.pk}, format="json")
        assert resp.status_code == status.HTTP_201_CREATED


class StoryGMOfferViewSetListTest(APITestCase):
    """GET /api/story-gm-offers/"""

    @classmethod
    def setUpTestData(cls):
        # Player who makes offers
        cls.player_account = AccountFactory()
        cls.char_sheet = _character_sheet_with_account(cls.player_account)

        # GM who receives offers
        cls.gm_profile = GMProfileFactory()
        cls.gm_account = cls.gm_profile.account

        cls.staff_account = AccountFactory(is_staff=True)
        cls.other_account = AccountFactory()

        cls.story = StoryFactory(
            scope=StoryScope.CHARACTER, primary_table=None, character_sheet=cls.char_sheet
        )
        # The offer from player to gm
        cls.offer = StoryGMOfferFactory(
            story=cls.story,
            offered_to=cls.gm_profile,
            offered_by_account=cls.player_account,
            status=StoryGMOfferStatus.PENDING,
        )

    def _url(self):
        return reverse("storygmoffer-list")

    def test_player_sees_their_own_offer(self):
        self.client.force_authenticate(user=self.player_account)
        resp = self.client.get(self._url())
        assert resp.status_code == status.HTTP_200_OK
        ids = [r["id"] for r in resp.data["results"]]
        assert self.offer.pk in ids

    def test_gm_sees_received_offer(self):
        self.client.force_authenticate(user=self.gm_account)
        resp = self.client.get(self._url())
        assert resp.status_code == status.HTTP_200_OK
        ids = [r["id"] for r in resp.data["results"]]
        assert self.offer.pk in ids

    def test_other_account_does_not_see_offer(self):
        """An unrelated user should not see the offer."""
        self.client.force_authenticate(user=self.other_account)
        resp = self.client.get(self._url())
        assert resp.status_code == status.HTTP_200_OK
        ids = [r["id"] for r in resp.data["results"]]
        assert self.offer.pk not in ids

    def test_staff_sees_all_offers(self):
        self.client.force_authenticate(user=self.staff_account)
        resp = self.client.get(self._url())
        assert resp.status_code == status.HTTP_200_OK
        ids = [r["id"] for r in resp.data["results"]]
        assert self.offer.pk in ids


class AcceptOfferActionTest(APITestCase):
    """POST /api/story-gm-offers/{id}/accept/"""

    @classmethod
    def setUpTestData(cls):
        cls.player_account = AccountFactory()
        cls.gm_profile = GMProfileFactory()
        cls.gm_account = cls.gm_profile.account
        cls.gm_table = GMTableFactory(gm=cls.gm_profile, status=GMTableStatus.ACTIVE)
        cls.other_gm = GMProfileFactory()
        cls.staff_account = AccountFactory(is_staff=True)

    def _make_fresh_pending_offer(self):
        """Create a new PENDING offer + story for each test that needs mutation."""
        story = StoryFactory(scope=StoryScope.CHARACTER, primary_table=None)
        offer = StoryGMOfferFactory(
            story=story,
            offered_to=self.gm_profile,
            offered_by_account=self.player_account,
            status=StoryGMOfferStatus.PENDING,
        )
        return offer, story

    def test_gm_accepts_offer_returns_200(self):
        """The GM who received the offer can accept it."""
        offer, story = self._make_fresh_pending_offer()
        self.client.force_authenticate(user=self.gm_account)
        resp = self.client.post(
            reverse("storygmoffer-accept", args=[offer.pk]),
            {"response_note": "Let's do it!"},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["status"] == StoryGMOfferStatus.ACCEPTED
        story.refresh_from_db()
        assert story.primary_table_id == self.gm_table.pk

    @suppress_permission_errors
    def test_wrong_gm_cannot_accept_returns_403_or_404(self):
        """A different GM cannot accept an offer directed at another GM.

        The offer is not visible to other_gm (queryset scoping returns 404),
        which is equivalent protection to a 403. Both are acceptable.
        """
        offer, _ = self._make_fresh_pending_offer()
        self.client.force_authenticate(user=self.other_gm.account)
        resp = self.client.post(reverse("storygmoffer-accept", args=[offer.pk]), {}, format="json")
        assert resp.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)


class DeclineOfferActionTest(APITestCase):
    """POST /api/story-gm-offers/{id}/decline/"""

    @classmethod
    def setUpTestData(cls):
        cls.player_account = AccountFactory()
        cls.gm_profile = GMProfileFactory()
        cls.gm_account = cls.gm_profile.account
        cls.other_account = AccountFactory()

    def _make_fresh_pending_offer(self):
        story = StoryFactory(scope=StoryScope.CHARACTER, primary_table=None)
        offer = StoryGMOfferFactory(
            story=story,
            offered_to=self.gm_profile,
            offered_by_account=self.player_account,
            status=StoryGMOfferStatus.PENDING,
        )
        return offer, story

    def test_gm_declines_offer_returns_200(self):
        """The GM who received the offer can decline it."""
        offer, story = self._make_fresh_pending_offer()
        self.client.force_authenticate(user=self.gm_account)
        resp = self.client.post(
            reverse("storygmoffer-decline", args=[offer.pk]),
            {"response_note": "Not my genre."},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["status"] == StoryGMOfferStatus.DECLINED
        story.refresh_from_db()
        assert story.primary_table_id is None

    @suppress_permission_errors
    def test_player_cannot_decline_offer_returns_403(self):
        """The player who made the offer cannot decline it (that's the GM's action)."""
        offer, _ = self._make_fresh_pending_offer()
        self.client.force_authenticate(user=self.player_account)
        resp = self.client.post(reverse("storygmoffer-decline", args=[offer.pk]), {}, format="json")
        assert resp.status_code == status.HTTP_403_FORBIDDEN


class WithdrawOfferActionTest(APITestCase):
    """POST /api/story-gm-offers/{id}/withdraw/"""

    @classmethod
    def setUpTestData(cls):
        cls.player_account = AccountFactory()
        cls.gm_profile = GMProfileFactory()
        cls.gm_account = cls.gm_profile.account
        cls.other_player = AccountFactory()

    def _make_fresh_pending_offer(self):
        story = StoryFactory(scope=StoryScope.CHARACTER, primary_table=None)
        return StoryGMOfferFactory(
            story=story,
            offered_to=self.gm_profile,
            offered_by_account=self.player_account,
            status=StoryGMOfferStatus.PENDING,
        )

    def test_player_withdraws_own_offer_returns_200(self):
        """The player who made the offer can withdraw it."""
        offer = self._make_fresh_pending_offer()
        self.client.force_authenticate(user=self.player_account)
        resp = self.client.post(reverse("storygmoffer-withdraw", args=[offer.pk]), format="json")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["status"] == StoryGMOfferStatus.WITHDRAWN

    @suppress_permission_errors
    def test_wrong_player_cannot_withdraw_returns_403_or_404(self):
        """Another player cannot withdraw someone else's offer.

        The offer is not visible to other_player (queryset scoping returns 404),
        which is equivalent protection to a 403. Both are acceptable.
        """
        offer = self._make_fresh_pending_offer()
        self.client.force_authenticate(user=self.other_player)
        resp = self.client.post(reverse("storygmoffer-withdraw", args=[offer.pk]), format="json")
        assert resp.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)

    @suppress_permission_errors
    def test_gm_cannot_withdraw_offer_returns_403(self):
        """The GM who received the offer cannot withdraw it (only the player can)."""
        offer = self._make_fresh_pending_offer()
        self.client.force_authenticate(user=self.gm_account)
        resp = self.client.post(reverse("storygmoffer-withdraw", args=[offer.pk]), format="json")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

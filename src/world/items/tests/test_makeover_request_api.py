"""``/api/items/makeover-requests/``: the target's pending asks and the answer (#4187)."""

from rest_framework import status
from rest_framework.test import APIClient

from world.consent.models import SocialConsentBlacklist
from world.items.tests.test_makeover_requests import MakeoverAskFixture
from world.scenes.action_constants import ActionRequestStatus

LIST_URL = "/api/items/makeover-requests/"


class MakeoverRequestApiTests(MakeoverAskFixture):
    def setUp(self):
        super().setUp()
        self.target_client = APIClient()
        self.target_client.force_authenticate(user=self.other_account)
        self.stylist_client = APIClient()
        self.stylist_client.force_authenticate(user=self.account)

    def respond_url(self, request):
        return f"{LIST_URL}{request.pk}/respond/"

    def test_list_shows_the_ask_to_the_target_only(self):
        request = self.offer()
        response = self.target_client.get(LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([row["id"] for row in response.data], [request.pk])
        row = response.data[0]
        self.assertEqual(row["option_name"], "crimson")
        self.assertEqual(row["trait_name"], "hair")
        self.assertEqual(row["item_name"], self.item.display_name)
        self.assertEqual(row["target_character_id"], self.other.pk)
        response = self.stylist_client.get(LIST_URL)
        self.assertEqual(response.data, [])

    def test_list_drops_a_lapsed_ask(self):
        self.offer()
        self.actor.location = self.remote
        response = self.target_client.get(LIST_URL)
        self.assertEqual(response.data, [])

    def test_anonymous_is_refused(self):
        response = APIClient().get(LIST_URL)
        self.assertIn(
            response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
        )

    def test_grant_restyles_and_spends_a_charge(self):
        request = self.offer()
        response = self.target_client.post(
            self.respond_url(request), {"decision": "grant", "remember": None}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["status"], ActionRequestStatus.ACCEPTED)
        self.assertEqual(self.charges(), 7)

    def test_decline_with_never_blacklists(self):
        request = self.offer()
        response = self.target_client.post(
            self.respond_url(request), {"decision": "decline", "remember": "never"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["status"], ActionRequestStatus.DENIED)
        self.assertEqual(self.charges(), 8)
        self.assertTrue(
            SocialConsentBlacklist.objects.filter(
                owner_tenure=self.other_tenure, blocked_tenure=self.actor_tenure
            ).exists()
        )

    def test_another_account_gets_404(self):
        request = self.offer()
        response = self.stylist_client.post(
            self.respond_url(request), {"decision": "grant"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.charges(), 8)

    def test_answering_twice_is_400(self):
        request = self.offer()
        self.target_client.post(self.respond_url(request), {"decision": "decline"}, format="json")
        response = self.target_client.post(
            self.respond_url(request), {"decision": "grant"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_grant_after_lapse_is_409(self):
        request = self.offer()
        self.actor.location = self.remote
        response = self.target_client.post(
            self.respond_url(request), {"decision": "grant"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("no longer here", response.data["detail"])

    def test_bad_decision_is_400(self):
        request = self.offer()
        response = self.target_client.post(
            self.respond_url(request), {"decision": "maybe"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
